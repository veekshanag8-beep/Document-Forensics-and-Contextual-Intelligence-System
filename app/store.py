"""Persistence: SQLite for cases, documents, reviewer decisions and a hash-chained audit log.

Audit log: every entry stores sha256(prev_hash + canonical entry). Changing, inserting or deleting any past entry
breaks the chain, which /api/audit/verify detects (tamper-evident, in the spirit of ISO/IEC 27037 chain of custody).
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CASES = DATA / "cases"
DB = DATA / "forensics.db"
_lock = threading.Lock()
GENESIS = "0" * 64


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def conn() -> sqlite3.Connection:
    DATA.mkdir(exist_ok=True)
    c = sqlite3.connect(DB, timeout=30, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def init():
    CASES.mkdir(parents=True, exist_ok=True)
    with _lock, conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS cases(id TEXT PRIMARY KEY, name TEXT, created TEXT, status TEXT, stage TEXT,
            progress REAL, error TEXT, stages TEXT);
        CREATE TABLE IF NOT EXISTS documents(case_id TEXT, doc_id TEXT, filename TEXT, sha256 TEXT, size INTEGER,
            uploaded TEXT, PRIMARY KEY(case_id, doc_id));
        CREATE TABLE IF NOT EXISTS reviews(case_id TEXT, finding_id TEXT, decision TEXT, note TEXT, reviewer TEXT,
            ts TEXT, PRIMARY KEY(case_id, finding_id));
        CREATE TABLE IF NOT EXISTS audit(seq INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, case_id TEXT, actor TEXT,
            action TEXT, details TEXT, prev_hash TEXT, hash TEXT);
        """)


def _entry_hash(prev, ts, case_id, actor, action, details) -> str:
    canon = json.dumps([prev, ts, case_id, actor, action, details], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode()).hexdigest()


def audit(case_id: str | None, action: str, details: dict | None = None, actor: str = "system") -> None:
    details_s = json.dumps(details or {}, sort_keys=True, default=str)
    with _lock, conn() as c:
        row = c.execute("SELECT hash FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
        prev = row["hash"] if row else GENESIS
        ts = now()
        h = _entry_hash(prev, ts, case_id, actor, action, details_s)
        c.execute("INSERT INTO audit(ts, case_id, actor, action, details, prev_hash, hash) VALUES(?,?,?,?,?,?,?)",
                  (ts, case_id, actor, action, details_s, prev, h))


def audit_entries(case_id: str | None = None) -> list[dict]:
    with conn() as c:
        if case_id:
            rows = c.execute("SELECT * FROM audit WHERE case_id=? ORDER BY seq", (case_id,)).fetchall()
        else:
            rows = c.execute("SELECT * FROM audit ORDER BY seq").fetchall()
    return [dict(r) | {"details": json.loads(r["details"])} for r in rows]


def verify_chain() -> dict:
    with conn() as c:
        rows = c.execute("SELECT * FROM audit ORDER BY seq").fetchall()
    prev = GENESIS
    for r in rows:
        h = _entry_hash(prev, r["ts"], r["case_id"], r["actor"], r["action"], r["details"])
        if r["prev_hash"] != prev or r["hash"] != h:
            return {"valid": False, "entries": len(rows), "broken_at_seq": r["seq"]}
        prev = r["hash"]
    return {"valid": True, "entries": len(rows), "head": prev}


def create_case(case_id: str, name: str, stages: list[str]):
    with _lock, conn() as c:
        c.execute("INSERT INTO cases VALUES(?,?,?,?,?,?,?,?)",
                  (case_id, name, now(), "queued", "queued", 0.0, None, json.dumps(
                      [{"name": s, "status": "pending"} for s in stages])))


def add_document(case_id, doc_id, filename, sha, size):
    with _lock, conn() as c:
        c.execute("INSERT INTO documents VALUES(?,?,?,?,?,?)", (case_id, doc_id, filename, sha, size, now()))


def update_case(case_id: str, **kw):
    if "stages" in kw:
        kw["stages"] = json.dumps(kw["stages"])
    sets = ", ".join(f"{k}=?" for k in kw)
    with _lock, conn() as c:
        c.execute(f"UPDATE cases SET {sets} WHERE id=?", (*kw.values(), case_id))


def get_case(case_id: str) -> dict | None:
    with conn() as c:
        r = c.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
        if not r:
            return None
        docs = c.execute("SELECT * FROM documents WHERE case_id=? ORDER BY doc_id", (case_id,)).fetchall()
    d = dict(r)
    d["stages"] = json.loads(d["stages"] or "[]")
    d["documents"] = [dict(x) for x in docs]
    return d


def list_cases() -> list[dict]:
    with conn() as c:
        rows = c.execute("SELECT id, name, created, status, progress FROM cases ORDER BY created DESC").fetchall()
    return [dict(r) for r in rows]


def set_review(case_id, finding_id, decision, note, reviewer):
    with _lock, conn() as c:
        c.execute("INSERT OR REPLACE INTO reviews VALUES(?,?,?,?,?,?)",
                  (case_id, finding_id, decision, note, reviewer, now()))


def reviews(case_id) -> dict:
    with conn() as c:
        rows = c.execute("SELECT * FROM reviews WHERE case_id=?", (case_id,)).fetchall()
    return {r["finding_id"]: dict(r) for r in rows}
