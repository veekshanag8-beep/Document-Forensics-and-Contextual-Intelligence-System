"""Score the system against samples/ground_truth.json and write docs/EVALUATION.md.

    python scripts/evaluate.py

A planted anomaly counts as detected when a non-observation finding of a matching check family points at the
same document and field. Any other non-observation finding is a false positive. Corroborated (correlated)
findings are summaries of other findings, so they are neither counted as hits nor as false positives.
"""
import json
import sys
import time
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from app import pipeline, store  # noqa: E402

FAMILIES = {
    "visual_tamper": {"noise_inconsistency", "ela_outlier", "layout_geometry"},
    "arithmetic": {"slip_net_arithmetic", "slip_gross_sum", "slip_deduction_sum"},
    "cross_mismatch": {"cross_person_name", "cross_date_of_birth", "cross_national_id", "cross_pan", "cross_address",
                       "cross_employer", "income_vs_payslip", "salary_credit_mismatch"},
    "overlay_hidden_text": {"overwritten_text", "opaque_overlay"},
    "font_inconsistency": {"font_inconsistency"},
    "signature_copy": {"signature_copy"},
    "age_dob": {"age_dob_mismatch"},
    "checksum": {"id_checksum", "id_format"},
    "running_balance": {"running_balance", "closing_balance"},
    "missing_signature": {"missing_signature", "missing_signature_block"},
}


def matches(exp, f):
    if f["check"] not in FAMILIES[exp["kind"]]:
        return False
    hit_doc = any(e["filename"] == exp["doc"] and (exp["field"] is None or exp["field"] in (e.get("field") or "")
                                                   or exp["field"] in f["fields"]) for e in f["evidence"])
    if not hit_doc:
        return False
    if exp.get("other_doc"):
        return any(e["filename"] == exp["other_doc"] for e in f["evidence"])
    return True


def main():
    truth = json.loads((root / "samples" / "ground_truth.json").read_text())
    rows, total = [], {"tp": 0, "fn": 0, "fp": 0, "expected": 0}
    details = []
    for case, spec in truth.items():
        folder = root / "samples" / case
        files = [(p.name, p.read_bytes()) for p in sorted(folder.iterdir()) if p.is_file()]
        t = time.time()
        cid = pipeline.create_case(f"Evaluation: {case}", files, actor="evaluator")
        pipeline.run_case(cid)
        secs = time.time() - t
        res = json.loads((store.CASES / cid / "results.json").read_text(encoding="utf-8"))
        fs = [f for f in res["findings"] if f["status"] != "observation" and f["category"] != "correlated"]
        used = set()
        tp = 0
        for exp in spec["expected"]:
            m = [f for f in fs if matches(exp, f)]
            ok = bool(m)
            tp += ok
            used.update(f["id"] for f in m)
            details.append((case, exp, [f["id"] + " " + f["check"] for f in m]))
        fp = [f for f in fs if f["id"] not in used]
        n = len(spec["expected"])
        rows.append((case, n, tp, n - tp, len(fp), len(res["findings"]), round(secs, 1),
                     sum(d["status"] == "failed" for d in res["documents"]), [f["title"] for f in fp]))
        total["tp"] += tp
        total["fn"] += n - tp
        total["fp"] += len(fp)
        total["expected"] += n
    recall = total["tp"] / total["expected"] if total["expected"] else 1
    # precision: findings that explain a planted anomaly vs. all non-observation findings
    precision_den = total["tp"] + total["fp"]
    precision = total["tp"] / precision_den if precision_den else 1

    md = ["# Evaluation on the demonstration dataset", "",
          f"Generated {time.strftime('%Y-%m-%d %H:%M')} by `scripts/evaluate.py` (full pipeline, fresh run).", "",
          "| Case | Planted anomalies | Detected | Missed | False positives | Total findings | Seconds | Rejected files |",
          "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} | {r[6]} | {r[7]} |")
    md += ["", f"**Recall (planted anomalies detected): {total['tp']}/{total['expected']} = {recall:.0%}**  ",
           f"**Precision (non-observation findings that correspond to a planted anomaly): {precision:.0%}** "
           f"({total['fp']} false positives)", "",
           "Observations (e.g. PDF revision metadata) and corroborated summaries are excluded from both counts.",
           "", "## Per-anomaly detail", "", "| Case | Document | Kind | Field | Detected by |", "|---|---|---|---|---|"]
    for case, exp, hits in details:
        md.append(f"| {case} | {exp['doc']} | {exp['kind']} | {exp['field'] or ''} | "
                  f"{', '.join(hits) if hits else '**MISSED**'} |")
    if any(r[8] for r in rows):
        md += ["", "## False positives", ""] + [f"- {r[0]}: {t}" for r in rows for t in r[8]]
    md += ["", "## Caveat", "",
           "The dataset is synthetic and small (3 cases, 12 documents, 17 planted anomalies + 2 robustness files). "
           "Thresholds were tuned on it, so these numbers demonstrate that each capability works end-to-end; they "
           "are not an estimate of real-world accuracy."]
    out = root / "docs" / "EVALUATION.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md[:12]))


if __name__ == "__main__":
    main()
