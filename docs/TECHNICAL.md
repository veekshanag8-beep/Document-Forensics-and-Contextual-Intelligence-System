# Technical documentation

## Processing pipeline

| # | Stage | Module | What happens |
|---|---|---|---|
| 1 | Document submission | `pipeline.create_case`, `ingest.load_document` | Files stored unmodified under `data/cases/<id>/originals`; SHA-256 recorded and audit-logged. Format detected by magic bytes (not extension). PDFs rendered at 2x; images kept at native resolution (downscaled above 3000 px, noted). |
| 2 | Classification | `extract.classify` | Strong (title) and weak (field label) keyword scores per type. Below 0.45 the document is `unknown` → field extraction skipped, forensics still run. |
| 3 | OCR & extraction | `ingest.ocr_image`, `ingest.pdf_units` | Digital PDF: characters grouped into phrases on large horizontal gaps; each phrase keeps its font and size. Scans: RapidOCR detection + recognition; overlapping fragments on a line are merged and re-recognised as one line (fixes split dates). OCR results cached by file hash. |
| 4 | Structural understanding | `extract.extract_fields`, `_bank_table`, `_structure` | Per-type schema of labels → value types. A label is matched exactly or fuzzily (rapidfuzz ≥ 88); its value is the nearest text to the right on the same row (multi-line for addresses). Transactions table: header columns located, rows grouped by vertical position, split cells merged. Sections: header → key/value block → table → sign-off. Missing and duplicated labels recorded. |
| 5 | Visual forensic analysis | `forensics.py` | See below. |
| 6 | Contextual verification | `context.py` | Verhoeff check digit on ID numbers; PAN / IFSC formats; PAN 5th letter vs surname; DOB plausibility; stated age vs DOB at application date; payslip components → gross, deductions → total, gross − deductions = net (identifies which figure is wrong); bank running balance row by row (single-culprit detection), closing balance, date order, dates inside statement period. |
| 7 | Cross-document correlation | `crossdoc.compare_attributes`, `financial_links`, `signature_links`, `build_graph` | Attributes clustered across documents (exact → fuzzy; addresses compared with PIN codes; employer legal suffixes ignored). Declared income vs payslip gross; payslip net vs salary credit in statement; salary account vs statement account; applicant signature vs ID signature. Entity graph (documents ↔ asserted values). |
| 8 | Anomaly investigation | `crossdoc.correlate` | Findings sharing a (document, field) are linked (union-find → "threads"). Where independent families — visual/file forensics **and** contextual logic — hit the same field, a **corroborated anomaly** is raised with combined confidence 1 − Π(1 − cᵢ). |
| 9 | Evidence generation | `pipeline._evidence` | Crop per evidence box, annotated full pages with finding ids, colours by status. |
| 10 | Investigation dossier | `explain.py`, `dossier.py` | Summary (deterministic template; Claude narrative when `ANTHROPIC_API_KEY` is set). Self-contained HTML (print → PDF) and JSON, with integrity re-check of every original. |

## Visual forensic methods

| Method | Applies to | Principle | Output |
|---|---|---|---|
| Hidden / overwritten text | digital PDF | Two text runs overlapping with different content: the earlier-drawn one is covered. Legitimate generators never do this. | potential manipulation, deterministic |
| Opaque overlay | digital PDF | White filled rectangle drawn over text (`page.get_drawings`). | inconsistency |
| Typography | digital PDF | Font used ≤2× in the document, or value size differs from the value-size mode. | inconsistency |
| Revision metadata | digital PDF | Count of `%%EOF` (incremental saves), creator ≠ producer, modDate ≠ creationDate, structure repaired. | observation |
| Noise-residual consistency | scans | Residual = image − median3(image); std per 16 px background block. Connected blocks with < 35% of the page median noise = digitally painted patch. | inconsistency |
| Error Level Analysis | JPEG scans | Re-save at q=90; mean error inside each body-text box (same background only) vs robust page statistics. Weak alone: reported as an observation unless strong. | observation / inconsistency |
| Text geometry | OCR documents | Value-vs-label vertical offset, value height vs comparable values, left-edge deviation; reported when ≥2 deviate. | inconsistency |
| Signature localisation | all | Ink (dark or blue-dominant) above a "Signature/Signatory" label, horizontal rules removed, dominant cluster kept. | missing signature |
| Signature copy | form vs ID | Normalised ink masks, resized, blurred; correlation ≥ 0.93 ⇒ near-identical copy (natural signatures measured 0.19–0.59). | potential manipulation |

## Finding model

```json
{
  "id": "F-001", "category": "visual|metadata|signature|contextual|cross_document|structural|correlated",
  "check": "overwritten_text", "title": "...", "status": "observation|inconsistency|potential_manipulation",
  "basis": "deterministic|heuristic", "confidence": 0.95, "severity": "low|medium|high",
  "explanation": "why this matters, with the numbers", "recommendation": "what to verify next",
  "fields": ["monthly_income"], "related": ["F-004", "F-007"],
  "evidence": [{"doc_id": "D01", "filename": "...", "page": 0, "bbox": [x0, y0, x1, y1], "field": "...",
                "value": "...", "note": "...", "crop": "F-001_0.png"}]
}
```

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/cases` (multipart: `name`, `files[]`) | create an investigation and start processing |
| POST | `/api/cases/from-sample/{name}` | run a demonstration dataset |
| GET | `/api/cases`, `/api/cases/{id}` | history; status, stage progress, results, reviews |
| GET | `/api/cases/{id}/files/{pages\|evidence}/{name}` | page images, crops, ELA maps |
| POST | `/api/cases/{id}/findings/{fid}/review` | reviewer decision `confirmed / dismissed / needs_info` |
| GET | `/api/cases/{id}/dossier[?download=1]`, `/dossier.json` | investigation dossier |
| GET | `/api/audit[?case_id=]` | audit entries + hash-chain verification |

## Demonstration dataset

`python -m datagen.generate` builds fictional cases (every document is stamped *SYNTHETIC SPECIMEN*):

- `case_01_genuine` – four consistent documents (digital PDFs + a JPEG scan).
- `case_02_visual_tamper` – net pay spliced into a scanned payslip; declared income overwritten in the PDF form
  with a white box + new text and re-saved by an "editor"; applicant signature pasted from the ID card.
- `case_03_contextual` – visually clean documents with name variant, DOB conflict, wrong age, mistyped ID number,
  payslip arithmetic error, salary credit mismatch, broken running balance, different address, unsigned payslip.
- `misc_failure_handling` – corrupted PDF and an unrelated document.

Every planted change is recorded in `samples/ground_truth.json`; `scripts/evaluate.py` scores the system
(see `EVALUATION.md`).

## Standards referenced (no compliance claimed)

- ISO/IEC 27037 – originals preserved unmodified, hashed at intake, integrity re-verified, chain-of-custody style audit log.
- ISO/IEC 27041 / 27042 – each method documented with its principle and limitations; findings separate observation from interpretation; basis and confidence recorded.
- NIST SP 800-86 – collection → examination → analysis → reporting mirrors stages 1 → 5-8 → 10.
- OWASP ML Top 10 – the LLM receives only structured findings (no raw document text) and cannot change statuses, limiting prompt-injection impact from document content; inputs are size- and type-checked.

## Licensing assumptions

Project code: MIT (assumed for the hackathon). Dependencies: PyMuPDF (AGPL-3.0 – acceptable for a prototype; a
commercial deployment needs an Artifex licence or a swap to pypdfium2), RapidOCR & PaddleOCR models (Apache-2.0),
OpenCV (Apache-2.0), FastAPI/Uvicorn (MIT/BSD), rapidfuzz (MIT), Pillow (HPND), NumPy (BSD), anthropic SDK (MIT).
