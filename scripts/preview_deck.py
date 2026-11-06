"""Approximate renderer for QA when PowerPoint/LibreOffice are unavailable.
Draws shapes, pictures, tables and wrapped text with the real Windows fonts, and reports text overflow.

    python scripts/preview_deck.py deliverables/DocForensics_Presentation.pptx out_dir
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE, MSO_SHAPE_TYPE
from pptx.util import Emu

DPI = 110
FONTS = {("Calibri", False, False): "calibri.ttf", ("Calibri", True, False): "calibrib.ttf",
         ("Calibri", False, True): "calibrii.ttf", ("Calibri", True, True): "calibriz.ttf",
         ("Cambria", False, False): "cambria.ttc", ("Cambria", True, False): "cambriab.ttf",
         ("Cambria", False, True): "cambriai.ttf", ("Cambria", True, True): "cambriaz.ttf"}
_cache = {}


def font(name, bold, italic, pt):
    key = (name or "Calibri", bool(bold), bool(italic), pt)
    if key not in _cache:
        fn = FONTS.get(key[:3], "calibri.ttf")
        _cache[key] = ImageFont.truetype("C:/Windows/Fonts/" + fn, max(6, int(round(pt * DPI / 72))))
    return _cache[key]


def px(emu):
    return int(Emu(emu).inches * DPI)


def rgb(c, default=(0, 0, 0)):
    try:
        return tuple(bytes.fromhex(str(c.rgb)))
    except Exception:
        return default


def draw_text(d, tf, box, issues, label):
    x0, y0, x1, y1 = box
    ml, mt = px(tf.margin_left), px(tf.margin_top)
    mr = px(tf.margin_right)
    width = max(10, (x1 - x0) - ml - mr)
    lines = []
    for p in tf.paragraphs:
        runs = [(r.text, r.font) for r in p.runs] or [("", None)]
        words = []
        for t, f in runs:
            fo = font(f.name if f else "Calibri", f.bold if f else False, f.italic if f else False,
                      f.size.pt if f and f.size else 18)
            col = rgb(f.color, (0, 0, 0)) if f is not None and f.color and f.color.type else (0, 0, 0)
            for i, w in enumerate(t.split(" ")):
                words.append((w + (" " if i < len(t.split(" ")) - 1 else ""), fo, col))
        line, lw, lh = [], 0, 0
        for w, fo, col in words:
            ww = fo.getlength(w)
            if lw + ww > width + 1 and line and w.strip():
                lines.append((line, lh, p.alignment))
                line, lw = [], 0
            line.append((w, fo, col, ww))
            lw += ww
            lh = max(lh, fo.size)
        lines.append((line, lh or 12, p.alignment))
        if p.space_after is not None:
            lines.append(([], int(p.space_after.pt * DPI / 72), None))
    total = sum(int(h * 1.2) for _, h, _ in lines)
    avail = (y1 - y0) - mt - px(tf.margin_bottom)
    anchor = str(tf.vertical_anchor) if tf.vertical_anchor is not None else ""
    y = y0 + mt
    if "MIDDLE" in anchor:
        y = y0 + (y1 - y0 - total) // 2
    if total > avail + 4:
        issues.append(f"{label}: text overflows by {total - avail}px")
    for line, h, al in lines:
        lw = sum(t[3] for t in line)
        x = x0 + ml
        if al is not None and "CENTER" in str(al):
            x = x0 + ml + (width - lw) / 2
        elif al is not None and "RIGHT" in str(al):
            x = x0 + ml + width - lw
        if lw > width + 2 and len(line) == 1:
            issues.append(f"{label}: a word wider than box: {line[0][0][:30]}")
        for w, fo, col, ww in line:
            d.text((x, y + h), w, font=fo, fill=col, anchor="ls")
            x += ww
        y += int(h * 1.2)


def render(path, out):
    prs = Presentation(path)
    W, H = px(prs.slide_width), px(prs.slide_height)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    all_issues = []
    for i, s in enumerate(prs.slides, 1):
        bgc = (255, 255, 255)
        try:
            bgc = rgb(s.background.fill.fore_color, bgc)
        except Exception:
            pass
        im = Image.new("RGB", (W, H), bgc)
        d = ImageDraw.Draw(im)
        issues = []
        for sh in s.shapes:
            b = (px(sh.left), px(sh.top), px(sh.left + sh.width), px(sh.top + sh.height))
            if b[2] > W + 2 or b[3] > H + 2 or b[0] < -2 or b[1] < -2:
                issues.append(f"{sh.name}: outside slide {b}")
            if sh.shape_type == MSO_SHAPE_TYPE.PICTURE:
                pic = Image.open(sh._element.blipFill and __import__("io").BytesIO(sh.image.blob)).convert("RGB")
                cl, cr, ct, cb = sh.crop_left, sh.crop_right, sh.crop_top, sh.crop_bottom
                pw, ph = pic.size
                pic = pic.crop((int(cl * pw), int(ct * ph), int(pw * (1 - cr)), int(ph * (1 - cb))))
                pic = pic.resize((max(1, b[2] - b[0]), max(1, b[3] - b[1])))
                im.paste(pic, b[:2])
                d.rectangle(b, outline=(213, 220, 229))
            elif sh.has_chart if hasattr(sh, "has_chart") else False:
                d.rectangle(b, outline=(180, 180, 180))
                ch = sh.chart
                cats = list(ch.plots[0].categories)
                series = [(se.name, list(se.values), rgb(se.format.fill.fore_color, (120, 120, 120)))
                          for se in ch.series]
                mx = max(max(v) for _, v, _ in series) or 1
                gw = (b[2] - b[0] - 60) / len(cats)
                for ci, _ in enumerate(cats):
                    for si, (_, vals, col) in enumerate(series):
                        bh = (b[3] - b[1] - 110) * vals[ci] / mx
                        bx = b[0] + 40 + ci * gw + 15 + si * (gw - 30) / len(series)
                        d.rectangle((bx, b[3] - 60 - bh, bx + (gw - 30) / len(series) - 4, b[3] - 60), fill=col)
                    d.text((b[0] + 40 + ci * gw + gw / 2, b[3] - 40), cats[ci], font=font("Calibri", 0, 0, 12),
                           fill=(91, 107, 127), anchor="mm")
                d.text(((b[0] + b[2]) / 2, b[1] + 18), "chart (approx.)", font=font("Calibri", 1, 0, 12),
                       fill=(15, 27, 45), anchor="mm")
            elif sh.has_table if hasattr(sh, "has_table") else False:
                t = sh.table
                y = b[1]
                for r, row in enumerate(t.rows):
                    x = b[0]
                    rh = px(row.height)
                    for c, cell in enumerate(row.cells):
                        cw = px(t.columns[c].width)
                        fillc = rgb(cell.fill.fore_color, (255, 255, 255)) if cell.fill.type else (255, 255, 255)
                        d.rectangle((x, y, x + cw, y + rh), fill=fillc, outline=(213, 220, 229))
                        draw_text(d, cell.text_frame if False else _CellTF(cell), (x, y, x + cw, y + rh), issues,
                                  f"table r{r}c{c}")
                        x += cw
                    y += rh
            else:
                if sh.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE:
                    fc = None
                    try:
                        if sh.fill.type == 1:
                            fc = rgb(sh.fill.fore_color)
                    except Exception:
                        pass
                    st = sh.auto_shape_type
                    if st == MSO_SHAPE.OVAL:
                        d.ellipse(b, fill=fc)
                    elif st in (MSO_SHAPE.RIGHT_ARROW, MSO_SHAPE.LEFT_RIGHT_ARROW):
                        d.rectangle((b[0], b[1] + (b[3] - b[1]) // 4, b[2], b[3] - (b[3] - b[1]) // 4), fill=fc)
                    elif st == MSO_SHAPE.ROUNDED_RECTANGLE:
                        rad = int(min(b[2] - b[0], b[3] - b[1]) * sh.adjustments[0])
                        d.rounded_rectangle(b, radius=rad, fill=fc)
                    else:
                        d.rectangle(b, fill=fc)
                if sh.has_text_frame and sh.text_frame.text.strip():
                    draw_text(d, sh.text_frame, b, issues, sh.name)
        im.save(out / f"slide-{i:02d}.png")
        for x in issues:
            all_issues.append(f"slide {i}: {x}")
    print("\n".join(all_issues) or "no overflow/outside issues detected")


class _CellTF:
    """Adapter giving a table cell the text-frame attributes draw_text needs."""

    def __init__(self, cell):
        self.paragraphs = cell.text_frame.paragraphs
        self.margin_left = cell.margin_left
        self.margin_right = cell.margin_right
        self.margin_top = cell.margin_top
        self.margin_bottom = cell.margin_bottom
        self.vertical_anchor = cell.vertical_anchor


if __name__ == "__main__":
    render(sys.argv[1], sys.argv[2])
