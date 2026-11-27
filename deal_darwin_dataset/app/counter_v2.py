"""Deal Darwin counter engine v2: evolutionary search with Drex as the fitness function.

fitness(offer) = Drex noul P(brand accepts | playbook, offer_text) x creator_utility.
Gen 0: 40 random red-line-safe offers (fixed seed). Each of 3 further generations keeps
the top 10 and adds 30 children that change ONE term to an adjacent grid value.
The simulator (expected_value / truth CSV) is used only to CHECK the final pick.

Run: python3 app/counter_v2.py [A B C D]
"""
import json
import os
import random
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from counter_engine import (CONTRACTS, PLAYBOOK_PDF, ROOT, ask_brand_accepts, load_truth,  # noqa: E402
                            pdftotext, plain_language, true_top10)
from drex_client import ask  # noqa: E402
from common import BRANDS, offer_text  # noqa: E402
from common import (GRID, OFFER_KEYS, SEED, creator_red_lines, creator_utility,  # noqa: E402
                    expected_value, iter_grid)

POP, ELITE, CHILDREN, GENERATIONS, WORKERS = 40, 10, 30, 3, 4
MAX_FAIL_SHARE = 0.25
MAX_CALLS = 120  # Drex calls per run (shared-IP safe); later generations get fewer children if needed
CACHE = os.path.join(ROOT, "app", "cache")


def key(o):
    return tuple(o[k] for k in OFFER_KEYS)


def accepts(brand, playbook, o):
    """Drex P(brand accepts). Built-in brand ids use the engine's question; any other name works the same way."""
    if brand in BRANDS:
        return ask_brand_accepts(brand, playbook, o)
    state = f"BRAND PLAYBOOK ({brand or 'the brand'}):\n{playbook}\n\nCOUNTER-OFFER FROM THE CREATOR:\n{offer_text(o)}"
    return ask(state, {"q": {"type": "noul", "instructions": (
        "Based on the brand's playbook, including its standard terms and hard limits, "
        "would the brand accept this counter-offer?")}})["q"]["noul"]


def score_all(offers, scores, brand, playbook, persona):
    """Score offers not yet in `scores` (key -> (p, utility, ev)) with Drex, 8 in parallel."""
    todo = [o for o in {key(o): o for o in offers}.values() if key(o) not in scores]

    def one(o):
        for attempt in range(2):  # retry once on any error
            try:
                return accepts(brand, playbook, o)
            except Exception as e:  # noqa: BLE001
                err = e
        print(f"    Drex failed twice for {key(o)}: {str(err)[:120]}")
        return None

    with ThreadPoolExecutor(WORKERS) as pool:
        ps = list(pool.map(one, todo))
    failed = sum(p is None for p in ps)
    if todo and failed > MAX_FAIL_SHARE * len(todo):  # an outage must not look like "brand rejects everything"
        raise RuntimeError(f"Drex failed for {failed}/{len(todo)} offers")
    for o, p in zip(todo, ps):
        p = p or 0.0  # an isolated failure counts as p=0, as before
        u = creator_utility(persona, o)
        scores[key(o)] = (p, u, p * u)
    return len(todo)


def rank(offers, scores):
    return sorted({key(o): o for o in offers}.values(), key=lambda o: (-scores[key(o)][2], key(o)))


def mutate(o, rng):
    k = rng.choice(OFFER_KEYS)
    i = GRID[k].index(o[k]) + rng.choice((-1, 1))
    if 0 <= i < len(GRID[k]):
        return {**o, k: GRID[k][i]}
    return None


def make_children(elite, persona, scores, rng):
    seen, kids = {key(o) for o in elite}, []
    for _ in range(5000):
        if len(kids) == CHILDREN:
            break
        c = mutate(rng.choice(elite), rng)
        if c is None or key(c) in seen or creator_red_lines(persona, c):
            continue
        seen.add(key(c))
        kids.append(c)
    return kids


def true_ev(brand, persona, o):
    return expected_value(brand, persona, o)[0]


def iter_search(brand, persona, playbook, seed=SEED):
    """Yield {"type": "gen", "gen": {...}} per generation, then {"type": "final", "top3", "n_drex_calls"}."""
    rng = random.Random(seed)
    pool = [o for o in iter_grid() if not creator_red_lines(persona, o)]
    scores, pop, elite = {}, rng.sample(pool, POP), []
    for g in range(GENERATIONS + 1):
        if g:
            budget, kids = MAX_CALLS - len(scores), []
            for c in make_children(elite, persona, scores, rng):
                if key(c) in scores or budget > 0:  # already-scored children are free
                    budget -= key(c) not in scores
                    kids.append(c)
            pop = elite + kids
        new = score_all(pop, scores, brand, playbook, persona)
        elite = rank(pop, scores)[:ELITE]
        best = scores[key(elite[0])]
        yield {"type": "gen", "gen": {
            "gen": g, "best_fitness": round(best[2], 4), "best_p": round(best[0], 4), "best_utility": best[1],
            "best_offer": elite[0], "new_drex_calls": new,
            "elite_mean_fitness": round(sum(scores[key(o)][2] for o in elite) / ELITE, 4)}}
    yield {"type": "final", "n_drex_calls": len(scores), "top3": [
        {**o, "p": scores[key(o)][0], "utility": scores[key(o)][1], "ev": round(scores[key(o)][2], 4)}
        for o in rank(pop, scores)[:3]]}


def run(cid, truth):
    meta, row = CONTRACTS[cid], truth[cid]
    brand, creator, persona = meta["brand"], meta["creator"], row["creator_persona"]
    playbook = pdftotext(os.path.join(ROOT, PLAYBOOK_PDF[brand]))
    gens, top = [], None
    for ev in iter_search(brand, persona, playbook):
        if ev["type"] == "gen":
            g = ev["gen"]
            gens.append(g)
            print(f"  [{cid}] gen {g['gen']}: best fitness {g['best_fitness']:.4f} "
                  f"(p {g['best_p']:.3f} x u {g['best_utility']:.3f}), {g['new_drex_calls']} new Drex calls")
        else:
            top, n_calls = ev["top3"], ev["n_drex_calls"]
    top3 = [{**o, "plain": plain_language(creator, o)} for o in top]

    # ---- checking only: simulator EVs and the truth CSV never influence the search ----
    asw_ev, max_rec = float(row["asw_expected_value"]), float(row["value_recovered"])
    t10 = {key(o) for o in true_top10(brand, persona)}
    v1_cache = json.load(open(os.path.join(CACHE, f"contract_{cid}_counters.json")))
    v1_top = (v1_cache.get("v1") or v1_cache)["top3"][0]
    v2_top = top3[0]
    check = {"v1_top_drex_ev": v1_top["_ev"], "v2_top_drex_ev": v2_top["ev"],
             "v1_top_true_ev": round(true_ev(brand, persona, v1_top), 4),
             "v2_top_true_ev": round(true_ev(brand, persona, v2_top), 4),
             "v2_in_true_top10": key(v2_top) in t10, "asw_true_ev": asw_ev,
             "best_true_ev": float(row["best_expected_value"]), "max_value_recovered": max_rec}
    check["v2_value_recovered"] = round(check["v2_top_true_ev"] - asw_ev, 4)
    check["v1_value_recovered"] = round(check["v1_top_true_ev"] - asw_ev, 4)
    out = {"contract": cid, "brand": brand, "creator": creator, "persona": persona,
           "method": "evolutionary search, fitness = Drex P(accept) x creator_utility",
           "params": {"pop": POP, "elite": ELITE, "children": CHILDREN, "generations": GENERATIONS,
                      "seed": SEED}, "n_drex_calls": n_calls,
           "generations": gens, "top3": top3, "check": check}
    json.dump(out, open(os.path.join(CACHE, f"contract_{cid}_counters_v2.json"), "w"), indent=2)
    return out


def main():
    cids = sys.argv[1:] or list("ABCD")
    truth, results = load_truth(), []
    for cid in cids:
        print(f"\n=== Contract {cid} ===")
        r = run(cid, truth)
        results.append(r)
        print("  Top 3 (v2):")
        for i, o in enumerate(r["top3"], 1):
            print(f"    {i}. EV {o['ev']:.3f} (p {o['p']:.2f}, u {o['utility']:.2f})  {o['plain']}")
    print("\nDrex EV = P(accept) x utility as scored by Drex. True EV / recovered = brand simulator (check only).")
    print(f"{'':3}{'v1 DrexEV':>10}{'v2 DrexEV':>10}{'v1 trueEV':>10}{'v2 trueEV':>10}"
          f"{'v2 top10':>9}{'v1 recov':>9}{'v2 recov':>9}{'max':>7}{'calls':>6}")
    for r in results:
        c = r["check"]
        print(f"{r['contract']:3}{c['v1_top_drex_ev']:10.3f}{c['v2_top_drex_ev']:10.3f}{c['v1_top_true_ev']:10.3f}"
              f"{c['v2_top_true_ev']:10.3f}{str(c['v2_in_true_top10']):>9}{c['v1_value_recovered']:9.3f}"
              f"{c['v2_value_recovered']:9.3f}{c['max_value_recovered']:7.3f}{r['n_drex_calls']:6d}")


if __name__ == "__main__":
    main()
