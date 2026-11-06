import sys, json
from pathlib import Path
root = Path(sys.argv[1])
sys.path.insert(0, str(root))
from app.models import Document
from app import ingest, extract

work = Path(sys.argv[2]); work.mkdir(parents=True, exist_ok=True)
for case in sorted((root / "samples").glob("case_*")):
    for f in sorted(case.iterdir()):
        b = f.read_bytes()
        d = Document(doc_id=f"{case.name[:7]}_{f.stem}", filename=f.name, sha256=ingest.sha256_bytes(b), media_type="")
        ingest.load_document(d, f, work)
        if d.media_type == "application/pdf":
            extract.mark_hidden_pdf_text(d)
        extract.classify(d)
        extract.extract_fields(d)
        print(f"\n== {case.name}/{f.name}: {d.doc_type} ({d.doc_type_conf}) missing={d.metadata.get('missing_fields')} dup={len(d.metadata.get('duplicate_labels', []))} hidden={[(h['hidden'], h['visible']) for h in d.metadata.get('hidden_text', [])]}")
        for k, v in d.fields.items():
            print(f"   {k:20s} {str(v.value)[:45]:45s} conf={v.conf} {v.source}")
        for t in d.tables:
            for r in t["rows"]:
                print("   ROW", r["date"], r["description"][:25], r["debit"], r["credit"], r["balance"])
