# Limitations, assumptions and known false positives

## Capability status

| Capability | Status |
|---|---|
| Ingestion of PDF / JPEG / PNG / TIFF / WEBP, multi-document cases | implemented |
| Printed OCR with confidence; digital PDF text layer with fonts | implemented |
| Four document schemas (loan application, identity card, salary slip, bank statement) | implemented |
| Key-value + table extraction with bounding boxes; missing / duplicate field detection | implemented |
| PDF forensics (hidden text, overlays, fonts, revisions) | implemented |
| Scan forensics (noise consistency, ELA, text geometry) | implemented |
| Signature presence + copy detection | implemented |
| Contextual & cross-document checks, entity graph, corroboration | implemented |
| Evidence crops, annotated pages, dossier, audit chain, reviewer decisions | implemented |
| LLM narrative summary | implemented, optional (needs `ANTHROPIC_API_KEY`) |
| Handwriting | partial – PP-OCR models target print; handwriting accuracy is low and not evaluated |
| Arbitrary document types | partial – classified `unknown`; forensics and metadata only |
| Multi-page field extraction | partial – fields are searched on all analysed pages, but the dataset is single-page |
| Signature authenticity (forgery vs genuine) | unsupported |
| Multilingual documents | unsupported |
| Learned splice / copy-move localisation | planned |

## Assumptions

- Documents use printed labels similar to the schema aliases ("Net Pay", "Date of Birth"...).
- One document per type per case is used for cross-checks (extra ones are noted in the dossier).
- Dates are day-first (Indian format). Amounts use Indian or Western digit grouping.
- Scans are roughly upright (no deskew step).

## Known false-positive sources

| Check | Can fire on genuine documents when... |
|---|---|
| Noise inconsistency | the scanner applies background whitening / "clean page" filters, or the image is a screenshot of a PDF (then the whole page is noise-free; the check disables itself when page noise is near zero). |
| ELA | the page contains logos, stamps or text of very different contrast; the file was re-saved many times. Reported as observation unless strong. |
| Text geometry | the scan is skewed or warped; OCR boxes include descenders differently. Needs two independent deviations to report. |
| Font inconsistency (PDF) | genuine forms that use a different font for one value (e.g. monospace account numbers). |
| Revision metadata | legitimately signed or form-filled PDFs (reported as observation only). |
| Name / address variation | transliteration variants, abbreviations, old vs new address – reported as inconsistency for human review. |
| ID checksum | an OCR misread of a single digit (explanations flag low OCR confidence). |
| Missing signature | signatures in very light ink or a stamp-only sign-off. |

## Unsupported scenarios (handled safely)

- Corrupted / truncated files → rejected with a reason, case continues, logged.
- Unknown formats (e.g. DOCX, ZIP) → rejected by magic-byte check.
- Unrecognised document type → marked unsupported, no fields, visual checks still run.
- Encrypted PDFs → rejected as unparseable.
- Files > 25 MB, > 12 files per case, PDFs beyond 5 pages (only first 5 analysed, noted).

## Accuracy statement

On the synthetic demonstration dataset the system detects 17/17 planted anomalies with 0 false positives
(`EVALUATION.md`). Thresholds were tuned on this dataset; real-world performance is unknown and requires
calibration on authorised real samples.
