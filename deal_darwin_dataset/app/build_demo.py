"""Build app/demo/index.html: a self-contained Deal Darwin demo page.

Reads app/cache/*.json, contracts/contracts_index.csv and
answer_keys/contract_counter_truth.csv, downscales creative/firefly/final_*.png,
and embeds everything into app/demo_template.html. No server needed.

Run: python3 app/build_demo.py
"""
import base64
import csv
import io
import json
import os
import sys

from PIL import Image

APP = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(APP)
sys.path.insert(0, APP)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from common import BRANDS, CREATORS, OFFER_KEYS, PERSONAS, expected_value  # noqa: E402
from counter_engine import plain_language  # noqa: E402

CACHE = os.path.join(APP, "cache")
OUT = os.path.join(APP, "demo", "index.html")
TEMPLATE = os.path.join(APP, "demo_template.html")
LABELS = {"A": "Fair", "B": "Predatory", "C": "Buried terms", "D": "Messy scan"}
METHODS = {
    "v1": "Top 40 offers by creator value over the full term grid; Drex answers "
          "\"would the brand accept?\" for each; ranked by expected value = P(accept) x creator value.",
    "v2": "Drex first reads the brand playbook to find the brand's limit on each term, then the "
          "40 best offers inside those limits are scored and ranked the same way as v1.",
    "evo": "Evolutionary search: 40 random offers, then 3 generations that keep the top 10 and mutate "
           "one term at a time; fitness = Drex P(accept) x creator value (app/counter_v2.py).",
}
NAMES = {"v1": "v1", "v2": "box", "evo": "v2"}  # evo = app/counter_v2.py; "box" = playbook-limits method
RULE_REASONS = {
    "R1": "the logo looks too small, cropped or crowded",
    "R2": "colors outside the brand palette were detected",
    "R3": "the #ad disclosure looks too small or low-contrast",
    "R4": "a competitor name or logo appears to be visible",
    "R5": "copy appears to sit in the bottom 15% safe zone",
}


def load(name):
    p = os.path.join(CACHE, name)
    return json.load(open(p)) if os.path.exists(p) else None


def read_csv(path):
    with open(os.path.join(ROOT, path), newline="", encoding="utf-8") as f:
        return {r["contract_id"]: r for r in csv.DictReader(f)}


def offer_view(o, creator):
    terms = {k: o[k] for k in OFFER_KEYS}
    return {**terms, "fee_usd": round(CREATORS[creator]["baseline_fee"] * o["fee_mult"]),
            "plain": plain_language(creator, terms),
            "p": o.get("_p", o.get("p")), "utility": o.get("_utility", o.get("utility")),
            "ev": o.get("_ev", o.get("ev"))}


def counters_view(c, truth_row, evo):
    creator, brand, persona = c["creator"], c["brand"], c["persona"]
    # D's cache predates v1/v2 and holds a single v1-style result at the top level.
    # UI shows only the evolutionary search (app/counter_v2.py); v1/box results stay in the cache, unused.
    runs = {}
    if evo:
        runs["evo"] = {"top3": evo["top3"], "comparison": {
            "our_top_ev": evo["top3"][0]["ev"], "in_true_top10": evo["check"]["v2_in_true_top10"]}}
    asw_ev = float(truth_row["asw_expected_value"])
    best = {k: float(truth_row[f"best_{k}"]) for k in OFFER_KEYS}
    methods = []
    for label, run in runs.items():
        cmp_ = run["comparison"]
        # Check only: score the top pick with the brand simulator so it is comparable to the truth EVs.
        true_ev = expected_value(brand, persona, {k: run["top3"][0][k] for k in OFFER_KEYS})[0]
        methods.append({
            "label": label, "name": NAMES[label], "about": METHODS[label],
            "top3": [offer_view(o, creator) for o in run["top3"]],
            "drex_ev": cmp_["our_top_ev"], "our_ev": round(true_ev, 4),
            "our_recovered": round(true_ev - asw_ev, 4),
            "in_true_top10": cmp_["in_true_top10"], "boundaries": run.get("boundaries"),
        })
    evolution = None
    if evo:
        evolution = {"n_drex_calls": evo.get("n_drex_calls"), "generations": [
            {"gen": g["gen"], "best": g["best_fitness"], "elite_mean": g["elite_mean_fitness"],
             "new_calls": g["new_drex_calls"], "p": g["best_p"], "utility": g["best_utility"],
             "offer": {k: g["best_offer"][k] for k in OFFER_KEYS}} for g in evo["generations"]]}
    return {
        "creator": creator, "persona": c["persona"], "methods": methods, "evolution": evolution,
        "truth": {"asw_ev": asw_ev, "best_ev": float(truth_row["best_expected_value"]),
                  "max_recovered": float(truth_row["value_recovered"]),
                  "best_offer": {**best, "fee_usd": round(CREATORS[creator]["baseline_fee"] * best["fee_mult"])},
                  "best_text": truth_row["best_offer_text"],
                  "interpretation": truth_row["interpretation"]},
    }


def thumb(path, width=600):
    with Image.open(path) as im:
        im = im.convert("RGB")
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=85, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def creative_view():
    scores = load("creative_scores.json")
    if not scores:
        return None
    winner = scores.get("winner")
    concepts = []
    for name, s in scores["concepts"].items():
        failed = [r for r, p in s["prob"].items() if p < 0.5]
        why = None
        if failed:
            parts = [f"{RULE_REASONS[r]} ({r} p={s['prob'][r]:.2f})" for r in failed]
            why = "Drex Max flagged that " + "; and ".join(parts) + "."
        concepts.append({"name": name, "prob": s["prob"], "p_prod": s["p_pass_product"],
                         "p_min": s["p_pass_min"], "winner": name == winner, "why": why, "failed": failed,
                         "img": thumb(os.path.join(ROOT, s["image"]))})
    val = load("creative_validation.json")
    return {"model": scores.get("model"), "concepts": concepts,
            "validation": {"n": val["n"], "correct": val["correct"]} if val else None}


def main():
    index = read_csv("contracts/contracts_index.csv")
    truth = read_csv("answer_keys/contract_counter_truth.csv")
    contracts = {}
    for cid in "ABCD":
        risk, counters = load(f"contract_{cid}_risk.json"), load(f"contract_{cid}_counters.json")
        if not risk:
            continue
        meta = index[cid]
        contracts[cid] = {
            "id": cid, "label": LABELS[cid], "scenario": meta["scenario"],
            "brand": meta["brand"], "creator": meta["creator"], "input_type": meta["input_type"],
            "pages": int(meta["pages"]), "source": "clean source PDF" if cid == "D" else "original PDF",
            "risk": risk,
            "counters": counters_view(counters, truth[cid], load(f"contract_{cid}_counters_v2.json"))
            if counters else None,
        }
    data = {"contracts": contracts, "creative": creative_view(),
            "brands": {k: v["name"] for k, v in BRANDS.items()},
            "config": {"personas": list(PERSONAS),
                       "sample_personas": {cid: truth[cid]["creator_persona"] for cid in contracts}}}
    blob = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    html = open(TEMPLATE, encoding="utf-8").read().replace("/*__DATA__*/null", blob)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"wrote {OUT} ({os.path.getsize(OUT) / 1e6:.2f} MB, {len(contracts)} contracts)")


if __name__ == "__main__":
    main()
