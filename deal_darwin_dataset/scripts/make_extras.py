"""README data card, Drex question templates, and the evaluation harness."""
import json
from common import path, write_json

TEMPLATES = {
  "note": "Typed questions for Drex (choice / noul = yes-no / score = ordered levels). Fill {placeholders}. Drex returns probabilities; it does not write text.",
  "clause_risk": {"type": "choice", "question": "How risky is this clause for the creator compared with the brand's standard terms?\n\nClause: {clause_text}\nStandard: {norm_reference}",
                  "options": ["1 - standard or favorable", "2 - slightly off", "3 - notable concern", "4 - high risk", "5 - severe, walk-away"]},
  "clause_deviates": {"type": "noul", "question": "Does this clause deviate from the standard terms?\n\nClause: {clause_text}\nStandard: {norm_reference}"},
  "brand_accept": {"type": "noul", "question": "Using the brand playbook below, would the brand accept this counter-offer?\n\nPlaybook: {playbook_text}\nOffer: {offer_text}"},
  "brand_accept_scale": {"type": "score", "question": "How likely is the brand to accept this offer, very unlikely to very likely?\n\nPlaybook: {playbook_text}\nOffer: {offer_text}", "levels": ["very_unlikely","unlikely","likely","very_likely"]},
  "creative_rule": {"type": "noul", "vision": True, "question": "Rule {rule_text}. Does the attached image satisfy this rule?", "rules": {
      "R1": "The Northwind logo is present, fully inside the frame, at least 22% of image width, with clear space equal to its height.",
      "R2": "Only Navy #0B2545, Orange #FF6B1A, Off-white #F6F3EE and Slate #5C6B7A are used for graphics and headline.",
      "R3": "The text #ad is present, at least 2.5% of image height, with contrast at least 4.5:1.",
      "R4": "No competitor name, logo or product is visible.",
      "R5": "Headline and body copy stay above the bottom 15% of the frame."}},
  "field_status": {"type": "choice", "question": "For the term '{field}', does the contract state a single clear value?", "options": ["found", "ambiguous", "not_found"]},
}

README = """# Deal Darwin synthetic dataset

Everything here is synthetic. The brands (Northwind Athletics, Vela Beauty, Kettle & Co), creators and contracts are fictional.
It exists to build and measure Deal Darwin: read a creator contract, score clause risk, predict brand acceptance, rank counter-offers.
Rebuild everything with `bash scripts/build_all.sh` (deterministic, seed 255). Run `python3 scripts/validate.py` to check it.

## What is in each folder
| Folder | Contents | Used for |
|---|---|---|
| brand/ | 3 two-page partnership playbooks (PDF), past_deals_<brand>.csv | Giving Drex the brand's rules; NDI extraction practice |
| clauses/ | clauses_benchmark.csv/.jsonl (112 clauses, 8 types x 14), norm_reference.json | Clause risk (1-5) and deviates-from-norm scoring |
| offers/ | offers_grid_all_brands.csv (24,000 offers), offers_benchmark.csv (600 labeled offers), ground_truth_best_offers.csv | Acceptance scoring; ranking counters by expected value |
| contracts/ | Contract A (fair), B (predatory), C (buried/ambiguous), D (messy scan, plus page JPGs), contracts_index.csv, rate_cards.csv | End-to-end demo and NDI extraction tests |
| answer_keys/ | contract_*_key.json (every field with quote, value, status found/not_found/ambiguous, risk), contract_counter_truth.csv, contract_D_clean_source.pdf | Scoring extraction and counters |
| creative/ | brief + guidelines PDF, 48 ad images (720x900), creative_labels.csv, creative_elements.json | Drex Max brand-guideline checks (rules R1-R5) |
| scripts/ | generators, validate.py, evaluate.py, drex_question_templates.json | Reproduce and score |

## How labels were made (read this before trusting a number)
- Brand acceptance comes from a transparent simulator: a weighted score of how each term compares with the brand's norm, passed through
  a sigmoid, with hard red lines that force rejection. Accept means no red line and p >= 0.5. The playbook PDFs are generated from the same
  parameters, so a reader of the PDF can in principle recover the labels.
- Creator utility uses three personas (rights_protective, cash_first, balanced) with walk-away limits. Expected value = P(accept) x utility.
- Clause risk labels (1 = standard, 5 = severe) are relative to the Northwind playbook and the creator's standard rate. Splits: dev 48, test 64.
- Creative labels are computed from recorded geometry and colors of each drawn element, so they are exact. Thresholds: logo >= 22% of width with
  clear space = logo height, disclosure >= 22.5 px tall with 4.5:1 contrast, copy ends above y = 765 px, palette limited to the four brand colors.
- Contract answer keys come from the same field registry that wrote the PDFs, so quotes and values match the documents.

## Limitations
- Labels measure agreement with the simulated brands. They say nothing about how real brands behave.
- Ads are flat vector-style drawings, not photographs or Firefly output. Real Firefly images are harder.
- Four contracts is a demo set, not a statistical sample. Use the clause (112) and offer (600) benchmarks for numbers.
- This is not legal advice. The contract terms are illustrative.

## Suggested evaluation protocol
1. Clause risk: predict 1-5 on the test split; report exact-match, within-1 and Spearman. Deviation: accuracy and F1.
2. Brand acceptance: predict accept on offers_benchmark test split; report accuracy, AUC and Brier score, and accuracy on the "near_" strata.
3. Extraction: for contracts A-D compare fields to answer_keys, including status. For ambiguous / not_found fields, correct status matters more than a guessed value.
4. Counter ranking: take the system's top-1 counter for a contract and persona, look up its true expected value in offers_grid_all_brands.csv, and report value_recovered vs. the best offer (contract_counter_truth.csv).
5. Creative: accuracy per rule R1-R5 and pass/fail on creative_labels.csv; report the "hard" difficulty subset separately.
`python3 scripts/evaluate.py --task <clauses|offers|creative> --pred preds.csv` scores a prediction file (columns listed in its --help).
"""

EVAL = '''"""Score predictions against the dataset. Usage: python3 evaluate.py --task clauses|offers|creative --pred preds.csv [--split test]
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
'''

def main():
    write_json(path("scripts", "drex_question_templates.json"), TEMPLATES)
    open(path("README.md"), "w", encoding="utf-8").write(README)
    open(path("scripts", "evaluate.py"), "w", encoding="utf-8").write(EVAL)
    print("extras written")

if __name__ == "__main__":
    main()
