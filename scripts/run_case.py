"""Run an investigation from the command line.

    python scripts/run_case.py samples/case_02_visual_tamper
"""
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from app import pipeline, store  # noqa: E402

folder = Path(sys.argv[1])
files = [(p.name, p.read_bytes()) for p in sorted(folder.iterdir()) if p.is_file()]
cid = pipeline.create_case(folder.name, files, actor="cli")
pipeline.run_case(cid)
case = store.get_case(cid)
print("case", cid, case["status"], case["error"] or "")
res = json.loads((store.CASES / cid / "results.json").read_text(encoding="utf-8"))
for d in res["documents"]:
    print(f"  {d['doc_id']} {d['filename']:24s} {d['doc_type']:16s} {d['status']:16s} {'; '.join(d['errors'])[:80]}")
print("  stats:", res["stats"])
for f in res["findings"]:
    print(f"  {f['id']} [{f['status'][:6]}|{f['severity'][:3]}|{f['confidence']:.2f}] {f['title'][:85]}  rel={f['related'][:4]}")
print("  summary:", res["summary"]["text"][:600])
