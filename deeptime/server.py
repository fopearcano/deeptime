"""A dependency-free HTTP server for the Deep-Time model.

Serves the static web interface and a small JSON API built only on the Python
standard library (no Flask/FastAPI), so the whole project runs with just
``numpy`` installed::

    python -m deeptime.server            # then open http://localhost:8000

Endpoints
---------
GET  /                         the web interface
GET  /api/config               default parameters, UI metadata, model glossary
GET  /api/model                the mathematical specification (markdown)
POST /api/simulate             run one history -> full snapshot (synchronous)
POST /api/montecarlo           start an ensemble job -> {job_id}
GET  /api/montecarlo/<job_id>  poll job progress / collect the result
"""

from __future__ import annotations

import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict
from urllib.parse import urlparse

from .config import Params, PARAM_META, TAG_MEANING
from . import state as S
from .model import Simulation
from .montecarlo import run_ensemble, QUESTIONS
from .serialize import run_snapshot

# --- locate the static web directory ---------------------------------------
_HERE = Path(__file__).resolve().parent
_WEB_CANDIDATES = [_HERE.parent / "web", _HERE / "web"]
WEB_DIR = next((p for p in _WEB_CANDIDATES if p.is_dir()), _WEB_CANDIDATES[0])
_DOCS = _HERE.parent / "docs" / "deep_time_complete_mathematical_model.md"

_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}

# --- in-memory Monte-Carlo job store ---------------------------------------
_JOBS: Dict[str, dict] = {}
_JOBS_LOCK = threading.Lock()
MAX_RUNS = 200
MAX_NODES = 120


def _config_payload() -> dict:
    return {
        "defaults": Params().to_dict(),
        "meta": PARAM_META,
        "tags": TAG_MEANING,
        "var_labels": S.VAR_LABELS,
        "domain_labels": S.DOMAIN_LABELS,
        "field_tiers": [{"threshold": t, "label": lbl} for t, lbl in S.FIELD_TIERS],
        "civ_eras": [
            {"level": lvl, "key": key, "name": en, "name_it": it,
             "K_min": kmin, "Phi_min": pmin, "desc": desc}
            for lvl, key, en, it, kmin, pmin, desc in S.CIV_ERAS
        ],
        "cosmo_eras": [
            {"key": key, "name": name, "start": lo,
             "end": (None if hi == float("inf") else hi), "note": note}
            for key, name, lo, hi, note in S.COSMO_ERAS
        ],
        "universe_age_now": S.UNIVERSE_AGE_NOW,
        "questions": list(QUESTIONS.keys()),
    }


def _clamp_params(raw: dict) -> Params:
    p = Params.from_dict(raw or {})
    p.n_nodes = int(max(3, min(MAX_NODES, p.n_nodes)))
    p.n_civ = int(max(1, min(p.n_nodes, p.n_civ)))
    p.t_max = float(max(5.0, min(400.0, p.t_max)))
    return p


def _start_mc_job(raw: dict) -> str:
    params = _clamp_params(raw)
    n_runs = int(max(2, min(MAX_RUNS, raw.get("n_runs", 40))))
    record_every = int(max(1, raw.get("record_every", 6)))
    job_id = uuid.uuid4().hex[:12]
    with _JOBS_LOCK:
        _JOBS[job_id] = {"status": "running", "done": 0, "total": n_runs,
                         "result": None, "error": None}

    def worker():
        def prog(done, total):
            with _JOBS_LOCK:
                if job_id in _JOBS:
                    _JOBS[job_id]["done"] = done
                    _JOBS[job_id]["total"] = total
        try:
            ens = run_ensemble(params, n_runs=n_runs, record_every=record_every,
                               n_samples=3, workers=0, progress=prog)
            with _JOBS_LOCK:
                _JOBS[job_id]["result"] = ens.to_dict()
                _JOBS[job_id]["status"] = "done"
        except Exception as exc:  # pragma: no cover - defensive
            with _JOBS_LOCK:
                _JOBS[job_id]["status"] = "error"
                _JOBS[job_id]["error"] = repr(exc)

    threading.Thread(target=worker, daemon=True).start()
    return job_id


class Handler(BaseHTTPRequestHandler):
    server_version = "DeepTime/1.0"

    # -- helpers ----------------------------------------------------------
    def _send_json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(self, body: bytes, content_type: str, status=200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}

    def log_message(self, fmt, *args):  # quieter logging
        pass

    # -- routing ----------------------------------------------------------
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/" or path == "":
            return self._serve_static("index.html")
        if path == "/api/config":
            return self._send_json(_config_payload())
        if path == "/api/model":
            try:
                text = _DOCS.read_text(encoding="utf-8")
            except OSError:
                text = "# Specification file not found."
            return self._send_json({"markdown": text})
        if path.startswith("/api/montecarlo/"):
            job_id = path.rsplit("/", 1)[-1]
            return self._serve_job(job_id)
        if path.startswith("/api/"):
            return self._send_json({"error": "unknown endpoint"}, status=404)
        # static asset
        return self._serve_static(path.lstrip("/"))

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/simulate":
            return self._serve_simulate()
        if path == "/api/montecarlo":
            raw = self._read_body()
            job_id = _start_mc_job(raw)
            return self._send_json({"job_id": job_id})
        return self._send_json({"error": "unknown endpoint"}, status=404)

    # -- handlers ---------------------------------------------------------
    def _serve_simulate(self):
        raw = self._read_body()
        params = _clamp_params(raw)
        record_every = int(max(1, raw.get("record_every", 4)))
        try:
            sim = Simulation(params=params)
            sim.run(record_every=record_every)
            snap = run_snapshot(sim)
        except Exception as exc:  # pragma: no cover - defensive
            return self._send_json({"error": repr(exc)}, status=500)
        return self._send_json(snap)

    def _serve_job(self, job_id: str):
        with _JOBS_LOCK:
            job = _JOBS.get(job_id)
            if job is None:
                return self._send_json({"error": "unknown job"}, status=404)
            payload = {"status": job["status"], "done": job["done"], "total": job["total"]}
            if job["status"] == "done":
                payload["result"] = job["result"]
            elif job["status"] == "error":
                payload["error"] = job["error"]
        if payload["status"] in ("done", "error"):
            with _JOBS_LOCK:
                _JOBS.pop(job_id, None)  # one-shot collect
        return self._send_json(payload)

    def _serve_static(self, rel: str):
        if not rel:
            rel = "index.html"
        # prevent path traversal
        target = (WEB_DIR / rel).resolve()
        try:
            target.relative_to(WEB_DIR.resolve())
        except ValueError:
            return self._send_json({"error": "forbidden"}, status=403)
        if not target.is_file():
            return self._send_json({"error": "not found", "path": rel}, status=404)
        ctype = _CONTENT_TYPES.get(target.suffix, "application/octet-stream")
        self._send_bytes(target.read_bytes(), ctype)


def serve(host: str = "0.0.0.0", port: int = 8000) -> None:
    httpd = ThreadingHTTPServer((host, port), Handler)
    shown = "localhost" if host in ("0.0.0.0", "") else host
    print(f"Deep-Time model server running at http://{shown}:{port}")
    print(f"Serving web interface from {WEB_DIR}")
    print("Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        httpd.shutdown()


def main(argv=None) -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Deep-Time model web server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    serve(args.host, args.port)


if __name__ == "__main__":
    main()
