"""Builds the offer datasets from the brand acceptance simulator.

Outputs (in ../offers and ../brand):
  offers_grid_all_brands.csv      every combination of terms x 3 brands (24,000 rows) with labels
  offers_benchmark.csv            stratified sample (600 rows) with offer_text, for acceptance scoring
  ground_truth_best_offers.csv    top 10 offers by expected value for each brand x creator persona
  past_deals_<brand>.csv          8 prior accepted deals per brand (also printed in the playbook PDF)
  rate_cards.csv                  creator baselines and add-on pricing
"""
import random
from common import (BRAND_ORDER, CREATORS, PERSONAS, OFFER_KEYS, SEED, iter_grid,
                    brand_eval, creator_utility, creator_red_lines, offer_text, usage_text, rev_text,
                    path, write_csv)


def main():
    rng = random.Random(SEED)
    all_rows = []
    for bid in BRAND_ORDER:
        for o in iter_grid():
            e = brand_eval(bid, o)
            row = dict(brand=bid, **o, **e)
            for persona in PERSONAS:
                u = creator_utility(persona, o)
                row[f"creator_red_{persona}"] = "|".join(creator_red_lines(persona, o))
                row[f"utility_{persona}"] = u
                row[f"ev_{persona}"] = round(e["p_accept"] * u, 4)
            all_rows.append(row)
    write_csv(path("offers", "offers_grid_all_brands.csv"), all_rows)

    # acceptance rates per brand
    for bid in BRAND_ORDER:
        rows = [r for r in all_rows if r["brand"] == bid]
        acc = sum(r["accept"] for r in rows)
        red = sum(1 for r in rows if r["red_lines"])
        print(f"{bid}: {len(rows)} offers, accept {acc} ({acc / len(rows):.1%}), red-line {red} ({red / len(rows):.1%})")

    # ---- stratified benchmark sample: 200 per brand
    bench = []
    for bid in BRAND_ORDER:
        rows = [r for r in all_rows if r["brand"] == bid]
        near_acc = [r for r in rows if not r["red_lines"] and 0.5 <= r["p_accept"] <= 0.7]
        near_rej = [r for r in rows if not r["red_lines"] and 0.3 <= r["p_accept"] < 0.5]
        clear_acc = [r for r in rows if r["p_accept"] > 0.75]
        clear_rej = [r for r in rows if not r["red_lines"] and r["p_accept"] < 0.3]
        red = [r for r in rows if r["red_lines"]]
        plan = [("near_accept", near_acc, 50), ("near_reject", near_rej, 50),
                ("clear_accept", clear_acc, 30), ("clear_reject", clear_rej, 30),
                ("red_line", red, 40)]
        picked, used = [], set()
        for tag, pool, n in plan:
            for r in rng.sample(pool, min(n, len(pool))):
                picked.append((tag, r))
                used.add(id(r))
        # top up to 200 from the boundary pools when a stratum is short, keeping accept/reject balanced
        refill = [("near_reject", near_rej), ("clear_reject", clear_rej), ("red_line", red),
                  ("near_accept", near_acc)]
        i = 0
        while len(picked) < 200:
            tag, pool = refill[i % len(refill)]
            i += 1
            cand = [r for r in pool if id(r) not in used]
            if not cand:
                if all(not [r for r in p if id(r) not in used] for _, p in refill):
                    break
                continue
            r = rng.choice(cand)
            picked.append((tag, r))
            used.add(id(r))
        rng.shuffle(picked)
        for i, (tag, r) in enumerate(picked):
            o = {k: r[k] for k in OFFER_KEYS}
            bench.append(dict(
                offer_id=f"{bid[:3].upper()}-{i + 1:03d}", brand=bid, stratum=tag,
                offer_text=offer_text(o), **o,
                accept=r["accept"], p_accept=r["p_accept"], red_lines=r["red_lines"], margin=r["margin"],
                split="dev" if i % 10 < 3 else "test"))
    write_csv(path("offers", "offers_benchmark.csv"), bench)
    print("benchmark rows:", len(bench), "accept rate:", round(sum(b["accept"] for b in bench) / len(bench), 3))

    # ---- ground-truth best offers per brand x persona
    best = []
    for bid in BRAND_ORDER:
        rows = [r for r in all_rows if r["brand"] == bid]
        for persona in PERSONAS:
            ranked = sorted(rows, key=lambda r: -r[f"ev_{persona}"])[:10]
            for rank, r in enumerate(ranked, start=1):
                o = {k: r[k] for k in OFFER_KEYS}
                best.append(dict(brand=bid, creator_persona=persona, rank=rank, offer_text=offer_text(o),
                                 **o, p_accept=r["p_accept"], creator_utility=r[f"utility_{persona}"],
                                 expected_value=r[f"ev_{persona}"]))
    write_csv(path("offers", "ground_truth_best_offers.csv"), best)

    # ---- past deals (accepted offers a brand actually "closed")
    first_names = ["Aaliyah", "Ben", "Camila", "Dev", "Elena", "Femi", "Grace", "Hiro", "Ines", "Jamal",
                   "Kara", "Luca", "Mina", "Noah", "Omar", "Pia", "Quinn", "Rosa", "Sam", "Tara"]
    dates = ["2025-02-11", "2025-03-27", "2025-05-08", "2025-06-19", "2025-08-04", "2025-09-16",
             "2025-11-03", "2026-01-22", "2026-03-10", "2026-05-14", "2026-07-08", "2026-09-02"]
    for bid in BRAND_ORDER:
        pool = [r for r in all_rows if r["brand"] == bid and 0.6 <= r["p_accept"] <= 0.95]
        picks = rng.sample(pool, 8)
        deals = []
        for i, r in enumerate(sorted(picks, key=lambda x: x["margin"], reverse=True)):
            base = rng.choice([1800, 2200, 2500, 3000, 3200, 3800, 4000, 4500, 5500, 6000])
            o = {k: r[k] for k in OFFER_KEYS}
            deals.append(dict(
                deal_id=f"{bid[:3].upper()}-PD-{i + 1:02d}", brand=bid, date=dates[i],
                creator=f"{rng.choice(first_names)} {chr(65 + rng.randrange(26))}.",
                creator_standard_rate_usd=base, fee_usd=int(round(base * o["fee_mult"], -1)),
                fee_pct_of_standard=round(o["fee_mult"] * 100), usage=usage_text(o["usage_months"]),
                exclusivity="none" if o["excl_months"] == 0 else f"{o['excl_months']} months",
                payment=f"net-{o['net_days']}", kill_fee_pct=o["kill_pct"], revisions=rev_text(o["revisions"])))
        write_csv(path("brand", f"past_deals_{bid}.csv"), deals)

    # ---- rate cards
    rc = []
    for cid, c in CREATORS.items():
        base = c["baseline_fee"]
        rc.append(dict(creator_id=cid, name=c["name"], handle=c["handle"], niche=c["niche"],
                       platform=c["platform"], followers=c["followers"], standard_package=c["package"],
                       standard_package_fee_usd=base,
                       addon_usage_plus_6_months_usd=round(base * 0.15),
                       addon_whitelisting_usd=round(base * 0.20),
                       addon_exclusivity_3_months_usd=round(base * 0.10),
                       addon_extra_revision_round_usd=round(base * 0.05),
                       addon_rush_delivery_usd=round(base * 0.25),
                       hourly_rate_extra_work_usd=150))
    write_csv(path("contracts", "rate_cards.csv"), rc)


if __name__ == "__main__":
    main()
