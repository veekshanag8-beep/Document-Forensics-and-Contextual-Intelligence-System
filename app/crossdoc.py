"""Stages 7-8: cross-document correlation, entity graph, and correlation of findings into investigations."""
from __future__ import annotations

from rapidfuzz import fuzz

from . import forensics
from .forensics import F
from .models import (DETERMINISTIC, HEURISTIC, INCONSISTENCY, OBSERVATION, POTENTIAL_MANIPULATION, Document,
                     Field, Finding, ev)
from .validators import digits, fmt_amount, norm_address, norm_company, norm_id, norm_name, pincode

# attribute -> {doc_type: field}
ATTRIBUTES = {
    "person_name": {"application_form": "applicant_name", "identity_card": "name", "salary_slip": "employee_name",
                    "bank_statement": "account_holder"},
    "date_of_birth": {"application_form": "date_of_birth", "identity_card": "date_of_birth"},
    "national_id": {"application_form": "national_id", "identity_card": "national_id"},
    "pan": {"application_form": "pan", "salary_slip": "pan"},
    "address": {"application_form": "address", "identity_card": "address", "bank_statement": "address"},
    "employer": {"application_form": "employer", "salary_slip": "employer"},
}
LABEL = {"person_name": "Name", "date_of_birth": "Date of birth", "national_id": "National ID number", "pan": "PAN",
         "address": "Address", "employer": "Employer"}


def _norm(attr: str, f: Field) -> str:
    if attr == "person_name":
        return norm_name(f.raw).replace(" ", "")
    if attr == "address":
        return norm_address(f.raw).replace(" ", "")
    if attr == "employer":
        return norm_company(f.raw).replace(" ", "")
    if attr in ("national_id", "pan"):
        return norm_id(f.raw)
    return str(f.value)


def _similar(attr: str, a: tuple, b: tuple) -> tuple[bool, float, str]:
    """Return (same_entity, similarity 0-100, relation) for two (normalised, Field) values."""
    na, nb = a[0], b[0]
    if na == nb:
        return True, 100.0, "exact"
    r = fuzz.ratio(na, nb)
    if attr == "address":
        pa, pb = pincode(a[1].raw), pincode(b[1].raw)
        if pa and pb and pa != pb:
            return False, r, "different PIN code"
        return (r >= 80), r, "minor formatting difference" if r >= 80 else "different"
    if attr == "employer":
        return (r >= 88), r, "legal-suffix / formatting variation" if r >= 88 else "different"
    if attr == "person_name":
        return False, r, "spelling variation" if r >= 80 else "different"
    return False, r, "different"


def compare_attributes(docs: list[Document]) -> tuple[list[Finding], list[dict]]:
    findings: list[Finding] = []
    comparisons: list[dict] = []
    for attr, mapping in ATTRIBUTES.items():
        vals = []
        for d in docs:
            fname = mapping.get(d.doc_type)
            f = d.fields.get(fname) if fname else None
            if f is not None and f.value not in (None, ""):
                vals.append((d, f, _norm(attr, f)))
        if len(vals) < 2:
            continue
        # cluster values: each new value joins the first cluster it matches
        clusters: list[list] = []
        for d, f, n in vals:
            for c in clusters:
                same, sim, rel = _similar(attr, (c[0][2], c[0][1]), (n, f))
                if same:
                    c.append((d, f, n))
                    break
            else:
                clusters.append([(d, f, n)])
        for i, (da, fa, na) in enumerate(vals):
            for db, fb, nb in vals[i + 1:]:
                same, sim, rel = _similar(attr, (na, fa), (nb, fb))
                comparisons.append({"attribute": attr, "doc_a": da.doc_id, "doc_b": db.doc_id, "value_a": fa.raw,
                                    "value_b": fb.raw, "match": same, "similarity": round(sim, 1), "relation": rel})
        if len(clusters) == 1:
            continue
        clusters.sort(key=len, reverse=True)
        major = clusters[0]
        for minor in clusters[1:]:
            d0, f0, n0 = minor[0]
            same, sim, rel = _similar(attr, (major[0][2], major[0][1]), (n0, f0))
            minor_docs = ", ".join(d.filename for d, _, _ in minor)
            major_docs = ", ".join(d.filename for d, _, _ in major)
            ocr_note = ""
            low = [f for _, f, _ in minor + major if f.source == "ocr" and f.conf < 0.9]
            if low:
                ocr_note = " Some values were read by OCR with reduced confidence; confirm against the originals."
            variation = rel in ("spelling variation", "minor formatting difference")
            status = INCONSISTENCY
            sev = "medium" if variation else "high"
            conf = min(0.97, 0.75 + (0.1 if not variation else 0) + 0.1 * min(f.conf for _, f, _ in minor + major))
            label = LABEL[attr]
            findings.append(F(
                "cross_document", f"cross_{attr}", f"{label} differs across documents",
                status, DETERMINISTIC if attr in ("national_id", "pan", "date_of_birth") else HEURISTIC, conf,
                f"{label} on {minor_docs} is '{f0.raw}', while {major_docs} show '{major[0][1].raw}' "
                f"(similarity {sim:.0f}%, {rel}). Documents belonging to one applicant should carry the same "
                f"{label.lower()}; a mismatch can indicate a document belonging to someone else, a clerical error, "
                f"or an altered field." + ocr_note,
                [ev(d, f, note="minority value") for d, f, _ in minor] +
                [ev(d, f, note="majority value") for d, f, _ in major],
                [mapping[d.doc_type] for d, _, _ in minor + major], sev,
                f"Confirm the correct {label.lower()} with the applicant and the issuing source."))
    return findings, comparisons


def financial_links(docs: list[Document]) -> tuple[list[Finding], list[dict]]:
    by = {}
    for d in docs:
        by.setdefault(d.doc_type, d)
    out, comps = [], []
    form, slip, bank = by.get("application_form"), by.get("salary_slip"), by.get("bank_statement")
    # declared income vs payslip
    if form and slip:
        fi = form.fields.get("monthly_income")
        g = slip.fields.get("gross_earnings")
        n = slip.fields.get("net_pay")
        if fi is not None and fi.value and g is not None and g.value:
            ratio = fi.value / g.value
            ok = ratio <= 1.05
            comps.append({"attribute": "income", "doc_a": form.doc_id, "doc_b": slip.doc_id, "value_a": fi.raw,
                          "value_b": g.raw, "match": ok, "similarity": round(min(ratio, 1 / ratio) * 100, 1),
                          "relation": "declared income vs payslip gross"})
            if not ok:
                out.append(F(
                    "cross_document", "income_vs_payslip", "Declared income exceeds payslip earnings",
                    INCONSISTENCY, DETERMINISTIC, 0.9,
                    f"The application declares a monthly income of {fmt_amount(fi.value)}, which is "
                    f"{(ratio - 1) * 100:.0f}% higher than the gross earnings of {fmt_amount(g.value)} on the "
                    f"salary slip submitted as proof"
                    + (f" (net pay printed: {fmt_amount(n.value)})" if n is not None and n.value else "") + ".",
                    [ev(form, fi, note="declared"), ev(slip, g, note="payslip gross")] +
                    ([ev(slip, n, note="payslip net")] if n is not None else []),
                    ["monthly_income", "gross_earnings"], "high",
                    "Verify income with employer / tax records."))
    # salary credit in bank statement vs payslip net pay
    if slip and bank and bank.tables:
        n = slip.fields.get("net_pay")
        rows = [r for r in bank.tables[0]["rows"] if "salary" in r["description"].lower() and r["credit"]]
        if n is not None and n.value and rows:
            r = rows[-1]
            c = r["cells"].get("credit")
            ok = abs(r["credit"] - n.value) <= 1
            comps.append({"attribute": "salary_credit", "doc_a": slip.doc_id, "doc_b": bank.doc_id,
                          "value_a": n.raw, "value_b": c["text"] if c else str(r["credit"]), "match": ok,
                          "similarity": round(min(r["credit"], n.value) / max(r["credit"], n.value) * 100, 1),
                          "relation": "payslip net pay vs salary credit"})
            if not ok:
                out.append(F(
                    "cross_document", "salary_credit_mismatch", "Salary credited differs from payslip net pay",
                    INCONSISTENCY, DETERMINISTIC, round(0.95 * min(n.conf, c["conf"] if c else 1), 2),
                    f"The bank statement shows a salary credit of {fmt_amount(r['credit'])} "
                    f"('{r['description']}'), but the salary slip for the same period states a net pay of "
                    f"{fmt_amount(n.value)} (difference {fmt_amount(n.value - r['credit'])}). The bank credit is "
                    f"produced independently of the payslip, so one of the two documents does not reflect the "
                    f"actual salary.",
                    [ev(slip, n, note="payslip net pay"),
                     ev(bank, bbox=c["bbox"] if c else r["bbox"], page=r["page"], value=c["text"] if c else "",
                        field_name="salary_credit", note=r["description"])],
                    ["net_pay", "salary_credit"], "high", "Ask the employer to confirm the salary paid."))
        elif n is not None and n.value and not rows:
            out.append(F("cross_document", "salary_credit_missing", "No salary credit found in bank statement",
                         OBSERVATION, HEURISTIC, 0.6,
                         "The salary slip implies a salary payment, but no credit described as salary appears in "
                         "the bank statement for the period.", [ev(bank, bbox=None, page=0)], [], "low"))
        # salary account number on slip vs statement account
        sa, an = slip.fields.get("salary_account"), bank.fields.get("account_number")
        if sa is not None and an is not None:
            d1, d2 = digits(sa.raw)[-4:], digits(an.raw)[-4:]
            if d1 and d2:
                comps.append({"attribute": "salary_account", "doc_a": slip.doc_id, "doc_b": bank.doc_id,
                              "value_a": sa.raw, "value_b": an.raw, "match": d1 == d2,
                              "similarity": 100.0 if d1 == d2 else 0.0, "relation": "last 4 digits"})
                if d1 != d2:
                    out.append(F("cross_document", "salary_account_mismatch",
                                 "Salary account differs from statement account", INCONSISTENCY, DETERMINISTIC, 0.85,
                                 f"Slip pays salary into account ending {d1}; statement is for account ending {d2}.",
                                 [ev(slip, sa), ev(bank, an)], ["salary_account", "account_number"], "medium"))
    return out, comps


def signature_links(docs: list[Document]) -> tuple[list[Finding], list[dict]]:
    by = {d.doc_type: d for d in docs}
    out, comps = [], []
    a, b = by.get("application_form"), by.get("identity_card")
    if a and b and a.signature and b.signature and a.signature.get("present") and b.signature.get("present"):
        sim = forensics.signature_similarity(a.doc_id, b.doc_id)
        if sim is None:
            return out, comps
        comps.append({"attribute": "signature", "doc_a": a.doc_id, "doc_b": b.doc_id, "value_a": "signature image",
                      "value_b": "signature image", "match": None, "similarity": round(sim * 100, 1),
                      "relation": "shape correlation"})
        a.signature["similarity_to_" + b.doc_id] = round(sim, 3)
        if sim >= 0.93:
            out.append(F(
                "signature", "signature_copy", "Signature appears to be a digital copy",
                POTENTIAL_MANIPULATION, HEURISTIC, round(min(0.9, sim - 0.05), 2),
                f"The applicant's signature on {a.filename} and the signature on {b.filename} are near-identical "
                f"in shape (correlation {sim:.2f}). Two genuine hand signatures always vary slightly in stroke "
                f"path and proportions; a match this close is characteristic of one signature image being copied "
                f"and pasted onto the other document.",
                [ev(a, bbox=a.signature["bbox"], page=0, field_name="applicant_signature", note="signature on form"),
                 ev(b, bbox=b.signature["bbox"], page=0, field_name="holder_signature", note="signature on ID")],
                ["applicant_signature", "holder_signature"], "high",
                "Obtain a wet-ink signature in the presence of staff."))
    return out, comps


def build_graph(docs: list[Document], comparisons: list[dict]) -> dict:
    nodes = [{"id": d.doc_id, "label": d.filename, "type": "document", "doc_type": d.doc_type} for d in docs]
    edges = []
    value_nodes: list[tuple[str, str, Field, str]] = []   # (attribute, normalised, field, node id)
    for attr, mapping in ATTRIBUTES.items():
        for d in docs:
            fname = mapping.get(d.doc_type)
            f = d.fields.get(fname) if fname else None
            if f is None or f.value in (None, ""):
                continue
            key = None
            for a, n, f0, vid in value_nodes:
                if a == attr and _similar(attr, (n, f0), (_norm(attr, f), f))[0]:
                    key = vid
                    break
            if key is None:
                key = f"{attr}:{len(value_nodes)}"
                value_nodes.append((attr, _norm(attr, f), f, key))
                nodes.append({"id": key, "label": f"{LABEL[attr]}: {f.raw[:32]}", "type": "entity",
                              "attribute": attr})
            edges.append({"source": d.doc_id, "target": key, "label": fname, "status": "asserts"})
    for c in comparisons:
        if c["attribute"] in ("income", "salary_credit", "salary_account", "signature"):
            edges.append({"source": c["doc_a"], "target": c["doc_b"], "label": c["relation"],
                          "status": "match" if c["match"] else ("conflict" if c["match"] is False else "info")})
    # mark entity nodes with conflicts (same attribute, >1 value node)
    per_attr = {}
    for n in nodes:
        if n["type"] == "entity":
            per_attr.setdefault(n["attribute"], []).append(n)
    for attr, ns in per_attr.items():
        for n in ns:
            n["conflict"] = len(ns) > 1
    return {"nodes": nodes, "edges": edges}


# ----------------------------------------------------------------------------- correlation of findings
INDEPENDENT_FAMILIES = {"visual": "visual", "metadata": "visual", "signature": "visual",
                        "contextual": "contextual", "cross_document": "contextual", "structural": "structural"}


def correlate(findings: list[Finding], docs: list[Document]) -> list[Finding]:
    """Link findings that point at the same document field; when independent methods (visual forensics AND
    contextual logic) agree on one field, raise a corroborated finding."""
    keys: dict[tuple, list[int]] = {}
    for i, f in enumerate(findings):
        for e in f.evidence:
            if e.get("field"):
                keys.setdefault((e["doc_id"], e["field"]), []).append(i)
    parent = list(range(len(findings)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for idx in keys.values():
        for j in idx[1:]:
            parent[find(j)] = find(idx[0])
    groups: dict[int, list[int]] = {}
    for i in range(len(findings)):
        groups.setdefault(find(i), []).append(i)
    # document-level metadata observations join the group of a visual finding in the same document
    for i, f in enumerate(findings):
        if f.category == "metadata" and len(groups.get(find(i), [])) == 1:
            doc_id = f.evidence[0]["doc_id"] if f.evidence else None
            for root, members in list(groups.items()):
                if root != find(i) and any(findings[m].category == "visual" and
                                           any(e["doc_id"] == doc_id for e in findings[m].evidence)
                                           for m in members):
                    groups[root].append(i)
                    groups.pop(find(i), None)
                    parent[i] = root
                    break
    threads = []
    for members in groups.values():
        if len(members) < 2:
            continue
        ids = [findings[m].id for m in members]
        for m in members:
            findings[m].related = [x for x in ids if x != findings[m].id]
        threads.append({"findings": ids,
                        "documents": sorted({e["filename"] for m in members for e in findings[m].evidence}),
                        "fields": sorted({fl for m in members for fl in findings[m].fields})})

    # corroboration: one (document, field) examined by independent method families
    new, done = [], set()
    by_id = {f.id: f for f in findings}
    for (doc_id, field), idx in keys.items():
        members = sorted(set(idx))
        sig = tuple(members)
        if sig in done:
            continue
        fams = {INDEPENDENT_FAMILIES.get(findings[m].category, "other") for m in members}
        strong_visual = [m for m in members if INDEPENDENT_FAMILIES.get(findings[m].category) == "visual"
                         and findings[m].status != OBSERVATION]
        if not ({"visual", "contextual"} <= fams and strong_visual):
            continue
        done.add(sig)
        p = 1.0
        for m in members:
            if findings[m].status != OBSERVATION:
                p *= (1 - findings[m].confidence)
        conf = round(min(0.97, 1 - p), 2)
        doc = next(d for d in docs if d.doc_id == doc_id)
        fld = doc.fields.get(field)
        lines = [f"- [{findings[m].id}] {findings[m].title} ({findings[m].category}, {findings[m].basis}, "
                 f"confidence {findings[m].confidence:.2f})" for m in members]
        ev_list = [ev(doc, fld, note="corroborated field")] if fld is not None else []
        seen = {(doc_id, tuple(fld.bbox))} if fld is not None else set()
        for m in members:
            for e in findings[m].evidence:
                k = (e["doc_id"], tuple(e["bbox"] or []))
                if e.get("bbox") and k not in seen:
                    seen.add(k)
                    ev_list.append(e)
        value = f" ('{fld.raw}')" if fld is not None else ""
        cf = Finding(id="", category="correlated", check="corroborated_anomaly",
                     title=f"Corroborated anomaly: {field.replace('_', ' ')} on {doc.filename}{value}",
                     status=POTENTIAL_MANIPULATION, basis=HEURISTIC, confidence=conf,
                     explanation=(f"{len(members)} findings from independent methods point at the same value. "
                                  "Visual/file forensics show signs of alteration AND contextual logic shows the "
                                  "value does not fit the rest of the evidence. Either kind of signal alone could "
                                  "be noise; together they make deliberate alteration the most likely explanation. "
                                  "This is not a fraud determination: human verification with the issuing source "
                                  "is required.\n" + "\n".join(lines)),
                     evidence=ev_list, fields=[field], related=[findings[m].id for m in members], severity="high",
                     recommendation="Escalate for manual review; verify the value with the issuing source.")
        new.append(cf)
    _ = by_id
    return new, threads
