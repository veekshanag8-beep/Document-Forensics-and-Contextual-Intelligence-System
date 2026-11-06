"""Build the hackathon presentation: deliverables/DocForensics_Presentation.pptx

    python scripts/build_deck.py      (run scripts/record_demo.py first so screenshots exist)
"""
from pathlib import Path

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION, XL_LABEL_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "deliverables" / "screenshots"
OUT = ROOT / "deliverables" / "DocForensics_Presentation.pptx"
REPO = "github.com/veekshanag8-beep/Document-Forensics-and-Contextual-Intelligence-System"

INK = RGBColor(0x0F, 0x1B, 0x2D)
NAVY = RGBColor(0x1B, 0x2A, 0x41)
AMBER = RGBColor(0xF2, 0xA9, 0x3B)
RED = RGBColor(0xD7, 0x26, 0x3D)
ORANGE = RGBColor(0xE0, 0x7A, 0x10)
BLUE = RGBColor(0x2F, 0x6F, 0xD6)
GREEN = RGBColor(0x1F, 0x8A, 0x4C)
SLATE = RGBColor(0x5B, 0x6B, 0x7F)
TEXT = RGBColor(0x1F, 0x29, 0x33)
LIGHT = RGBColor(0xF1, 0xF4, 0xF8)
LINE = RGBColor(0xD5, 0xDC, 0xE5)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
ICE = RGBColor(0xC8, 0xD3, 0xE0)
HEAD, BODY = "Cambria", "Calibri"

prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
BLANK = prs.slide_layouts[6]
SW = 13.333


def bg(slide, color):
    f = slide.background.fill
    f.solid()
    f.fore_color.rgb = color


def text(slide, x, y, w, h, runs, size=16, color=TEXT, font=BODY, bold=False, align=PP_ALIGN.LEFT,
         anchor=MSO_ANCHOR.TOP, italic=False, spacing=None, name=None):
    """runs: str | list of paragraphs; a paragraph is str or list of (text, {opts})."""
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    if name:
        tb.name = name
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    paras = runs if isinstance(runs, list) else [runs]
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        if spacing:
            p.space_after = Pt(spacing)
        parts = para if isinstance(para, list) else [(para, {})]
        for t, o in parts:
            r = p.add_run()
            r.text = t
            f = r.font
            f.name = o.get("font", font)
            f.size = Pt(o.get("size", size))
            f.bold = o.get("bold", bold)
            f.italic = o.get("italic", italic)
            f.color.rgb = o.get("color", color)
    return tb


def bullets(slide, x, y, w, h, items, size=15, color=TEXT, gap=7):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    for i, it in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(gap)
        head, rest = it if isinstance(it, tuple) else (None, it)
        r0 = p.add_run()
        r0.text = "▸  "
        r0.font.color.rgb = AMBER
        r0.font.size = Pt(size)
        r0.font.name = BODY
        if head:
            r = p.add_run()
            r.text = head + " "
            r.font.bold = True
            r.font.size = Pt(size)
            r.font.name = BODY
            r.font.color.rgb = color
        r = p.add_run()
        r.text = rest
        r.font.size = Pt(size)
        r.font.name = BODY
        r.font.color.rgb = color
    return tb


def box(slide, x, y, w, h, fill=LIGHT, line=None, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.08, name=None,
        shadow=False):
    s = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    if name:
        s.name = name
    s.fill.solid()
    s.fill.fore_color.rgb = fill
    if line is None:
        s.line.fill.background()
    else:
        s.line.color.rgb = line
        s.line.width = Pt(1)
    if shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        s.adjustments[0] = radius
    if not shadow:
        s.shadow.inherit = False
    return s


def num(slide, x, y, n, d=0.5, fill=AMBER, color=INK, size=16):
    c = box(slide, x, y, d, d, fill=fill, shape=MSO_SHAPE.OVAL)
    tf = c.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    r = p.add_run()
    r.text = str(n)
    r.font.bold = True
    r.font.size = Pt(size)
    r.font.name = BODY
    r.font.color.rgb = color
    return c


def title(slide, t, sub=None, dark=False):
    text(slide, 0.6, 0.42, 12.1, 0.8, t, size=34, font=HEAD, bold=True, color=WHITE if dark else INK, name="Title")
    if sub:
        text(slide, 0.6, 1.2, 12.1, 0.45, sub, size=16, color=ICE if dark else SLATE, name="Subtitle")


def footer(slide, n, dark=False):
    text(slide, 0.6, 7.05, 8, 0.3, "DocForensics  ·  DataOps Innovation Hackathon 2026", size=10,
         color=ICE if dark else SLATE)
    text(slide, 11.9, 7.05, 0.85, 0.3, str(n), size=10, color=ICE if dark else SLATE, align=PP_ALIGN.RIGHT)


def picture(slide, path, x, y, w=None, h=None, border=True):
    p = Path(path)
    if not p.exists():
        ph = box(slide, x, y, w or 6, h or 3.5, fill=LIGHT, line=LINE)
        ph.text_frame.text = f"[screenshot missing: {p.name}]"
        return ph
    pic = slide.shapes.add_picture(str(p), Inches(x), Inches(y), Inches(w) if w else None,
                                   Inches(h) if h else None)
    if border:
        pic.line.color.rgb = LINE
        pic.line.width = Pt(1)
    return pic


def crop_to(pic, ratio):
    """Crop picture (top-anchored) to the given width/height ratio, keeping its width."""
    if not hasattr(pic, "crop_bottom"):
        return
    w, h = pic.width, pic.height
    target_h = int(w / ratio)
    if target_h < h:
        pic.crop_bottom = 1 - target_h / h
        pic.height = target_h


def shot(slide, name, x, y, w, ratio=None, left=300, top=52):
    """Insert an app screenshot cropped to the content area (sidebar and top bar removed) at the slot's aspect."""
    import io
    from PIL import Image
    p = SHOTS / f"{name}.png"
    if not p.exists():
        return picture(slide, p, x, y, w=w, h=w / (ratio or 1.6))
    im = Image.open(p).convert("RGB")
    cw = im.width - left
    ch = min(im.height - top, int(cw / (ratio or 1.6)))
    im = im.crop((left, top, left + cw, top + ch))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    buf.seek(0)
    pic = slide.shapes.add_picture(buf, Inches(x), Inches(y), Inches(w), Inches(w * ch / cw))
    pic.line.color.rgb = LINE
    pic.line.width = Pt(1)
    return pic


def notes(slide, t):
    slide.notes_slide.notes_text_frame.text = t


n = 0


def new(dark=False):
    global n
    n += 1
    s = prs.slides.add_slide(BLANK)
    bg(s, INK if dark else WHITE)
    return s


# 1 ------------------------------------------------------------------ title
s = new(dark=True)
num(s, 0.6, 0.7, "DF", d=0.62, size=15)
text(s, 1.4, 0.74, 8, 0.5, "DataOps Innovation Hackathon 2026  ·  Problem Statement 2", size=16, color=ICE)
text(s, 0.6, 2.0, 12, 1.2, "DocForensics", size=60, font=HEAD, bold=True, color=WHITE)
text(s, 0.6, 3.15, 11.5, 1.0, "AI-Powered Document Forensics & Contextual Intelligence System", size=28,
     font=HEAD, color=AMBER)
text(s, 0.6, 4.2, 11, 0.9, "OCR tells you what a document says. DocForensics tells you whether to believe it, "
                           "and shows you exactly where to look.", size=18, color=ICE)
text(s, 0.6, 5.55, 8, 0.8, [[("Presented by  ", {"color": ICE}), ("veekshanag8-beep", {"bold": True})],
                            [("B.Tech CSE", {"color": ICE})]], size=16, color=WHITE)
text(s, 0.6, 6.75, 12, 0.35, REPO, size=12, color=ICE)
notes(s, "Introduce the project in one line: we turn document processing from extraction into investigation.")

# 2 ------------------------------------------------------------------ problem
s = new()
title(s, "OCR extracts text. It does not establish trust",
      "Loan and KYC files are verified field by field, so the most damaging manipulations slip through")
cards = [
    ("Altered fields", "A salary figure retyped over the original, a value pasted into a scan. "
                       "OCR reads the forged value perfectly.", RED),
    ("Hidden contradictions", "Each document looks fine alone. Only together do the name, date of birth, "
                              "income and bank credits disagree.", ORANGE),
    ("Manipulated artefacts", "Copied signatures, edited PDFs, spliced images. Visible only in how the file "
                              "and pixels were produced.", BLUE),
]
for i, (h, b, col) in enumerate(cards):
    x = 0.6 + i * 4.1
    box(s, x, 2.0, 3.8, 3.3, fill=LIGHT)
    c = box(s, x + 0.35, 2.35, 0.55, 0.55, fill=col, shape=MSO_SHAPE.OVAL)
    text(s, x + 0.35, 3.1, 3.1, 0.5, h, size=20, font=HEAD, bold=True, color=INK)
    text(s, x + 0.35, 3.65, 3.15, 1.6, b, size=15, color=TEXT)
box(s, 0.6, 5.65, 12.1, 1.05, fill=INK)
text(s, 0.95, 5.65, 11.5, 1.05, [[("What is needed: ", {"bold": True, "color": AMBER}),
                                  ("a system that understands structure, examines visual characteristics, correlates "
                                   "documents and explains every anomaly with evidence.", {})]],
     size=17, color=WHITE, anchor=MSO_ANCHOR.MIDDLE)
footer(s, n)
notes(s, "Three classes of manipulation that field-level OCR validation misses.")

# 3 ------------------------------------------------------------------ approach
s = new()
title(s, "Three independent lenses, one corroborated verdict",
      "Each document is examined three ways. When independent methods agree on a field, confidence rises")
lenses = [("1", "File & pixel forensics", "How was this file and image produced? Hidden text, fonts, revisions, "
                                           "scanner noise, ELA, signatures."),
          ("2", "Internal logic", "Do the values inside the document make sense? Arithmetic, check digits, age vs "
                                  "DOB, running balances."),
          ("3", "Cross-document", "Does it agree with every other document? Name, DOB, ID, address, income, salary "
                                  "credit, account.")]
for i, (k, h, b) in enumerate(lenses):
    y = 1.95 + i * 1.6
    box(s, 0.6, y, 6.6, 1.35, fill=LIGHT)
    num(s, 0.85, y + 0.38, k, d=0.6, size=18)
    text(s, 1.7, y + 0.18, 5.3, 0.4, h, size=19, font=HEAD, bold=True, color=INK)
    text(s, 1.7, y + 0.6, 5.3, 0.7, b, size=14, color=TEXT)
    a = s.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Inches(7.35), Inches(y + 0.48), Inches(0.6), Inches(0.38))
    a.fill.solid()
    a.fill.fore_color.rgb = AMBER
    a.line.fill.background()
box(s, 8.15, 1.95, 4.55, 4.5, fill=INK)
text(s, 8.5, 2.2, 3.9, 0.5, "Corroborated anomaly", size=22, font=HEAD, bold=True, color=AMBER)
text(s, 8.5, 2.8, 3.9, 1.3, "Visual forensics AND contextual logic both point at the same field, so we raise "
                            "confidence and say exactly why.", size=15, color=WHITE)
for i, (lab, col) in enumerate([("Observation", BLUE), ("Inconsistency", ORANGE),
                                ("Potential manipulation", RED)]):
    y = 4.35 + i * 0.6
    b = box(s, 8.5, y, 3.85, 0.45, fill=col, radius=0.5)
    text(s, 8.7, y, 3.5, 0.45, lab, size=14, bold=True, color=WHITE, anchor=MSO_ANCHOR.MIDDLE)
text(s, 0.6, 6.6, 12, 0.35, "Never \"fraud\": a status ladder plus a human reviewer for every consequential decision.",
     size=13, italic=True, color=SLATE)
footer(s, n)
notes(s, "Core idea: independence of evidence. A visual signal alone can be noise; a logic error alone can be a "
         "typo; together on the same field they are strong evidence.")

# 4 ------------------------------------------------------------------ pipeline
s = new()
title(s, "End-to-end investigation pipeline", "Ten stages, live progress, each one audit-logged")
stages = [("Submission", "SHA-256, originals immutable"), ("Classification", "4 types + unknown, confidence"),
          ("OCR & extraction", "PDF text layer or RapidOCR"), ("Structure", "fields, tables, sections"),
          ("Visual forensics", "PDF + scan + signature"), ("Contextual checks", "arithmetic, checksums, dates"),
          ("Cross-document", "entity matching + graph"), ("Investigation", "link & corroborate findings"),
          ("Evidence", "crops, annotated pages"), ("Dossier", "HTML / PDF / JSON + audit")]
for i, (h, b) in enumerate(stages):
    row, col = divmod(i, 5)
    x, y = 0.6 + col * 2.46, 2.05 + row * 2.3
    box(s, x, y, 2.25, 1.85, fill=LIGHT if row == 0 else RGBColor(0xFF, 0xF4, 0xE2))
    num(s, x + 0.2, y + 0.2, i + 1, d=0.5, size=15, fill=INK if row == 0 else AMBER,
        color=WHITE if row == 0 else INK)
    text(s, x + 0.2, y + 0.82, 1.9, 0.4, h, size=16, bold=True, color=INK)
    text(s, x + 0.2, y + 1.2, 1.9, 0.6, b, size=13, color=SLATE)
text(s, 0.6, 6.55, 12, 0.35, "Row 1: understand the documents     Row 2: investigate them", size=13, italic=True,
     color=SLATE)
footer(s, n)
notes(s, "Mirrors the required flow in the problem statement exactly.")

# 5 ------------------------------------------------------------------ architecture
s = new()
title(s, "Architecture", "Lightweight, offline-capable, explainable by design")
blocks = [(0.6, "Investigation Console", ["HTML / JS, no build step", "upload, live progress", "viewer, graph, reviews"]),
          (3.75, "FastAPI service", ["REST API", "background worker per case", "dossier rendering"]),
          (6.9, "Forensic pipeline", ["ingest, extract, forensics", "context, cross-document", "correlate, explain"]),
          (10.05, "Evidence store", ["SQLite + files", "hash-chained audit log", "reviewer decisions"])]
for x, h, b in blocks:
    box(s, x, 2.0, 2.65, 2.2, fill=INK)
    text(s, x + 0.25, 2.2, 2.2, 0.45, h, size=17, bold=True, color=AMBER)
    text(s, x + 0.25, 2.75, 2.25, 1.4, b, size=13, color=WHITE, spacing=3)
for x in (3.3, 6.45, 9.6):
    a = s.shapes.add_shape(MSO_SHAPE.LEFT_RIGHT_ARROW, Inches(x), Inches(2.9), Inches(0.4), Inches(0.35))
    a.fill.solid()
    a.fill.fore_color.rgb = AMBER
    a.line.fill.background()
tech = [("OCR", "RapidOCR (PaddleOCR models, ONNX)"), ("PDF", "PyMuPDF: text layer, fonts, drawings, metadata"),
        ("Vision", "OpenCV + NumPy: ELA, noise residuals, geometry"), ("Matching", "rapidfuzz entity resolution"),
        ("LLM", "Claude (optional) writes the narrative from structured findings only"),
        ("Data", "synthetic generator with ground truth for evaluation")]
for i, (k, v) in enumerate(tech):
    col, row = divmod(i, 3)
    x, y = 0.6 + col * 6.15, 4.55 + row * 0.7
    box(s, x, y, 5.95, 0.55, fill=LIGHT)
    text(s, x + 0.2, y, 1.2, 0.55, k, size=14, bold=True, color=INK, anchor=MSO_ANCHOR.MIDDLE)
    text(s, x + 1.35, y, 4.5, 0.55, v, size=13, color=TEXT, anchor=MSO_ANCHOR.MIDDLE)
footer(s, n)
notes(s, "The LLM never decides a status; it only narrates. That limits hallucination and prompt-injection risk.")

# 6 ------------------------------------------------------------------ visual forensics
s = new()
title(s, "Visual forensic analysis", "Looking at how the document was made, not just what it says")
bullets(s, 0.6, 1.95, 5.3, 4.8, [
    ("Overwritten text:", "a value typed over a white box; the original still sits in the PDF text layer"),
    ("Typography:", "a font or size used nowhere else on the form"),
    ("Revision metadata:", "incremental saves, editor software, modified after creation"),
    ("Scanner-noise map:", "a digitally pasted patch has no sensor noise"),
    ("Error Level Analysis:", "inserted content recompresses differently"),
    ("Text geometry:", "baseline, height and alignment outliers"),
    ("Signatures:", "missing ink, or a pixel-identical copy (0.97 vs 0.19-0.59 for real ones)"),
], size=15, gap=8)
shot(s, "06_overwritten", 6.2, 1.95, 6.5, ratio=6.5 / 4.6)
text(s, 6.2, 6.62, 6.5, 0.35, "Original 58,000 found hidden under the displayed 95,000 (deterministic evidence)",
     size=11, italic=True, color=SLATE)
footer(s, n)
notes(s, "Deterministic checks (hidden text) are reported with high confidence; statistical ones (ELA) are "
         "downgraded to observations unless strong.")

# 7 ------------------------------------------------------------------ contextual
s = new()
title(s, "Contextual intelligence across documents", "The largest scoring criterion, handled by reasoning, not keywords")
shot(s, "11_graph", 0.6, 1.95, 6.9, ratio=6.9 / 4.55)
text(s, 0.6, 6.62, 6.9, 0.35, "Entity graph: red nodes are values that conflict between documents", size=11,
     italic=True, color=SLATE)
text(s, 7.85, 1.95, 4.85, 0.4, "Within a document", size=18, font=HEAD, bold=True, color=INK)
bullets(s, 7.85, 2.45, 4.85, 1.9, [
    "Verhoeff check digit on ID numbers; PAN / IFSC format",
    "Stated age vs date of birth",
    "Payslip: components, then gross - deductions = net",
    "Running balance: pinpoints the single wrong figure",
], size=14, gap=5)
text(s, 7.85, 4.35, 4.85, 0.4, "Across documents", size=18, font=HEAD, bold=True, color=INK)
bullets(s, 7.85, 4.85, 4.85, 1.9, [
    "Name, DOB, ID, PAN, address (PIN-aware), employer",
    "Declared income vs payslip gross",
    "Payslip net pay vs bank salary credit",
    "Tolerates 'Pvt Ltd' variants; flags real conflicts",
], size=14, gap=5)
footer(s, n)
notes(s, "Example reasoning: when components add up but net pay does not, the system names net pay as the "
         "figure that does not fit.")

# 8 ------------------------------------------------------------------ explainability
s = new()
title(s, "Explainable, evidence-backed findings", "Every finding answers: what, where, how sure, and why it matters")
shot(s, "04_corroborated", 0.6, 1.95, 7.2, ratio=7.2 / 4.6)
anatomy = [("Status", "observation / inconsistency / potential manipulation"),
           ("Basis", "deterministic fact or heuristic signal"),
           ("Confidence", "per finding; corroboration combines them"),
           ("Evidence", "document, field, value, page + pixel box, crop"),
           ("Explanation", "plain-language reasoning with the numbers"),
           ("Next step", "what a human should verify, and with whom")]
for i, (k, v) in enumerate(anatomy):
    y = 1.95 + i * 0.76
    box(s, 8.1, y, 4.6, 0.64, fill=LIGHT)
    text(s, 8.3, y, 1.35, 0.64, k, size=14, bold=True, color=INK, anchor=MSO_ANCHOR.MIDDLE)
    text(s, 9.65, y, 2.95, 0.64, v, size=12, color=TEXT, anchor=MSO_ANCHOR.MIDDLE)
footer(s, n)
notes(s, "Show the corroborated anomaly: three independent findings on the same Net Pay field.")

# 9 ------------------------------------------------------------------ traceability
s = new()
title(s, "Traceability, audit and human oversight", "Inspired by ISO/IEC 27037 / 27042 and NIST SP 800-86")
shot(s, "05_traceability", 5.4, 1.95, 7.3, ratio=7.3 / 4.6, left=760)
for i, (k, v) in enumerate([("Integrity", "originals hashed (SHA-256) at intake and re-verified in the dossier"),
                            ("Traceability", "every evidence item carries page + pixel coordinates; one click "
                                             "jumps to the region"),
                            ("Audit trail", "each action hash-chained, so editing the log breaks the chain"),
                            ("Oversight", "reviewers confirm / dismiss / request info; logged and reported")]):
    y = 1.95 + i * 1.17
    num(s, 0.6, y + 0.05, i + 1, d=0.5, size=15)
    text(s, 1.3, y, 3.8, 0.4, k, size=17, bold=True, color=INK)
    text(s, 1.3, y + 0.4, 3.8, 0.7, v, size=13, color=TEXT)
footer(s, n)
notes(s, "Judges' checklist: trace selected findings back to original locations, demonstrate potential vs confirmed.")

# 10 ----------------------------------------------------------------- results
s = new()
title(s, "Results on the demonstration dataset", "Genuine and manipulated synthetic documents with a ground-truth key")
stats = [("17/17", "planted anomalies detected"), ("0", "false positives (genuine case clean)"),
         ("12", "documents across 3 cases + 2 failure files"), ("~20 s", "per 4-document case on a laptop CPU")]
for i, (big, lab) in enumerate(stats):
    y = 1.95 + i * 1.17
    text(s, 0.6, y, 2.6, 0.75, big, size=44, font=HEAD, bold=True, color=AMBER if i < 2 else INK)
    text(s, 3.2, y + 0.18, 3.0, 0.75, lab, size=15, color=TEXT)
cd = CategoryChartData()
cd.categories = ["Genuine", "Visual tamper", "Contextual"]
cd.add_series("Planted", (0, 7, 10))
cd.add_series("Detected", (0, 7, 10))
cd.add_series("False positives", (0, 0, 0))
gf = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(6.6), Inches(1.9), Inches(6.1), Inches(4.4), cd)
ch = gf.chart
ch.has_title = True
ch.chart_title.text_frame.text = "Anomalies per case"
ch.chart_title.text_frame.paragraphs[0].runs[0].font.size = Pt(14)
ch.chart_title.text_frame.paragraphs[0].runs[0].font.bold = True
ch.chart_title.text_frame.paragraphs[0].runs[0].font.color.rgb = INK
ch.has_legend = True
ch.legend.position = XL_LEGEND_POSITION.BOTTOM
ch.legend.include_in_layout = False
ch.legend.font.size = Pt(12)
ch.legend.font.color.rgb = SLATE
for ser, col in zip(ch.series, (SLATE, AMBER, RED)):
    ser.format.fill.solid()
    ser.format.fill.fore_color.rgb = col
ch.plots[0].gap_width = 70
ch.plots[0].has_data_labels = True
dl = ch.plots[0].data_labels
dl.font.size = Pt(12)
dl.font.color.rgb = TEXT
dl.position = XL_LABEL_POSITION.OUTSIDE_END
ch.value_axis.has_major_gridlines = True
ch.value_axis.major_gridlines.format.line.color.rgb = LINE
ch.value_axis.tick_labels.font.size = Pt(11)
ch.value_axis.tick_labels.font.color.rgb = SLATE
ch.value_axis.format.line.fill.background()
ch.category_axis.tick_labels.font.size = Pt(12)
ch.category_axis.tick_labels.font.color.rgb = SLATE
text(s, 0.6, 6.6, 12.1, 0.4, "Honest caveat: the data is synthetic and thresholds were tuned on it. These numbers "
                             "prove each capability works end to end, not real-world accuracy.", size=12,
     italic=True, color=SLATE)
footer(s, n)
notes(s, "Mention that the evaluation script regenerates these numbers from scratch: scripts/evaluate.py.")

# 11 ----------------------------------------------------------------- product tour
s = new()
title(s, "The investigation console", "Upload, follow progress live, inspect evidence, review, export the dossier")
grid = [("03_results", "Summary and prioritised findings"), ("08_documents", "Structured extraction + overlays"),
        ("10_contextual", "Contextual case: 10 inconsistencies"), ("14_dossier", "Investigation dossier")]
for i, (nm, cap) in enumerate(grid):
    col, row = i % 2, i // 2
    x, y = 0.6 + col * 6.15, 1.85 + row * 2.6
    shot(s, nm, x, y, 5.95, ratio=5.95 / 2.15, **({"left": 200, "top": 0} if nm == "14_dossier" else {}))
    text(s, x, y + 2.18, 5.95, 0.3, cap, size=12, color=SLATE)
footer(s, n)
notes(s, "Switch to the live demo here if time allows.")

# 12 ----------------------------------------------------------------- responsible AI
s = new()
title(s, "Responsible by design", "Built around the safety and integrity requirements of the problem statement")
box(s, 0.6, 1.95, 5.95, 3.95, fill=LIGHT)
text(s, 0.9, 2.15, 5.4, 0.45, "Safeguards", size=20, font=HEAD, bold=True, color=INK)
bullets(s, 0.9, 2.75, 5.4, 3.9, [
    "Only synthetic documents (fictional people and organisations)",
    "OCR output is never treated as ground truth",
    "No finding is labelled fraud; statuses + basis + confidence",
    "Human reviewer for every consequential decision",
    "LLM sees structured findings only, never decides a status",
    "Corrupted / unsupported files fail safely, honestly reported",
], size=14, gap=6)
box(s, 6.75, 1.95, 5.95, 3.95, fill=RGBColor(0xFF, 0xF4, 0xE2))
text(s, 7.05, 2.15, 5.4, 0.45, "Known limitations", size=20, font=HEAD, bold=True, color=INK)
bullets(s, 7.05, 2.75, 5.4, 3.9, [
    "Thresholds calibrated on synthetic data only",
    "Handwriting OCR is weak; English only",
    "Signature check detects copies, not skilled forgeries",
    "ELA / noise can be fooled by re-scanning or heavy compression",
    "Four document schemas; others classified 'unknown'",
    "Full list with false-positive sources in docs/LIMITATIONS.md",
], size=14, gap=6)
footer(s, n)
notes(s, "Being explicit about limits is part of the evaluation (safe failure, honest capability reporting).")

# 13 ----------------------------------------------------------------- criteria mapping
s = new()
title(s, "How we address the judging criteria")
rows = [("OCR & Information Extraction", "15", "Text layer + OCR, field confidence, fragment repair, tables"),
        ("Document Understanding", "15", "Classification, label-value layout, sections, missing / duplicate fields"),
        ("Visual Forensic Analysis", "15", "Hidden text, fonts, revisions, noise, ELA, geometry, signatures"),
        ("Contextual Intelligence", "20", "Arithmetic, checksums, cross-document entities, graph, corroboration"),
        ("Evidence & Traceability", "10", "Pixel boxes, crops, annotated pages, SHA-256, audit chain"),
        ("AI Reasoning & Explainability", "10", "Reasoned explanations, culprit detection, optional Claude narrative"),
        ("Technical Implementation", "10", "Modular pipeline, REST API, safe failure, evaluation script"),
        ("Innovation", "5", "Corroboration across independent methods, tamper-evident audit")]
tbl = s.shapes.add_table(len(rows) + 1, 3, Inches(0.6), Inches(1.55), Inches(12.1), Inches(5.2)).table
tbl.columns[0].width = Inches(3.6)
tbl.columns[1].width = Inches(1.0)
tbl.columns[2].width = Inches(7.5)
for c, h in enumerate(["Criterion", "Points", "What we built"]):
    cell = tbl.cell(0, c)
    cell.text = h
for r, row in enumerate(rows, start=1):
    for c, v in enumerate(row):
        tbl.cell(r, c).text = v
for r in range(len(rows) + 1):
    for c in range(3):
        cell = tbl.cell(r, c)
        cell.fill.solid()
        cell.fill.fore_color.rgb = INK if r == 0 else (LIGHT if r % 2 else WHITE)
        cell.margin_left = cell.margin_right = Inches(0.12)
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        for p in cell.text_frame.paragraphs:
            p.alignment = PP_ALIGN.CENTER if c == 1 else PP_ALIGN.LEFT
            for run in p.runs:
                run.font.size = Pt(14)
                run.font.name = BODY
                run.font.bold = r == 0 or c == 0
                run.font.color.rgb = WHITE if r == 0 else (INK if c < 2 else TEXT)
footer(s, n)
notes(s, "Map every 100-point criterion to concrete features.")

# 14 ----------------------------------------------------------------- close
s = new(dark=True)
text(s, 0.6, 0.55, 12, 0.8, "What's next", size=34, font=HEAD, bold=True, color=WHITE)
nxt = [("Calibrate on real data", "authorised real samples to tune thresholds and measure true accuracy"),
       ("Learned models", "LayoutLM / Donut for extraction; trained splice and copy-move localisation"),
       ("More documents", "utility bills, tax returns, multilingual and handwritten forms"),
       ("Integration", "API hooks into loan-origination and KYC workflows")]
for i, (h, b) in enumerate(nxt):
    y = 1.65 + i * 0.95
    num(s, 0.6, y, i + 1, d=0.55, size=16)
    text(s, 1.4, y - 0.02, 4.2, 0.4, h, size=18, bold=True, color=AMBER)
    text(s, 1.4, y + 0.38, 6.2, 0.5, b, size=14, color=ICE)
box(s, 8.2, 1.65, 4.5, 2.95, fill=NAVY)
text(s, 8.5, 1.9, 3.9, 0.5, "Thank you", size=30, font=HEAD, bold=True, color=WHITE)
text(s, 8.5, 2.6, 3.9, 2.5, [[("Source code", {"bold": True, "color": AMBER})],
                             [("github.com/veekshanag8-beep/", {})],
                             [("Document-Forensics-and-Contextual-", {})],
                             [("Intelligence-System", {})],
                             [("Run it: setup.ps1, then run.ps1", {"color": ICE})]],
     size=14, color=WHITE)
text(s, 0.6, 5.85, 12, 0.6, "From extraction to investigation: contextual, evidence-driven and explainable.",
     size=20, font=HEAD, italic=True, color=WHITE)
footer(s, n, dark=True)
notes(s, "Close with the tagline and invite questions.")

prs.save(OUT)
print("saved", OUT, n, "slides")
