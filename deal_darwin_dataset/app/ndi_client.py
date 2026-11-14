"""NDI (Nace Document Intelligence) client: upload -> parse -> extract, no dependencies.

extract_terms(pdf_path) returns
  {"source": "ndi" | "fallback", "text": str, "ocr_applied": bool | None,
   "fields": {name: {"status", "value", "quote", "page", "confidence"}},
   "cost_usd": float, "job_ids": [...]}
for the five contract terms plus brand_name and creator_name.
On any NDI error it falls back to pdftotext: source="fallback", fields={} (callers decide).
API: POST /v1/documents/upload-grants, multipart upload, POST /v1/documents/{parse,extract}.
"""
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
import uuid

import drex_client  # noqa: F401  (loads NACE_API_KEY from .env)

BASE = "https://console.nace.ai/v1/documents"
TERMS = {
    "fee": "The creator's fee or payment amount, including any deductions.",
    "usage_rights": "How long and where the brand may use the content (license term, channels, territory).",
    "exclusivity": "Category exclusivity: what the creator may not do and for how long.",
    "payment_terms": "When the fee is paid (e.g. net days, after which event).",
    "kill_fee": "Cancellation or kill fee owed to the creator if the brand cancels.",
    "brand_name": "The brand or company party to the agreement.",
    "creator_name": "The creator or influencer party to the agreement.",
}
OTHER_TERMS = {
    "type": "array",
    "description": ("Other notable terms not covered by the fields above, for example termination, "
                    "liability, indemnity, IP ownership, content approval, morality clause, revisions."),
    "items": {"type": "object", "properties": {
        "name": {"type": "string", "description": "Short name of the term, e.g. 'Termination'."},
        "text": {"type": "string", "description": "What the clause says, in one sentence."}}},
}
INSTRUCTIONS = ("Creator-brand sponsorship contract. Check definitions and schedules too; if a term is "
                "stated in more than one place with different values, or defers to another section, "
                "mark it ambiguous.")


def _key():
    k = os.environ.get("NACE_API_KEY")
    if not k:
        raise RuntimeError("NACE_API_KEY not set")
    return k


def _send(req, timeout=90):
    """Shared polite sender: <=4 in flight, backoff 2/4/8 s with Retry-After, short gateway errors."""
    try:
        return drex_client.send(req, timeout=timeout)
    except drex_client.NaceError as e:
        raise RuntimeError(f"NDI {e}")


def _api(path, body=None, method="POST", wait=None, idem=None):
    url = f"{BASE}/{path}" + (f"?wait_seconds={wait}" if wait else "")
    headers = {"Authorization": f"Bearer {_key()}", "Content-Type": "application/json"}
    if idem:
        headers["Idempotency-Key"] = idem
    data = json.dumps(body).encode() if body is not None else None
    return _send(urllib.request.Request(url, data=data, method=method, headers=headers), timeout=(wait or 0) + 60)


def _wait(job, limit=240):
    t0 = time.time()
    while job["status"] not in ("succeeded", "failed", "cancelled"):
        if time.time() - t0 > limit:
            raise RuntimeError(f"NDI job {job['job_id']} still {job['status']} after {limit}s")
        time.sleep(2)
        job = _api(f"jobs/{job['job_id']}", method="GET")
    if job["status"] != "succeeded":
        raise RuntimeError(f"NDI job {job['job_id']} {job['status']}: {job.get('error')}")
    return job


def upload(pdf_path):
    """Upload a PDF (free); returns a workspace_file source. Same bytes at the same path dedupe."""
    path = "deal-darwin/" + os.path.basename(pdf_path)
    grant = _api("upload-grants", {"path": path, "ttl_seconds": 600})
    boundary = uuid.uuid4().hex
    meta = json.dumps({"path": path, "on_conflict": "new_version"})
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"metadata\"\r\n\r\n{meta}\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{os.path.basename(pdf_path)}\"\r\n"
            f"Content-Type: application/pdf\r\n\r\n").encode() + open(pdf_path, "rb").read() + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(grant["upload_url"], data=body, method="POST", headers={
        "X-Upload-Token": grant["token"], "Content-Type": f"multipart/form-data; boundary={boundary}"})
    f = _wait(_send(req))["result"]["file"]
    return {"type": "workspace_file", "workspace_id": f["workspace_id"], "file_id": f["file_id"]}


def _cost(job):
    return float((job.get("cost") or {}).get("total_usd") or 0)


def _ndi(pdf_path, extras=False):
    src = upload(pdf_path)
    tag = os.path.basename(pdf_path)
    parse = _wait(_api("parse", {"source": src, "output": {"formats": ["markdown"]}}, wait=60))
    doc = parse["result"]["document"]
    props = {k: {"type": "string", "description": d} for k, d in TERMS.items()}
    if extras:
        props["other_terms"] = OTHER_TERMS
    ext = _wait(_api("extract", {
        "source": {"type": "parse_result", "job_id": parse["job_id"]},
        "schema": {"type": "object", "properties": props},
        "instructions": INSTRUCTIONS}, wait=60, idem=f"dd-extract{'x' if extras else ''}-{parse['job_id']}-{tag}"[:200]))
    fields, others = {}, []
    for f in ext["result"]["fields"]:
        cit = dict((f.get("citations") or [{}])[0])
        if cit.get("source_text"):  # table cells can come back as HTML
            cit["source_text"] = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", cit["source_text"])).strip()
        parts = f["path"].strip("/").split("/")
        if parts[0] == "other_terms":
            v = f.get("value")
            if isinstance(v, str):  # array items can come back as JSON text
                try:
                    v = json.loads(v)
                except ValueError:
                    v = {"name": "Other term", "text": v}
            if len(parts) == 2 and isinstance(v, dict) and (v.get("name") or v.get("text")):
                others.append({"name": v.get("name") or "Other term", "text": v.get("text"), "status": f["status"],
                               "quote": cit.get("source_text"), "page": (cit.get("location") or {}).get("page")})
            continue
        fields[parts[0]] = {
            "status": f["status"], "value": f.get("value"), "quote": cit.get("source_text"),
            "page": (cit.get("location") or {}).get("page"), "confidence": f.get("confidence")}
    return {"source": "ndi", "text": doc.get("markdown") or "", "ocr_applied": parse["result"].get("ocr_applied"),
            "fields": fields, "others": others, "cost_usd": round(_cost(parse) + _cost(ext), 4),
            "reused": all(ln.get("execution") == "reused" for j in (parse, ext) for ln in (j.get("cost") or {}).get("lines", [])),
            "job_ids": [parse["job_id"], ext["job_id"]]}


def extract_terms(pdf_path, fallback_pdf=None, extras=False):
    try:
        return _ndi(pdf_path, extras)
    except Exception as e:  # noqa: BLE001
        print(f"  NDI failed ({e}); falling back to pdftotext")
        text = subprocess.run(["pdftotext", "-layout", fallback_pdf or pdf_path, "-"],
                              check=True, capture_output=True, text=True).stdout
        return {"source": "fallback", "text": text, "ocr_applied": None, "fields": {}, "others": [],
                "cost_usd": 0.0, "job_ids": [], "error": str(e)}


if __name__ == "__main__":
    import sys
    r = extract_terms(sys.argv[1])
    print(r["source"], r.get("ocr_applied"), r["cost_usd"], len(r["text"]), "chars")
    for k, f in r["fields"].items():
        print(f"  {k:<14} {f['status']:<10} p{f['page']}  {str(f['value'])[:70]}")
