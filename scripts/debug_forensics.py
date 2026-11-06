"""Developer helper: run ingestion + extraction + visual forensics on every sample and print findings."""
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from app import ingest, extract, forensics  # noqa: E402
from app.models import Document  # noqa: E402

work = root / "data" / "_test"
work.mkdir(parents=True, exist_ok=True)
docs = {}
for case in sorted((root / "samples").glob("case_*")):
    for f in sorted(case.iterdir()):
        b = f.read_bytes()
        d = Document(doc_id=f"{case.name[:7]}_{f.stem}", filename=f.name, sha256=ingest.sha256_bytes(b),
                     media_type="")
        ingest.load_document(d, f, work)
        if d.media_type == "application/pdf":
            extract.mark_hidden_pdf_text(d)
        extract.classify(d)
        extract.extract_fields(d)
        fs = forensics.analyse(d, work)
        docs[d.doc_id] = d
        print(f"\n== {case.name}/{f.name}  noise={d.metadata.get('noise_level')} sig={d.signature and d.signature.get('present')} ink={d.signature and d.signature.get('ink_pixels')}")
        for x in fs:
            print(f"   [{x.status[:6]}] {x.check:22s} {x.title[:70]}  conf={x.confidence} fields={x.fields}")
print("\nSignature similarity (form vs id card):")
for c in ("case_01", "case_02", "case_03"):
    print(" ", c, forensics.signature_similarity(f"{c}_application_form", f"{c}_identity_card"))
print("  cross-person case_01 vs case_03:", forensics.signature_similarity("case_01_application_form", "case_03_identity_card"))
