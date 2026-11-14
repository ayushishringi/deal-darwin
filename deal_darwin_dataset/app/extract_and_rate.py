"""Deal Darwin: extract key terms from creator-brand contracts and rate creator risk.

For each contract:
  1. Extract with NDI (app/ndi_client.py): text, per-term status, quote, value and page; contract D
     is read from the real scan (NDI OCR). If NDI fails, fall back to pdftotext + Drex status.
  2. For five aspects (fee, usage_rights, exclusivity, payment_terms, kill_fee) ask Drex:
       - a choice question for status (found / ambiguous / not_found)
       - a choice question for risk 1-5 versus the standard terms (clauses/norm_reference.json)
  3. Save app/cache/contract_X_risk.json with per-aspect status/quote/value/risk plus
     the overall weighted risk (fee .3, usage .25, exclusivity .2, payment .15, kill_fee .1).
  4. Compare against answer_keys/contract_X_key.json and print a table
     (status match, risk within 1).

Drex API shapes (learned from probing):
  choice: questions.q = {"type": "choice", "instructions": ..., "criteria": {label: description}}
          -> answers.q = {"choice": winning_label, "probabilities": {label: p}, "confidence": ...}
  score:  questions.q = {"type": "score",  "instructions": ..., "criteria": [label, ...]}
          -> answers.q = {"score": float, "probabilities": {"0": p, ...}, "confidence": ...}
"""
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from drex_client import ask
from ndi_client import extract_terms

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NORM = json.load(open(os.path.join(ROOT, "clauses", "norm_reference.json")))

CONTRACTS = {
    "A": "contracts/contract_A_northwind_maya.pdf",
    "B": "contracts/contract_B_vela_priya.pdf",
    "C": "contracts/contract_C_kettle_jordan.pdf",
    "D": "contracts/contract_D_northwind_diego_SCAN.pdf",  # NDI OCRs the real scan
}
FALLBACK_PDF = {"D": "answer_keys/contract_D_clean_source.pdf"}  # pdftotext can't read the scan

ASPECTS = ["fee", "usage_rights", "exclusivity", "payment_terms", "kill_fee"]
WEIGHTS = {"fee": 0.30, "usage_rights": 0.25, "exclusivity": 0.20,
           "payment_terms": 0.15, "kill_fee": 0.10}

STATUS_CRITERIA = {
    "found": "the term is explicitly stated in the contract",
    "ambiguous": "the term is partially stated, conditional, or unclear",
    "not_found": "the term is not mentioned at all",
}
RISK_CRITERIA = {
    "1": "on par with or better than the standard terms - minimal risk to the creator",
    "2": "slightly off the standard terms - low risk to the creator",
    "3": "meaningfully off the standard terms - moderate risk to the creator",
    "4": "far off the standard terms in the brand's favor - high risk to the creator",
    "5": "severely off the standard terms - very high risk to the creator",
}

# Best-effort quote/value heuristics per aspect (used only to fill the cache fields).
_LINE_PATTERNS = {
    "fee": r"(?i)fee",
    "usage_rights": r"(?i)(licens|usage|rights to use)",
    "exclusivity": r"(?i)exclusiv",
    "payment_terms": r"(?i)(net|invoice|payment|pay)",
    "kill_fee": r"(?i)(cancell|terminat|kill fee)",
}


def extract_text(pdf_path):
    return subprocess.run(["pdftotext", "-layout", pdf_path, "-"],
                          check=True, capture_output=True, text=True).stdout


def find_quote(text, aspect):
    """Return the contract line (or short span) most likely to state this term."""
    pat = _LINE_PATTERNS[aspect]
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    hits = [ln for ln in lines if re.search(pat, ln)]
    if aspect == "fee":
        hits = [ln for ln in hits if re.search(r"\$[\d,]+", ln)] or hits
    if aspect == "payment_terms":
        hits = [ln for ln in hits if re.search(r"day", ln, re.I)] or hits
    if aspect == "kill_fee":
        hits = [ln for ln in hits if re.search(r"cancell", ln, re.I)] or hits
    return next((ln for ln in hits if re.search(r"\d", ln)), hits[0] if hits else None)


def extract_value(aspect, quote):
    if isinstance(quote, (int, float)):  # already a number (e.g. from the cache)
        return quote
    if not quote:
        return None
    if aspect == "fee":
        m = re.search(r"\$\s*([\d,]+)", quote)
        return int(m.group(1).replace(",", "")) if m else None
    if aspect == "usage_rights":
        m = re.search(r"(\d+)\s*(?:\((\d+)\)\s*)?months", quote)
        return int(m.group(2) or m.group(1)) if m else None
    if aspect == "exclusivity":
        m = re.search(r"(\d+)\s*(?:\((\d+)\)\s*)?months", quote)
        return int(m.group(2) or m.group(1)) if m else None
    if aspect == "payment_terms":
        m = re.search(r"net\s*-\s*(\d+)", quote, re.I)
        if m:
            return int(m.group(1))
        days = [int(x) for x in re.findall(r"(\d+)\s*(?:\((\d+)\)\s*)?(?:business\s*)?days", quote)]
        return max(days) if days else None
    if aspect == "kill_fee":
        m = re.search(r"(\d+)(?:\.\d+)?\s*%|(\d+)\s*percent", quote, re.I)
        if m:
            return float(m.group(1) or m.group(2))
    return None


def ask_status(text, aspect):
    q = {
        "type": "choice",
        "instructions": (f"Look at this creator-brand contract. For the aspect '{aspect}', "
                         "decide whether that term is present in the contract text."),
        "criteria": STATUS_CRITERIA,
    }
    return ask(text, {"s": q})["s"]


AMBIGUITY_QUESTIONS = {
    "conflict": ("Does the contract state this term in more than one place with different or "
                 "conflicting values (for example main text vs definitions vs a schedule)?"),
    "vague": ("Does the clause defer to another section or schedule, or use vague wording "
              "(reasonable, as agreed, to be determined) instead of a single concrete value?"),
}


def ask_ambiguity(text, aspect):
    """Two noul questions per aspect; returns {name: p_yes}."""
    qs = {name: {"type": "noul", "instructions": f"For the contract term '{aspect}': {q}"}
          for name, q in AMBIGUITY_QUESTIONS.items()}
    ans = ask(text, qs)
    return {name: ans[name]["noul"] for name in qs}


def ask_risk(text, aspect, quote=None):
    state = text + (f"\n\nEXTRACTED CLAUSE for {aspect} (from NDI): {quote}" if quote else "")
    state += f"\n\nSTANDARD TERM for {aspect} (the benchmark a fair contract matches): {NORM[aspect]}"
    q = {
        "type": "choice",
        "instructions": (f"Compare the '{aspect}' terms in this contract against the STANDARD TERM "
                         f"for {aspect} given at the end. How risky are the contract's {aspect} terms "
                         "for the creator? 1 = matches or beats the standard, 5 = far worse."),
        "criteria": RISK_CRITERIA,
    }
    return ask(state, {"r": q})["r"]


def process_contract(cid, ext):
    """ext = ndi_client.extract_terms(...). NDI gives status/quote/value/page; Drex rates risk."""
    cache = None
    for ev in iter_contract(cid, ext):
        if ev["type"] == "aspect":
            x, amb = ev["aspect"], ev["aspect"]["ambiguity_probabilities"]
            print(f"  {x['aspect']:<14} status={x['status']:<10} (ndi={x['ndi_status']}) risk={x['risk']}  "
                  f"p_conflict={amb['conflict']:.2f} p_vague={amb['vague']:.2f}")
        else:
            cache = ev["cache"]
    cache_path = os.path.join(ROOT, "app", "cache", f"contract_{cid}_risk.json")
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump(cache, f, indent=2)
    return cache


def iter_contract(cid, ext):
    """Yield {"type": "aspect", "aspect": {...}} per term (Drex risk + ambiguity), then {"type": "done", "cache"}."""
    text, ndi = ext["text"], ext["source"] == "ndi"
    cache = {"contract": cid, "aspects": {}, "overall_risk": None,
             "extraction": {k: ext.get(k) for k in ("source", "ocr_applied", "cost_usd", "job_ids", "error")},
             "parties": {k: (ext["fields"].get(k) or {}).get("value") for k in ("brand_name", "creator_name")}}
    overall = 0.0
    for aspect in ASPECTS:
        f = ext["fields"].get(aspect) or {}
        if ndi:
            s, status, quote, page = {}, f["status"], f.get("quote"), f.get("page")
            value = extract_value(aspect, f.get("value")) or extract_value(aspect, quote)
        else:  # fallback: the old pdftotext + Drex status path
            s = ask_status(text, aspect)
            status, page = s["choice"], None
        r = ask_risk(text, aspect, quote if ndi else None)
        amb = ask_ambiguity(text, aspect)
        if status == "found" and max(amb.values()) >= 0.5:
            status = "ambiguous"  # present, but conflicting or vague (not_found stays as is)
        risk = int(r["choice"])
        if not ndi:
            quote = find_quote(text, aspect) if status != "not_found" else None
            value = extract_value(aspect, quote)
        cache["aspects"][aspect] = {
            "aspect": aspect,
            "status": status,
            "source": ext["source"],
            "ndi_status": f.get("status"),
            "ndi_confidence": f.get("confidence"),
            "page": page,
            "status_probabilities": s.get("probabilities"),
            "ambiguity_probabilities": amb,
            "quote": quote,
            "value": value,
            "risk": risk,
            "risk_probabilities": r.get("probabilities"),
            "weight": WEIGHTS[aspect],
        }
        overall += WEIGHTS[aspect] * risk
        yield {"type": "aspect", "aspect": cache["aspects"][aspect]}
    cache["overall_risk"] = round(overall, 3)
    yield {"type": "done", "cache": cache}


def compare():
    keys = {}
    rows = []
    for cid in CONTRACTS:
        key = json.load(open(os.path.join(ROOT, "answer_keys", f"contract_{cid}_key.json")))["fields"]
        cache = json.load(open(os.path.join(ROOT, "app", "cache", f"contract_{cid}_risk.json")))
        keys[cid] = key
        for aspect in ASPECTS:
            pred, gold = cache["aspects"][aspect], key[aspect]
            rows.append((cid, aspect, pred["status"], gold["status"],
                         pred["risk"], gold["risk"]))

    hdr = f"{'C':<3} {'aspect':<14} {'status (pred/key)':<26} {'match':<6} {'risk (pred/key)':<16} {'within 1':<9}"
    print("\n" + hdr)
    print("-" * len(hdr))
    n_status = n_risk = n_risk_total = 0
    for cid, aspect, p_s, g_s, p_r, g_r in rows:
        s_ok = p_s == g_s
        n_status += s_ok
        if g_r is None:  # gold key has no risk (e.g. term absent) - not scoreable
            r_cell, r_flag = "-", "n/a"
        else:
            n_risk_total += 1
            r_ok = abs(p_r - g_r) <= 1
            n_risk += r_ok
            r_cell, r_flag = str(p_r) + " / " + str(g_r), "OK" if r_ok else "X"
        print(f"{cid:<3} {aspect:<14} {p_s + ' / ' + g_s:<26} {'OK' if s_ok else 'X':<6} "
              f"{r_cell:<16} {r_flag:<9}")
    print("-" * len(hdr))
    print(f"status match: {n_status}/{len(rows)}   risk within 1: {n_risk}/{n_risk_total}")


def main():
    for cid, rel in CONTRACTS.items():
        print(f"contract {cid}: {rel}")
        fb = FALLBACK_PDF.get(cid)
        ext = extract_terms(os.path.join(ROOT, rel), os.path.join(ROOT, fb) if fb else None)
        print(f"  extraction: {ext['source']}  ocr={ext.get('ocr_applied')}  ${ext['cost_usd']}")
        process_contract(cid, ext)
    compare()


if __name__ == "__main__":
    main()
