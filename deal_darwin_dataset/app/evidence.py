"""Evidence tab: numbers read or computed from files on disk only (no API calls). Missing inputs -> row omitted."""
import json
import os

APP = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(APP)
CACHE = os.path.join(APP, "cache")
ASPECTS = ["fee", "usage_rights", "exclusivity", "payment_terms", "kill_fee"]
CIDS = "ABCD"


def _load(*parts):
    p = os.path.join(*parts)
    try:
        return json.load(open(p))
    except (OSError, ValueError):
        return None


def extraction():
    summary = _load(CACHE, "eval_summary.json") or {}
    rows = [{**r, "source": "console log"} for r in summary.get("extraction", [])]
    keys = {c: (_load(ROOT, "answer_keys", f"contract_{c}_key.json") or {}).get("fields") for c in CIDS}
    risk = {c: _load(CACHE, f"contract_{c}_risk.json") for c in CIDS}
    if all(keys.values()) and all(risk.values()) and all((risk[c].get("extraction") or {}).get("source") == "ndi" for c in CIDS):
        pairs = [(risk[c]["aspects"][a], keys[c][a]) for c in CIDS for a in ASPECTS]
        if all("ndi_status" in p for p, _ in pairs):
            rows.append({"variant": "NDI only", "status": [sum(p["ndi_status"] == k["status"] for p, k in pairs), len(pairs)],
                         "risk_within_1": None, "source": "computed"})
        scored = [(p, k) for p, k in pairs if k.get("risk") is not None]
        rows.append({"variant": "NDI + Drex (current)", "status": [sum(p["status"] == k["status"] for p, k in pairs), len(pairs)],
                     "risk_within_1": [sum(abs(p["risk"] - k["risk"]) <= 1 for p, k in scored), len(scored)], "source": "computed"})
    return {"rows": rows, "note": summary.get("note")}


def counters():
    rows = []
    for c in CIDS:
        chk = (_load(CACHE, f"contract_{c}_counters_v2.json") or {}).get("check") or {}
        if all(k in chk for k in ("v1_value_recovered", "v2_value_recovered", "max_value_recovered")):
            rows.append({"contract": c, "baseline": chk["v1_value_recovered"], "evolution": chk["v2_value_recovered"],
                         "max": chk["max_value_recovered"], "in_true_top10": chk.get("v2_in_true_top10")})
    return rows


def creative():
    v = _load(CACHE, "creative_validation.json")
    if not v or "correct" not in v:
        return None
    return {"n": v["n"], "split": v.get("split", "dev"), "threshold": v.get("threshold", 0.5), "correct": v["correct"]}


def cost():
    out = []
    ndi = [(c, (r.get("extraction") or {}).get("cost_usd")) for c in CIDS if (r := _load(CACHE, f"contract_{c}_risk.json"))]
    ndi = [(c, x) for c, x in ndi if x is not None]
    if ndi:
        out.append({"label": f"NDI extraction, {len(ndi)} contracts", "value": round(sum(x for _, x in ndi), 4), "unit": "usd",
                    "detail": {c: x for c, x in ndi}})
    calls = [(c, d.get("n_drex_calls")) for c in CIDS if (d := _load(CACHE, f"contract_{c}_counters_v2.json"))]
    calls = [(c, n) for c, n in calls if n]
    if calls:
        out.append({"label": f"Drex calls, counter search ({len(calls)} runs)", "value": sum(n for _, n in calls), "unit": "calls",
                    "detail": {c: n for c, n in calls}})
    return out


def evidence():
    return {"extraction": extraction(), "counters": counters(), "creative": creative(), "cost": cost()}


if __name__ == "__main__":
    print(json.dumps(evidence(), indent=1))
