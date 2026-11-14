"""Deal Darwin live pipeline: Ingest (NDI) -> Score (Drex) -> Counter (evolution) -> Creative (Drex Max) -> Pack.

run(emit, sample=None, pdf=None, persona=None, brand=None) calls emit(event) as work progresses and
returns the final result. Each stage runs as a generator under a watchdog: if it raises, or produces no
event for STAGE_TIMEOUT seconds, a sample run falls back to the cached JSON and the stage is "cached".
Env: DD_STAGE_TIMEOUT (default 40), DD_FAIL_STAGES (comma list, forces a fallback, for testing).
"""
import json
import os
import queue
import sys
import threading
import time

APP = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(APP)
for p in (APP, ROOT, os.path.join(ROOT, "scripts")):
    sys.path.insert(0, p)
from common import BRANDS, CREATORS, OFFER_KEYS, PERSONAS, expected_value  # noqa: E402
from counter_engine import CONTRACTS as SAMPLES, PLAYBOOK_PDF, load_truth, pdftotext  # noqa: E402
from counter_v2 import iter_search  # noqa: E402
from extract_and_rate import ASPECTS, CONTRACTS as PDFS, FALLBACK_PDF, extract_value, iter_contract  # noqa: E402
from ndi_client import extract_terms  # noqa: E402
from app.creative_loop import iter_scores  # noqa: E402

CACHE = os.path.join(APP, "cache")
TIMEOUT = float(os.environ.get("DD_STAGE_TIMEOUT", 40))
FAIL = set(filter(None, os.environ.get("DD_FAIL_STAGES", "").split(",")))


def load(name):
    p = os.path.join(CACHE, name)
    return json.load(open(p)) if os.path.exists(p) else None


def watch(gen, stage):
    """Iterate `gen` on a worker thread; raise if it errors or stalls for TIMEOUT seconds."""
    if stage in FAIL:
        raise RuntimeError(f"forced fallback ({stage})")
    q, stop = queue.Queue(), threading.Event()

    def pump():
        try:
            for ev in gen:
                if stop.is_set():
                    return
                q.put(("ev", ev))
            q.put(("end", None))
        except Exception as e:  # noqa: BLE001
            q.put(("err", e))
    threading.Thread(target=pump, daemon=True).start()
    try:
        while True:
            try:
                kind, ev = q.get(timeout=TIMEOUT)
            except queue.Empty:
                raise TimeoutError(f"no progress in {TIMEOUT:.0f}s")
            if kind == "end":
                return
            if kind == "err":
                raise ev
            yield ev
    finally:
        stop.set()


def match_brand(name, override=None):
    n = (name or "").lower()
    for bid, b in BRANDS.items():
        if bid in n or b["name"].split()[0].lower() in n:
            return bid
    return override if override in BRANDS else None


def offer_view(o, creator):
    base = CREATORS.get(creator, {}).get("baseline_fee")
    return {**{k: o[k] for k in OFFER_KEYS}, "fee_usd": round(base * o["fee_mult"]) if base else None,
            "p": o["p"], "utility": o["utility"], "ev": o["ev"]}


def gen_view(g):
    return {"gen": g["gen"], "best": g["best_fitness"], "elite_mean": g["elite_mean_fitness"],
            "new_calls": g["new_drex_calls"], "p": g["best_p"], "utility": g["best_utility"],
            "offer": {k: g["best_offer"][k] for k in OFFER_KEYS}}


def run(emit, sample=None, pdf=None, persona=None, brand=None):
    res = {"stages": {}, "sample": sample}

    def stage(name, status, err=None, reset=False):
        res["stages"][name] = status
        emit({"type": "stage", "stage": name, "status": status, "reset": reset, **({"error": err} if err else {})})

    # ---------- 1. Ingest: NDI upload -> parse -> extract ----------
    stage("ingest", "running")
    path = pdf or os.path.join(ROOT, PDFS[sample])
    fb = FALLBACK_PDF.get(sample) if sample else None

    def ndi():
        yield extract_terms(path, os.path.join(ROOT, fb) if fb else None)
    try:
        ext = next(watch(ndi(), "ingest"))
        if ext["source"] != "ndi" and sample:
            raise RuntimeError(ext.get("error") or "NDI fallback")
        status = "live" if ext["source"] == "ndi" else "fallback"
    except Exception as e:  # noqa: BLE001
        if not sample:
            stage("ingest", "error", str(e)); return res
        c = load(f"contract_{sample}_risk.json")
        ext = {"source": "ndi", "cost_usd": None, "ocr_applied": (c.get("extraction") or {}).get("ocr_applied"),
               "text": pdftotext(os.path.join(ROOT, fb or PDFS[sample])),
               "fields": {**{k: {"status": a.get("ndi_status") or a["status"], "value": a.get("value"),
                                 "quote": a.get("quote"), "page": a.get("page"), "confidence": a.get("ndi_confidence")}
                             for k, a in c["aspects"].items()},
                          **{k: {"value": v} for k, v in (c.get("parties") or {}).items()}}}
        status, ext["error"] = "cached", str(e)
    parties = {k: (ext["fields"].get(k) or {}).get("value") for k in ("brand_name", "creator_name")}
    res["extraction"] = {"source": ext["source"], "ocr_applied": ext.get("ocr_applied"),
                         "cost_usd": ext.get("cost_usd") if status == "live" else None,
                         "reused": ext.get("reused"), "job_ids": ext.get("job_ids")}
    emit({"type": "meta", "brand": parties["brand_name"], "creator": parties["creator_name"], "extraction": res["extraction"]})
    for k in ASPECTS:
        f = ext["fields"].get(k)
        if f:
            emit({"type": "clause", "aspect": {"aspect": k, "status": f.get("status") or "found", "quote": f.get("quote"),
                                               "page": f.get("page"), "value": extract_value(k, f.get("value")) or extract_value(k, f.get("quote"))}})
            time.sleep(0.25)  # one by one on screen
    stage("ingest", status, ext.get("error") if status != "live" else None)

    # ---------- 2. Score: Drex risk + ambiguity per clause ----------
    stage("score", "running")
    risk = None
    try:
        for ev in watch(iter_contract(sample or "UPLOAD", ext), "score"):
            if ev["type"] == "aspect":
                emit({"type": "risk", "aspect": ev["aspect"]})
            else:
                risk = ev["cache"]
        stage("score", "live")
    except Exception as e:  # noqa: BLE001
        if not sample:
            stage("score", "error", str(e)); return res
        risk = load(f"contract_{sample}_risk.json")
        stage("score", "cached", str(e), reset=True)
        for a in risk["aspects"].values():
            emit({"type": "risk", "aspect": a})
    res["risk"] = risk
    emit({"type": "overall", "overall_risk": risk["overall_risk"]})

    # ---------- 3. Counter: evolutionary search, Drex P(accept) x creator utility ----------
    stage("counter", "running")
    bid = match_brand(parties["brand_name"], brand) or (SAMPLES[sample]["brand"] if sample else None)
    creator = SAMPLES[sample]["creator"] if sample else None
    truth = load_truth().get(sample) if sample else None
    persona = persona if persona in PERSONAS else (truth["creator_persona"] if truth else "balanced")
    res.update(brand=bid, persona=persona)
    if not bid:
        stage("counter", "error", "brand not recognised; pick one"); return res
    top3, gens, n_calls = None, [], None
    try:
        playbook = pdftotext(os.path.join(ROOT, PLAYBOOK_PDF[bid]))
        for ev in watch(iter_search(bid, persona, playbook), "counter"):
            if ev["type"] == "gen":
                gens.append(gen_view(ev["gen"])); emit({"type": "gen", "gen": gens[-1]})
            else:
                top3, n_calls = ev["top3"], ev["n_drex_calls"]
        stage("counter", "live")
    except Exception as e:  # noqa: BLE001
        c = load(f"contract_{sample}_counters_v2.json") if sample else None
        if not c:
            stage("counter", "error", str(e)); return res
        stage("counter", "cached", str(e), reset=True)
        gens = [gen_view(g) for g in c["generations"]]
        for g in gens:
            emit({"type": "gen", "gen": g})
        top3, n_calls, persona = c["top3"], c["n_drex_calls"], c["persona"]
    rec = t = None
    if truth and persona == truth["creator_persona"]:  # check only: simulator EV vs the truth file
        asw = float(truth["asw_expected_value"])
        rec = round(expected_value(bid, persona, {k: top3[0][k] for k in OFFER_KEYS})[0] - asw, 4)
        t = {"max_recovered": float(truth["value_recovered"]), "asw_ev": asw}
    method = {"label": "evo", "name": "v2", "top3": [offer_view(o, creator) for o in top3], "our_recovered": rec}
    res["counters"] = {"method": method, "truth": t, "generations": gens, "n_drex_calls": n_calls, "persona": persona}
    emit({"type": "offers", "method": method, "truth": t, "n_drex_calls": n_calls})

    # ---------- 4. Creative: Drex Max scores each Firefly concept ----------
    stage("creative", "running")
    cached = load("creative_scores.json")
    names = list(cached["concepts"])
    paths = [(n, os.path.join(ROOT, cached["concepts"][n]["image"])) for n in names]
    scores = []
    try:
        emit({"type": "concept_start", "index": 0})
        for i, s in enumerate(watch(iter_scores(paths), "creative")):
            s["failed"] = [r for r, p in s["prob"].items() if p < 0.5]
            scores.append(s)
            emit({"type": "concept", "index": i, "concept": {**s, "p_prod": s["p_pass_product"]}})
            if i + 1 < len(paths):
                emit({"type": "concept_start", "index": i + 1})
        stage("creative", "live")
    except Exception as e:  # noqa: BLE001
        stage("creative", "cached", str(e), reset=True)
        scores = []
        for i, n in enumerate(names):
            s = cached["concepts"][n]
            scores.append({"name": n, "prob": s["prob"], "p_pass_product": s["p_pass_product"],
                           "failed": [r for r, p in s["prob"].items() if p < 0.5]})
            emit({"type": "concept", "index": i, "concept": {**scores[-1], "p_prod": s["p_pass_product"]}})
    win = max(range(len(scores)), key=lambda i: scores[i]["p_pass_product"])
    res["creative"] = {"concepts": scores, "winner": scores[win]["name"]}
    emit({"type": "winner", "index": win})

    # ---------- 5. Pack ----------
    stage("pack", "live")
    return res
