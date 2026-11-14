"""Deal Darwin counter engine.

V1 (default, spec pipeline):
  1. Enumerate candidate counter-offers with iter_grid(); drop any that break the
     creator's walk-away limits (creator_red_lines).
  2. Keep the 40 best by creator_utility, ask Drex a noul question for each:
     "Would the brand accept this counter-offer?" with state = brand playbook text
     (pdftotext of brand/*_partnership_playbook.pdf) + offer_text(offer).
     p = answers.q.noul.
  3. Rank by expected value = p_accept * creator_utility; print the top 3 as
     plain-language offers.
  4. Compare the top pick with answer_keys/contract_counter_truth.csv (ground truth
     was generated with brand_eval; here brand_eval is used ONLY to build the check
     ranking, never to judge Drex's candidates).
  5. Save app/cache/contract_X_counters.json.

V2 (--v2 flag, runs v1 too so both are reported):
  1. First ask Drex six choice questions (one per grid dimension) to discover the
     brand's acceptance box from the playbook: the most creator-favorable value
     the brand would still accept for each dimension, all else at the brand's
     standard.
  2. Shortlist = top 40 by creator_utility inside that box (still respecting the
     creator's walk-away limits), then the same noul EV ranking as v1.
"""
import csv
import json
import os
import subprocess
import sys

APP = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(APP)
sys.path.insert(0, APP)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from common import (BRANDS, CREATORS, OFFER_KEYS, USAGE_PERPETUAL, REV_UNLIMITED,
                    GRID, iter_grid, creator_red_lines, creator_utility,
                    expected_value, offer_text, usage_text, rev_text)
from drex_client import ask

TOP_N = 40

PLAYBOOK_PDF = {
    "northwind": "brand/northwind_partnership_playbook.pdf",
    "vela": "brand/vela_partnership_playbook.pdf",
    "kettle": "brand/kettle_partnership_playbook.pdf",
}
CONTRACTS = {
    "A": dict(brand="northwind", creator="maya_okafor"),
    "B": dict(brand="vela", creator="priya_nair"),
    "C": dict(brand="kettle", creator="jordan_lee"),
    "D": dict(brand="northwind", creator="diego_ramirez"),
}

# dimension -> (label -> grid value) plus the boundary question
BOUNDARY_QUESTIONS = {
    "fee_mult": ({
        "90% of the standard rate": 0.9, "100% of the standard rate": 1.0,
        "115% of the standard rate": 1.15, "130% of the standard rate": 1.3,
        "150% of the standard rate": 1.5,
    }, "What is the highest fee, as a percentage of the creator's standard rate, "
       "that the brand would still accept, if every other term is at the brand's "
       "standard?"),
    "usage_months": ({
        "3 months": 3, "6 months": 6, "12 months": 12, "24 months": 24,
        "perpetual": USAGE_PERPETUAL,
    }, "What is the shortest usage period (in months) the brand would still "
       "accept, if every other term is at the brand's standard?"),
    "excl_months": ({
        "none": 0, "3 months": 3, "6 months": 6, "12 months": 12,
    }, "What is the shortest category exclusivity period the brand would still "
       "accept, if every other term is at the brand's standard?"),
    "net_days": ({
        "net-15": 15, "net-30": 30, "net-45": 45, "net-60": 60, "net-90": 90,
    }, "What is the shortest payment period (fewest net days) the brand would "
       "still offer, if every other term is at the brand's standard?"),
    "kill_pct": ({
        "0%": 0, "10%": 10, "25%": 25, "50%": 50,
    }, "What is the highest cancellation (kill) fee, as a percentage of the fee, "
       "that the brand would still accept, if every other term is at the brand's "
       "standard?"),
    "revisions": ({
        "1 round": 1, "2 rounds": 2, "4 rounds": 4, "unlimited": REV_UNLIMITED,
    }, "What is the fewest rounds of revisions the brand would still accept, "
       "if every other term is at the brand's standard?"),
}
# how each boundary constrains the candidate box
BOX_RULES = {
    "fee_mult": lambda o, b: o["fee_mult"] <= b + 1e-9,
    "usage_months": lambda o, b: o["usage_months"] >= b - 1e-9,
    "excl_months": lambda o, b: o["excl_months"] >= b - 1e-9,
    "net_days": lambda o, b: o["net_days"] >= b - 1e-9,
    "kill_pct": lambda o, b: o["kill_pct"] <= b + 1e-9,
    "revisions": lambda o, b: o["revisions"] >= b - 1e-9,
}


def pdftotext(path):
    return subprocess.run(["pdftotext", "-layout", path, "-"],
                          check=True, capture_output=True, text=True).stdout


def load_truth():
    """contract_id -> ground-truth row (persona, as-written and best terms)."""
    with open(os.path.join(ROOT, "answer_keys", "contract_counter_truth.csv"),
              newline="", encoding="utf-8") as f:
        return {r["contract_id"]: r for r in csv.DictReader(f)}


def plain_language(creator_id, o):
    fee_usd = round(CREATORS[creator_id]["baseline_fee"] * o["fee_mult"])
    excl = "none" if o["excl_months"] == 0 else f"{o['excl_months']} months"
    return (f"Ask for ${fee_usd:,} ({round(o['fee_mult'] * 100)}% of the standard rate), "
            f"{usage_text(o['usage_months'])} of usage rights, {excl} of category exclusivity, "
            f"payment in net-{o['net_days']}, a {o['kill_pct']}% kill fee, "
            f"and {rev_text(o['revisions'])} of revisions.")


def clean(o):
    return {k: o[k] for k in OFFER_KEYS + ["_utility", "_p", "_ev"]}


def true_top10(brand_id, persona, n=10):
    """Ground-truth check only: rank the whole grid by the simulator's expected value."""
    scored = []
    for o in iter_grid():
        ev, _e, _u = expected_value(brand_id, persona, o)
        scored.append((ev, o))
    scored.sort(key=lambda t: (-t[0], *[t[1][k] for k in OFFER_KEYS]))
    return [o for _ev, o in scored[:n]]


def ask_brand_accepts(brand_id, playbook, offer):
    state = (f"BRAND PLAYBOOK ({BRANDS[brand_id]['name']}):\n{playbook}"
             f"\n\nCOUNTER-OFFER FROM THE CREATOR:\n{offer_text(offer)}")
    ans = ask(state, {"q": {"type": "noul",
                            "instructions": ("Based on the brand's playbook, including its standard "
                                             "terms and hard limits, would the brand accept this "
                                             "counter-offer?")}})
    return ans["q"]["noul"]


def discover_boundaries(brand_id, playbook):
    """Ask Drex one choice question per dimension: the most creator-favorable value
    the brand would still accept (all else at standard). Returns {dim: value}."""
    out = {}
    for dim, (label2val, question) in BOUNDARY_QUESTIONS.items():
        ans = ask(f"BRAND PLAYBOOK ({BRANDS[brand_id]['name']}):\n{playbook}",
                  {"q": {"type": "choice", "instructions": question,
                         "criteria": {label: label for label in label2val}}})
        chosen = ans["q"]["choice"]
        val = label2val.get(chosen)
        if val is None:
            print(f"    boundary '{dim}': unparsable choice {chosen!r} -> unconstrained")
        else:
            out[dim] = val
            print(f"    boundary '{dim}': {chosen!r} -> {val}")
    return out


def shortlist(persona, box, n=TOP_N):
    candidates = [o for o in iter_grid()
                  if not creator_red_lines(persona, o) and all(r(o, b) for r, b in box)]
    for o in candidates:
        o["_utility"] = creator_utility(persona, o)
    candidates.sort(key=lambda o: (-o["_utility"], *[o[k] for k in OFFER_KEYS]))
    return candidates[:n]


def eval_shortlist(brand_id, playbook, persona, short):
    for i, o in enumerate(short, 1):
        o["_p"] = ask_brand_accepts(brand_id, playbook, o)
        o["_ev"] = round(o["_p"] * o["_utility"], 4)
        if i % 10 == 0:
            print(f"    {i}/{len(short)} evaluated")
    short.sort(key=lambda o: -o["_ev"])
    return short


def method_result(short, label):
    top3 = short[:3]
    print(f"  TOP 3 [{label}] (EV = p_accept x creator_utility):")
    for i, o in enumerate(top3, 1):
        print(f"    {i}. EV {o['_ev']:.4f}  (p_accept {o['_p']:.3f}, utility {o['_utility']:.4f})  "
              f"{plain_language(CREATORS_NAME, o)}")
    return {
        "shortlist": [clean(o) for o in short],
        "top3": [clean(o) for o in top3],
    }


CREATORS_NAME = None  # set per contract before printing


def comparison(top, truth_row, brand_id, persona):
    t_top10 = true_top10(brand_id, persona)
    in_top10 = any(all(top[k] == t[k] for k in OFFER_KEYS) for t in t_top10)
    truth_best = {k: (float if k == "fee_mult" else lambda v: int(float(v)))(truth_row[f"best_{k}"])
                  for k in OFFER_KEYS}
    return {
        "our_top_offer": {k: top[k] for k in OFFER_KEYS},
        "our_top_ev": top["_ev"],
        "our_value_recovered": round(top["_ev"] - float(truth_row["asw_expected_value"]), 4),
        "in_true_top10": in_top10,
        "true_best_offer": truth_best,
        "true_best_ev": float(truth_row["best_expected_value"]),
        "true_value_recovered": float(truth_row["value_recovered"]),
    }


def v2_box_items(boundaries):
    """Box predicates: for each discovered boundary, a (predicate, value) pair."""
    return [(lambda o, b, d=dim: BOX_RULES[d](o, b), b) for dim, b in boundaries.items()]


def run_contract(cid, meta, truth, run_v2):
    brand_id, creator_id = meta["brand"], meta["creator"]
    global CREATORS_NAME
    CREATORS_NAME = creator_id
    persona = truth[cid]["creator_persona"]
    playbook = pdftotext(os.path.join(ROOT, PLAYBOOK_PDF[brand_id]))
    result = {"contract": cid, "brand": brand_id, "creator": creator_id, "persona": persona}

    # ---- v1 (default): top 40 by creator_utility over the red-line-filtered grid
    print(f"contract {cid} ({BRANDS[brand_id]['name']} x {CREATORS[creator_id]['name']}, persona {persona})")
    print("  [v1] top 40 by creator_utility over the full red-line-filtered grid")
    v1_short = shortlist(persona, [])
    v1_short = eval_shortlist(brand_id, playbook, persona, v1_short)
    v1_res = method_result(v1_short, "v1")
    v1_res["comparison"] = comparison(v1_short[0], truth[cid], brand_id, persona)
    result["v1"] = v1_res

    if run_v2:
        # ---- v2: Drex-discovered acceptance box, then top 40 by utility inside it
        print("  [v2] discovering brand acceptance box (6 Drex choice calls)")
        boundaries = discover_boundaries(brand_id, playbook)
        box = v2_box_items(boundaries)
        n_in_box = sum(1 for o in iter_grid()
                       if not creator_red_lines(persona, o) and all(r(o, b) for r, b in box))
        if n_in_box == 0:
            print("  [v2] box is empty (boundaries conflict with creator limits); "
                  "falling back to the full red-line-filtered grid")
            box, n_in_box = [], None
        v2_short = shortlist(persona, box)
        print(f"  [v2] box holds {n_in_box} offers; shortlisting top {len(v2_short)} by utility")
        v2_short = eval_shortlist(brand_id, playbook, persona, v2_short)
        v2_res = method_result(v2_short, "v2")
        v2_res["boundaries"] = boundaries
        v2_res["comparison"] = comparison(v2_short[0], truth[cid], brand_id, persona)
        result["v2"] = v2_res

    cache = os.path.join(APP, "cache", f"contract_{cid}_counters.json")
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    with open(cache, "w") as f:
        json.dump(result, f, indent=2)
    print(f"  saved {cache}")
    return result


def print_table(results):
    methods = [m for m in ("v1", "v2") if m in next(iter(results.values()))]
    for method in methods:
        hdr = (f"{method.upper()}: {'C':<3} {'brand':<10} {'persona':<18} {'top EV':>7} {'p':>5} "
               f"{'util':>5}  {'true best EV':>13} {'true val rec':>13} {'our val rec':>11} {'in true top10'}")
        print("\n" + hdr)
        print("-" * len(hdr))
        for cid in sorted(results):
            r = results[cid][method]
            c = r["comparison"]
            t = r["top3"][0]
            print(f"{cid:<3} {results[cid]['brand']:<10} {results[cid]['persona']:<18} "
                  f"{t['_ev']:>7.4f} {t['_p']:>5.3f} {t['_utility']:>5.3f}  "
                  f"{c['true_best_ev']:>13.4f} {c['true_value_recovered']:>13.4f} "
                  f"{c['our_value_recovered']:>11.4f} {'YES' if c['in_true_top10'] else 'no'}")


def main():
    run_v2 = "--v2" in sys.argv
    ids = [a.upper() for a in sys.argv[1:] if a != "--v2" and a.upper() in CONTRACTS] or sorted(CONTRACTS)
    truths = load_truth()
    results = {}
    for cid in ids:
        results[cid] = run_contract(cid, CONTRACTS[cid], truths, run_v2)
    print_table(results)


if __name__ == "__main__":
    main()
