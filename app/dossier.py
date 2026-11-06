"""Investigation dossier: a self-contained HTML report (images embedded) with the sections required in 7.1-7.6.
Print it from the browser to get a PDF."""
from __future__ import annotations

import base64
import html
import io
from pathlib import Path

from PIL import Image

STATUS_LABEL = {"potential_manipulation": "Potential manipulation", "inconsistency": "Inconsistency",
                "observation": "Observation"}
STATUS_CSS = {"potential_manipulation": "pm", "inconsistency": "inc", "observation": "obs"}
DECISION = {"confirmed": "Confirmed by reviewer", "dismissed": "Dismissed by reviewer",
            "needs_info": "Needs more information"}


def e(s) -> str:
    return html.escape(str(s if s is not None else ""))


def img_b64(path: Path, max_w=900, quality=78) -> str:
    try:
        im = Image.open(path).convert("RGB")
        if im.width > max_w:
            im = im.resize((max_w, int(im.height * max_w / im.width)), Image.LANCZOS)
        b = io.BytesIO()
        im.save(b, "JPEG", quality=quality)
        return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()
    except Exception:
        return ""


def render(res: dict, cdir: Path, reviews: dict, audit: list[dict], chain: dict) -> str:
    ev = cdir / "evidence"
    docs = res["documents"]
    dmap = {d["doc_id"]: d for d in docs}
    F = res["findings"]
    s = res["stats"]
    out = []
    w = out.append
    w(f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Investigation Dossier - {e(res['case']['name'])}</title><style>
body{{font:14px/1.5 -apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#1f2933;max-width:1000px;margin:0 auto;padding:24px;background:#fff}}
h1{{font-size:24px;margin:0}} h2{{font-size:18px;border-bottom:2px solid #1e3a5f;padding-bottom:4px;margin-top:36px;color:#1e3a5f}}
h3{{font-size:15px;margin:18px 0 6px}} table{{border-collapse:collapse;width:100%;margin:8px 0}} td,th{{border:1px solid #d5dbe3;padding:5px 8px;text-align:left;vertical-align:top;font-size:13px}}
th{{background:#f1f4f8}} .muted{{color:#64748b}} .pill{{display:inline-block;border-radius:10px;padding:1px 8px;font-size:12px;font-weight:600}}
.pm{{background:#fde2e2;color:#a61b1b}} .inc{{background:#fff0d6;color:#9a5b00}} .obs{{background:#e0ebff;color:#1d4ed8}}
.finding{{border:1px solid #d5dbe3;border-left:5px solid #999;border-radius:6px;padding:10px 14px;margin:12px 0;page-break-inside:avoid}}
.finding.pm{{border-left-color:#dc2626;background:#fff}} .finding.inc{{border-left-color:#ea8c00;background:#fff}} .finding.obs{{border-left-color:#2563eb;background:#fff}}
.crops img{{max-height:130px;max-width:46%;border:1px solid #ccc;margin:4px 6px 4px 0}} .page img{{max-width:100%;border:1px solid #ccc}}
.banner{{background:#1e3a5f;color:#fff;padding:18px 22px;border-radius:8px}} .banner .muted{{color:#c8d3e0}}
.kpis{{display:flex;gap:10px;flex-wrap:wrap;margin-top:12px}} .kpi{{background:#fff2;border-radius:6px;padding:6px 12px}}
pre{{white-space:pre-wrap;font:inherit;margin:0}} .note{{background:#fff8e6;border:1px solid #f3d38b;padding:8px 12px;border-radius:6px}}
@media print{{body{{padding:0}} .finding{{break-inside:avoid}} h2{{break-after:avoid}}}}
</style></head><body>""")
    pr = res["summary"]["review_priority"]
    w(f"""<div class="banner"><div class="muted">AI-assisted Document Forensics - Investigation Dossier</div>
<h1>{e(res['case']['name'])}</h1><div class="muted">Case {e(res['case']['id'])} &middot; created {e(res['case']['created'][:19])} UTC</div>
<div class="kpis"><span class="kpi">Review priority: <b>{e(pr.upper())}</b></span><span class="kpi">{s['documents']} documents</span>
<span class="kpi">{s['by_status']['potential_manipulation']} potential manipulation</span><span class="kpi">{s['by_status']['inconsistency']} inconsistencies</span>
<span class="kpi">{s['by_status']['observation']} observations</span></div></div>
<p class="note"><b>Important:</b> This dossier contains automated findings. <b>Observation</b> = factual characteristic;
<b>Inconsistency</b> = detected discrepancy; <b>Potential manipulation</b> = evidence pattern consistent with deliberate
alteration. None of these is a fraud determination. OCR output is not treated as ground truth. Consequential decisions require human review.</p>""")

    # 7.6 summary first (executive)
    w("<h2>Investigation Summary</h2>")
    w(f"<pre>{e(res['summary']['text'])}</pre><p class='muted'>{e(res['summary']['note'])}</p>")

    # 7.1 overview
    w("<h2>1. Document Overview</h2><table><tr><th>ID</th><th>File</th><th>Type</th><th>Source format</th>"
      "<th>SHA-256 (intake)</th><th>Integrity</th><th>Processing status</th></tr>")
    integ = {i["doc_id"]: i for i in res["integrity"]}
    for d in docs:
        md = d.get("metadata") or {}
        conf = f" ({d['doc_type_conf']:.0%})" if d["doc_type"] != "unknown" else ""
        ok = integ.get(d["doc_id"], {}).get("unchanged")
        w(f"<tr><td>{e(d['doc_id'])}</td><td>{e(d['filename'])}</td><td>{e(d['doc_type_label'])}{conf}</td>"
          f"<td>{e(md.get('source_format', d['media_type']))}</td><td style='font-family:monospace;font-size:11px'>{e(d['sha256'][:32])}&hellip;</td>"
          f"<td>{'unchanged' if ok else 'CHANGED / missing'}</td><td>{e(d['status'])}{'<br><span class=muted>' + e('; '.join(d['errors'])) + '</span>' if d['errors'] else ''}</td></tr>")
    w("</table>")

    # 7.2 extracted information
    w("<h2>2. Extracted Information</h2>")
    for d in docs:
        if not d["fields"]:
            continue
        w(f"<h3>{e(d['doc_id'])} &middot; {e(d['filename'])} <span class='muted'>({e(d['doc_type_label'])})</span></h3>")
        st = (d.get("metadata") or {}).get("structure") or []
        if st:
            w("<p class='muted'>Structure: " + " &rarr; ".join(e(x["section"]) for x in st) + "</p>")
        w("<table><tr><th>Field</th><th>Value (as read)</th><th>Normalised</th><th>Confidence</th><th>Source</th>"
          "<th>Location (page, bbox px)</th></tr>")
        for k, f in d["fields"].items():
            w(f"<tr><td>{e(k)}</td><td>{e(f['raw'])}</td><td>{e(f['value'])}</td><td>{f['conf']:.2f}</td>"
              f"<td>{e(f['source'])}</td><td class='muted'>p{f['page'] + 1} [{', '.join(str(int(v)) for v in f['bbox'])}]</td></tr>")
        w("</table>")
        for t in d.get("tables") or []:
            w(f"<p><b>Table: {e(t['name'])}</b></p><table><tr>" + "".join(f"<th>{e(c)}</th>" for c in t["columns"]) +
              "</tr>")
            for r in t["rows"]:
                w("<tr>" + "".join(f"<td>{e(r['cells'].get(c, {}).get('text', ''))}</td>" for c in t["columns"]) +
                  "</tr>")
            w("</table>")

    def section(title, pred):
        items = [f for f in F if pred(f)]
        w(f"<h2>{title}</h2>")
        if not items:
            w("<p class='muted'>No findings in this category.</p>")
        for f in items:
            finding_html(f)

    def finding_html(f):
        css = STATUS_CSS[f["status"]]
        rv = reviews.get(f["id"])
        w(f"<div class='finding {css}'><div><span class='pill {css}'>{STATUS_LABEL[f['status']]}</span> "
          f"<b>[{e(f['id'])}] {e(f['title'])}</b></div>")
        w(f"<div class='muted'>{e(f['category'])} &middot; check: {e(f['check'])} &middot; basis: {e(f['basis'])} "
          f"&middot; confidence {f['confidence']:.2f} &middot; severity {e(f['severity'])}"
          f"{' &middot; related: ' + ', '.join(e(x) for x in f['related']) if f['related'] else ''}</div>")
        w(f"<pre>{e(f['explanation'])}</pre>")
        rows = []
        crops = []
        for x in f["evidence"]:
            d = dmap.get(x["doc_id"], {})
            loc = f"p{x.get('page', 0) + 1} [{', '.join(str(int(v)) for v in x['bbox'])}]" if x.get("bbox") else "document-level"
            rows.append(f"<tr><td>{e(x['doc_id'])} {e(d.get('filename', ''))}</td><td>{e(x.get('field') or '')}</td>"
                        f"<td>{e(x.get('value') or '')}</td><td>{e(loc)}</td><td>{e(x.get('note') or '')}</td></tr>")
            if x.get("crop"):
                crops.append(f"<img src='{img_b64(ev / x['crop'], 500, 85)}' title='{e(x['doc_id'])} {e(loc)}'>")
        if rows:
            w("<table><tr><th>Document</th><th>Field</th><th>Value</th><th>Location</th><th>Note</th></tr>" +
              "".join(rows) + "</table>")
        if crops:
            w("<div class='crops'>" + "".join(crops) + "</div>")
        if f.get("recommendation"):
            w(f"<div><b>Further verification:</b> {e(f['recommendation'])}</div>")
        if rv:
            w(f"<div><b>Reviewer:</b> {e(DECISION.get(rv['decision'], rv['decision']))} by {e(rv['reviewer'])} "
              f"({e(rv['ts'][:19])}) {e(rv['note'])}</div>")
        else:
            w("<div class='muted'>Reviewer decision: pending</div>")
        w("</div>")

    # 7.3 contextual
    section("3. Contextual Analysis (within-document & structural)",
            lambda f: f["category"] in ("contextual", "structural"))
    w("<h3>Cross-document discrepancies</h3>")
    for f in [f for f in F if f["category"] == "cross_document"]:
        finding_html(f)
    w("<h3>Cross-document comparison matrix</h3><table><tr><th>Attribute</th><th>Document A</th><th>Value A</th>"
      "<th>Document B</th><th>Value B</th><th>Similarity</th><th>Result</th></tr>")
    for c in res["comparisons"]:
        r = "match" if c["match"] else ("CONFLICT" if c["match"] is False else "see signature findings")
        w(f"<tr><td>{e(c['attribute'])}</td><td>{e(c['doc_a'])}</td><td>{e(c['value_a'])}</td><td>{e(c['doc_b'])}</td>"
          f"<td>{e(c['value_b'])}</td><td>{c['similarity']}</td><td>{e(r)} <span class='muted'>({e(c['relation'])})</span></td></tr>")
    w("</table>")

    # 7.4 visual
    section("4. Visual Forensic Findings", lambda f: f["category"] in ("visual", "metadata", "signature"))
    w("<h3>Checks applied per document</h3><table><tr><th>Document</th><th>Checks</th><th>Signature</th></tr>")
    for d in docs:
        md = d.get("metadata") or {}
        sig = d.get("signature") or {}
        sg = "-" if not sig else ("present" if sig.get("present") else "not found")
        w(f"<tr><td>{e(d['doc_id'])} {e(d['filename'])}</td><td>{e(', '.join(md.get('forensic_checks_applied', [])))}</td>"
          f"<td>{e(sg)}</td></tr>")
    w("</table>")

    # 7.5 evidence & traceability
    w("<h2>5. Evidence and Traceability</h2>")
    section_corr = [f for f in F if f["category"] == "correlated"]
    if section_corr:
        w("<h3>Corroborated anomalies (independent methods agree)</h3>")
        for f in section_corr:
            finding_html(f)
    if res.get("threads"):
        w("<h3>Finding relationships</h3><table><tr><th>Linked findings</th><th>Documents</th><th>Fields</th></tr>")
        for t in res["threads"]:
            w(f"<tr><td>{e(', '.join(t['findings']))}</td><td>{e(', '.join(t['documents']))}</td>"
              f"<td>{e(', '.join(t['fields']))}</td></tr>")
        w("</table>")
    w("<h3>Annotated documents</h3><p class='muted'>Boxes are drawn at the exact page coordinates recorded for each "
      "finding (red = potential manipulation, orange = inconsistency, blue = observation).</p>")
    for d in docs:
        for p in d.get("pages") or []:
            if p.get("annotated"):
                w(f"<div class='page'><p><b>{e(d['doc_id'])} {e(d['filename'])}</b> page {p['index'] + 1}</p>"
                  f"<img src='{img_b64(ev / p['annotated'], 900)}'></div>")

    # 7.6 summary details
    w("<h2>6. Areas Requiring Additional Verification &amp; Limitations</h2><ul>")
    recs = []
    for f in F:
        if f["status"] != "observation" and f.get("recommendation") and f["recommendation"] not in recs:
            recs.append(f["recommendation"])
    for r in recs:
        w(f"<li>{e(r)}</li>")
    if not recs:
        w("<li>No specific verification actions; routine checks apply.</li>")
    w("</ul><h3>Investigation limitations</h3><ul>" + "".join(f"<li>{e(x)}</li>" for x in res["limitations"]) + "</ul>")
    w("<h3>Capability status</h3><table><tr><th>Capability</th><th>Status</th></tr>" +
      "".join(f"<tr><td>{e(c['capability'])}</td><td>{e(c['status'])}</td></tr>" for c in res["capabilities"]) +
      "</table>")

    # audit trail
    w(f"<h2>Audit Trail</h2><p>Hash-chain verification: <b>{'VALID' if chain.get('valid') else 'BROKEN'}</b> "
      f"({chain.get('entries')} entries in log).</p><table><tr><th>#</th><th>Time (UTC)</th><th>Actor</th>"
      f"<th>Action</th><th>Details</th><th>Entry hash</th></tr>")
    for a in audit:
        det = ", ".join(f"{k}={v}" for k, v in a["details"].items() if k not in ("findings", "trace"))
        w(f"<tr><td>{a['seq']}</td><td>{e(a['ts'][:23])}</td><td>{e(a['actor'])}</td><td>{e(a['action'])}</td>"
          f"<td style='font-size:11px'>{e(det[:220])}</td><td style='font-family:monospace;font-size:10px'>{e(a['hash'][:16])}</td></tr>")
    w("</table><p class='muted'>Generated by the Document Forensics prototype. Processing time "
      f"{s['processing_seconds']}s.</p></body></html>")
    return "".join(out)
