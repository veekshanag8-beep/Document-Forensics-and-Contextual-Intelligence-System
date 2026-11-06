"""Stage 9: investigation summary.

Deterministic template summary always. If ANTHROPIC_API_KEY (or ANTHROPIC_AUTH_TOKEN) is set, Claude writes a
narrative summary from the structured findings only (it never sees document images and never decides a
finding's status - statuses come from the deterministic/heuristic checks, keeping a human in the loop).
"""
from __future__ import annotations

import json
import os

from .models import INCONSISTENCY, OBSERVATION, POTENTIAL_MANIPULATION

MODEL = "claude-opus-5-5"

SYSTEM = """You are a document-forensics analyst writing the summary section of an investigation dossier.
You receive structured findings produced by automated checks on a set of submitted documents.
Rules:
- Use only the findings provided. Do not invent facts, values or documents.
- Never state that fraud is confirmed. Use the finding statuses exactly: "observation", "inconsistency",
  "potential manipulation". Automated results require human verification.
- Cite finding ids in square brackets, e.g. [F-003].
- Explain how findings relate to each other (which ones corroborate the same field or story).
- Output plain text, no markdown headings: one paragraph of 4-7 sentences, then a line "Verify next:" followed
  by 2-4 short hyphenated action items."""


def review_priority(findings) -> str:
    if any(f.status == POTENTIAL_MANIPULATION for f in findings):
        return "high"
    if sum(1 for f in findings if f.status == INCONSISTENCY and f.severity == "high") >= 1:
        return "elevated"
    if any(f.status == INCONSISTENCY for f in findings):
        return "moderate"
    return "low"


def template_summary(docs, findings) -> str:
    pm = [f for f in findings if f.status == POTENTIAL_MANIPULATION]
    inc = [f for f in findings if f.status == INCONSISTENCY]
    obs = [f for f in findings if f.status == OBSERVATION]
    types = ", ".join(sorted({d.doc_type.replace("_", " ") for d in docs if d.status == "analysed"})) or "none"
    parts = [f"{len(docs)} document(s) were submitted ({types}). Automated analysis produced {len(findings)} "
             f"finding(s): {len(pm)} potential manipulation, {len(inc)} inconsistency, {len(obs)} observation."]
    if pm:
        parts.append("Highest-priority items: " + "; ".join(f"[{f.id}] {f.title}" for f in pm[:4]) + ".")
    hi = [f for f in inc if f.severity == "high"]
    if hi:
        parts.append("Key inconsistencies: " + "; ".join(f"[{f.id}] {f.title}" for f in hi[:5]) + ".")
    if not pm and not inc:
        parts.append("No inconsistencies were detected; the documents are mutually consistent within the limits "
                     "of the checks applied.")
    parts.append("These are automated findings, not a fraud determination; each item needs human verification.")
    text = " ".join(parts)
    verify = list(dict.fromkeys(f"- {f.recommendation}" for f in (pm + hi) if f.recommendation))[:4]
    if verify:
        text += "\nVerify next:\n" + "\n".join(verify)
    return text


def llm_summary(docs, findings) -> tuple[str | None, str]:
    """Returns (text or None, status note)."""
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        return None, "LLM summary disabled (no ANTHROPIC_API_KEY set) - template summary used"
    try:
        import anthropic
    except ImportError:
        return None, "anthropic package not installed - template summary used"
    payload = {
        "documents": [{"doc_id": d.doc_id, "file": d.filename, "type": d.doc_type, "status": d.status}
                      for d in docs],
        "findings": [{"id": f.id, "title": f.title, "status": f.status, "basis": f.basis, "severity": f.severity,
                      "confidence": f.confidence, "category": f.category, "fields": f.fields,
                      "related": f.related, "explanation": f.explanation[:900]} for f in findings],
    }
    try:
        client = anthropic.Anthropic(timeout=90.0, max_retries=2)
        resp = client.beta.messages.create(
            model=MODEL,
            max_tokens=4000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": "low"},
            system=SYSTEM,
            messages=[{"role": "user", "content": "Write the investigation summary for these findings:\n"
                                                  + json.dumps(payload, indent=1)}],
        )
    except anthropic.AuthenticationError:
        return None, "LLM summary failed: invalid API key - template summary used"
    except anthropic.RateLimitError:
        return None, "LLM summary failed: rate limited - template summary used"
    except anthropic.APIStatusError as e:
        return None, f"LLM summary failed: API error {e.status_code} - template summary used"
    except anthropic.APIConnectionError:
        return None, "LLM summary failed: network unavailable - template summary used"
    except Exception as e:  # never let the optional LLM break an investigation
        return None, f"LLM summary failed ({type(e).__name__}) - template summary used"
    if resp.stop_reason == "refusal":
        return None, "LLM declined to summarise - template summary used"
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
    if not text:
        return None, "LLM returned no text - template summary used"
    return text, f"Summary written by {resp.model} from structured findings; statuses set by automated checks"


def summarise(docs, findings) -> dict:
    template = template_summary(docs, findings)
    text, note = llm_summary(docs, findings)
    return {"text": text or template, "template": template, "generator": "llm" if text else "template",
            "note": note, "review_priority": review_priority(findings)}
