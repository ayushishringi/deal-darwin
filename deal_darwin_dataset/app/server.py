"""Deal Darwin server (Python standard library only).

Run:  python3 app/server.py [port]        then open http://127.0.0.1:8765/
  GET  /                      the guided web app (app/web/)          GET /classic   the earlier demo page
  POST /api/analyze           multipart: file=<pdf or images> | sample=A-D        -> {"job_id"}
  POST /api/run               classic live run (file | sample, persona, brand)    -> {"job_id"}
  GET  /api/events/<job_id>   server-sent events (one JSON object per message; "end" event when done)
  GET  /api/result/<job_id>   final result JSON (202 while running)
"""
import email.parser
import email.policy
import io
import json
import mimetypes
import os
import sys
import tempfile
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PIL import Image

APP = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(APP)
sys.path.insert(0, APP)
import build_demo  # noqa: E402
import pipeline  # noqa: E402
import web_pipeline  # noqa: E402
import evidence  # noqa: E402

WEB = os.path.join(APP, "web")
CLASSIC = os.path.join(APP, "demo", "index.html")
UPLOADS = tempfile.mkdtemp(prefix="dealdarwin-")
MAX_BODY = 30 * 1024 * 1024
JOBS = {}
IMAGES = {}  # uploaded image id -> path


class Job:
    def __init__(self):
        self.events, self.done, self.result = [], False, None
        self.cond = threading.Condition()

    def emit(self, ev):
        with self.cond:
            self.events.append(ev)
            self.cond.notify_all()


def start_job(target):
    """Run target(emit) -> result on a thread; events stream over SSE."""
    job_id, job = uuid.uuid4().hex[:12], Job()
    JOBS[job_id] = job

    def work():
        try:
            job.result = target(job.emit)
        except Exception as e:  # noqa: BLE001
            job.emit({"type": "error", "message": str(e)})
        finally:
            job.emit({"type": "done", "stages": (job.result or {}).get("stages")})
            with job.cond:
                job.done = True
                job.cond.notify_all()
    threading.Thread(target=work, daemon=True).start()
    return job_id


def public(obj):
    return {k: v for k, v in obj.items() if not k.startswith("_")} if isinstance(obj, dict) else obj


def parse_form(handler, body):
    """Returns (fields, files) where files = [(filename, bytes)]."""
    ctype = handler.headers.get("Content-Type", "")
    if ctype.startswith("application/json"):
        return json.loads(body or b"{}"), []
    msg = email.parser.BytesParser(policy=email.policy.HTTP).parsebytes(
        f"Content-Type: {ctype}\r\n\r\n".encode() + body)
    fields, files = {}, []
    for part in msg.iter_parts():
        name = part.get_param("name", header="content-disposition")
        data = part.get_payload(decode=True) or b""
        if part.get_filename():
            if data:
                files.append((part.get_filename(), data))
        elif name:
            fields[name] = data.decode(errors="replace").strip()
    return fields, files


def save_document(files):
    """A PDF is saved as is; one or more images (screenshots, photos) become one PDF for NDI OCR."""
    pdfs = [d for _, d in files if d.startswith(b"%PDF")]
    if pdfs:
        data = pdfs[0]
    else:
        pages = []
        for fname, d in files:
            try:
                pages.append(Image.open(io.BytesIO(d)).convert("RGB"))
            except Exception:  # noqa: BLE001
                raise ValueError(f"{fname}: not a PDF or a readable image")
        if not pages:
            raise ValueError("no file")
        buf = io.BytesIO()
        pages[0].save(buf, "PDF", resolution=150, save_all=True, append_images=pages[1:])
        data = buf.getvalue()
    path = os.path.join(UPLOADS, uuid.uuid4().hex + ".pdf")
    open(path, "wb").write(data)
    return path


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        if "/api/" in self.path:
            sys.stderr.write("  %s\n" % (fmt % args))

    def send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path):
        if not os.path.isfile(path):
            return self.send_json({"error": "not found"}, 404)
        data = open(path, "rb").read()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(path)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def send_static(self, base, rel):
        full = os.path.realpath(os.path.join(base, rel))
        if not full.startswith(os.path.realpath(base) + os.sep):
            return self.send_json({"error": "forbidden"}, 403)
        return self.send_file(full)

    def job(self, p):
        return JOBS.get(p.rstrip("/").rsplit("/", 1)[-1])

    def do_GET(self):
        p = self.path.split("?")[0]
        if p in ("/", "/index.html"):
            return self.send_file(os.path.join(WEB, "index.html"))
        if p.startswith("/web/"):
            return self.send_static(WEB, p[len("/web/"):])
        if p in ("/classic", "/classic/"):
            return self.send_file(CLASSIC)
        if p.startswith("/creative/"):
            return self.send_static(os.path.join(ROOT, "creative"), p[len("/creative/"):])
        if p == "/api/evidence":  # read-only, from files
            return self.send_json(evidence.evidence())
        if p == "/api/meta":
            return self.send_json(meta())
        if p.startswith("/api/image/"):
            path = IMAGES.get(p.rsplit("/", 1)[-1])
            return self.send_file(path) if path else self.send_json({"error": "unknown image"}, 404)
        if p.startswith("/api/result/"):
            job = self.job(p)
            if not job:
                return self.send_json({"error": "unknown job"}, 404)
            return self.send_json(public(job.result) if job.done else {"status": "running"}, 200 if job.done else 202)
        if p.startswith("/api/events/"):
            return self.stream(self.job(p))
        self.send_json({"error": "not found"}, 404)

    def stream(self, job):
        if not job:
            return self.send_json({"error": "unknown job"}, 404)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        i = 0
        try:
            while True:
                with job.cond:
                    while i >= len(job.events) and not job.done:
                        if not job.cond.wait(15):
                            break
                    batch, done = job.events[i:], job.done
                i += len(batch)
                out = "".join(f"data: {json.dumps(ev)}\n\n" for ev in batch) or ": ping\n\n"
                if done:
                    out += "event: end\ndata: {}\n\n"
                self.wfile.write(out.encode())
                self.wfile.flush()
                if done:
                    return
        except (BrokenPipeError, ConnectionResetError):
            return

    def read_form(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            raise ValueError("file too large")
        return parse_form(self, self.rfile.read(n))

    def do_POST(self):
        p = self.path.split("?")[0]
        try:
            fields, files = self.read_form()
        except Exception as e:  # noqa: BLE001
            return self.send_json({"error": f"bad request: {e}"}, 400)
        try:
            handler = getattr(self, "post_" + p.strip("/").replace("/", "_"), None)
            if not handler:
                return self.send_json({"error": "not found"}, 404)
            return handler(fields, files)
        except ValueError as e:
            return self.send_json({"error": str(e)}, 400)
        except Exception as e:  # noqa: BLE001
            return self.send_json({"error": f"server error: {e}"}, 500)

    def post_api_analyze(self, fields, files):
        sample = (fields.get("sample") or "").upper() or None
        if files:
            path, name, sample = save_document(files), files[0][0], None
        elif sample in pipeline.PDFS:
            path, name = None, None
        else:
            raise ValueError("send a PDF, an image, or a sample A-D")
        job_id = start_job(lambda emit: web_pipeline.analyze(emit, pdf=path, sample=sample, name=name))
        self.send_json({"job_id": job_id, "sample": sample})

    def analysis(self, fields):
        job = JOBS.get(fields.get("job_id") or "")
        if not job or not job.done or not (job.result or {}).get("clauses"):
            raise ValueError("Analyze a contract first.")
        return job.result

    def post_api_ask(self, fields, files):
        an = self.analysis(fields)
        opts = fields.get("options") or []
        if isinstance(opts, str):
            opts = [o for o in opts.split(",")]
        try:
            out = web_pipeline.ask_drex(an, fields.get("question"), fields.get("mode") or "auto", opts)
        except ValueError:
            raise
        except Exception as e:  # noqa: BLE001
            return self.send_json({"error": "Drex didn't answer: " + web_pipeline.short(e)}, 502)
        self.send_json(out)

    def post_api_negotiate(self, fields, files):
        an = self.analysis(fields)
        playbook = None
        if files:
            if not files[0][1].startswith(b"%PDF"):
                raise ValueError("The playbook must be a PDF.")
            playbook = save_document(files[:1])
        try:
            rate = float(fields.get("rate")) if fields.get("rate") else None
        except ValueError:
            raise ValueError("Standard rate must be a number.")
        if rate is not None and not (0 < rate < 10_000_000):
            raise ValueError("Standard rate looks off.")
        persona, brand = fields.get("persona") or None, fields.get("brand") or None
        job_id = start_job(lambda emit: web_pipeline.negotiate(emit, an, persona, rate, playbook, brand))
        self.send_json({"job_id": job_id})

    def post_api_image(self, fields, files):
        if not files:
            raise ValueError("No image.")
        try:
            im = Image.open(io.BytesIO(files[0][1]))
            im.verify()
            im = Image.open(io.BytesIO(files[0][1])).convert("RGB")
        except Exception:  # noqa: BLE001
            raise ValueError("That file isn't a readable image.")
        img_id = uuid.uuid4().hex[:12]
        path = os.path.join(UPLOADS, img_id + ".jpg")
        im.save(path, "JPEG", quality=90)
        IMAGES[img_id] = path
        self.send_json({"id": img_id, "url": f"/api/image/{img_id}", "name": files[0][0]})

    def image_path(self, fields):
        if fields.get("concept") in web_pipeline.CONCEPTS:
            return web_pipeline.CONCEPTS[fields["concept"]], fields["concept"]
        if fields.get("image") in IMAGES:
            return IMAGES[fields["image"]], None
        raise ValueError("Unknown image.")

    def post_api_creative_check(self, fields, files):
        path, concept = self.image_path(fields)
        try:
            self.send_json(web_pipeline.check_image(path, concept))
        except RuntimeError as e:
            self.send_json({"error": str(e)}, 502)

    def post_api_creative_ask(self, fields, files):
        path, _ = self.image_path(fields)
        try:
            self.send_json(web_pipeline.ask_image(path, fields.get("question")))
        except ValueError:
            raise
        except Exception as e:  # noqa: BLE001
            self.send_json({"error": "Drex Max didn't answer: " + web_pipeline.short(e)}, 502)

    def post_api_run(self, fields, files):  # classic page
        sample = (fields.get("sample") or "").upper() or None
        path = None
        if files:
            if not files[0][1].startswith(b"%PDF"):
                raise ValueError("not a PDF")
            path, sample = save_document(files[:1]), None
        elif sample not in pipeline.PDFS:
            raise ValueError("send a PDF or sample A-D")
        persona, brand = fields.get("persona") or None, fields.get("brand") or None
        job_id = start_job(lambda emit: pipeline.run(emit, sample=sample, pdf=path, persona=persona, brand=brand))
        self.send_json({"job_id": job_id, "sample": sample})


def meta():
    from common import BRANDS, PERSONAS
    tpl = json.load(open(os.path.join(ROOT, "scripts", "drex_question_templates.json")))["creative_rule"]["rules"]
    truth = pipeline.load_truth()
    return {"personas": list(PERSONAS), "brands": {k: v["name"] for k, v in BRANDS.items()}, "rules": tpl,
            "sample_personas": {k: v["creator_persona"] for k, v in truth.items()},
            "concepts": [{"name": n, "url": "/" + os.path.relpath(p, ROOT)} for n, p in web_pipeline.CONCEPTS.items()],
            "firefly": "https://firefly.adobe.com"}


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    build_demo.main()  # refresh /classic with the latest cache
    print(f"Deal Darwin: http://127.0.0.1:{port}/   classic: /classic   (stage timeout {pipeline.TIMEOUT:.0f}s)", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
