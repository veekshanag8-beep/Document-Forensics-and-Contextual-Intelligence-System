"""Stage 5: visual forensic analysis.

Raster documents (scans / photos):
  * Error Level Analysis (ELA)      - regions that recompress differently from the rest (splices)
  * Noise-residual consistency      - patches with no scanner/sensor noise (digitally painted areas)
  * Text geometry                   - value baseline / height / alignment outliers vs the rest of the form
Digital PDFs:
  * Hidden / overwritten text       - text covered by later-drawn text or opaque boxes
  * Typography                      - fonts or sizes used nowhere else in the field values
  * Revision metadata               - incremental saves, producer/creator mismatch, modified-after-creation
All documents:
  * Signature localisation          - is there ink in the sign-off area; crop kept for cross-document comparison
"""
from __future__ import annotations

import io
import statistics
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from .models import (DETERMINISTIC, HEURISTIC, INCONSISTENCY, OBSERVATION, POTENTIAL_MANIPULATION, Document,
                     Finding, ev)

EDITING_SOFTWARE = ["photoshop", "gimp", "canva", "pixlr", "snapseed", "paint.net", "illustrator", "affinity",
                    "photopea", "editor", "acrobat pro", "foxit phantom", "pdfescape", "sejda", "smallpdf",
                    "ilovepdf", "quickpdf"]

_sig_cache: dict[str, np.ndarray] = {}   # doc_id -> binary ink mask of the signature


def F(category, check, title, status, basis, confidence, explanation, evidence, fields=(), severity="medium",
      recommendation=""):
    return Finding(id="", category=category, check=check, title=title, status=status, basis=basis,
                   confidence=round(float(confidence), 2), explanation=explanation, evidence=evidence,
                   fields=list(fields), severity=severity, recommendation=recommendation)


def _fields_at(doc: Document, bbox, page=0, min_frac=0.3):
    out = []
    for f in doc.fields.values():
        if f.page != page or f.source == "header":
            continue
        ix = min(f.bbox[2], bbox[2]) - max(f.bbox[0], bbox[0])
        iy = min(f.bbox[3], bbox[3]) - max(f.bbox[1], bbox[1])
        if ix > 0 and iy > 0 and ix * iy >= min_frac * (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]):
            out.append(f)
    return out


def _robust_z(values: list[float]) -> tuple[float, float]:
    med = statistics.median(values)
    mad = statistics.median([abs(v - med) for v in values]) * 1.4826
    return med, mad


# ============================================================================= raster forensics
def ela_analysis(doc: Document, img: np.ndarray, work_dir: Path) -> list[Finding]:
    """Error Level Analysis: re-save at a known JPEG quality and measure per-region error."""
    findings = []
    pil = Image.fromarray(img)
    buf = io.BytesIO()
    pil.save(buf, "JPEG", quality=90)
    re = np.asarray(Image.open(io.BytesIO(buf.getvalue())).convert("RGB")).astype(np.int16)
    diff = np.abs(img.astype(np.int16) - re).max(axis=2).astype(np.float32)
    # heatmap for the UI
    vis = np.clip(diff * 255.0 / max(8.0, np.percentile(diff, 99.7)), 0, 255).astype(np.uint8)
    heat = cv2.applyColorMap(vis, cv2.COLORMAP_INFERNO)
    hp = work_dir / "evidence" / f"{doc.doc_id}_ela.png"
    hp.parent.mkdir(exist_ok=True)
    cv2.imwrite(str(hp), heat)
    doc.metadata.setdefault("forensic_maps", {})["ela"] = hp.name

    # Compare like with like: body text only (headers use large/bold/coloured type with more edges).
    H = img.shape[0]
    body = [u for u in doc.units if not u.hidden and len(u.text) >= 3 and u.bbox[1] > 0.10 * H]
    if len(body) < 8:
        return findings
    mh = statistics.median([u.h for u in body])
    gray = img.mean(axis=2)

    def paper(u):  # background brightness behind the text
        x0, y0, x1, y1 = [int(v) for v in u.bbox]
        p = gray[max(0, y0):y1, max(0, x0):x1]
        return float(np.percentile(p, 90)) if p.size else 0.0

    bg = {id(u): paper(u) for u in body}
    page_bg = statistics.median(bg.values())
    units = [u for u in body if u.h < 1.5 * mh and abs(bg[id(u)] - page_bg) < 12]
    scores = []
    for u in units:
        x0, y0, x1, y1 = [int(v) for v in u.bbox]
        patch = diff[max(0, y0):y1, max(0, x0):x1]
        scores.append(float(patch.mean()) if patch.size else 0.0)
    logs = [float(np.log(max(s, 1e-3))) for s in scores]
    med, mad = _robust_z(logs)
    mad = max(mad, 0.08)
    for u, s, l in zip(units, scores, logs):
        z = (l - med) / mad
        ratio = float(np.exp(l - med))
        if z >= 2.8 and ratio >= 1.3:
            flds = _fields_at(doc, u.bbox, u.page)
            names = [f.name for f in flds]
            strong = z >= 4.5 and ratio >= 1.8
            findings.append(F(
                "visual", "ela_outlier", f"Elevated error level around '{u.text}'",
                INCONSISTENCY if strong else OBSERVATION, HEURISTIC, min(0.85, 0.35 + 0.05 * z),
                f"Error Level Analysis: this text recompresses {ratio:.2f}x more strongly than typical body text "
                f"on the page (robust z-score {z:.1f}). Content inserted after the image was last compressed "
                f"often behaves this way. ELA is weak when the whole file was re-saved at the same quality and is "
                f"sensitive to contrast, so on its own this is only a pointer for review.",
                [ev(doc, bbox=u.bbox, page=u.page, value=u.text, field_name=names[0] if names else None,
                    note=f"ELA ratio {ratio:.2f}, z={z:.1f}")],
                names, "medium" if strong else "low", "Inspect the original scan / request the source document."))
    return findings


def noise_analysis(doc: Document, img: np.ndarray) -> list[Finding]:
    """Scans carry sensor/paper noise everywhere. A patch with almost no noise was likely painted digitally."""
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY).astype(np.float32)
    resid = gray - cv2.medianBlur(gray.astype(np.uint8), 3).astype(np.float32)
    ink = cv2.dilate((gray < 200).astype(np.uint8), np.ones((5, 5), np.uint8))
    B = 16
    H, W = gray.shape
    gh, gw = H // B, W // B
    stds = np.full((gh, gw), np.nan, np.float32)
    for by in range(gh):
        for bx in range(gw):
            sl = (slice(by * B, (by + 1) * B), slice(bx * B, (bx + 1) * B))
            bg = ink[sl] == 0
            if bg.mean() > 0.7:
                stds[by, bx] = resid[sl][bg].std()
    valid = stds[~np.isnan(stds)]
    if valid.size < 50:
        return []
    m = float(np.median(valid))
    doc.metadata["noise_level"] = round(m, 2)
    if m < 0.8:
        doc.metadata.setdefault("notes", []).append(
            "Image carries almost no sensor noise (likely digitally generated); noise analysis not applicable.")
        return []
    flat = np.nan_to_num(stds < 0.35 * m, nan=0).astype(np.uint8)
    flat[np.isnan(stds)] = 0
    n, lab, stats, _ = cv2.connectedComponentsWithStats(flat, connectivity=8)
    out = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area < 3:
            continue
        bbox = [float(x * B), float(y * B), float((x + w) * B), float((y + h) * B)]
        # grow the box a little vertically to catch text sitting on the patch
        grown = [bbox[0] - 2 * B, bbox[1] - 2 * B, bbox[2] + 2 * B, bbox[3] + 2 * B]
        flds = _fields_at(doc, grown, 0, 0.05)
        names = [f.name for f in flds]
        ratio = float(np.nanmean(np.where(lab == i, stds, np.nan)) / m)
        conf = min(0.92, 0.6 + 0.04 * area)
        out.append(F(
            "visual", "noise_inconsistency", "Noise-free patch in scanned document" + (
                f" (over {', '.join(names)})" if names else ""),
            INCONSISTENCY, HEURISTIC, conf,
            f"The rest of the page has uniform scanner noise (median residual {m:.1f}); this {area}-block region "
            f"has only {ratio:.0%} of that noise. A smooth patch like this is typical of content painted or "
            f"pasted digitally after scanning (e.g. a white box used to cover a value).",
            [ev(doc, flds[0], note="value lies on/near the noise-free patch") for _ in flds[:1]] +
            [ev(doc, bbox=bbox, page=0, note=f"noise ratio {ratio:.2f} of page median")],
            names, "high" if names else "medium", "Compare against an independently sourced copy."))
    return out


def geometry_analysis(doc: Document) -> list[Finding]:
    """Field values in a printed form share a baseline offset, height and left edge. Outliers suggest edits."""
    rows = []
    for f in doc.fields.values():
        lb = (doc.metadata.get("label_units") or {}).get(f.name)
        if not lb or f.source not in ("ocr",) or len(f.units) != 1:
            continue
        lcy = (lb[1] + lb[3]) / 2
        vcy = (f.bbox[1] + f.bbox[3]) / 2
        rows.append((f, vcy - lcy, f.bbox[3] - f.bbox[1], f.bbox[0], lb[3] - lb[1]))
    if len(rows) < 6:
        return []
    out = []
    dys = [r[1] for r in rows]
    med_dy, mad_dy = _robust_z(dys)
    med_lh = statistics.median([r[4] for r in rows])
    # compare value heights within the same kind of content (numbers vs. text)
    groups: dict[str, list] = {}
    for r in rows:
        groups.setdefault("amount" if r[0].vtype == "amount" else "other", []).append(r)
    hmed = {k: statistics.median([r[2] for r in v]) for k, v in groups.items() if len(v) >= 4}
    xs = [r[3] for r in rows]
    med_x = statistics.median(xs)
    for f, dy, h, x0, lh in rows:
        issues = []
        off = dy - med_dy
        if abs(off) > max(3 * mad_dy, 0.12 * med_lh, 3):
            issues.append(f"baseline offset {off:+.0f}px relative to its label (typical {med_dy:+.0f}px)")
        g = "amount" if f.vtype == "amount" else "other"
        if g in hmed:
            hr = h / hmed[g]
            if hr > 1.15 or hr < 0.85:
                issues.append(f"text height {hr:.0%} of comparable values")
        if abs(x0 - med_x) < 0.15 * 1000 and abs(x0 - med_x) > 0.6 * med_lh:
            issues.append(f"left edge shifted {x0 - med_x:+.0f}px from the value column")
        doc.metadata.setdefault("geometry_notes", {})[f.name] = issues
        if len(issues) >= 2:  # a single deviation is within OCR box noise; recorded but not reported
            conf = min(0.85, 0.45 + 0.15 * len(issues))
            out.append(F(
                "visual", "layout_geometry", f"Typography/alignment irregularity in '{f.name}'",
                INCONSISTENCY, HEURISTIC, conf,
                "Printed forms place every value on the same baseline and in the same font. This value deviates: "
                + "; ".join(issues) + ". Such deviations commonly appear when a value is retyped or pasted over "
                                      "the original, but can also result from scanning skew or OCR box noise.",
                [ev(doc, f, note="; ".join(issues))], [f.name], "medium" if len(issues) >= 2 else "low"))
    return out


def image_metadata(doc: Document) -> list[Finding]:
    out = []
    exif = doc.metadata.get("exif") or {}
    sw = " ".join(str(exif.get(k, "")) for k in ("Software", "ProcessingSoftware", "HostComputer")).lower()
    hit = [s for s in EDITING_SOFTWARE if s in sw]
    if hit:
        out.append(F("metadata", "editing_software", "Image saved by editing software", OBSERVATION, DETERMINISTIC,
                     0.9, f"EXIF metadata names '{sw.strip()}'. Editing software in the save chain means the image "
                          f"is not a direct scanner/camera output. This alone does not imply manipulation.",
                     [ev(doc, bbox=None, page=0, note=f"EXIF Software: {sw.strip()}")], severity="low"))
    return out


# ============================================================================= PDF forensics
def pdf_analysis(doc: Document) -> list[Finding]:
    out = []
    for hp in doc.metadata.get("hidden_text", []):
        flds = _fields_at(doc, hp["visible_bbox"], hp["page"], 0.2)
        names = [f.name for f in flds]
        out.append(F(
            "visual", "overwritten_text", f"Overwritten value: '{hp['hidden']}' hidden under '{hp['visible']}'",
            POTENTIAL_MANIPULATION, DETERMINISTIC, 0.95,
            f"The PDF text layer contains the value '{hp['hidden']}' (font {hp['hidden_font']}) at the same "
            f"position as the displayed value '{hp['visible']}' (font {hp['visible_font']}). The displayed value "
            f"was drawn later, on top of the original. Legitimate document generators do not produce overlapping "
            f"values, so this is strong evidence that the field was altered after the document was created.",
            [ev(doc, bbox=hp["visible_bbox"], page=hp["page"], value=hp["visible"],
                field_name=names[0] if names else None, note="visible (later-drawn) value"),
             ev(doc, bbox=hp["hidden_bbox"], page=hp["page"], value=hp["hidden"],
                field_name=names[0] if names else None, note="original value hidden underneath")],
            names, "high", "Treat the displayed value as unverified; obtain the original from the issuer."))
    hidden_boxes = [hp["visible_bbox"] for hp in doc.metadata.get("hidden_text", [])]
    for pno, rects in (doc.metadata.get("white_overlays") or {}).items():
        for r in rects:
            if any(_iou(r, hb) > 0 for hb in hidden_boxes):
                continue  # already explained by an overwritten-text finding
            under = [u for u in doc.units if u.page == int(pno) and _overlap(u.bbox, r) > 0.5]
            if under:
                out.append(F("visual", "opaque_overlay", "Opaque white box drawn over text", INCONSISTENCY,
                             DETERMINISTIC, 0.8,
                             "An opaque white rectangle is drawn over existing text. This is a common way to hide "
                             "original content in a PDF.",
                             [ev(doc, bbox=r, page=int(pno), note="white overlay rectangle")], severity="medium"))
    # typography: fonts / sizes of values that appear nowhere else
    vis = [u for u in doc.units if not u.hidden and u.font]
    if len(vis) >= 8:
        counts: dict[str, int] = {}
        for u in vis:
            counts[u.font] = counts.get(u.font, 0) + 1
        rare = {f for f, c in counts.items() if c <= 2 and len(counts) > 1}
        vfields = [f for f in doc.fields.values() if f.source == "pdf_text_layer"]
        sizes = {}
        for f in vfields:
            us = [u for u in vis if u.order in f.units]
            if us:
                sizes[f.name] = (us[0].font, us[0].size, f)
        if sizes:
            mode_size = statistics.mode([round(s[1], 1) for s in sizes.values()])
            for name, (font, size, f) in sizes.items():
                issues = []
                if font in rare:
                    common = sorted(counts, key=counts.get, reverse=True)[:2]
                    issues.append(f"font '{font}' is used only {counts[font]}x in the document (others: "
                                  f"{', '.join(common)})")
                if abs(size - mode_size) > 0.3:
                    issues.append(f"font size {size}pt vs {mode_size}pt for other values")
                if issues:
                    out.append(F(
                        "visual", "font_inconsistency", f"Font inconsistency in '{name}'",
                        INCONSISTENCY, DETERMINISTIC, 0.85 if font in rare else 0.6,
                        "This value is typeset differently from every other value on the form: " + "; ".join(issues)
                        + ". A document produced by one generator normally uses one font for all values.",
                        [ev(doc, f, note="; ".join(issues))], [name], "medium"))
    # revision / metadata
    md = doc.metadata.get("pdf_metadata") or {}
    eofs = doc.metadata.get("eof_markers", 1)
    if eofs > 1:
        out.append(F("metadata", "incremental_update", f"PDF was modified after creation ({eofs - 1} revision(s))",
                     OBSERVATION, DETERMINISTIC, 0.95,
                     f"The file contains {eofs} end-of-file markers, meaning {eofs - 1} incremental update(s) were "
                     f"appended after the original was written. Updates are normal for signing or form filling, but "
                     f"also how PDF editors save changes.",
                     [ev(doc, bbox=None, page=0, note=f"%%EOF markers: {eofs}")], severity="low"))
    cr, pr = (md.get("creator") or "").strip(), (md.get("producer") or "").strip()
    if cr and pr and cr.lower() != pr.lower():
        sus = any(s in pr.lower() for s in EDITING_SOFTWARE)
        out.append(F("metadata", "producer_mismatch", "Creator and producer software differ",
                     OBSERVATION, DETERMINISTIC, 0.9,
                     f"Created by '{cr}' but last written by '{pr}'." + (
                         " The producer is a PDF editing tool." if sus else ""),
                     [ev(doc, bbox=None, page=0, note=f"creator={cr}; producer={pr}")],
                     severity="medium" if sus else "low"))
    cd, mdt = md.get("creationDate") or "", md.get("modDate") or ""
    if cd and mdt and cd[:16] != mdt[:16]:
        out.append(F("metadata", "modified_after_creation", "Modification date differs from creation date",
                     OBSERVATION, DETERMINISTIC, 0.9, f"Created {_pdfdate(cd)}, modified {_pdfdate(mdt)}.",
                     [ev(doc, bbox=None, page=0, note=f"creationDate={cd}; modDate={mdt}")], severity="low"))
    if doc.metadata.get("repaired"):
        out.append(F("structural", "pdf_repaired", "PDF structure was damaged and repaired on load", OBSERVATION,
                     DETERMINISTIC, 0.9, "The cross-reference table was broken; content may be incomplete.",
                     [ev(doc, bbox=None, page=0)], severity="low"))
    return out


def _pdfdate(s: str) -> str:
    s = s.replace("D:", "")
    return f"{s[6:8]}/{s[4:6]}/{s[0:4]} {s[8:10]}:{s[10:12]}" if len(s) >= 12 else s


def _overlap(b, r):
    ix = min(b[2], r[2]) - max(b[0], r[0])
    iy = min(b[3], r[3]) - max(b[1], r[1])
    if ix <= 0 or iy <= 0:
        return 0.0
    return ix * iy / max(1e-6, (b[2] - b[0]) * (b[3] - b[1]))


def _iou(a, b):
    ix = min(a[2], b[2]) - max(a[0], b[0])
    iy = min(a[3], b[3]) - max(a[1], b[1])
    if ix <= 0 or iy <= 0:
        return 0.0
    inter = ix * iy
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter)


# ============================================================================= signatures
SIGNATURE_REQUIRED = {"application_form": "applicant_signature", "identity_card": "holder_signature",
                      "salary_slip": "authorised_signature"}


def locate_signature(doc: Document, img: np.ndarray, work_dir: Path) -> list[Finding]:
    from .extract import compact
    labels = [u for u in doc.units if not u.hidden and u.page == 0
              and any(k in compact(u.text) for k in ("signature", "signatory"))
              and len(u.text) <= 40]  # skip sentences such as "...does not require a signature"
    req = SIGNATURE_REQUIRED.get(doc.doc_type)
    if not labels:
        if req:
            return [F("structural", "missing_signature_block", "No signature block found", INCONSISTENCY, HEURISTIC,
                      0.6, f"A {doc.doc_type.replace('_', ' ')} is expected to carry a signature, but no "
                           f"'Signature' label was found on the document.", [ev(doc, bbox=None, page=0)],
                      [req], "medium")]
        return []
    lab = labels[0]
    H, W = img.shape[:2]
    lh = lab.h
    x0 = int(max(0, lab.bbox[0] - lh))
    x1 = int(min(W, lab.bbox[0] + 0.45 * W))
    y1 = int(max(0, lab.bbox[1] - 2))
    y0 = int(max(0, y1 - 6.5 * lh))
    region = img[y0:y1, x0:x1].astype(np.int16)
    if region.size == 0:
        return []
    r, g, b = region[..., 0], region[..., 1], region[..., 2]
    gray = (r + g + b) / 3
    ink = ((gray < 140) | ((b > r + 35) & (b > g + 15))).astype(np.uint8)
    # remove other text in the area
    for u in doc.units:
        if u is lab or u.page != 0:
            continue
        ux0, uy0, ux1, uy1 = [int(v) for v in u.bbox]
        ink[max(0, uy0 - y0):max(0, uy1 - y0), max(0, ux0 - x0):max(0, ux1 - x0)] = 0
    # remove long horizontal rules (signature line)
    rows = ink.sum(axis=1)
    for yy in np.where(rows > 0.5 * ink.shape[1])[0]:
        ink[max(0, yy - 2):yy + 3, :] = 0
    # keep only the dominant ink cluster (drops stray glyph fragments around the signature)
    if ink.any():
        merged = cv2.dilate(ink, np.ones((15, 15), np.uint8))
        ncc, lab_img, stats, _ = cv2.connectedComponentsWithStats(merged, connectivity=8)
        if ncc > 2:
            best = max(range(1, ncc), key=lambda i: int(ink[lab_img == i].sum()))
            ink = (ink & (lab_img == best)).astype(np.uint8)
    n = int(ink.sum())
    present = n > max(80, 0.002 * ink.size)
    sig = {"label_bbox": lab.bbox, "search_bbox": [x0, y0, x1, y1], "present": present, "ink_pixels": n,
           "field": req}
    out = []
    if present:
        ys, xs = np.where(ink > 0)
        bx0, by0, bx1, by1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
        sig["bbox"] = [float(x0 + bx0), float(y0 + by0), float(x0 + bx1), float(y0 + by1)]
        crop = img[y0 + by0:y0 + by1, x0 + bx0:x0 + bx1]
        cp = work_dir / "evidence" / f"{doc.doc_id}_signature.png"
        cp.parent.mkdir(exist_ok=True)
        Image.fromarray(crop).save(cp)
        sig["crop"] = cp.name
        _sig_cache[doc.doc_id] = ink[by0:by1, bx0:bx1].copy()
        # placement: the signature should sit above its label, not far off to the side
        if sig["bbox"][0] > lab.bbox[2] + 3 * lh:
            out.append(F("signature", "signature_placement", "Signature placed away from its signature line",
                         OBSERVATION, HEURISTIC, 0.5, "The detected signature starts well to the right of its label.",
                         [ev(doc, bbox=sig["bbox"], page=0, field_name=req)], [req] if req else [], "low"))
    elif req:
        out.append(F("signature", "missing_signature", f"Signature missing ({req.replace('_', ' ')})",
                     INCONSISTENCY, HEURISTIC, 0.8,
                     f"The signature area above the '{lab.text}' label contains no ink ({n} dark pixels). A "
                     f"{doc.doc_type.replace('_', ' ')} is normally signed here.",
                     [ev(doc, bbox=[x0, y0, x1, y1], page=0, field_name=req, note="empty signature area")],
                     [req], "medium", "Request a signed copy."))
    doc.signature = sig
    return out


def signature_similarity(a_id: str, b_id: str) -> float | None:
    a, b = _sig_cache.get(a_id), _sig_cache.get(b_id)
    if a is None or b is None:
        return None

    def vec(m):
        v = cv2.resize(m.astype(np.float32), (240, 80), interpolation=cv2.INTER_AREA)
        v = cv2.GaussianBlur(v, (0, 0), 1.5)
        v = v - v.mean()
        return v / (np.linalg.norm(v) + 1e-9)

    return float((vec(a) * vec(b)).sum())


# ============================================================================= entry point
def analyse(doc: Document, work_dir: Path) -> list[Finding]:
    findings: list[Finding] = []
    if not doc.pages:
        return findings
    img = np.asarray(Image.open(work_dir / "pages" / doc.pages[0]["image"]).convert("RGB"))
    raster = doc.media_type != "application/pdf" or doc.metadata.get("source_format") == "scanned PDF"
    applied = []
    if raster:
        if doc.media_type == "image/jpeg" and not any("downscaled" in e for e in doc.errors):
            findings += ela_analysis(doc, img, work_dir)
            applied.append("error_level_analysis")
        findings += noise_analysis(doc, img)
        findings += geometry_analysis(doc)
        findings += image_metadata(doc)
        applied += ["noise_consistency", "text_geometry", "exif_metadata"]
    else:
        findings += pdf_analysis(doc)
        applied += ["hidden_text_layer", "opaque_overlays", "typography", "revision_metadata"]
    findings += locate_signature(doc, img, work_dir)
    applied.append("signature_localisation")
    doc.metadata["forensic_checks_applied"] = applied
    return findings
