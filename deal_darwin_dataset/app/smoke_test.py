"""Run once: prints the raw answer for each question type so we can see Drex's response shapes."""
import json
from drex_client import ask

state = ("Fee: 90% of the creator's standard rate; usage rights: 6 months; exclusivity: 3 months; "
         "payment: net-60; kill fee: 25%; revisions: 2 rounds. Brand standard: fee 90-110%, usage up to 12 months, net-30.")
qs = {
    "accept": {"type": "noul", "instructions": "Would the brand accept this counter-offer?"},
    "risk": {"type": "choice", "instructions": "How risky are these terms for the creator?",
             "options": ["low", "medium", "high"]},
    "fairness": {"type": "score", "instructions": "How fair is this offer to the creator?",
                 "levels": ["very_unfair", "unfair", "fair", "very_fair"]},
}
try:
    print(json.dumps(ask(state, qs), indent=2))
except RuntimeError as e:
    print("Combined call failed:", e)
    for name, q in qs.items():
        try:
            print(name, json.dumps(ask(state, {name: q})))
        except RuntimeError as e2:
            print(name, "FAILED:", e2)
