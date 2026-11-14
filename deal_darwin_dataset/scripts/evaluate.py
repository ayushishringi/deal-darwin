"""Score predictions against the dataset. Usage: python3 evaluate.py --task clauses|offers|creative --pred preds.csv [--split test]
clauses: pred columns clause_id, risk_score, deviates_from_norm(yes/no)
offers:  pred columns offer_id, p_accept (0-1)
creative: pred columns image_id, R1..R5 (1 = rule satisfied), optional passes_all
"""
import argparse, csv, math, os
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

def rd(p):
    return list(csv.DictReader(open(p, newline="", encoding="utf-8")))

def rank(v):
    s = sorted(range(len(v)), key=lambda i: v[i]); r = [0.0] * len(v); i = 0
    while i < len(s):
        j = i
        while j + 1 < len(s) and v[s[j + 1]] == v[s[i]]: j += 1
        for k in range(i, j + 1): r[s[k]] = (i + j) / 2 + 1
        i = j + 1
    return r

def spearman(a, b):
    ra, rb = rank(a), rank(b); n = len(a)
    ma, mb = sum(ra) / n, sum(rb) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = math.sqrt(sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb))
    return num / den if den else 0.0

def auc(y, p):
    pos = [q for t, q in zip(y, p) if t]; neg = [q for t, q in zip(y, p) if not t]
    if not pos or not neg: return float("nan")
    w = sum((a > b) + 0.5 * (a == b) for a in pos for b in neg)
    return w / (len(pos) * len(neg))

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--task", required=True); ap.add_argument("--pred", required=True)
    ap.add_argument("--split", default="test"); a = ap.parse_args()
    pred = {r[list(r)[0]]: r for r in rd(a.pred)}
    if a.task == "clauses":
        g = [r for r in rd(f"{D}/clauses/clauses_benchmark.csv") if a.split == "all" or r["split"] == a.split]
        g = [r for r in g if r["clause_id"] in pred]
        t = [int(r["risk_score"]) for r in g]; p = [int(float(pred[r["clause_id"]]["risk_score"])) for r in g]
        n = len(g)
        print(f"n={n} exact={sum(x == y for x, y in zip(t, p)) / n:.3f} within1={sum(abs(x - y) <= 1 for x, y in zip(t, p)) / n:.3f} spearman={spearman(t, p):.3f}")
        if "deviates_from_norm" in next(iter(pred.values())):
            ty = [r["deviates_from_norm"] == "yes" for r in g]; py = [pred[r["clause_id"]]["deviates_from_norm"] == "yes" for r in g]
            tp = sum(x and y for x, y in zip(ty, py)); fp = sum((not x) and y for x, y in zip(ty, py)); fn = sum(x and (not y) for x, y in zip(ty, py))
            f1 = 2 * tp / (2 * tp + fp + fn) if tp else 0.0
            print(f"deviation acc={sum(x == y for x, y in zip(ty, py)) / n:.3f} f1={f1:.3f}")
    elif a.task == "offers":
        g = [r for r in rd(f"{D}/offers/offers_benchmark.csv") if a.split == "all" or r["split"] == a.split]
        g = [r for r in g if r["offer_id"] in pred]
        y = [int(r["accept"]) for r in g]; p = [float(pred[r["offer_id"]]["p_accept"]) for r in g]; n = len(g)
        print(f"n={n} acc={sum((q >= 0.5) == bool(t) for t, q in zip(y, p)) / n:.3f} auc={auc(y, p):.3f} brier={sum((q - t) ** 2 for t, q in zip(y, p)) / n:.3f}")
        for s in sorted({r["stratum"] for r in g}):
            idx = [i for i, r in enumerate(g) if r["stratum"] == s]
            print(f"  {s}: n={len(idx)} acc={sum((p[i] >= 0.5) == bool(y[i]) for i in idx) / len(idx):.3f}")
    elif a.task == "creative":
        g = [r for r in rd(f"{D}/creative/creative_labels.csv") if a.split == "all" or r["split"] == a.split]
        g = [r for r in g if r["image_id"] in pred]
        keys = {"R1": "R1_logo_ok", "R2": "R2_palette_ok", "R3": "R3_disclosure_ok", "R4": "R4_competitor_ok", "R5": "R5_safe_zone_ok"}
        for k, col in keys.items():
            if k in next(iter(pred.values())):
                print(f"{k} acc={sum(int(pred[r['image_id']][k]) == int(r[col]) for r in g) / len(g):.3f}")
        if "passes_all" in next(iter(pred.values())):
            print(f"pass/fail acc={sum(int(pred[r['image_id']]['passes_all']) == int(r['passes_all']) for r in g) / len(g):.3f}")
        print(f"n={len(g)}")

if __name__ == "__main__":
    main()
