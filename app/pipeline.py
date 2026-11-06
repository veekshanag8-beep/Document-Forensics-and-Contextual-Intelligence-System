"""End-to-end investigation pipeline:

Submission -> Classification -> OCR & Extraction -> Structure -> Visual Forensics -> Contextual Verification ->
Cross-Document Correlation -> Anomaly Investigation -> Evidence Generation -> Investigation Dossier
"""
from __future__ import annotations

import json
import time
import traceback
from dataclasses import asdict
from pathlib import Path

from PIL import Image, ImageDraw

from . import context, crossdoc, explain, extract, forensics, ingest, store
from .models import (INCONSISTENCY, OBSERVATION, POTENTIAL_MANIPULATION, Document, Finding, IdGen)

STAGES = ["Document submission", "Document classification", "OCR & information extraction",
          "Structural understanding", "Visual forensic analysis", "Contextual verification",
          "Cross-document correlation", "Anomaly investigation", "Evidence generation", "Investigation dossier"]

STATUS_RANK = {POTENTIAL_MANIPULATION: 0, INCONSISTENCY: 1, OBSERVATION: 2}
SEV_RANK = {"high": 0, "medium": 1, "low": 2}
STATUS_COLOR = {POTENTIAL_MANIPULATION: (220, 38, 38), INCONSISTENCY: (234, 140, 0), OBSERVATION: (37, 99, 235)}

CAPABILITIES = [
    ("Document ingestion (PDF, JPEG, PNG, TIFF, WEBP), multi-document cases", "implemented"),
    ("SHA-256 hashing of originals and integrity re-verification", "implemented"),
    ("Document classification (application form, identity card, salary slip, bank statement)", "implemented"),
    ("Printed-text OCR with per-line confidence (RapidOCR / PaddleOCR models)", "implemented"),
    ("Digital-PDF text layer extraction with font metadata", "implemented"),
    ("Key-value field extraction with source bounding boxes", "implemented"),
    ("Table extraction (bank transactions)", "implemented"),
    ("Layout structure (header / fields / table / sign-off), missing & duplicate fields", "implemented"),
    ("Overwritten / hidden PDF text, opaque overlays, font & size anomalies, revision metadata", "implemented"),
    ("Scan forensics: noise-consistency, error level analysis, baseline/height/alignment geometry", "implemented"),
    ("Signature presence detection and copy-paste (near-identical) detection", "implemented"),
    ("Arithmetic, checksum (Verhoeff), format, age/DOB and date-order checks", "implemented"),
    ("Cross-document entity matching (name, DOB, ID, PAN, address, employer, income, salary credit)", "implemented"),
    ("Entity relationship graph and correlation of findings into corroborated anomalies", "implemented"),
    ("Evidence crops, annotated pages, traceability to page coordinates", "implemented"),
    ("Investigation dossier (HTML / print-to-PDF / JSON), reviewer decisions, hash-chained audit log",
     "implemented"),
    ("LLM-written investigation narrative (Claude)", "implemented (optional, needs API key)"),
    ("Handwritten text recognition", "partial - OCR models are tuned for print; handwriting is unreliable"),
    ("Generic document types beyond the four schemas", "partial - classified as 'unknown'; visual forensics "
                                                       "and metadata checks still run, no field extraction"),
    ("Signature authenticity verification (genuine vs. skilled forgery)", "unsupported - only presence and "
                                                                          "copy detection"),
    ("Multilingual documents", "unsupported (English only)"),
    ("Deep-learning manipulation localisation (e.g. trained splice detectors)", "planned"),
]

LIMITATIONS = [
    "OCR output is treated as unverified input; low-confidence reads are flagged in explanations.",
    "Visual forensics are heuristic: ELA and noise analysis can be affected by re-scanning, heavy compression, "
    "photos of screens, and image resizing. A clean result does not prove authenticity.",
    "Signature analysis detects absence and near-identical copies only; it cannot authenticate a signature.",
    "Field extraction relies on printed labels; documents with unusual layouts may yield missing fields.",
    "Only the first 5 pages of a PDF are analysed.",
    "Thresholds were calibrated on the synthetic demonstration dataset; real-world documents need recalibration.",
    "No finding is a fraud determination. Human review is required before any consequential decision.",
]


def create_case(name: str, files: list[tuple[str, bytes]], actor: str = "analyst") -> str:
    """Store submitted files (originals are never modified) and register the case. Returns case id."""
    import re
    import uuid
    store.init()
    case_id = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    cdir = store.CASES / case_id
    (cdir / "originals").mkdir(parents=True)
    store.create_case(case_id, name, STAGES)
    seen = set()
    for i, (fname, data) in enumerate(files):
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", Path(fname).name)[:120] or f"file_{i}"
        while safe in seen:
            safe = f"{i}_{safe}"
        seen.add(safe)
        (cdir / "originals" / safe).write_bytes(data)
        doc_id = f"D{i + 1:02d}"
        sha = ingest.sha256_bytes(data)
        store.add_document(case_id, doc_id, safe, sha, len(data))
        store.audit(case_id, "document_submitted", {"doc_id": doc_id, "filename": safe, "sha256": sha,
                                                    "bytes": len(data)}, actor=actor)
    store.audit(case_id, "case_created", {"name": name, "documents": len(files)}, actor=actor)
    return case_id


def _stage(case_id, stages, i, status, progress=None):
    stages[i]["status"] = status
    if status == "running":
        stages[i]["started"] = time.time()
    if status in ("done", "failed", "skipped") and "started" in stages[i]:
        stages[i]["secs"] = round(time.time() - stages[i]["started"], 2)
    kw = {"stages": stages, "stage": STAGES[i]}
    if progress is not None:
        kw["progress"] = progress
    store.update_case(case_id, **kw)


def run_case(case_id: str) -> None:
    case = store.get_case(case_id)
    cdir = store.CASES / case_id
    stages = case["stages"]
    store.update_case(case_id, status="running")
    store.audit(case_id, "investigation_started", {"documents": len(case["documents"])})
    try:
        _run(case_id, case, cdir, stages)
        store.update_case(case_id, status="done", stage="complete", progress=1.0)
        store.audit(case_id, "investigation_completed", {})
    except Exception as e:
        store.update_case(case_id, status="failed", error=f"{type(e).__name__}: {e}")
        store.audit(case_id, "investigation_failed", {"error": str(e), "trace": traceback.format_exc()[-800:]})


def _run(case_id, case, cdir: Path, stages):
    t0 = time.time()
    docs: list[Document] = []
    n = len(case["documents"])
    # 1. submission / ingestion
    _stage(case_id, stages, 0, "running", 0.02)
    for i, row in enumerate(case["documents"]):
        d = Document(doc_id=row["doc_id"], filename=row["filename"], sha256=row["sha256"], media_type="")
        try:
            ingest.load_document(d, cdir / "originals" / row["filename"], cdir)
            if d.media_type == "application/pdf":
                extract.mark_hidden_pdf_text(d)
            d.status = "ingested"
            store.audit(case_id, "document_ingested", {"doc_id": d.doc_id, "media_type": d.media_type,
                                                       "pages": len(d.pages), "text_units": len(d.units)})
        except Exception as e:
            d.status = "failed"
            d.errors.append(str(e))
            store.audit(case_id, "document_rejected", {"doc_id": d.doc_id, "reason": str(e)})
        docs.append(d)
        store.update_case(case_id, progress=0.02 + 0.35 * (i + 1) / n)
    _stage(case_id, stages, 0, "done")
    ok = [d for d in docs if d.status != "failed"]

    # 2. classification
    _stage(case_id, stages, 1, "running", 0.4)
    for d in ok:
        extract.classify(d)
        if d.doc_type == "unknown":
            d.status = "unsupported_type"
            d.errors.append("Document type not recognised; field extraction and contextual checks skipped. "
                            "Visual forensics and metadata checks were still applied.")
        store.audit(case_id, "document_classified", {"doc_id": d.doc_id, "type": d.doc_type,
                                                     "confidence": d.doc_type_conf})
    _stage(case_id, stages, 1, "done")

    # 3-4. extraction + structure
    _stage(case_id, stages, 2, "running", 0.45)
    for d in ok:
        if d.doc_type != "unknown":
            try:
                extract.extract_fields(d)
            except Exception as e:
                d.errors.append(f"Field extraction failed: {e}")
    _stage(case_id, stages, 2, "done")
    _stage(case_id, stages, 3, "running", 0.5)
    _stage(case_id, stages, 3, "done")

    findings: list[Finding] = []
    # 5. visual forensics
    _stage(case_id, stages, 4, "running", 0.55)
    for d in ok:
        try:
            findings += forensics.analyse(d, cdir)
        except Exception as e:
            d.errors.append(f"Visual forensic analysis failed: {e}")
    _stage(case_id, stages, 4, "done")

    # 6. contextual
    _stage(case_id, stages, 5, "running", 0.7)
    for d in ok:
        try:
            findings += context.analyse(d)
        except Exception as e:
            d.errors.append(f"Contextual checks failed: {e}")
        if d.status == "ingested":
            d.status = "analysed"
    _stage(case_id, stages, 5, "done")

    # 7. cross-document
    _stage(case_id, stages, 6, "running", 0.78)
    known = [d for d in ok if d.doc_type != "unknown"]
    comparisons = []
    for fn in (crossdoc.compare_attributes, crossdoc.financial_links, crossdoc.signature_links):
        try:
            fs, cs = fn(known)
            findings += fs
            comparisons += cs
        except Exception as e:
            store.audit(case_id, "cross_document_check_failed", {"check": fn.__name__, "error": str(e)})
    graph = crossdoc.build_graph(known, comparisons)
    dup = {}
    for d in known:
        dup.setdefault(d.doc_type, []).append(d.filename)
    for t, files in dup.items():
        if len(files) > 1:
            known_note = f"Multiple documents of type {t} ({', '.join(files)}); only the first is used for " \
                         f"cross-document checks of that type."
            for d in known:
                if d.doc_type == t and d.filename != files[0]:
                    d.errors.append(known_note)
    _stage(case_id, stages, 6, "done")

    # 8. anomaly investigation: ids, correlation, ordering
    _stage(case_id, stages, 7, "running", 0.85)
    findings.sort(key=lambda f: (STATUS_RANK[f.status], SEV_RANK.get(f.severity, 3), -f.confidence))
    gen = IdGen("F")
    for f in findings:
        f.id = gen()
    corroborated, threads = crossdoc.correlate(findings, docs)
    for f in corroborated:
        f.id = gen()
    findings = corroborated + findings
    _stage(case_id, stages, 7, "done")

    # 9. evidence generation
    _stage(case_id, stages, 8, "running", 0.9)
    _evidence(docs, findings, cdir)
    _stage(case_id, stages, 8, "done")

    # 10. dossier
    _stage(case_id, stages, 9, "running", 0.95)
    summary = explain.summarise(docs, findings)
    integrity = []
    for d in docs:
        p = cdir / "originals" / d.filename
        h = ingest.sha256_bytes(p.read_bytes()) if p.exists() else None
        integrity.append({"doc_id": d.doc_id, "filename": d.filename, "sha256_at_intake": d.sha256,
                          "sha256_now": h, "unchanged": h == d.sha256})
    result = {
        "case": {"id": case_id, "name": case["name"], "created": case["created"]},
        "documents": [_doc_json(d) for d in docs],
        "findings": [asdict(f) for f in findings],
        "comparisons": comparisons,
        "graph": graph,
        "threads": threads,
        "summary": summary,
        "integrity": integrity,
        "stats": {
            "documents": len(docs), "failed": sum(d.status == "failed" for d in docs),
            "findings": len(findings),
            "by_status": {s: sum(f.status == s for f in findings) for s in STATUS_RANK},
            "processing_seconds": round(time.time() - t0, 1),
        },
        "capabilities": [{"capability": c, "status": s} for c, s in CAPABILITIES],
        "limitations": LIMITATIONS,
        "stages": [{k: v for k, v in s.items() if k != "started"} for s in stages],
    }
    (cdir / "results.json").write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")
    store.audit(case_id, "findings_recorded", {
        "count": len(findings), "by_status": result["stats"]["by_status"],
        "findings": [{"id": f.id, "check": f.check, "status": f.status,
                      "docs": sorted({e["doc_id"] for e in f.evidence})} for f in findings]})
    store.audit(case_id, "dossier_generated", {"summary_generator": summary["generator"],
                                               "integrity_ok": all(i["unchanged"] for i in integrity)})
    _stage(case_id, stages, 9, "done")


def _doc_json(d: Document) -> dict:
    j = asdict(d)
    j["units"] = [u for u in j["units"]]
    j["doc_type_label"] = extract.DOC_TYPES.get(d.doc_type, {}).get("label", "Unknown / unsupported")
    return j


def _evidence(docs: list[Document], findings: list[Finding], cdir: Path):
    """Crop every evidence region and draw annotated pages (finding ids on the page)."""
    ev_dir = cdir / "evidence"
    ev_dir.mkdir(exist_ok=True)
    by_id = {d.doc_id: d for d in docs}
    marks: dict[tuple, list] = {}
    for f in findings:
        for k, e in enumerate(f.evidence):
            d = by_id.get(e["doc_id"])
            if not d or not e.get("bbox") or not d.pages:
                continue
            page = d.pages[min(e.get("page", 0), len(d.pages) - 1)]
            img = Image.open(cdir / "pages" / page["image"]).convert("RGB")
            x0, y0, x1, y1 = e["bbox"]
            pad = 14
            box = (max(0, int(x0 - pad)), max(0, int(y0 - pad)), min(img.width, int(x1 + pad)),
                   min(img.height, int(y1 + pad)))
            if box[2] - box[0] < 4 or box[3] - box[1] < 4:
                continue
            crop = img.crop(box)
            dr = ImageDraw.Draw(crop)
            dr.rectangle([x0 - box[0], y0 - box[1], x1 - box[0], y1 - box[1]], outline=STATUS_COLOR[f.status],
                         width=2)
            name = f"{f.id}_{k}.png"
            crop.save(ev_dir / name)
            e["crop"] = name
            if f.category != "correlated":
                marks.setdefault((d.doc_id, e.get("page", 0)), []).append((f, e["bbox"]))
    for d in docs:
        for p in d.pages:
            img = Image.open(cdir / "pages" / p["image"]).convert("RGB")
            dr = ImageDraw.Draw(img)
            for f, b in marks.get((d.doc_id, p["index"]), []):
                c = STATUS_COLOR[f.status]
                dr.rectangle(b, outline=c, width=3)
                dr.rectangle([b[0], b[1] - 18, b[0] + 52, b[1]], fill=c)
                dr.text((b[0] + 3, b[1] - 16), f.id, fill=(255, 255, 255))
            name = f"annotated_{d.doc_id}_p{p['index']}.jpg"
            img.save(ev_dir / name, quality=80)
            p["annotated"] = name
