"""Minimal Drex client (no dependencies). Reads NACE_API_KEY from the environment or a .env file.
Set DREX_MOCK=1 to skip the API (returns None answers), useful for building the UI offline."""
import email.utils, json, os, threading, time, urllib.request, urllib.error

URL = "https://console.nace.ai/v1/systemone"
MODEL = os.environ.get("DREX_MODEL", "drex-max-v1.1")


def _load_env():
    for p in (".env", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")):
        if os.path.exists(p):
            for line in open(p):
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()

# ---- polite API use (shared venue IP): every Nace call goes through send() ----
MAX_PARALLEL = 4                   # concurrent Nace calls per process, across all threads and jobs
BACKOFF = (2, 4, 8)                # seconds before retry 1, 2, 3
_SLOTS = threading.BoundedSemaphore(MAX_PARALLEL)


class NaceError(RuntimeError):
    pass


def _checkpoint(body):
    return "Vercel Security Checkpoint" in body or body.lstrip()[:15].lower().startswith(("<!doctype", "<html"))


def _retry_after(e, attempt):
    """Seconds to wait: the Retry-After header (seconds or HTTP date, capped at 120) or the backoff step."""
    ra = e.headers.get("Retry-After") if e.headers else None
    if ra:
        try:
            return min(120.0, max(1.0, float(ra)))
        except ValueError:
            d = email.utils.parsedate_to_datetime(ra)
            if d:
                return min(120.0, max(1.0, d.timestamp() - time.time()))
    return BACKOFF[attempt]


def send(req, timeout=60):
    """urlopen + JSON with at most MAX_PARALLEL calls in flight. Retries up to 3 times (2s, 4s, 8s, or Retry-After)
    on 429, 5xx and the 403 gateway checkpoint; never retries in a tight loop. Raises NaceError with a short message."""
    for attempt in range(len(BACKOFF) + 1):
        try:
            with _SLOTS:  # the slot is released before any sleep
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    return json.loads(r.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            blocked = e.code == 403 and _checkpoint(body)
            if (blocked or e.code == 429 or e.code >= 500) and attempt < len(BACKOFF):
                time.sleep(_retry_after(e, attempt))
                continue
            if blocked:
                raise NaceError("HTTP 403: blocked by the API gateway (Vercel security checkpoint); back off and retry later")
            raise NaceError(f"HTTP {e.code}: {body[:300]}")
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < len(BACKOFF):
                time.sleep(BACKOFF[attempt])
                continue
            raise NaceError(f"network error: {e}")


def ask(state, questions, model=None, retries=2):
    """questions: {name: {"type": "noul"|"choice"|"score", "instructions": "...", ...}}
    Returns the raw 'answers' dict from Drex."""
    key = os.environ.get("NACE_API_KEY")
    if os.environ.get("DREX_MOCK") == "1" or not key:
        raise RuntimeError("DREX_MOCK=1 or no NACE_API_KEY set")
    body = json.dumps({"model": model or MODEL, "state": state, "questions": questions}).encode()
    req = urllib.request.Request(URL, data=body, method="POST", headers={
        "Authorization": f"Bearer {key}", "X-Nace-Client": "nace-agent-prompt/1", "Content-Type": "application/json"})
    try:
        return send(req, timeout=60)["answers"]
    except NaceError as e:
        raise NaceError(f"Drex {e}")


def p_yes(state, instructions, model=None):
    """Probability of 'yes' for one yes/no (noul) question."""
    return ask(state, {"q": {"type": "noul", "instructions": instructions}}, model)["q"]["noul"]
