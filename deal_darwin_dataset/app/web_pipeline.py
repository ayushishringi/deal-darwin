"""Deal Darwin web app back end: analyze any contract (NDI + Drex), ask Drex, negotiate.

analyze(emit, pdf=None, sample=None, name=None) -> analysis dict. Keys starting with "_" stay on the server.
Stages: reading (NDI) -> rating (Drex) -> good (sort into "watch out" / "looks good").
Uses pipeline.watch: a stage that errors or stalls for STAGE_TIMEOUT s falls back to the cache (samples only).
"""
import os
import re
import time

import pipeline
from pipeline import ROOT, load, match_brand, watch
from drex_client import ask
from extract_and_rate import (ASPECTS, CONTRACTS as PDFS, FALLBACK_PDF, RISK_CRITERIA, extract_value,
                              iter_contract)
from ndi_client import extract_terms
from counter_engine import pdftotext

LABELS = {"fee": "Fee", "usage_rights": "Usage rights", "exclusivity": "Exclusivity",
          "payment_terms": "Payment terms", "kill_fee": "Kill fee"}
SAMPLE_NAMES = {"A": "Sample A", "B": "Sample B", "C": "Sample C", "D": "Sample D (scan)"}


# ---------- missing-term fallback: keyword-ranked paragraphs + a Drex yes/no check ----------
SEARCH_KEYS = {
    "fee": ["fee", "compensation", "$", "payment"],
    "payment_terms": ["days", "invoice", "net", "pay"],
    "usage_rights": ["licence", "usage", "license", "media"],
    "exclusivity": ["exclusive", "compet", "restricted"],
    "kill_fee": ["cancel", "terminat", "kill"],
}
TERM_WORDS = {"fee": "fee", "payment_terms": "payment terms", "usage_rights": "usage rights",
              "exclusivity": "exclusivity", "kill_fee": "kill fee"}
FOUND_P = 0.6
VALUE_RE = {   # a concrete value for the term earns a bonus, so a passage that states it beats one that only mentions it
    "fee": r"\$\s?\d[\d,]{2,}", "payment_terms": r"\(\d+\)\s*(business\s+)?days|\bnet[- ]?\d+|\d+\s*days",
    "usage_rights": r"\d+\)?\s*months|perpetu", "exclusivity": r"\d+\)?\s*months", "kill_fee": r"\d+\s*%|percent",
}


def rank_score(key, text):
    hits = sum(text.lower().count(k) for k in SEARCH_KEYS[key])
    if not hits:
        return 0.0
    return hits / max(1.0, len(text) / 400) + (3 if re.search(VALUE_RE[key], text, re.I) else 0)


def paragraphs(pdf):
    """[(page, text)] from pdftotext -layout: every page incl. exhibits, split on blank lines; long blocks chunked."""
    try:
        pages = pdftotext(pdf).split("\f")
    except Exception:  # noqa: BLE001
        return []
    out = []
    for n, page in enumerate(pages, 1):
        for block in re.split(r"\n\s*\n", page):
            lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
            for i in range(0, len(lines), 8):  # ~8-line windows keep quotes readable
                txt = re.sub(r"\s+", " ", " ".join(lines[i:i + 8])).strip()
                if len(txt) >= 40:
                    out.append((n, txt))
    return out


def text_search(pdf, key, paras=None):
    """Top-2 keyword paragraphs for a term, checked by Drex. Returns {quote, page, p} if p >= FOUND_P, else None."""
    paras = paras if paras is not None else paragraphs(pdf)
    scored = sorted(((rank_score(key, t), -i, pg, t) for i, (pg, t) in enumerate(paras)), reverse=True)
    best = None
    for score, _, pg, t in scored[:2]:
        if score <= 0:
            break
        q = {"q": {"type": "noul", "instructions": f"Does this passage state the {TERM_WORDS[key]}?"}}
        p = float(ask(f"PASSAGE (page {pg}):\n{t}", q)["q"]["noul"])
        if p >= FOUND_P and (not best or p > best["p"]):
            best = {"quote": t[:700], "page": pg, "p": round(p, 3)}
    return best


def short(err):
    """Readable error: drop HTML bodies (e.g. a gateway block page)."""
    s = str(err).split("<!DOCTYPE")[0].split("<html")[0].strip(" :")
    return (s + (" (blocked by the API gateway)" if "403" in s and "gateway" not in s else ""))[:160]


def rate_extra(text, x):
    """Drex rates a clause outside the five standard terms (no benchmark, so 'typical deals')."""
    name = x.get("name") or x.get("label") or "this"
    state = f"{text}\n\nCLAUSE ({name}): {x.get('quote') or x.get('text')}"
    q = {"type": "choice", "criteria": RISK_CRITERIA,
         "instructions": (f"How risky is the '{name}' clause for the creator compared with what is typical "
                          "in creator-brand sponsorship deals? 1 = standard or favorable, 5 = far worse.")}
    r = ask(state, {"r": q})["r"]
    return {**x, "risk": int(r["choice"]), "risk_probabilities": r.get("probabilities")}


def clause_view(key, a, kind="core"):
    extra = {"found_by": a["found_by"]} if a.get("found_by") else {}   # only set by the text-search pass
    return {**extra, "key": key, "label": LABELS.get(key, a.get("name") or key), "kind": kind,
            "status": a.get("status") or "found", "value": a.get("value"), "quote": a.get("quote"),
            "page": a.get("page"), "risk": a.get("risk"), "risk_probabilities": a.get("risk_probabilities"),
            "ambiguity_probabilities": a.get("ambiguity_probabilities"), "text": a.get("text")}


def analyze(emit, pdf=None, sample=None, name=None):
    res = {"stages": {}, "sample": sample, "name": name or SAMPLE_NAMES.get(sample, "Contract")}

    def stage(st, status, err=None, reset=False):
        res["stages"][st] = status
        emit({"type": "stage", "stage": st, "status": status, "reset": reset, **({"error": short(err)} if err else {})})

    # ---------- reading: NDI parse + extract (five terms, parties, other terms) ----------
    stage("reading", "running")
    path = pdf or os.path.join(ROOT, PDFS[sample])
    fb = FALLBACK_PDF.get(sample) if sample else None

    def ndi():
        yield extract_terms(path, os.path.join(ROOT, fb) if fb else None, extras=True)
    try:
        ext = next(watch(ndi(), "reading"))
        if ext["source"] != "ndi" and sample:
            raise RuntimeError(ext.get("error") or "NDI fallback")
        status = "live" if ext["source"] == "ndi" else "fallback"
        if status == "fallback" and len(ext["text"].strip()) < 50:  # scan/screenshot with no text layer
            stage("reading", "error", ext.get("error") or "no readable text"); return res
    except Exception as e:  # noqa: BLE001
        if not sample:
            stage("reading", "error", str(e)); return res
        c = load(f"contract_{sample}_risk.json")
        ext = {"source": "ndi", "ocr_applied": (c.get("extraction") or {}).get("ocr_applied"), "others": [],
               "text": pdftotext(os.path.join(ROOT, fb or PDFS[sample])), "error": str(e),
               "fields": {**{k: {"status": a.get("ndi_status") or a["status"], "value": a.get("value"),
                                 "quote": a.get("quote"), "page": a.get("page")} for k, a in c["aspects"].items()},
                          **{k: {"value": v} for k, v in (c.get("parties") or {}).items()}}}
        status = "cached"
    parties = {k: (ext["fields"].get(k) or {}).get("value") for k in ("brand_name", "creator_name")}
    res["extraction"] = {"source": ext["source"], "ocr_applied": ext.get("ocr_applied"), "reused": ext.get("reused"),
                         "cost_usd": ext.get("cost_usd") if status == "live" else None}
    res.update(parties=parties, brand=match_brand(parties["brand_name"]), _text=ext["text"])
    try:
        res["pages"] = pdftotext(path).count("\f") or None   # one form feed per page
    except Exception:  # noqa: BLE001
        res["pages"] = None
    emit({"type": "meta", "parties": parties, "extraction": res["extraction"], "name": res["name"], "pages": res["pages"]})
    clauses = {}
    for k in ASPECTS:
        f = ext["fields"].get(k) or {"status": "not_found"}
        clauses[k] = clause_view(k, {**f, "value": extract_value(k, f.get("value")) or extract_value(k, f.get("quote"))})
        emit({"type": "clause", "clause": clauses[k]})
        time.sleep(0.12)
    # second pass for standard terms NDI could not find or could not cite: search the full text (all pages, incl. exhibits)
    missing = [k for k in ASPECTS if clauses[k]["status"] == "not_found" or not clauses[k]["quote"]]
    if missing:
        paras = paragraphs(path)
        for k in missing:
            try:
                hit = text_search(path, k, paras)
            except Exception as e:  # noqa: BLE001
                hit = None
                print(f"  text search for {k} failed: {short(e)}")
            f = ext["fields"].get(k) or {}
            if hit:  # found (or cited) by text search; keep NDI's status/value when it had one
                ext["fields"][k] = {"status": f.get("status") if f.get("status") not in (None, "not_found") else "found",
                                    "quote": hit["quote"], "page": hit["page"], "value": f.get("value"), "found_by": "text search"}
            elif f.get("value") and f.get("status") != "not_found":  # NDI read a value but gave no citation
                ext["fields"][k] = {**f, "quote": str(f["value"])}
            else:
                continue
            v = ext["fields"][k].get("value")
            clauses[k] = clause_view(k, {**ext["fields"][k], "value": extract_value(k, v) or extract_value(k, ext["fields"][k]["quote"])})
            emit({"type": "clause", "clause": clauses[k]})
    for i, x in enumerate(ext.get("others") or []):
        clauses[f"x{i}"] = clause_view(f"x{i}", x, "extra")
        emit({"type": "clause", "clause": clauses[f"x{i}"]})
    stage("reading", status, ext.get("error") if status != "live" else None)

    # ---------- rating: Drex risk (+ ambiguity for the five standard terms) ----------
    stage("rating", "running")
    extras = [k for k in clauses if clauses[k]["kind"] == "extra"]

    def rate():
        for ev in iter_contract(sample or "WEB", ext):
            yield ev
        for k in extras:
            yield {"type": "extra", "key": k, "clause": rate_extra(ext["text"], clauses[k])}
    overall = None
    try:
        for ev in watch(rate(), "rating"):
            if ev["type"] == "aspect":
                a = ev["aspect"]
                clauses[a["aspect"]].update(clause_view(a["aspect"], a))
                emit({"type": "clause", "clause": clauses[a["aspect"]]})
            elif ev["type"] == "extra":
                clauses[ev["key"]].update(risk=ev["clause"]["risk"], risk_probabilities=ev["clause"]["risk_probabilities"])
                emit({"type": "clause", "clause": clauses[ev["key"]]})
            else:
                overall = ev["cache"]["overall_risk"]
        stage("rating", "live")
    except Exception as e:  # noqa: BLE001
        cached = load(f"contract_{sample}_risk.json") if sample else None
        if not cached:
            stage("rating", "error", str(e)); return res
        else:
            stage("rating", "cached", str(e), reset=True)
            for k, a in cached["aspects"].items():
                clauses[k].update(clause_view(k, a))
                emit({"type": "clause", "clause": clauses[k]})
            overall = cached["overall_risk"]
    res["overall_risk"] = overall
    emit({"type": "overall", "overall_risk": overall})

    # ---------- good parts: split into watch-out and looks-good ----------
    stage("good", "running")
    order = {"not_found": 0, "ambiguous": 1, "found": 2}
    rated = list(clauses.values())
    good = [c for c in rated if c["status"] == "found" and c["risk"] is not None and c["risk"] <= 2]
    bad = sorted([c for c in rated if c not in good], key=lambda c: (order.get(c["status"], 2), -(c["risk"] or 0)))
    res.update(clauses=rated, watch=[c["key"] for c in bad], good=[c["key"] for c in good])
    emit({"type": "summary", "watch": res["watch"], "good": res["good"]})
    stage("good", "live")
    return res


TIMEOUT = pipeline.TIMEOUT


# ---------- Ask Drex ----------
def detect_options(q):
    """'Is the fee 2500 or 2250?' -> ['2500', '2250']; 'A, B or C' lists too. [] when there is no 'or'."""
    s = q.strip().rstrip("?").strip()
    parts = re.split(r"\s+or\s+", s, flags=re.I)
    if len(parts) < 2:
        return []
    head, middle, last = parts[0], parts[1:-1], parts[-1]
    tail = [p.strip() for p in head.split(",")[1:]] if "," in head else []
    head = head.split(",")[0]
    k = max(1, len(last.split()))
    opts = [" ".join(head.split()[-k:])] + tail + middle + [last]
    out = []
    for o in (o.strip(" ,.;:") for o in opts):
        if o and o.lower() not in [x.lower() for x in out]:
            out.append(o[:80])
    return out[:6] if len(out) >= 2 else []


def plain(p):
    return "likely" if p >= 0.65 else "unlikely" if p <= 0.35 else "uncertain"


def ask_drex(an, question, mode="auto", options=None):
    q = (question or "").strip()[:500]
    if len(q) < 3:
        raise ValueError("Type a question first.")
    ctx = [c for c in an.get("clauses", []) if c.get("quote") or c.get("text")]
    lines = "\n".join(f"- {c['label']} ({STATUS_WORD.get(c['status'], c['status'])}"
                      f"{', page ' + str(c['page']) if c.get('page') else ''}): {c.get('quote') or c.get('text')}" for c in ctx)
    missing = [c["label"] for c in an.get("clauses", []) if c["status"] == "not_found"]
    state = (f"EXTRACTED CLAUSES (from NDI):\n{lines}\n"
             + (f"NOT FOUND IN THE CONTRACT: {', '.join(missing)}\n" if missing else "")
             + f"\nFULL CONTRACT TEXT:\n{(an.get('_text') or '')[:60000]}")
    opts = [o.strip()[:80] for o in (options or []) if o and o.strip()]
    if mode == "auto":
        opts = opts or detect_options(q)
        mode = "choice" if len(opts) >= 2 else "yesno"
    context = [{"label": c["label"], "page": c.get("page"), "status": c["status"]} for c in ctx]
    t0 = time.time()
    if mode == "choice":
        opts = opts or detect_options(q)
        if len(opts) < 2:
            raise ValueError("Give at least two options, separated by commas.")
        a = ask(state, {"q": {"type": "choice", "instructions": q, "criteria": {o: o for o in opts}}})["q"]
        probs = {o: float(a["probabilities"].get(o, 0)) for o in opts}
        return {"mode": "choice", "question": q, "choice": a.get("choice"), "probabilities": probs,
                "context": context, "ms": round((time.time() - t0) * 1000)}
    a = ask(state, {"q": {"type": "noul", "instructions": q}})["q"]
    p = float(a["noul"])
    return {"mode": "yesno", "question": q, "p": p, "label": plain(p), "context": context,
            "ms": round((time.time() - t0) * 1000)}


STATUS_WORD = {"found": "found", "ambiguous": "unclear", "not_found": "missing"}


# ---------- Negotiate ----------
from common import BRANDS, CREATORS, OFFER_KEYS, PERSONAS, expected_value  # noqa: E402
from counter_engine import CONTRACTS as SAMPLES, PLAYBOOK_PDF, load_truth  # noqa: E402
from counter_v2 import iter_search  # noqa: E402
from extract_and_rate import NORM  # noqa: E402
from pipeline import gen_view  # noqa: E402

GENERIC_PLAYBOOK = ("GENERIC BRAND PLAYBOOK (no brand-specific playbook was provided; these are the dataset's "
                    "reference standard terms for creator deals):\n"
                    + "\n".join(f"- {k.replace('_', ' ')}: {v}" for k, v in NORM.items()))


def negotiate(emit, an, persona=None, rate=None, playbook=None, brand=None):
    res = {"stages": {}}

    def stage(st, status, err=None, reset=False):
        res["stages"][st] = status
        emit({"type": "stage", "stage": st, "status": status, "reset": reset, **({"error": short(err)} if err else {})})

    sample, parties = an.get("sample"), an.get("parties") or {}
    bid = brand if brand in BRANDS else an.get("brand")
    who = parties.get("brand_name") or "the brand"
    if playbook:
        text, source, key = pdftotext(playbook), "uploaded", who
        if len(text.strip()) < 200:
            stage("search", "error", "Couldn't read text from that playbook PDF."); return res
    elif bid:
        text, source, key, who = pdftotext(os.path.join(ROOT, PLAYBOOK_PDF[bid])), "built-in", bid, BRANDS[bid]["name"]
    else:
        text, source, key = GENERIC_PLAYBOOK, "generic", who
    truth = load_truth().get(sample) if sample else None
    persona = persona if persona in PERSONAS else (truth["creator_persona"] if truth else "balanced")
    if not rate and sample:
        rate = CREATORS[SAMPLES[sample]["creator"]]["baseline_fee"]
    res.update(persona=persona, rate=rate, playbook={"source": source, "brand": who})
    emit({"type": "plan", "persona": persona, "rate": rate, "playbook": res["playbook"], "generations": 4})

    stage("search", "running")
    gens, top3, n_calls = [], None, None
    try:
        for ev in watch(iter_search(key, persona, text), "counter"):
            if ev["type"] == "gen":
                gens.append(gen_view(ev["gen"])); emit({"type": "gen", "gen": gens[-1]})
            else:
                top3, n_calls = ev["top3"], ev["n_drex_calls"]
        stage("search", "live")
    except Exception as e:  # noqa: BLE001
        c = load(f"contract_{sample}_counters_v2.json") if sample and source == "built-in" else None
        if not c or c.get("persona") != persona:
            stage("search", "error", e); return res
        stage("search", "cached", e, reset=True)
        gens = [gen_view(g) for g in c["generations"]]
        for g in gens:
            emit({"type": "gen", "gen": g})
        top3, n_calls = c["top3"], c["n_drex_calls"]
    offers = [{**{k: o[k] for k in OFFER_KEYS}, "p": o["p"], "utility": o["utility"], "ev": o["ev"],
               "fee_usd": round(float(rate) * o["fee_mult"]) if rate else None} for o in top3]
    rec = None
    if truth and persona == truth["creator_persona"] and source == "built-in":  # check only, vs the truth file
        asw = float(truth["asw_expected_value"])
        got = expected_value(bid, persona, {k: top3[0][k] for k in OFFER_KEYS})[0] - asw
        rec = {"recovered": round(got, 4), "max": float(truth["value_recovered"])}
    res.update(offers=offers, generations=gens, n_drex_calls=n_calls, recovered=rec)
    emit({"type": "offers", "offers": offers, "n_drex_calls": n_calls, "recovered": rec})
    return res


# ---------- Creative studio ----------
from app import creative_loop  # noqa: E402

CONCEPTS = {n: os.path.join(ROOT, c["image"]) for n, c in (load("creative_scores.json") or {"concepts": {}})["concepts"].items()}


def check_image(path, concept=None):
    try:
        probs = creative_loop.ask_rules(path)
        status = "live"
    except Exception as e:  # noqa: BLE001
        cached = (load("creative_scores.json") or {}).get("concepts", {}).get(concept) if concept else None
        if not cached:
            raise RuntimeError("Drex Max didn't answer: " + short(e))
        probs, status = cached["prob"], "cached"
    prod = 1.0
    for p in probs.values():
        prod *= p
    return {"prob": probs, "p_prod": prod, "failed": [r for r, p in probs.items() if p < 0.5], "status": status}


def ask_image(path, question):
    q = (question or "").strip()[:400]
    if len(q) < 3:
        raise ValueError("Type a question first.")
    a = creative_loop.ask_image(path, {"q": {"type": "noul", "instructions": "Look at Image 1. " + q}})
    p = float(a["q"]["noul"])
    return {"question": q, "p": p, "label": plain(p)}
