"""Sanity checks over the whole dataset. Exits non-zero on failure."""
import csv, json, os, subprocess, sys
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
fails = []

def rd(p):
    return list(csv.DictReader(open(os.path.join(D, p), newline="", encoding="utf-8")))

def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond: fails.append(msg)

grid = rd("offers/offers_grid_all_brands.csv")
check(len(grid) == 24000, f"offer grid rows = {len(grid)}")
check(all(0 <= float(r["p_accept"]) <= 1 for r in grid), "p_accept within [0,1]")
check(all(not (r["red_lines"] and r["accept"] == "1") for r in grid), "red-line offers never accepted")
for b in ("northwind", "vela", "kettle"):
    rows = [r for r in grid if r["brand"] == b]
    rate = sum(int(r["accept"]) for r in rows) / len(rows)
    check(0.1 <= rate <= 0.6, f"{b} acceptance rate {rate:.1%} in [10%,60%]")
    # monotonic: higher fee_mult at same other terms never raises p_accept
    key = lambda r: tuple(r[k] for k in ("usage_months", "excl_months", "net_days", "kill_pct", "revisions"))
    grp = {}
    for r in rows: grp.setdefault(key(r), []).append((float(r["fee_mult"]), float(r["p_accept"])))
    bad = sum(1 for v in grp.values() if any(b2[1] > a[1] + 1e-9 for a, b2 in zip(sorted(v), sorted(v)[1:])))
    check(bad == 0, f"{b}: p_accept non-increasing in fee_mult ({bad} violations)")
bench = rd("offers/offers_benchmark.csv")
check(len(bench) == 600, f"offer benchmark rows = {len(bench)}")
acc = sum(int(r["accept"]) for r in bench) / len(bench)
check(0.35 <= acc <= 0.65, f"benchmark accept rate {acc:.1%} roughly balanced")
check({r["split"] for r in bench} == {"dev", "test"}, "benchmark has dev and test splits")
best = rd("offers/ground_truth_best_offers.csv")
check(len(best) == 90 and all(float(r["p_accept"]) >= 0.5 for r in best), "90 best offers, all with p_accept >= 0.5")
cl = rd("clauses/clauses_benchmark.csv")
check(len(cl) == 112, f"clauses = {len(cl)}")
check(all(1 <= int(r["risk_score"]) <= 5 for r in cl), "risk scores in 1..5")
check({int(r["risk_score"]) for r in cl} == {1, 2, 3, 4, 5}, "all risk levels present")
cr = rd("creative/creative_labels.csv")
check(len(cr) == 48, f"creative images = {len(cr)}")
check(all(os.path.exists(os.path.join(D, "creative", r["filename"])) for r in cr), "all creative image files exist")
check(10 <= sum(int(r["passes_all"]) for r in cr) <= 16, "creative has a healthy number of compliant images")
for k in ("R1_logo_ok", "R2_palette_ok", "R3_disclosure_ok", "R4_competitor_ok", "R5_safe_zone_ok"):
    n = sum(1 for r in cr if r[k] == "0")
    check(n >= 4, f"{k}: {n} violating examples")
for cid in "ABCD":
    k = json.load(open(os.path.join(D, f"answer_keys/contract_{cid}_key.json")))
    f = os.path.join(D, k["file"])
    check(os.path.exists(f), f"contract {cid} file exists")
    check(all(v["status"] in ("found", "not_found", "ambiguous") for v in k["fields"].values()), f"contract {cid} statuses valid")
    # quotes of found fields must appear in the source (clean source for the scan)
    src = os.path.join(D, "answer_keys/contract_D_clean_source.pdf") if cid == "D" else f
    txt = " ".join(subprocess.run(["pdftotext", "-layout", src, "-"], capture_output=True, text=True).stdout.split())
    miss = [n for n, v in k["fields"].items() if v["status"] == "found" and v.get("quote") and " ".join(v["quote"].split()) not in txt]
    check(not miss, f"contract {cid} found-quotes appear in text (missing: {miss})")
check(all(os.path.exists(os.path.join(D, "brand", f"{b}_partnership_playbook.pdf")) for b in ("northwind", "vela", "kettle")), "3 playbooks exist")
print("\nALL CHECKS PASSED" if not fails else f"\n{len(fails)} CHECK(S) FAILED")
sys.exit(1 if fails else 0)
