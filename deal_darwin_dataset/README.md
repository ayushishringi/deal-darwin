# Deal Darwin synthetic dataset

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
