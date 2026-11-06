# Live demo script (maps 1:1 to the judges' checklist, section 10)

Before judging: run `.\run.ps1`, open http://localhost:8000, and run each sample once so the OCR cache is warm
(first run ~20 s per case, later runs faster). Keep the browser at full width.

| # | Judges' checklist item | What to do / say | Where |
|---|---|---|---|
| 1 | Upload multiple documents, ingestion | Drag all 4 files of `samples/case_02_visual_tamper` into the drop zone → *Start investigation*. Point at the 10 live stages and the SHA-256 recorded at submission. | progress view |
| 2 | Classification + OCR | *Documents & extraction* → each document shows type + confidence + type scores, and whether text came from the PDF text layer or OCR. Toggle *OCR / text units*. | Documents tab |
| 3 | Structured representation | Field table (raw value, normalised value, confidence, source); click a row → its box pulses on the page. Bank statement → transactions table. "Download JSON". | Documents tab |
| 4 | Suspicious regions highlighted | Salary slip (D04): orange boxes on Net Pay; tick *ELA heat-map*. Findings: *Noise-free patch* and *Typography/alignment irregularity*. | Documents / Findings |
| 5 | Inconsistencies within a document | *Net pay does not equal gross minus deductions*: "components add up, so Net Pay is the figure that does not fit". | Findings |
| 6 | Cross-document conflicts | *Salary credited differs from payslip net pay*, *Declared income exceeds payslip earnings*. Then switch to case 3 → *Cross-document* graph: two names, two DOBs, two ID numbers, two addresses in red. | Findings / Cross-document |
| 7 | Relationships between findings | Open *Corroborated anomaly: net pay* → lists the visual findings AND the contextual findings that hit the same field; click *Related findings* links. Cross-document tab → *Finding relationships*. | Findings |
| 8 | Inspect evidence | Evidence table + crops; click any row to jump the viewer to that document & box. | Findings |
| 9 | Final dossier | *Open dossier* → sections 1–6 + audit trail; print to PDF. | Dossier |
| 10 | Trace findings to original locations | In the dossier/viewer each evidence row shows `page + [x0,y0,x1,y1]` and the annotated page shows the same box with the finding id. | Findings / Dossier |
| 11 | Potential vs confirmed | Explain the three statuses + *basis* (deterministic vs heuristic). Show *Overwritten value: '58,000.00' hidden under '95,000.00'* (deterministic fact) vs *Elevated error level* (heuristic observation). Click *Confirm* / *Dismiss* → reviewer decision appears in dossier and audit trail. | Findings |
| 12 | Safe failure + honest capabilities | Run `misc_failure_handling`: corrupted PDF rejected with reason, unrelated note marked unsupported, case still completes. Open *Capabilities & limits* tab. | sample set |

Extra (Innovation): *Audit trail* tab → hash-chain VALID; explain tamper-evidence. Show `docs/EVALUATION.md`
(17/17, 0 false positives on the genuine case) and say honestly that the data is synthetic.

## 60-second pitch

"OCR tells you *what* a document says. We tell you *whether to believe it*. Our system reads every document, but
then checks it three independent ways: how the file and pixels were made, whether the numbers inside it add up,
and whether it agrees with every other document in the application. When two independent methods point at the
same field, we raise a corroborated anomaly, with the exact pixel box, the reasoning, and a confidence. We never
call fraud; we tell an investigator precisely where to look and why, and we keep a tamper-evident record of
everything we did."

## Likely judge questions

- *Why not just use an LLM?* LLMs hallucinate and can't see compression artefacts or PDF layers; we use deterministic
  checks for facts and the LLM only to narrate them. It also keeps document text away from prompt-injection.
- *How do you avoid false positives?* Basis + status separation, weak signals downgraded to observations,
  corroboration across independent methods, 0 false positives on the genuine case, documented FP sources.
- *What about real documents?* Thresholds need calibration on authorised real samples; the pipeline and evidence
  model stay the same. Swap-in points: a layout model (LayoutLMv3/Donut) for extraction and a trained splice
  detector for localisation.
