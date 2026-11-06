"""Core data structures shared by every pipeline stage.

Coordinates: every bbox is [x0, y0, x1, y1] in *page-image pixels* of the
rendered page PNG that the UI displays. That single convention is what makes
findings traceable back to the exact place on the original document.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

# Finding status ladder. The system never claims "fraud".
OBSERVATION = "observation"                    # a factual characteristic, not necessarily a problem
INCONSISTENCY = "inconsistency"                # a detected discrepancy that needs explanation
POTENTIAL_MANIPULATION = "potential_manipulation"  # evidence pattern consistent with deliberate alteration

# Basis of a finding: deterministic = exactly reproducible fact (arithmetic, hidden text layer);
# heuristic = statistical / model-based signal that can produce false positives.
DETERMINISTIC = "deterministic"
HEURISTIC = "heuristic"


@dataclass
class TextUnit:
    """A phrase of text located on a page (an OCR line or a PDF text run)."""
    text: str
    bbox: list[float]
    conf: float
    page: int = 0
    font: Optional[str] = None      # PDF only
    size: Optional[float] = None    # PDF only
    order: int = 0                  # drawing / reading order
    hidden: bool = False            # covered by another unit or an opaque overlay

    @property
    def cy(self) -> float:
        return (self.bbox[1] + self.bbox[3]) / 2

    @property
    def h(self) -> float:
        return self.bbox[3] - self.bbox[1]


@dataclass
class Field:
    name: str
    value: Any
    raw: str
    conf: float
    page: int
    bbox: list[float]
    label_bbox: Optional[list[float]] = None
    source: str = "ocr"   # ocr | pdf_text_layer | header | table
    vtype: str = "text"
    units: list = field(default_factory=list)   # order ids of the text units forming the value


@dataclass
class Finding:
    id: str
    category: str          # visual | contextual | cross_document | structural | metadata | signature | correlated
    check: str             # machine name of the check that produced it
    title: str
    status: str            # OBSERVATION | INCONSISTENCY | POTENTIAL_MANIPULATION
    basis: str             # DETERMINISTIC | HEURISTIC
    confidence: float
    explanation: str
    evidence: list[dict] = field(default_factory=list)   # [{doc_id, page, bbox, field, value, note}]
    fields: list[str] = field(default_factory=list)
    related: list[str] = field(default_factory=list)     # ids of linked findings
    severity: str = "medium"   # low | medium | high
    recommendation: str = ""


@dataclass
class Document:
    doc_id: str
    filename: str
    sha256: str
    media_type: str
    doc_type: str = "unknown"
    doc_type_conf: float = 0.0
    doc_type_scores: dict = field(default_factory=dict)
    pages: list[dict] = field(default_factory=list)      # [{index, image, width, height}]
    units: list[TextUnit] = field(default_factory=list)
    fields: dict[str, Field] = field(default_factory=dict)
    tables: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    signature: Optional[dict] = None
    errors: list[str] = field(default_factory=list)
    status: str = "pending"

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


class IdGen:
    def __init__(self, prefix: str = "F"):
        self._c = itertools.count(1)
        self.prefix = prefix

    def __call__(self) -> str:
        return f"{self.prefix}-{next(self._c):03d}"


def ev(doc: "Document", f: Optional[Field] = None, *, bbox=None, page=None, note="", value=None, field_name=None) -> dict:
    """Build an evidence reference pointing at a location in an original document."""
    return {
        "doc_id": doc.doc_id,
        "filename": doc.filename,
        "doc_type": doc.doc_type,
        "page": f.page if f is not None else (page or 0),
        "bbox": list(f.bbox) if f is not None else (list(bbox) if bbox else None),
        "field": f.name if f is not None else field_name,
        "value": (f.raw if f is not None else value),
        "note": note,
    }
