"""FastAPI server: upload documents, follow progress, explore evidence, record reviewer decisions, get dossier.

Run:  .venv\\Scripts\\python -m uvicorn app.main:app --port 8000
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import dossier, pipeline, store

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"
STATIC = ROOT / "static"
MAX_FILES = 12

app = FastAPI(title="Document Forensics & Contextual Intelligence")
store.init()
_run_lock = threading.Semaphore(2)


def _start(case_id: str):
    def work():
        with _run_lock:
            pipeline.run_case(case_id)
    threading.Thread(target=work, daemon=True).start()


@app.get("/", response_class=HTMLResponse)
def index():
    return (STATIC / "index.html").read_text(encoding="utf-8")


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/api/samples")
def samples():
    out = []
    truth = {}
    gt = SAMPLES / "ground_truth.json"
    if gt.exists():
        truth = json.loads(gt.read_text())
    for d in sorted(p for p in SAMPLES.iterdir() if p.is_dir()) if SAMPLES.exists() else []:
        out.append({"name": d.name, "files": sorted(p.name for p in d.iterdir() if p.is_file()),
                    "description": truth.get(d.name, {}).get("description", "")})
    return out


@app.post("/api/cases")
async def create_case(name: str = Form("Untitled investigation"), files: list[UploadFile] = File(...)):
    if not files:
        raise HTTPException(400, "No files uploaded")
    if len(files) > MAX_FILES:
        raise HTTPException(400, f"At most {MAX_FILES} files per investigation")
    payload = [(f.filename or f"upload_{i}", await f.read()) for i, f in enumerate(files)]
    cid = pipeline.create_case(name[:120], payload)
    _start(cid)
    return {"case_id": cid}


@app.post("/api/cases/from-sample/{sample}")
def case_from_sample(sample: str):
    d = (SAMPLES / sample).resolve()
    if d.parent != SAMPLES.resolve() or not d.is_dir():
        raise HTTPException(404, "Unknown sample set")
    payload = [(p.name, p.read_bytes()) for p in sorted(d.iterdir()) if p.is_file()]
    cid = pipeline.create_case(f"Sample: {sample}", payload)
    _start(cid)
    return {"case_id": cid}


@app.get("/api/cases")
def cases():
    return store.list_cases()


def _results(case_id: str) -> dict | None:
    p = store.CASES / case_id / "results.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


@app.get("/api/cases/{case_id}")
def case(case_id: str):
    c = store.get_case(case_id)
    if not c:
        raise HTTPException(404, "Case not found")
    c["results"] = _results(case_id) if c["status"] == "done" else None
    c["reviews"] = store.reviews(case_id)
    return c


@app.get("/api/cases/{case_id}/files/{kind}/{name}")
def case_file(case_id: str, kind: str, name: str):
    if kind not in ("pages", "evidence"):
        raise HTTPException(404)
    base = (store.CASES / case_id / kind).resolve()
    p = (base / name).resolve()
    if p.parent != base or not p.exists():
        raise HTTPException(404)
    return FileResponse(p)


class Review(BaseModel):
    decision: str
    note: str = ""
    reviewer: str = "analyst"


@app.post("/api/cases/{case_id}/findings/{finding_id}/review")
def review(case_id: str, finding_id: str, r: Review):
    if r.decision not in ("confirmed", "dismissed", "needs_info"):
        raise HTTPException(400, "decision must be confirmed | dismissed | needs_info")
    res = _results(case_id)
    if not res or finding_id not in {f["id"] for f in res["findings"]}:
        raise HTTPException(404, "Finding not found")
    store.set_review(case_id, finding_id, r.decision, r.note[:500], r.reviewer[:60])
    store.audit(case_id, "reviewer_decision", {"finding": finding_id, "decision": r.decision, "note": r.note[:500]},
                actor=r.reviewer[:60] or "analyst")
    return {"ok": True}


@app.get("/api/cases/{case_id}/dossier", response_class=HTMLResponse)
def get_dossier(case_id: str, download: int = 0):
    res = _results(case_id)
    if not res:
        raise HTTPException(404, "Dossier not ready")
    html = dossier.render(res, store.CASES / case_id, store.reviews(case_id), store.audit_entries(case_id),
                          store.verify_chain())
    store.audit(case_id, "dossier_viewed" if not download else "dossier_exported", {})
    headers = {"Content-Disposition": f'attachment; filename="dossier_{case_id}.html"'} if download else {}
    return HTMLResponse(html, headers=headers)


@app.get("/api/cases/{case_id}/dossier.json")
def get_dossier_json(case_id: str):
    res = _results(case_id)
    if not res:
        raise HTTPException(404, "Dossier not ready")
    res["reviews"] = store.reviews(case_id)
    return JSONResponse(res, headers={"Content-Disposition": f'attachment; filename="dossier_{case_id}.json"'})


@app.get("/api/audit")
def audit(case_id: str | None = None):
    return {"chain": store.verify_chain(), "entries": store.audit_entries(case_id)}
