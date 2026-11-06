"""Stage 6: contextual verification inside a single document (field relationships, arithmetic, identifiers)."""
from __future__ import annotations

from datetime import date

from .forensics import F
from .models import DETERMINISTIC, HEURISTIC, INCONSISTENCY, OBSERVATION, Document, Finding, ev
from .validators import (IFSC_RE, PAN_RE, age_on, digits, fmt_amount, norm_id, norm_name, parse_date,
                         verhoeff_valid)

TOL = 0.5  # currency rounding tolerance


def _v(doc: Document, name: str):
    f = doc.fields.get(name)
    return (f, f.value) if f is not None and f.value is not None else (None, None)


def _ocr_caveat(*fs) -> str:
    low = [f for f in fs if f is not None and f.source == "ocr" and f.conf < 0.9]
    if low:
        return (" Note: " + ", ".join(f"'{f.name}' was read by OCR with confidence {f.conf:.2f}" for f in low) +
                " - re-check the original before relying on this finding.")
    return ""


def _conf(*fs, base=0.97):
    c = base
    for f in fs:
        if f is not None:
            c *= max(0.5, f.conf)
    return round(c, 2)


def check_national_id(doc: Document, out: list):
    f, v = _v(doc, "national_id")
    if f is None:
        return
    d = digits(f.raw)
    if len(d) != 12:
        out.append(F("contextual", "id_format", "National ID number has wrong length", INCONSISTENCY,
                     DETERMINISTIC, _conf(f), f"Expected 12 digits, found {len(d)} ('{f.raw}')." + _ocr_caveat(f),
                     [ev(doc, f)], ["national_id"], "medium"))
    elif not verhoeff_valid(d):
        out.append(F("contextual", "id_checksum", "National ID number fails its check digit", INCONSISTENCY,
                     DETERMINISTIC, _conf(f),
                     f"'{f.raw}' does not satisfy the Verhoeff checksum that every valid 12-digit ID number carries, "
                     f"so the number as printed cannot be a valid ID. Typical causes: a typing error or an altered "
                     f"digit." + _ocr_caveat(f), [ev(doc, f, note="Verhoeff checksum failed")], ["national_id"],
                     "high", "Verify the ID number against the identity document / issuing registry."))


def check_pan(doc: Document, out: list, name_field: str):
    f, v = _v(doc, "pan")
    if f is None:
        return
    p = norm_id(f.raw)
    if not PAN_RE.match(p):
        out.append(F("contextual", "pan_format", "PAN does not match the required format", INCONSISTENCY,
                     DETERMINISTIC, _conf(f), f"'{f.raw}' does not follow the 5-letter / 4-digit / 1-letter pattern "
                                              f"of a personal PAN." + _ocr_caveat(f),
                     [ev(doc, f)], ["pan"], "medium"))
        return
    nf, nv = _v(doc, name_field)
    if nf is not None:
        toks = norm_name(nv).split()
        if len(toks) >= 2 and p[4] != toks[-1][0].upper():
            out.append(F("contextual", "pan_surname", "PAN does not correspond to holder's surname", OBSERVATION,
                         DETERMINISTIC, 0.6,
                         f"The 5th character of an individual's PAN is normally the first letter of the surname. "
                         f"PAN '{p}' has '{p[4]}' but the surname '{toks[-1].title()}' starts with "
                         f"'{toks[-1][0].upper()}'. Surname conventions vary, so this is a weak signal.",
                         [ev(doc, f), ev(doc, nf)], ["pan", name_field], "low"))


def check_dob(doc: Document, out: list, ref_date: date | None):
    f, v = _v(doc, "date_of_birth")
    if f is None:
        return
    dob = date.fromisoformat(v)
    ref = ref_date or date.today()
    a = age_on(dob, ref)
    if a < 18 or a > 100:
        out.append(F("contextual", "dob_plausibility", "Date of birth is implausible", INCONSISTENCY,
                     DETERMINISTIC, _conf(f), f"DOB {dob:%d/%m/%Y} gives an age of {a} on {ref:%d/%m/%Y}.",
                     [ev(doc, f)], ["date_of_birth"], "medium"))
    af, av = _v(doc, "age")
    if af is not None and av != a:
        out.append(F("contextual", "age_dob_mismatch", "Stated age does not match date of birth", INCONSISTENCY,
                     DETERMINISTIC, _conf(f, af),
                     f"The form states age {av}, but a person born on {dob:%d/%m/%Y} was {a} on the application "
                     f"date {ref:%d/%m/%Y}. One of the two values is wrong." + _ocr_caveat(f, af),
                     [ev(doc, af, note=f"stated {av}"), ev(doc, f, note=f"implies {a}")],
                     ["age", "date_of_birth"], "medium"))


def check_application(doc: Document, out: list):
    df, dv = _v(doc, "application_date")
    ref = date.fromisoformat(dv) if dv else None
    if ref and ref > date.today():
        out.append(F("contextual", "future_date", "Application date is in the future", INCONSISTENCY, DETERMINISTIC,
                     _conf(df), f"Application dated {ref:%d/%m/%Y}.", [ev(doc, df)], ["application_date"]))
    check_dob(doc, out, ref)
    check_national_id(doc, out)
    check_pan(doc, out, "applicant_name")


def check_identity(doc: Document, out: list):
    check_dob(doc, out, None)
    check_national_id(doc, out)


def check_salary_slip(doc: Document, out: list):
    g = {k: _v(doc, k) for k in ("basic", "hra", "special_allowance", "gross_earnings", "provident_fund",
                                 "income_tax", "total_deductions", "net_pay")}
    gross_ok = ded_ok = None
    comps = [g[k] for k in ("basic", "hra", "special_allowance") if g[k][0] is not None]
    gf, gv = g["gross_earnings"]
    if gf is not None and len(comps) == 3:
        s = sum(v for _, v in comps)
        gross_ok = abs(s - gv) <= TOL
        if not gross_ok:
            out.append(F("contextual", "slip_gross_sum", "Earnings components do not add up to gross",
                         INCONSISTENCY, DETERMINISTIC, _conf(gf, *[f for f, _ in comps]),
                         f"Basic + HRA + Special = {fmt_amount(s)}, but Gross Earnings shows {fmt_amount(gv)} "
                         f"(difference {fmt_amount(gv - s)}).", [ev(doc, gf)] + [ev(doc, f) for f, _ in comps],
                         ["gross_earnings"], "high"))
    df, dv = g["total_deductions"]
    dcomps = [g[k] for k in ("provident_fund", "income_tax") if g[k][0] is not None]
    if df is not None and len(dcomps) == 2:
        s = sum(v for _, v in dcomps)
        ded_ok = abs(s - dv) <= TOL
        if not ded_ok:
            out.append(F("contextual", "slip_deduction_sum", "Deduction components do not add up", INCONSISTENCY,
                         DETERMINISTIC, _conf(df, *[f for f, _ in dcomps]),
                         f"PF + Tax = {fmt_amount(s)}, but Total Deductions shows {fmt_amount(dv)}.",
                         [ev(doc, df)] + [ev(doc, f) for f, _ in dcomps], ["total_deductions"], "high"))
    nf, nv = g["net_pay"]
    if gf is not None and df is not None and nf is not None:
        expected = gv - dv
        if abs(expected - nv) > TOL:
            culprit = ""
            if gross_ok and ded_ok:
                culprit = (" Because the earnings and deduction components are internally consistent, the Net Pay "
                           "figure is the one that does not fit.")
            out.append(F("contextual", "slip_net_arithmetic", "Net pay does not equal gross minus deductions",
                         INCONSISTENCY, DETERMINISTIC, _conf(gf, df, nf),
                         f"Gross {fmt_amount(gv)} - Deductions {fmt_amount(dv)} = {fmt_amount(expected)}, but the "
                         f"slip shows Net Pay {fmt_amount(nv)} (difference {fmt_amount(nv - expected)})." + culprit
                         + _ocr_caveat(gf, df, nf),
                         [ev(doc, nf, note=f"expected {fmt_amount(expected)}"), ev(doc, gf), ev(doc, df)],
                         ["net_pay", "gross_earnings", "total_deductions"], "high",
                         "Obtain payroll confirmation from the employer."))
    check_pan(doc, out, "employee_name")


def check_bank(doc: Document, out: list):
    f, v = _v(doc, "ifsc")
    if f is not None and not IFSC_RE.match(norm_id(f.raw)):
        out.append(F("contextual", "ifsc_format", "IFSC code has an invalid format", INCONSISTENCY, DETERMINISTIC,
                     _conf(f), f"'{f.raw}' is not a valid 11-character IFSC (4 letters, '0', 6 alphanumerics)."
                     + _ocr_caveat(f), [ev(doc, f)], ["ifsc"], "medium"))
    if not doc.tables:
        return
    rows = doc.tables[0]["rows"]
    of, ov = _v(doc, "opening_balance")
    prev = ov
    prev_date = None
    period = _v(doc, "statement_period")[1]
    pstart = pend = None
    if period:
        import re
        ds = re.findall(r"\d{1,2}/\d{1,2}/\d{4}", period)
        if len(ds) == 2:
            pstart, pend = parse_date(ds[0]), parse_date(ds[1])
    for i, r in enumerate(rows):
        bcell = r["cells"].get("balance")
        if r["balance"] is None or bcell is None:
            continue
        if prev is not None:
            exp = prev - (r["debit"] or 0) + (r["credit"] or 0)
            if abs(exp - r["balance"]) > TOL:
                # One wrong printed balance breaks two equations (its own row and the next). If the next row is
                # consistent with the *computed* balance, the printed figure in this row is the culprit.
                nxt = rows[i + 1] if i + 1 < len(rows) else None
                single = nxt is not None and nxt["balance"] is not None and \
                    abs(exp - (nxt["debit"] or 0) + (nxt["credit"] or 0) - nxt["balance"]) <= TOL
                out.append(F("contextual", "running_balance", f"Running balance breaks on {r['cells'].get('date', {}).get('text', f'row {i + 1}')}",
                             INCONSISTENCY, DETERMINISTIC, round(0.97 * bcell["conf"], 2),
                             f"Previous balance {fmt_amount(prev)} - debit {fmt_amount(r['debit'] or 0)} + credit "
                             f"{fmt_amount(r['credit'] or 0)} = {fmt_amount(exp)}, but the statement shows "
                             f"{fmt_amount(r['balance'])} (difference {fmt_amount(r['balance'] - exp)}). Bank systems "
                             f"compute balances automatically, so a break indicates an edited or retyped figure."
                             + (" The following row is consistent with the computed balance, so this printed "
                                "balance is the single figure that does not fit." if single else ""),
                             [ev(doc, bbox=bcell["bbox"], page=r["page"], value=bcell["text"],
                                 field_name=f"row{i + 1}_balance", note=f"expected {fmt_amount(exp)}"),
                              ev(doc, bbox=r["bbox"], page=r["page"], value=r["description"],
                                 field_name=f"row{i + 1}", note="transaction row")],
                             [f"row{i + 1}_balance"], "high", "Request the statement directly from the bank."))
                carry = exp if single else r["balance"]
            else:
                carry = r["balance"]
        else:
            carry = r["balance"]
        prev = carry
        if r["date"]:
            d = date.fromisoformat(r["date"])
            if prev_date and d < prev_date:
                out.append(F("contextual", "date_order", "Transactions out of chronological order", INCONSISTENCY,
                             DETERMINISTIC, 0.8, f"{d:%d/%m/%Y} appears after {prev_date:%d/%m/%Y}.",
                             [ev(doc, bbox=r["bbox"], page=r["page"], value=r["description"],
                                 field_name=f"row{i + 1}")], [f"row{i + 1}"], "medium"))
            if pstart and pend and not (pstart <= d <= pend):
                out.append(F("contextual", "date_outside_period", "Transaction outside the statement period",
                             INCONSISTENCY, DETERMINISTIC, 0.85,
                             f"{d:%d/%m/%Y} is outside {pstart:%d/%m/%Y} - {pend:%d/%m/%Y}.",
                             [ev(doc, bbox=r["bbox"], page=r["page"], value=r["description"],
                                 field_name=f"row{i + 1}")], [f"row{i + 1}"], "medium"))
            prev_date = d
    cf, cv = _v(doc, "closing_balance")
    if cf is not None and rows and rows[-1]["balance"] is not None and abs(rows[-1]["balance"] - cv) > TOL:
        out.append(F("contextual", "closing_balance", "Closing balance differs from last transaction balance",
                     INCONSISTENCY, DETERMINISTIC, _conf(cf),
                     f"Last row balance {fmt_amount(rows[-1]['balance'])} vs closing balance {fmt_amount(cv)}.",
                     [ev(doc, cf)], ["closing_balance"], "high"))


def check_structure(doc: Document, out: list):
    miss = doc.metadata.get("missing_fields") or []
    if miss:
        out.append(F("structural", "missing_fields", f"{len(miss)} expected field(s) not found",
                     INCONSISTENCY if len(miss) <= 3 else OBSERVATION, HEURISTIC, 0.6,
                     f"A {doc.doc_type.replace('_', ' ')} normally contains: {', '.join(miss)}. They were not found. "
                     f"Either the information is missing from the document or extraction failed (e.g. poor scan "
                     f"quality) - check the original.", [ev(doc, bbox=None, page=0, note="missing: " + ", ".join(miss))],
                     miss, "medium"))
    for d in doc.metadata.get("duplicate_labels") or []:
        out.append(F("structural", "duplicate_field", f"Field '{d['field']}' appears {d['count']} times",
                     INCONSISTENCY, HEURISTIC, 0.7,
                     "The same field label is printed more than once; one of the values may have been added.",
                     [ev(doc, bbox=b, page=0, field_name=d["field"]) for b in d["bboxes"]], [d["field"]], "medium"))


CHECKS = {"application_form": check_application, "identity_card": check_identity,
          "salary_slip": check_salary_slip, "bank_statement": check_bank}


def analyse(doc: Document) -> list[Finding]:
    out: list[Finding] = []
    fn = CHECKS.get(doc.doc_type)
    if fn:
        fn(doc, out)
        check_structure(doc, out)
    return out
