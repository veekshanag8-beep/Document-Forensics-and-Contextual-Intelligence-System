"""Stage 1-3: document submission, page rendering and text acquisition.

Digital PDFs: text comes from the PDF text layer (exact positions + font names).
Scanned PDFs / images: text comes from OCR (RapidOCR, PaddleOCR models on ONNX).
Every text unit keeps its bounding box in page-image pixels.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
from pathlib import Path

import numpy as np
from PIL import Image, ExifTags

from .models import Document, TextUnit

try:
    import pymupdf as fitz
except ImportError:  # older PyMuPDF
    import fitz

ZOOM = 2.0          # PDF points -> page-image pixels
MAX_PAGES = 5
MAX_BYTES = 25 * 1024 * 1024

_ocr_engine = None


def ocr_engine():
    global _ocr_engine
    if _ocr_engine is None:
        from rapidocr_onnxruntime import RapidOCR
        _ocr_engine = RapidOCR()
    return _ocr_engine


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sniff(b: bytes) -> str | None:
    if b[:5] == b"%PDF-":
        return "application/pdf"
    if b[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if b[:4] in (b"II*\x00", b"MM\x00*"):
        return "image/tiff"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "image/webp"
    return None


def _respace(t: str) -> str:
    """OCR often drops spaces ('EmployeeName'); restore the obvious ones for display."""
    t = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", t)
    t = re.sub(r"(?<=[a-z])(?=\d)", " ", t)
    t = re.sub(r"\s*&\s*", " & ", t)
    return re.sub(r"\s+", " ", t).strip()


# ----------------------------------------------------------------------------- OCR
def ocr_image(img: Image.Image, page: int, cache_dir: Path | None, key: str) -> list[TextUnit]:
    cache = cache_dir / f"ocr_{key}_{page}.json" if cache_dir else None
    if cache and cache.exists():
        raw = json.loads(cache.read_text())
    else:
        arr = np.asarray(img.convert("RGB"))[:, :, ::-1]  # BGR for the engine
        res, _ = ocr_engine()(arr)
        raw = []
        for box, text, conf in (res or []):
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            raw.append([[float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys))], text, float(conf)])
        if cache:
            cache.write_text(json.dumps(raw))
    raw = _repair_fragments(raw, img)
    units = []
    for i, (bb, text, conf) in enumerate(raw):
        units.append(TextUnit(text=_respace(text), bbox=[round(v, 1) for v in bb], conf=round(conf, 3), page=page,
                              order=i))
    return units


def _repair_fragments(raw: list, img: Image.Image) -> list:
    """The text detector sometimes splits one word into overlapping pieces ('12/0', '109/2', '/2026').
    Merge pieces on the same line that overlap or touch, and re-recognise the merged region as a single line."""
    rows: list[list] = []
    for r in sorted(raw, key=lambda r: (r[0][1] + r[0][3]) / 2):
        cy, h = (r[0][1] + r[0][3]) / 2, r[0][3] - r[0][1]
        if rows and abs(rows[-1][0] - cy) < 0.4 * h:
            rows[-1][1].append(r)
        else:
            rows.append([cy, [r]])
    items = [r for _, row in rows for r in sorted(row, key=lambda r: r[0][0])]
    out: list = []
    groups: list[list] = []
    for r in items:
        bb = r[0]
        h = bb[3] - bb[1]
        g = groups[-1] if groups else None
        if g:
            pb = g[-1][0]
            same_row = min(pb[3], bb[3]) - max(pb[1], bb[1]) > 0.5 * min(h, pb[3] - pb[1])
            if same_row and bb[0] - pb[2] < 0.15 * h:
                g.append(r)
                continue
        groups.append([r])
    arr = None
    for g in groups:
        if len(g) == 1:
            out.append(g[0])
            continue
        x0 = min(r[0][0] for r in g)
        y0 = min(r[0][1] for r in g)
        x1 = max(r[0][2] for r in g)
        y1 = max(r[0][3] for r in g)
        if arr is None:
            arr = np.asarray(img.convert("RGB"))[:, :, ::-1]
        pad = 4
        crop = arr[max(0, int(y0) - pad):int(y1) + pad, max(0, int(x0) - pad):int(x1) + pad].copy()
        try:
            res, _ = ocr_engine()(crop, use_det=False, use_cls=False, use_rec=True)
            text, conf = res[0][0], float(res[0][1])
        except Exception:
            text, conf = "", 0.0
        if text and conf >= 0.6:
            out.append([[x0, y0, x1, y1], text, conf])
        else:
            out.extend(g)
    return out


# ----------------------------------------------------------------------------- PDF text layer
def pdf_units(page, pno: int) -> list[TextUnit]:
    """Group PDF characters into phrases (split on large horizontal gaps), keeping font information."""
    d = page.get_text("rawdict")
    units: list[TextUnit] = []
    order = 0

    def flush(cur):
        nonlocal order
        if not cur or not cur["text"].strip():
            return
        fonts = cur["fonts"]
        font = max(fonts, key=fonts.get)
        units.append(TextUnit(
            text=cur["text"].strip(), bbox=[round(v * ZOOM, 1) for v in cur["bbox"]], conf=1.0, page=pno,
            font=font if len(fonts) == 1 else "+".join(sorted(fonts)), size=round(cur["size"], 2), order=order))
        order += 1

    for b in d["blocks"]:
        if b.get("type") != 0:
            continue
        for ln in b["lines"]:
            cur = None
            for sp in ln["spans"]:
                for ch in sp["chars"]:
                    c, bb = ch["c"], ch["bbox"]
                    if cur and c != " " and bb[0] - cur["last_x1"] > max(sp["size"] * 1.2, 6):
                        flush(cur)
                        cur = None
                    if cur is None:
                        if c == " ":
                            continue
                        cur = {"text": "", "bbox": list(bb), "fonts": {}, "size": sp["size"], "last_x1": bb[2]}
                    cur["text"] += c
                    if c != " ":
                        cur["bbox"] = [min(cur["bbox"][0], bb[0]), min(cur["bbox"][1], bb[1]),
                                       max(cur["bbox"][2], bb[2]), max(cur["bbox"][3], bb[3])]
                        cur["fonts"][sp["font"]] = cur["fonts"].get(sp["font"], 0) + 1
                        cur["last_x1"] = bb[2]
            flush(cur)
    return units


def pdf_white_overlays(page) -> list[list[float]]:
    out = []
    try:
        for dr in page.get_drawings():
            fill = dr.get("fill")
            if fill and min(fill) > 0.97 and dr.get("rect") is not None:
                r = dr["rect"]
                if r.width > 4 and r.height > 4 and r.width * r.height < page.rect.width * page.rect.height * 0.5:
                    out.append([round(v * ZOOM, 1) for v in (r.x0, r.y0, r.x1, r.y1)])
    except Exception:
        pass
    return out


# ----------------------------------------------------------------------------- main entry
def load_document(doc: Document, path: Path, work_dir: Path) -> None:
    """Populate pages, text units and raw metadata. Raises ValueError for unusable input."""
    data = path.read_bytes()
    if len(data) > MAX_BYTES:
        raise ValueError(f"File exceeds {MAX_BYTES // (1024 * 1024)} MB limit")
    kind = sniff(data)
    if kind is None:
        raise ValueError("Unsupported or unrecognised file format (accepted: PDF, JPEG, PNG, TIFF, WEBP)")
    doc.media_type = kind
    pages_dir = work_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = work_dir / "cache"
    cache_dir.mkdir(exist_ok=True)

    if kind == "application/pdf":
        _load_pdf(doc, data, pages_dir, cache_dir)
    else:
        _load_image(doc, data, path, pages_dir, cache_dir)


def _load_pdf(doc: Document, data: bytes, pages_dir: Path, cache_dir: Path):
    try:
        pdf = fitz.open(stream=data, filetype="pdf")
        n = pdf.page_count
    except Exception as e:
        raise ValueError(f"PDF could not be parsed ({type(e).__name__}); file may be corrupted") from e
    if n == 0:
        raise ValueError("PDF has no pages")
    meta = dict(pdf.metadata or {})
    doc.metadata = {
        "source_format": "digital PDF",
        "pdf_metadata": meta,
        "page_count": n,
        "eof_markers": data.count(b"%%EOF"),
        "repaired": bool(getattr(pdf, "is_repaired", False)),
        "white_overlays": {},
        "text_source": {},
    }
    if n > MAX_PAGES:
        doc.errors.append(f"Only the first {MAX_PAGES} of {n} pages were analysed")
    for pno in range(min(n, MAX_PAGES)):
        page = pdf[pno]
        pix = page.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM), alpha=False)
        img_path = pages_dir / f"{doc.doc_id}_p{pno}.png"
        pix.save(str(img_path))
        doc.pages.append({"index": pno, "image": img_path.name, "width": pix.width, "height": pix.height})
        units = pdf_units(page, pno)
        if sum(len(u.text) for u in units) < 20:  # image-only (scanned) PDF -> OCR
            img = Image.open(img_path)
            units = ocr_image(img, pno, cache_dir, doc.sha256[:16])
            doc.metadata["text_source"][pno] = "ocr"
            doc.metadata["source_format"] = "scanned PDF"
        else:
            doc.metadata["text_source"][pno] = "pdf_text_layer"
        doc.units.extend(units)
        doc.metadata["white_overlays"][pno] = pdf_white_overlays(page)
    pdf.close()


def _load_image(doc: Document, data: bytes, path: Path, pages_dir: Path, cache_dir: Path):
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as e:
        raise ValueError(f"Image could not be decoded ({type(e).__name__}); file may be corrupted") from e
    exif = {}
    try:
        for k, v in (img.getexif() or {}).items():
            name = ExifTags.TAGS.get(k, str(k))
            if isinstance(v, (str, int, float)):
                exif[name] = v
    except Exception:
        pass
    rgb = img.convert("RGB")
    # keep very large scans manageable
    if max(rgb.size) > 3000:
        s = 3000 / max(rgb.size)
        rgb = rgb.resize((int(rgb.width * s), int(rgb.height * s)), Image.LANCZOS)
        doc.errors.append("Image was downscaled to 3000px for analysis")
    img_path = pages_dir / f"{doc.doc_id}_p0.png"
    rgb.save(str(img_path))
    doc.pages.append({"index": 0, "image": img_path.name, "width": rgb.width, "height": rgb.height})
    doc.metadata = {
        "source_format": "scanned image" if doc.media_type == "image/jpeg" else "raster image",
        "image_format": img.format, "image_size": list(img.size), "exif": exif,
        "jpeg_quality_estimate": _jpeg_quality(img) if img.format == "JPEG" else None,
        "text_source": {0: "ocr"},
    }
    doc.units = ocr_image(rgb, 0, cache_dir, doc.sha256[:16])


def _jpeg_quality(img: Image.Image) -> int | None:
    """Rough JPEG quality estimate from the luminance quantisation table."""
    try:
        q = img.quantization
        if not q:
            return None
        t = q[0]
        avg = sum(t) / len(t)
        # standard IJG table average ~57.6 at quality 50
        scale = avg / 57.625 * 100
        quality = (200 - scale) / 2 if scale <= 100 else 5000 / scale
        return int(max(1, min(100, round(quality))))
    except Exception:
        return None
