"""Synthetic demonstration dataset generator.

Creates fictional "loan application" cases (application form, identity card,
salary slip, bank statement). Every person, organisation and number is made up
and every document is stamped SYNTHETIC SPECIMEN. Tampered cases are produced by
applying realistic edits to genuine documents, and every edit is written to
ground_truth.json so detection accuracy can be measured.

Run:  python -m datagen.generate
"""
from __future__ import annotations

import io
import json
import math
import random
import shutil
import sys
from datetime import date
from pathlib import Path

import fitz  # PyMuPDF
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.validators import fmt_amount, verhoeff_check_digit  # noqa: E402

OUT = ROOT / "samples"
SCALE = 2.0  # image render scale (pt -> px), same zoom the pipeline uses for PDFs
FONT_FILES = {
    "helv": "C:/Windows/Fonts/arial.ttf",
    "hebo": "C:/Windows/Fonts/arialbd.ttf",
    "tiro": "C:/Windows/Fonts/times.ttf",
    "cour": "C:/Windows/Fonts/cour.ttf",
}
_font_cache: dict = {}


def pil_font(name: str, size_px: float) -> ImageFont.FreeTypeFont:
    key = (name, round(size_px, 1))
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(FONT_FILES[name], int(round(size_px)))
    return _font_cache[key]


def text_bbox_pt(text: str, x: float, y: float, font: str, size: float) -> list[float]:
    f = pil_font(font, size * 4)
    l, t, r, b = f.getbbox(text, anchor="ls")
    return [x + l / 4, y + t / 4, x + r / 4, y + b / 4]


# ----------------------------------------------------------------------------- signatures
def make_signature(seed: int, jitter: int = 0, w: int = 320, h: int = 110, color=(20, 40, 140)) -> Image.Image:
    """A person's signature = fixed 'style' from seed; jitter gives natural variation between signings."""
    base = random.Random(seed)
    jit = random.Random(seed * 1000 + jitter)
    n = base.randint(7, 10)
    pts = []
    for i in range(n * 6):
        t = i / (n * 6 - 1)
        x = 15 + t * (w - 40)
        y = h / 2 + math.sin(t * base.uniform(9, 15) + base.uniform(0, 3)) * base.uniform(18, 30) * (1 - 0.5 * t)
        y += math.sin(t * base.uniform(30, 45)) * base.uniform(5, 12)
        if jitter:
            x += jit.gauss(0, 2.5)
            y += jit.gauss(0, 3.5)
        pts.append((x, y))
    img = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    d = ImageDraw.Draw(img)
    d.line(pts, fill=color + (255,), width=3, joint="curve")
    # underline flourish
    fx = base.uniform(0.2, 0.4) * w
    d.line([(fx, h * 0.8 + (jit.gauss(0, 2) if jitter else 0)), (w - 20, h * 0.72)], fill=color + (255,), width=2)
    return img


def png_bytes(img: Image.Image) -> bytes:
    b = io.BytesIO()
    img.save(b, "PNG")
    return b.getvalue()


# ----------------------------------------------------------------------------- page model
class Page:
    """Resolution-independent drawing ops (points), rendered to PDF or to a scanned image."""

    def __init__(self, width: float, height: float):
        self.w, self.h = width, height
        self.ops: list[dict] = []
        self.fields: dict[str, list[float]] = {}  # field -> value bbox (pt)

    def text(self, x, y, s, font="helv", size=10.5, color=(0, 0, 0), field=None):
        self.ops.append(dict(op="text", x=x, y=y, s=s, font=font, size=size, color=color))
        if field:
            self.fields[field] = text_bbox_pt(s, x, y, font, size)

    def line(self, x0, y0, x1, y1, color=(0.4, 0.4, 0.4), width=0.8):
        self.ops.append(dict(op="line", p=(x0, y0, x1, y1), color=color, width=width))

    def rect(self, x0, y0, x1, y1, color=(0.4, 0.4, 0.4), fill=None, width=0.8):
        self.ops.append(dict(op="rect", r=(x0, y0, x1, y1), color=color, fill=fill, width=width))

    def image(self, x0, y0, x1, y1, img: Image.Image, field=None):
        self.ops.append(dict(op="image", r=(x0, y0, x1, y1), img=img))
        if field:
            self.fields[field] = [x0, y0, x1, y1]

    # ---------------- renderers
    def to_pdf(self, path: Path, title: str):
        doc = fitz.open()
        pg = doc.new_page(width=self.w, height=self.h)
        for o in self.ops:
            if o["op"] == "text":
                pg.insert_text((o["x"], o["y"]), o["s"], fontname=o["font"], fontsize=o["size"], color=o["color"])
            elif o["op"] == "line":
                x0, y0, x1, y1 = o["p"]
                pg.draw_line((x0, y0), (x1, y1), color=o["color"], width=o["width"])
            elif o["op"] == "rect":
                pg.draw_rect(fitz.Rect(o["r"]), color=o["color"], fill=o["fill"], width=o["width"])
            elif o["op"] == "image":
                pg.insert_image(fitz.Rect(o["r"]), stream=png_bytes(o["img"]))
        stamp = "D:20261004101500+05'30'"
        doc.set_metadata({"title": title, "author": "Synthetic DocGen", "creator": "Synthetic DocGen 1.0",
                          "producer": "Synthetic DocGen 1.0", "creationDate": stamp, "modDate": stamp})
        doc.save(str(path), garbage=3, deflate=True)
        doc.close()

    def to_image(self, path: Path, quality=88, noise=5.0, seed=0) -> None:
        s = SCALE
        img = Image.new("RGB", (int(self.w * s), int(self.h * s)), (255, 255, 255))
        d = ImageDraw.Draw(img)
        to255 = lambda c: tuple(int(v * 255) if isinstance(v, float) or v <= 1 else v for v in c)  # noqa: E731
        for o in self.ops:
            if o["op"] == "text":
                d.text((o["x"] * s, o["y"] * s), o["s"], font=pil_font(o["font"], o["size"] * s),
                       fill=to255(o["color"]), anchor="ls")
            elif o["op"] == "line":
                x0, y0, x1, y1 = o["p"]
                d.line([(x0 * s, y0 * s), (x1 * s, y1 * s)], fill=to255(o["color"]), width=max(1, int(o["width"] * s)))
            elif o["op"] == "rect":
                x0, y0, x1, y1 = o["r"]
                d.rectangle([x0 * s, y0 * s, x1 * s, y1 * s], outline=to255(o["color"]) if o["color"] else None,
                            fill=to255(o["fill"]) if o["fill"] else None, width=max(1, int(o["width"] * s)))
            elif o["op"] == "image":
                x0, y0, x1, y1 = [int(v * s) for v in o["r"]]
                im = o["img"].resize((x1 - x0, y1 - y0), Image.LANCZOS)
                img.paste(im, (x0, y0), im)
        img = scan_effect(img, noise, seed)
        img.save(str(path), "JPEG", quality=quality)


def scan_effect(img: Image.Image, noise: float, seed: int) -> Image.Image:
    rng = np.random.default_rng(seed)
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    a = np.asarray(img).astype(np.float32)
    a = a * 0.97 + 4  # slight paper tone
    a += rng.normal(0, noise, a.shape[:2])[..., None]
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def px(b):
    return [round(v * SCALE, 1) for v in b]


# ----------------------------------------------------------------------------- document templates
A4 = (595, 842)
LX, VX, STEP = 55, 235, 23


def header(p: Page, org: str, title: str, subtitle: str = ""):
    p.rect(0, 0, p.w, 62, color=None, fill=(0.85, 0.89, 0.95))
    p.text(LX, 34, org, font="hebo", size=17, color=(0.08, 0.16, 0.35))
    p.text(LX, 52, "SYNTHETIC SPECIMEN - FOR DEMONSTRATION ONLY", font="helv", size=7.5, color=(0.5, 0.2, 0.2))
    p.text(LX, 96, title, font="hebo", size=14)
    if subtitle:
        p.text(LX, 114, subtitle, font="helv", size=9.5, color=(0.3, 0.3, 0.3))
    p.line(LX, 124, p.w - LX, 124)


def rows(p: Page, y: float, items: list[tuple[str, str, str]], vsize=10.5):
    for label, value, fname in items:
        p.text(LX, y, label, font="hebo", size=10)
        p.text(VX, y, value, font="helv", size=vsize, field=fname)
        y += STEP
    return y


def application_form(P: dict, sig: Image.Image) -> Page:
    p = Page(*A4)
    header(p, "Northwind Bank", "Personal Loan Application Form", f"Application No: {P['app_no']}")
    y = rows(p, 152, [
        ("Application Date", P["app_date"], "application_date"),
        ("Applicant Name", P["name_form"], "applicant_name"),
        ("Date of Birth", P["dob_form"], "date_of_birth"),
        ("Age (years)", str(P["age_form"]), "age"),
        ("Gender", P["gender"], "gender"),
        ("PAN", P["pan_form"], "pan"),
        ("National ID No", P["id_form_fmt"], "national_id"),
        ("Residential Address", P["address_form"], "address"),
        ("Mobile", P["mobile"], "mobile"),
        ("Employer", P["employer_form"], "employer"),
        ("Monthly Income (INR)", fmt_amount(P["income_form"]), "monthly_income"),
        ("Loan Amount (INR)", fmt_amount(P["loan"]), "loan_amount"),
        ("Loan Purpose", P["purpose"], "loan_purpose"),
    ], vsize=10)
    p.line(LX, y, p.w - LX, y)
    p.text(LX, y + 22, "Declaration: I confirm that the information provided above is true and complete.", size=9)
    p.text(LX, y + 36, "I authorise the bank to verify the documents submitted with this application.", size=9)
    sy = y + 120
    p.image(LX, sy - 62, LX + 170, sy - 4, sig, field="applicant_signature")
    p.line(LX, sy, LX + 190, sy)
    p.text(LX, sy + 14, "Applicant Signature", font="hebo", size=9.5)
    p.text(360, sy + 14, f"Place: {P['city']}", size=9.5)
    return p


def id_card(P: dict, sig: Image.Image) -> Page:
    p = Page(500, 315)
    p.rect(0, 0, 500, 52, color=None, fill=(0.80, 0.90, 0.85))
    p.text(18, 26, "Identity Card", font="hebo", size=16, color=(0.05, 0.3, 0.2))
    p.text(18, 43, "SYNTHETIC SPECIMEN - NOT A REAL IDENTITY DOCUMENT", size=7)
    p.rect(18, 66, 118, 186, color=(0.4, 0.4, 0.4), fill=(0.88, 0.88, 0.88))
    p.text(44, 132, "PHOTO", font="helv", size=10, color=(0.5, 0.5, 0.5))
    x0, x1, y = 135, 228, 84
    for label, value, fname in [("Name", P["name_id"], "name"), ("Date of Birth", P["dob_id"], "date_of_birth"),
                                ("Gender", P["gender"], "gender"), ("ID No", P["id_card_fmt"], "national_id")]:
        p.text(x0, y, label, font="hebo", size=9.5)
        p.text(x1, y, value, size=10.5, field=fname)
        y += 24
    p.text(x0, y, "Address", font="hebo", size=9.5)
    p.text(x1, y, P["address_id_1"], size=9, field="address")
    p.text(x1, y + 14, P["address_id_2"], size=9, field="address_line2")
    p.image(300, 222, 440, 268, sig, field="holder_signature")
    p.line(300, 272, 470, 272)
    p.text(300, 286, "Signature", font="hebo", size=9)
    return p


def salary_slip(P: dict, sig) -> Page:
    p = Page(*A4)
    header(p, P["employer_slip"], f"Salary Slip - {P['month']}", "Private & Confidential")
    y = rows(p, 152, [
        ("Employee Name", P["name_slip"], "employee_name"),
        ("Employee ID", P["emp_id"], "employee_id"),
        ("Designation", P["designation"], "designation"),
        ("PAN", P["pan_slip"], "pan"),
        ("Pay Period", P["month"], "pay_period"),
        ("Salary Account", P["account_masked"], "salary_account"),
    ])
    p.line(LX, y - 8, p.w - LX, y - 8)
    p.text(LX, y + 10, "Earnings & Deductions", font="hebo", size=11)
    y = rows(p, y + 36, [
        ("Basic Salary", fmt_amount(P["basic"]), "basic"),
        ("House Rent Allowance", fmt_amount(P["hra"]), "hra"),
        ("Special Allowance", fmt_amount(P["special"]), "special_allowance"),
        ("Gross Earnings", fmt_amount(P["gross"]), "gross_earnings"),
        ("Provident Fund", fmt_amount(P["pf"]), "provident_fund"),
        ("Income Tax (TDS)", fmt_amount(P["tds"]), "income_tax"),
        ("Total Deductions", fmt_amount(P["deductions"]), "total_deductions"),
        ("Net Pay (INR)", fmt_amount(P["net_printed"]), "net_pay"),
    ])
    p.line(LX, y - 8, p.w - LX, y - 8)
    p.text(LX, y + 14, "This is a system generated salary slip.", size=8.5, color=(0.35, 0.35, 0.35))
    sy = y + 110
    if sig is not None:
        p.image(360, sy - 60, 520, sy - 4, sig, field="authorised_signature")
    p.line(360, sy, 540, sy)
    p.text(360, sy + 14, "Authorised Signatory", font="hebo", size=9.5)
    return p


def bank_statement(P: dict) -> Page:
    p = Page(*A4)
    header(p, "Northwind Bank", "Account Statement", f"Statement Period: {P['period']}")
    y = rows(p, 152, [
        ("Account Holder", P["name_bank"], "account_holder"),
        ("Address", P["address_bank"], "address"),
        ("Account No", P["account_no"], "account_number"),
        ("IFSC", P["ifsc"], "ifsc"),
        ("Opening Balance", fmt_amount(P["opening"]), "opening_balance"),
    ], vsize=10)
    y += 8
    cols = [(LX, "Date"), (125, "Description"), (330, "Debit"), (410, "Credit"), (490, "Balance")]
    p.rect(LX - 4, y - 14, p.w - LX + 4, y + 6, color=None, fill=(0.9, 0.9, 0.9))
    for x, h in cols:
        p.text(x, y, h, font="hebo", size=9.5)
    y += 22
    for i, t in enumerate(P["txns"]):
        p.text(cols[0][0], y, t["date"], size=9, field=f"txn{i}_date")
        p.text(cols[1][0], y, t["desc"], size=9, field=f"txn{i}_desc")
        if t["debit"]:
            p.text(cols[2][0], y, fmt_amount(t["debit"]), size=9, field=f"txn{i}_debit")
        if t["credit"]:
            p.text(cols[3][0], y, fmt_amount(t["credit"]), size=9, field=f"txn{i}_credit")
        p.text(cols[4][0], y, fmt_amount(t["balance_printed"]), size=9, field=f"txn{i}_balance")
        y += 20
    p.line(LX, y - 8, p.w - LX, y - 8)
    y += 12
    p.text(LX, y, "Closing Balance", font="hebo", size=10)
    p.text(VX, y, fmt_amount(P["closing_printed"]), size=10, field="closing_balance")
    p.text(LX, y + 40, "This statement is computer generated and does not require a signature.", size=8.5,
           color=(0.35, 0.35, 0.35))
    return p


# ----------------------------------------------------------------------------- people / cases
def national_id(seed: int) -> str:
    r = random.Random(seed)
    body = str(r.randint(2, 9)) + "".join(str(r.randint(0, 9)) for _ in range(10))
    return body + verhoeff_check_digit(body)


def fmt_id(n: str) -> str:
    return f"{n[0:4]} {n[4:8]} {n[8:12]}"


def build_person(seed, name, surname_initial, dob, gender, address1, address2, city, employer, basic, hra, special,
                 pf, tds, opening, spend, loan, purpose, designation):
    nid = national_id(seed)
    r = random.Random(seed)
    pan = "".join(r.choice("ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(3)) + "P" + surname_initial + \
        f"{r.randint(1000, 9999)}" + r.choice("ABCDEFGHJKLMNPQRSTUVWXYZ")
    gross = basic + hra + special
    ded = pf + tds
    net = gross - ded
    acct = f"5010{r.randint(10 ** 9, 10 ** 10 - 1)}"
    bal = opening
    txns = []
    for d, desc, amt in spend:
        bal -= amt
        txns.append(dict(date=d, desc=desc, debit=amt, credit=0, balance=bal))
    bal += net
    txns.append(dict(date="30/09/2026", desc=f"SALARY CREDIT {employer.split()[0].upper()}", debit=0, credit=net,
                     balance=bal))
    for t in txns:
        t["balance_printed"] = t["balance"]
    app_date = date(2026, 10, 5)
    dd, mm, yy = map(int, dob.split("/"))
    age = app_date.year - yy - ((app_date.month, app_date.day) < (mm, dd))
    full_addr = f"{address1}, {address2}"
    return dict(
        seed=seed, name_form=name, name_id=name, name_slip=name, name_bank=name.upper(), dob_form=dob, dob_id=dob,
        age_form=age, gender=gender, pan_form=pan, pan_slip=pan, id_form_fmt=fmt_id(nid), id_card_fmt=fmt_id(nid),
        address_form=full_addr, address_id_1=address1 + ",", address_id_2=address2, address_bank=full_addr,
        city=city, mobile=f"+91 9{r.randint(100000000, 999999999)}", employer_form=employer, employer_slip=employer,
        income_form=gross, basic=basic, hra=hra, special=special, gross=gross, pf=pf, tds=tds, deductions=ded,
        net=net, net_printed=net, loan=loan, purpose=purpose, designation=designation,
        emp_id=f"EMP{r.randint(10000, 99999)}", month="September 2026", account_no=acct,
        account_masked="XXXXXX" + acct[-4:], ifsc=f"NWBK000{r.randint(1000, 9999)}", period="01/09/2026 to 30/09/2026",
        opening=opening, txns=txns, closing_printed=bal, app_no=f"PL-2026-{r.randint(100000, 999999)}",
        app_date=app_date.strftime("%d/%m/%Y"),
    )


SPEND = [("03/09/2026", "UPI/GROCERY MART", 2340.0), ("07/09/2026", "RENT TRANSFER", 25000.0),
         ("12/09/2026", "ATM WITHDRAWAL", 5000.0), ("18/09/2026", "UPI/ELECTRICITY BILL", 1870.0)]


def tamper_image_value(path: Path, bbox_pt, new_text, font="tiro", size=13.5, dy_pt=2.6, quality=88):
    """Paste a replacement value over a scanned field: white patch + new text + re-save (classic splice)."""
    img = Image.open(path).convert("RGB")
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = bbox_pt
    pad = 3
    patch = [int((x0 - pad) * SCALE), int((y0 - pad) * SCALE), int((x1 + 40) * SCALE), int((y1 + pad) * SCALE)]
    d.rectangle(patch, fill=(250, 250, 250))
    d.text((x0 * SCALE, (y1 - 1 + dy_pt) * SCALE), new_text, font=pil_font(font, size * SCALE), fill=(10, 10, 10),
           anchor="ls")
    img.save(str(path), "JPEG", quality=quality)
    return patch


def tamper_pdf_value(path: Path, bbox_pt, new_text, font="tiro", size=10.5):
    """Cover a value with a white box, type a new one on top, save incrementally with an editor's metadata."""
    doc = fitz.open(str(path))
    pg = doc[0]
    x0, y0, x1, y1 = bbox_pt
    r = fitz.Rect(x0 - 2, y0 - 2, x1 + 30, y1 + 3)
    pg.draw_rect(r, color=None, fill=(1, 1, 1), overlay=True)
    pg.insert_text((x0, y1 - 1.5), new_text, fontname=font, fontsize=size)
    md = doc.metadata
    md["producer"] = "QuickPDF Editor 7.2"
    md["modDate"] = "D:20261005184211+05'30'"
    doc.set_metadata(md)
    doc.save(str(path), incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
    doc.close()
    return [v * SCALE for v in (r.x0, r.y0, r.x1, r.y1)]


def gt(doc, kind, field=None, bbox=None, other_doc=None, note=""):
    return dict(doc=doc, kind=kind, field=field, bbox=bbox, other_doc=other_doc, note=note)


def make_case(case_dir: Path, P: dict, formats: dict, sigs: dict, slip_sig=True):
    case_dir.mkdir(parents=True, exist_ok=True)
    pages = {
        "application_form": application_form(P, sigs["form"]),
        "identity_card": id_card(P, sigs["id"]),
        "salary_slip": salary_slip(P, sigs["employer"] if slip_sig else None),
        "bank_statement": bank_statement(P),
    }
    files = {}
    for i, (kind, page) in enumerate(pages.items()):
        fmt = formats[kind]
        fn = f"{kind}.{fmt}"
        if fmt == "pdf":
            page.to_pdf(case_dir / fn, kind.replace("_", " ").title())
        else:
            page.to_image(case_dir / fn, seed=P["seed"] * 10 + i)
        files[kind] = (fn, page)
    return files


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    truth = {}

    # ---------------- Case 1: genuine & consistent
    P = build_person(11, "Ananya Sharma", "S", "14/03/1992", "Female", "Flat 12B, Lotus Residency, MG Road",
                     "Pune, Maharashtra 411001", "Pune", "Brightwave Technologies Pvt Ltd", 46000, 18400, 27600, 5520,
                     7480, 124350.0, SPEND, 1500000, "Home renovation", "Senior Software Engineer")
    sig = 101
    make_case(OUT / "case_01_genuine", P,
              dict(application_form="pdf", identity_card="jpg", salary_slip="pdf", bank_statement="pdf"),
              dict(form=make_signature(sig, 1), id=make_signature(sig, 2), employer=make_signature(901, 1)))
    truth["case_01_genuine"] = {"description": "Genuine, mutually consistent documents. Expect no inconsistencies.",
                                "expected": []}

    # ---------------- Case 2: visual tampering (income inflated)
    P = build_person(22, "Rohan Mehta", "M", "02/11/1989", "Male", "House 44, Green Park Colony, Sector 12",
                     "Jaipur, Rajasthan 302012", "Jaipur", "Kestrel Logistics Pvt Ltd", 29000, 11600, 17400, 3480,
                     5020, 38210.0, SPEND, 2500000, "Vehicle purchase", "Operations Executive")
    id_sig = make_signature(202, 2)
    cdir = OUT / "case_02_visual_tamper"
    files = make_case(cdir, P, dict(application_form="pdf", identity_card="jpg", salary_slip="jpg",
                                    bank_statement="pdf"),
                      dict(form=id_sig, id=id_sig, employer=make_signature(902, 1)))  # same pixels = pasted signature
    slip_page = files["salary_slip"][1]
    fake_net = 94500.0
    patch = tamper_image_value(cdir / "salary_slip.jpg", slip_page.fields["net_pay"], fmt_amount(fake_net))
    form_page = files["application_form"][1]
    fake_income = 95000.0
    rect = tamper_pdf_value(cdir / "application_form.pdf", form_page.fields["monthly_income"], fmt_amount(fake_income))
    truth["case_02_visual_tamper"] = {
        "description": "Net pay on scanned salary slip spliced (49,500 -> 94,500); declared monthly income on the "
                       "digital form overwritten with a white box (58,000 -> 95,000) and re-saved by a PDF editor; "
                       "the applicant's signature on the form is a pixel copy of the ID card signature.",
        "expected": [
            gt("salary_slip.jpg", "visual_tamper", "net_pay", patch, note="spliced value region"),
            gt("salary_slip.jpg", "arithmetic", "net_pay", note="gross - deductions != net pay"),
            gt("salary_slip.jpg", "cross_mismatch", "net_pay", other_doc="bank_statement.pdf",
               note="salary credit 49,500 vs slip net 94,500"),
            gt("application_form.pdf", "overlay_hidden_text", "monthly_income", rect,
               note="original 58,000.00 still in text layer under white box"),
            gt("application_form.pdf", "font_inconsistency", "monthly_income", rect),
            gt("application_form.pdf", "cross_mismatch", "monthly_income", other_doc="salary_slip.jpg",
               note="declared income 95,000 vs slip gross 58,000"),
            gt("application_form.pdf", "signature_copy", "applicant_signature", other_doc="identity_card.jpg"),
        ]}

    # ---------------- Case 3: contextual inconsistencies (all visually clean)
    P = build_person(33, "Priya Nair", "N", "22/07/1990", "Female", "No. 7, Lakeview Apartments, Kakkanad",
                     "Kochi, Kerala 682030", "Kochi", "Orion Analytics Pvt Ltd", 37500, 15000, 22500, 4500, 5300,
                     61540.0, SPEND, 1200000, "Education", "Data Analyst")
    P["name_id"] = "Priya Nayar"                       # spelling variant on ID card
    P["dob_id"] = "22/07/1988"                         # DOB conflict
    P["age_form"] = 34                                 # true age on 05/10/2026 is 36
    good = P["id_form_fmt"].replace(" ", "")
    bad = good[:-1] + str((int(good[-1]) + 3) % 10)    # one digit off -> breaks checksum & cross-match
    P["id_form_fmt"] = fmt_id(bad)
    P["employer_form"] = "Orion Analytics Ltd"         # benign variation (should NOT be flagged as conflict)
    P["net_printed"] = P["net"] + 2000                 # slip arithmetic error
    P["address_bank"] = "22 Residency Road, Bengaluru, Karnataka 560025"  # different address
    t = P["txns"][2]
    t["balance_printed"] = t["balance"] + 1000         # running balance broken on 12/09 row
    make_case(OUT / "case_03_contextual", P,
              dict(application_form="pdf", identity_card="jpg", salary_slip="pdf", bank_statement="jpg"),
              dict(form=make_signature(303, 1), id=make_signature(303, 2), employer=None), slip_sig=False)
    truth["case_03_contextual"] = {
        "description": "Visually clean documents with contextual problems: name spelling variant, DOB conflict, "
                       "stated age inconsistent with DOB, ID number mistyped (checksum fails), slip arithmetic "
                       "error, salary credit different from slip, broken running balance, different address on "
                       "bank statement, missing authorised signature on salary slip.",
        "expected": [
            gt("identity_card.jpg", "cross_mismatch", "name", other_doc="application_form.pdf"),
            gt("application_form.pdf", "cross_mismatch", "date_of_birth", other_doc="identity_card.jpg"),
            gt("application_form.pdf", "age_dob", "age"),
            gt("application_form.pdf", "checksum", "national_id"),
            gt("application_form.pdf", "cross_mismatch", "national_id", other_doc="identity_card.jpg"),
            gt("salary_slip.pdf", "arithmetic", "net_pay"),
            gt("bank_statement.jpg", "cross_mismatch", "salary_credit", other_doc="salary_slip.pdf"),
            gt("bank_statement.jpg", "running_balance", "balance"),
            gt("bank_statement.jpg", "cross_mismatch", "address", other_doc="application_form.pdf"),
            gt("salary_slip.pdf", "missing_signature", "authorised_signature"),
        ]}

    # ---------------- Robustness samples
    misc = OUT / "misc_failure_handling"
    misc.mkdir()
    (misc / "corrupted_upload.pdf").write_bytes(b"%PDF-1.7\n" + bytes(random.Random(5).randrange(256)
                                                                        for _ in range(4000)))
    note = Page(420, 260)
    note.text(30, 50, "Meeting notes", font="hebo", size=16)
    note.text(30, 90, "Discuss quarterly roadmap and hiring plan.", size=11)
    note.text(30, 112, "Follow up with design team on Friday.", size=11)
    note.to_image(misc / "unrelated_note.jpg", seed=7)
    truth["misc_failure_handling"] = {"description": "A corrupted PDF and an unsupported document type. Expect safe "
                                                     "failure and honest 'unsupported' reporting.", "expected": []}

    (OUT / "ground_truth.json").write_text(json.dumps(truth, indent=2))
    print("Generated:", ", ".join(sorted(p.name for p in OUT.iterdir())))


if __name__ == "__main__":
    main()
