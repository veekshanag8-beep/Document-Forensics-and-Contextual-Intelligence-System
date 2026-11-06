"""Stages 2-4: document classification, field extraction, table extraction, structure understanding."""
from __future__ import annotations

import re
from typing import Optional

from rapidfuzz import fuzz

from .models import Document, Field, TextUnit
from .validators import parse_amount, parse_date


def compact(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


# ----------------------------------------------------------------------------- classification
DOC_TYPES = {
    "application_form": {"label": "Loan Application Form",
                         "strong": ["applicationform", "loanapplication"],
                         "weak": ["applicant", "declaration", "loanamount", "loanpurpose", "monthlyincome"]},
    "identity_card": {"label": "Identity Card",
                      "strong": ["identitycard"],
                      "weak": ["dateofbirth", "idno", "gender", "signature", "photo"]},
    "salary_slip": {"label": "Salary Slip",
                    "strong": ["salaryslip", "payslip"],
                    "weak": ["netpay", "grossearnings", "totaldeductions", "basicsalary", "providentfund",
                             "employeename"]},
    "bank_statement": {"label": "Bank Statement",
                       "strong": ["accountstatement", "bankstatement"],
                       "weak": ["openingbalance", "closingbalance", "ifsc", "debit", "credit", "accountholder"]},
}


def classify(doc: Document) -> None:
    text = compact(" ".join(u.text for u in doc.units if not u.hidden))
    scores = {}
    for t, spec in DOC_TYPES.items():
        s = sum(3 for k in spec["strong"] if k in text) + sum(1 for k in spec["weak"] if k in text)
        mx = 3 * len(spec["strong"][:1]) + len(spec["weak"])
        scores[t] = round(min(1.0, s / mx), 3)
    best = max(scores, key=scores.get)
    doc.doc_type_scores = scores
    if scores[best] < 0.45:
        doc.doc_type = "unknown"
        doc.doc_type_conf = round(1 - scores[best], 3)
    else:
        doc.doc_type = best
        second = sorted(scores.values())[-2]
        doc.doc_type_conf = round(min(0.99, 0.5 + 0.5 * (scores[best] - second) + 0.3 * scores[best]), 3)


# ----------------------------------------------------------------------------- field schemas
# (field, [label aliases], value type, options)
SCHEMAS: dict[str, list[tuple]] = {
    "application_form": [
        ("application_no", ["Application No"], "id", {"inline": True, "required": False}),
        ("application_date", ["Application Date"], "date", {}),
        ("applicant_name", ["Applicant Name"], "name", {}),
        ("date_of_birth", ["Date of Birth", "DOB"], "date", {}),
        ("age", ["Age (years)", "Age"], "int", {}),
        ("gender", ["Gender"], "text", {"required": False}),
        ("pan", ["PAN"], "id", {}),
        ("national_id", ["National ID No", "ID No"], "id", {}),
        ("address", ["Residential Address", "Address"], "address", {}),
        ("mobile", ["Mobile"], "text", {"required": False}),
        ("employer", ["Employer"], "company", {}),
        ("monthly_income", ["Monthly Income (INR)", "Monthly Income"], "amount", {}),
        ("loan_amount", ["Loan Amount (INR)", "Loan Amount"], "amount", {}),
        ("loan_purpose", ["Loan Purpose"], "text", {"required": False}),
    ],
    "identity_card": [
        ("name", ["Name"], "name", {}),
        ("date_of_birth", ["Date of Birth", "DOB"], "date", {}),
        ("gender", ["Gender"], "text", {"required": False}),
        ("national_id", ["ID No", "ID Number"], "id", {}),
        ("address", ["Address"], "address", {"multiline": True}),
    ],
    "salary_slip": [
        ("employee_name", ["Employee Name"], "name", {}),
        ("employee_id", ["Employee ID"], "id", {"required": False}),
        ("designation", ["Designation"], "text", {"required": False}),
        ("pan", ["PAN"], "id", {}),
        ("pay_period", ["Pay Period"], "text", {}),
        ("salary_account", ["Salary Account"], "id", {"required": False}),
        ("basic", ["Basic Salary"], "amount", {}),
        ("hra", ["House Rent Allowance"], "amount", {"required": False}),
        ("special_allowance", ["Special Allowance"], "amount", {"required": False}),
        ("gross_earnings", ["Gross Earnings"], "amount", {}),
        ("provident_fund", ["Provident Fund"], "amount", {"required": False}),
        ("income_tax", ["Income Tax (TDS)", "Income Tax"], "amount", {"required": False}),
        ("total_deductions", ["Total Deductions"], "amount", {}),
        ("net_pay", ["Net Pay (INR)", "Net Pay"], "amount", {}),
    ],
    "bank_statement": [
        ("statement_period", ["Statement Period"], "text", {"inline": True}),
        ("account_holder", ["Account Holder"], "name", {}),
        ("address", ["Address"], "address", {}),
        ("account_number", ["Account No", "Account Number"], "id", {}),
        ("ifsc", ["IFSC"], "id", {}),
        ("opening_balance", ["Opening Balance"], "amount", {}),
        ("closing_balance", ["Closing Balance"], "amount", {}),
    ],
}


def _same_row(a: TextUnit, b: TextUnit) -> bool:
    ov = min(a.bbox[3], b.bbox[3]) - max(a.bbox[1], b.bbox[1])
    return ov > 0.45 * min(a.h, b.h)


def _label_match(u: TextUnit, aliases: list[str]) -> tuple[float, Optional[str]]:
    """Return (score, inline_remainder) for a unit acting as a label."""
    ct = compact(u.text)
    best, rem = 0.0, None
    for a in aliases:
        ca = compact(a)
        if not ca:
            continue
        if ct == ca:
            return 100.0, None
        # inline "Label: value"
        if ":" in u.text:
            head, tail = u.text.split(":", 1)
            if compact(head) == ca and tail.strip():
                return 99.0, tail.strip()
        if len(ca) >= 5 and abs(len(ct) - len(ca)) <= 2:
            r = fuzz.ratio(ct, ca)
            if r > best:
                best, rem = r, None
    return best, rem


def _parse(vtype: str, raw: str):
    if vtype == "amount":
        return parse_amount(raw)
    if vtype == "date":
        d = parse_date(raw)
        return d.isoformat() if d else None
    if vtype == "int":
        m = re.search(r"\d+", raw)
        return int(m.group(0)) if m else None
    if vtype == "id":
        return re.sub(r"[^A-Z0-9]", "", raw.upper()) or None
    return raw.strip() or None


def extract_fields(doc: Document) -> None:
    schema = SCHEMAS.get(doc.doc_type)
    if not schema:
        return
    visible = [u for u in doc.units if not u.hidden]
    all_alias = {compact(a) for _, al, _, _ in schema for a in al}
    used_labels: set[int] = set()
    label_units: dict[str, TextUnit] = {}
    doc.metadata.setdefault("missing_fields", [])
    doc.metadata.setdefault("duplicate_labels", [])

    for fname, aliases, vtype, opts in schema:
        cands = []
        for i, u in enumerate(visible):
            if i in used_labels:
                continue
            score, rem = _label_match(u, aliases)
            if score >= 88:
                cands.append((score, i, u, rem))
        if not cands:
            if opts.get("required", True):
                doc.metadata["missing_fields"].append(fname)
            continue
        cands.sort(key=lambda c: (-c[0], c[2].bbox[1]))
        exact = [c for c in cands if c[0] >= 99]
        if len(exact) > 1 and fname not in ("address",):
            doc.metadata["duplicate_labels"].append({"field": fname, "count": len(exact),
                                                     "bboxes": [c[2].bbox for c in exact]})
        score, li, lab, rem = cands[0]
        used_labels.add(li)
        label_units[fname] = lab
        if rem is not None:
            # inline value: approximate the value bbox as the right part of the unit
            frac = max(0.0, 1 - len(rem) / max(1, len(lab.text)))
            x0 = lab.bbox[0] + (lab.bbox[2] - lab.bbox[0]) * frac
            val_units = [TextUnit(text=rem, bbox=[x0, lab.bbox[1], lab.bbox[2], lab.bbox[3]], conf=lab.conf,
                                  page=lab.page, font=lab.font, size=lab.size, order=lab.order)]
        else:
            row = [u for u in visible if u is not lab and u.page == lab.page and _same_row(lab, u)
                   and u.bbox[0] >= lab.bbox[2] - 5 and compact(u.text) not in all_alias]
            row.sort(key=lambda u: u.bbox[0])
            if not row:
                if opts.get("required", True):
                    doc.metadata["missing_fields"].append(fname)
                continue
            val_units = [row[0]]
            if opts.get("multiline"):
                v = row[0]
                for u in sorted(visible, key=lambda u: u.bbox[1]):
                    if u.page == v.page and 0 < u.bbox[1] - val_units[-1].bbox[3] < 1.2 * v.h \
                            and abs(u.bbox[0] - v.bbox[0]) < 0.6 * v.h and compact(u.text) not in all_alias:
                        val_units.append(u)
        raw = " ".join(u.text for u in val_units).strip()
        bbox = [min(u.bbox[0] for u in val_units), min(u.bbox[1] for u in val_units),
                max(u.bbox[2] for u in val_units), max(u.bbox[3] for u in val_units)]
        value = _parse(vtype, raw)
        conf = min([lab.conf] + [u.conf for u in val_units]) * (1.0 if value is not None else 0.6)
        doc.fields[fname] = Field(name=fname, value=value, raw=raw, conf=round(conf, 3), page=val_units[0].page,
                                  bbox=[round(v, 1) for v in bbox], label_bbox=lab.bbox,
                                  source="pdf_text_layer" if lab.font else "ocr")
        doc.fields[fname].vtype = vtype
        # inline values ("Label: value") share the label's text unit, so they carry no own typography
        doc.fields[fname].units = [] if rem is not None else [u.order for u in val_units]

    doc.metadata["label_units"] = {k: v.bbox for k, v in label_units.items()}
    _header_fields(doc, visible)
    if doc.doc_type == "bank_statement":
        _bank_table(doc, visible)
    _structure(doc, visible, label_units)


def _header_fields(doc: Document, visible: list[TextUnit]):
    """The issuing organisation is the most prominent text in the top band of page 0."""
    if not doc.pages:
        return
    top = [u for u in visible if u.page == 0 and u.bbox[3] < doc.pages[0]["height"] * 0.09]
    if not top:
        return
    org = max(top, key=lambda u: u.h * len(u.text) ** 0.3)
    doc.fields["issuer"] = Field(name="issuer", value=org.text, raw=org.text, conf=org.conf, page=0, bbox=org.bbox,
                                 source="header")
    doc.fields["issuer"].vtype = "company"
    if doc.doc_type == "salary_slip":
        f = Field(name="employer", value=org.text, raw=org.text, conf=org.conf, page=0, bbox=org.bbox,
                  source="header")
        f.vtype = "company"
        doc.fields["employer"] = f


def _bank_table(doc: Document, visible: list[TextUnit]):
    hdr_names = ["date", "description", "debit", "credit", "balance"]
    desc = [u for u in visible if compact(u.text) == "description"]
    if not desc:
        doc.metadata.setdefault("missing_fields", []).append("transactions_table")
        return
    d0 = desc[0]
    headers = {}
    for u in visible:
        if u.page == d0.page and _same_row(u, d0) and compact(u.text) in hdr_names:
            headers[compact(u.text)] = u
    if len(headers) < 4:
        doc.metadata.setdefault("missing_fields", []).append("transactions_table")
        return
    end_y = min([u.bbox[1] for u in visible if compact(u.text).startswith("closingbalance")
                 and u.bbox[1] > d0.bbox[3]] or [1e9])
    body = [u for u in visible if u.page == d0.page and d0.bbox[3] + 2 < u.cy < end_y]
    body.sort(key=lambda u: u.cy)
    rows: list[list[TextUnit]] = []
    for u in body:
        if rows and abs(rows[-1][0].cy - u.cy) < 0.6 * max(u.h, rows[-1][0].h):
            rows[-1].append(u)
        else:
            rows.append([u])
    cols = sorted(headers.items(), key=lambda kv: kv[1].bbox[0])
    table_rows = []
    for r in rows:
        rec = {"cells": {}, "bbox": [min(u.bbox[0] for u in r), min(u.bbox[1] for u in r),
                                     max(u.bbox[2] for u in r), max(u.bbox[3] for u in r)], "page": d0.page}
        for u in sorted(r, key=lambda u: u.bbox[0]):
            # a unit belongs to the right-most column header that starts left of it (with tolerance)
            left = [kv for kv in cols if kv[1].bbox[0] <= u.bbox[0] + 0.8 * u.h]
            name = (left[-1] if left else cols[0])[0]
            if name in rec["cells"]:  # OCR split one cell into several pieces -> merge
                c0 = rec["cells"][name]
                gap = u.bbox[0] - c0["bbox"][2]
                c0["text"] = c0["text"] + ("" if gap < 0.35 * u.h else " ") + u.text
                c0["bbox"] = [min(c0["bbox"][0], u.bbox[0]), min(c0["bbox"][1], u.bbox[1]),
                              max(c0["bbox"][2], u.bbox[2]), max(c0["bbox"][3], u.bbox[3])]
                c0["conf"] = min(c0["conf"], u.conf)
            else:
                rec["cells"][name] = {"text": u.text, "bbox": u.bbox, "conf": u.conf}
        c = rec["cells"]
        rec["date"] = (parse_date(c.get("date", {}).get("text", "")) or None)
        rec["date"] = rec["date"].isoformat() if rec["date"] else None
        rec["description"] = c.get("description", {}).get("text", "")
        rec["debit"] = parse_amount(c["debit"]["text"]) if "debit" in c else 0.0
        rec["credit"] = parse_amount(c["credit"]["text"]) if "credit" in c else 0.0
        rec["balance"] = parse_amount(c["balance"]["text"]) if "balance" in c else None
        table_rows.append(rec)
    doc.tables.append({"name": "transactions", "columns": [k for k, _ in cols], "rows": table_rows,
                       "header_bbox": [min(u.bbox[0] for u in headers.values()), d0.bbox[1],
                                       max(u.bbox[2] for u in headers.values()), d0.bbox[3]], "page": d0.page})


def _structure(doc: Document, visible: list[TextUnit], labels: dict[str, TextUnit]):
    """Describe the document layout as a section hierarchy: header -> key/value block -> table -> sign-off."""
    if not doc.pages:
        return
    H = doc.pages[0]["height"]
    secs = []
    hdr = [u for u in visible if u.page == 0 and u.bbox[3] < H * 0.15]
    if hdr:
        secs.append({"section": "header", "bbox": _union([u.bbox for u in hdr]),
                     "items": [u.text for u in hdr][:6]})
    kv = [f for f in doc.fields.values() if f.source in ("ocr", "pdf_text_layer")]
    if kv:
        boxes = [f.bbox for f in kv] + [labels[f.name].bbox for f in kv if f.name in labels]
        secs.append({"section": "key_value_fields", "bbox": _union(boxes), "items": [f.name for f in kv]})
    for t in doc.tables:
        if t["rows"]:
            secs.append({"section": f"table:{t['name']}", "bbox": _union([t["header_bbox"]] +
                                                                         [r["bbox"] for r in t["rows"]]),
                         "items": t["columns"] + [f"{len(t['rows'])} rows"]})
    sig = [u for u in visible if any(k in compact(u.text) for k in ("signature", "signatory"))
           and len(u.text) <= 40]
    if sig:
        secs.append({"section": "sign_off", "bbox": sig[0].bbox, "items": [sig[0].text]})
    doc.metadata["structure"] = secs
    expected = len(SCHEMAS.get(doc.doc_type, []))
    doc.metadata["field_coverage"] = round(len([f for f in doc.fields if f not in ("issuer",)]) / expected, 3) \
        if expected else 0


def _union(boxes):
    return [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]


def mark_hidden_pdf_text(doc: Document) -> None:
    """In a PDF, if two text units overlap with different content, the earlier-drawn one is covered."""
    us = doc.units
    hidden_pairs = []
    for i, a in enumerate(us):
        for b in us[i + 1:]:
            if a.page != b.page:
                continue
            ix = min(a.bbox[2], b.bbox[2]) - max(a.bbox[0], b.bbox[0])
            iy = min(a.bbox[3], b.bbox[3]) - max(a.bbox[1], b.bbox[1])
            if ix <= 0 or iy <= 0:
                continue
            inter = ix * iy
            area = min((a.bbox[2] - a.bbox[0]) * a.h, (b.bbox[2] - b.bbox[0]) * b.h)
            if area > 0 and inter / area > 0.4 and compact(a.text) != compact(b.text):
                under, over = (a, b) if a.order < b.order else (b, a)
                under.hidden = True
                hidden_pairs.append({"hidden": under.text, "hidden_bbox": under.bbox, "hidden_font": under.font,
                                     "visible": over.text, "visible_bbox": over.bbox, "visible_font": over.font,
                                     "page": under.page})
    # text fully under an opaque white overlay is hidden as well
    for pno, rects in (doc.metadata.get("white_overlays") or {}).items():
        for r in rects:
            for u in us:
                if u.page == int(pno) and not u.hidden and _inside(u.bbox, r, 0.8):
                    # only hidden if the overlay was drawn after it: approximated by "another unit drawn on top"
                    covering = [v for v in us if v is not u and v.page == u.page and _inside(v.bbox, r, 0.6)
                                and v.order > u.order]
                    if covering:
                        u.hidden = True
                        if not any(p["hidden_bbox"] == u.bbox for p in hidden_pairs):
                            hidden_pairs.append({"hidden": u.text, "hidden_bbox": u.bbox, "hidden_font": u.font,
                                                 "visible": covering[0].text, "visible_bbox": covering[0].bbox,
                                                 "visible_font": covering[0].font, "page": u.page})
    doc.metadata["hidden_text"] = hidden_pairs


def _inside(b, r, frac):
    ix = min(b[2], r[2]) - max(b[0], r[0])
    iy = min(b[3], r[3]) - max(b[1], r[1])
    if ix <= 0 or iy <= 0:
        return False
    return ix * iy >= frac * (b[2] - b[0]) * (b[3] - b[1])
