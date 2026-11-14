#!/usr/bin/env bash
# Rebuilds every generated file in the dataset from scratch. Deterministic (seed 255).
set -euo pipefail
cd "$(dirname "$0")"
python3 make_clauses.py
python3 make_offers.py
python3 make_brand_pdfs.py
python3 make_contracts.py
python3 make_creative.py
python3 make_extras.py
python3 validate.py
