# Deal Darwin

Know what you're signing. Negotiate what you're worth.

Deal Darwin helps creators review brand sponsorship contracts:

- **Read**: NDI (Nace Document Intelligence) parses the contract, OCR included, and extracts fee, usage rights, exclusivity, payment terms, kill fee and other notable terms, each with its quote and page. If NDI misses a standard term, a keyword search over the full text is checked by Drex.
- **Rate**: Drex rates the risk of every term (1-5) and flags vague or conflicting wording.
- **Counter**: an evolutionary search proposes counter-offers. Drex judges each one ("would the brand accept this?") against the brand playbook, and offers are ranked by chance of acceptance times value to the creator.
- **Create**: Adobe Firefly campaign concepts are checked against the brand's creative rules by Drex Max (vision).

## Run it

```bash
cp .env.example .env          # then set NACE_API_KEY in .env
pip install -r requirements.txt
python3 deal_darwin_dataset/app/server.py
```

Open http://127.0.0.1:8765. The earlier demo page is at `/classic`.

Requires Python 3.10+ and `pdftotext` (Poppler: `brew install poppler` or `apt install poppler-utils`). The server uses only the Python standard library plus Pillow.

## Tools used

- NDI: parse and extract only
- Drex (risk, acceptance, Q&A) and Drex Max (image rule checks)
- Intern
- Adobe Firefly (image generation, done in Firefly)

## Honest limits

- Brands, contracts and labels are synthetic; the test sets are small. This is a pilot, not a benchmark.
- Counter-offer "value recovered" is measured against a simulated brand from the dataset.
- The four Firefly concepts were generated in Firefly beforehand; the app scores them, it does not generate images.
- Drex returns probabilities, not explanations.

## Layout

- `deal_darwin_dataset/app/`: server, pipelines, cache, web app (`app/web/`)
- `deal_darwin_dataset/contracts/`, `brand/`, `creative/`, `answer_keys/`: sample contracts, playbooks, images and labels
- `deal_darwin_dataset/scripts/`: dataset generation and evaluation
