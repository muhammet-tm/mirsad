"""SQLite store: candidates, scores, evidence, captures, summaries, decisions, runs, and an audit log.

The audit table is append-only by design (no update or delete statement anywhere in the code base),
and every view, decision, and export writes to it. Query strings are stored only as a keyed hash in
`url_redacted`; the raw URL stays in `url` for the evidence package and is never sent to the
dashboard's list views.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from ..config import DB_PATH, settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS candidates (
  id TEXT PRIMARY KEY, url TEXT NOT NULL, url_redacted TEXT NOT NULL, canonical TEXT NOT NULL,
  host TEXT, domain TEXT, channel TEXT NOT NULL, channel_detail TEXT, query TEXT, rank INTEGER,
  is_ad INTEGER DEFAULT 0, listing_json TEXT, imitates TEXT, first_seen TEXT, discovered_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'new', assigned_to TEXT, UNIQUE(canonical, channel));
CREATE TABLE IF NOT EXISTS scores (
  candidate_id TEXT PRIMARY KEY REFERENCES candidates(id), risk REAL, model_mean REAL, votes_json TEXT,
  reasons_json TEXT, rules_json TEXT, threshold REAL, scoring_ms REAL, scored_at TEXT);
CREATE TABLE IF NOT EXISTS evidence (
  id INTEGER PRIMARY KEY AUTOINCREMENT, candidate_id TEXT REFERENCES candidates(id), kind TEXT, label TEXT,
  source TEXT, value_json TEXT, observed_at TEXT);
CREATE TABLE IF NOT EXISTS captures (
  candidate_id TEXT PRIMARY KEY REFERENCES candidates(id), screenshot TEXT, title TEXT, final_url TEXT,
  forms_json TEXT, text_excerpt TEXT, brand_json TEXT, captured_at TEXT);
CREATE TABLE IF NOT EXISTS summaries (
  candidate_id TEXT PRIMARY KEY REFERENCES candidates(id), model TEXT, en TEXT, ar TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS decisions (
  id INTEGER PRIMARY KEY AUTOINCREMENT, candidate_id TEXT REFERENCES candidates(id), action TEXT,
  analyst TEXT, note TEXT, at TEXT);
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, channel TEXT, started TEXT, finished TEXT, items INTEGER,
  flagged INTEGER, state TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS screened (
  day TEXT, channel TEXT, count INTEGER, PRIMARY KEY(day, channel));
CREATE TABLE IF NOT EXISTS audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, actor TEXT, action TEXT, target TEXT, detail TEXT);
CREATE INDEX IF NOT EXISTS idx_candidates_status ON candidates(status);
CREATE INDEX IF NOT EXISTS idx_evidence_candidate ON evidence(candidate_id);
"""

_lock = threading.Lock()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def redact(url: str) -> str:
    """Replace each query value with a short keyed hash, so victim emails or tokens never show."""
    from ..features.url import split

    p = split(url)
    base = f"{p.scheme}://{p.host}{':' + str(p.port) if p.port else ''}{p.path}"
    if not p.query:
        return base
    key = (settings.key("MIRSAD_REDACTION_KEY") or "mirsad-local").encode()
    parts = []
    for pair in p.query.split("&"):
        name, _, value = pair.partition("=")
        digest = hmac.new(key, value.encode(), hashlib.sha256).hexdigest()[:8] if value else ""
        parts.append(f"{name}=[{digest}]" if value else name)
    return base + "?" + "&".join(parts)


class Store:
    def __init__(self, path: Path | None = None):
        # Read the module-level path at call time, so tests (and a second database) can redirect it.
        path = path or globals()["DB_PATH"]
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def conn(self):
        with _lock:
            c = sqlite3.connect(self.path, timeout=30)
            c.row_factory = sqlite3.Row
            try:
                yield c
                c.commit()
            finally:
                c.close()

    # ---- writes -------------------------------------------------------------------------
    def audit(self, actor: str, action: str, target: str = "", detail: str = "") -> None:
        with self.conn() as c:
            c.execute("INSERT INTO audit(at, actor, action, target, detail) VALUES (?,?,?,?,?)",
                      (now(), actor, action, target, detail))

    def next_id(self, c) -> str:
        n = c.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
        return f"MR-{n + 101:04d}"

    def upsert_candidate(self, url: str, channel: str, *, channel_detail: str = "", query: str = "",
                         rank: int | None = None, is_ad: bool = False, listing: dict | None = None,
                         imitates: str | None = None, first_seen: str | None = None) -> tuple[str, bool]:
        """Insert a candidate link, or return the existing one for the same canonical URL and channel."""
        from ..features.url import canonical, host_of, registered_domain

        canon = canonical(url)
        with self.conn() as c:
            row = c.execute("SELECT id FROM candidates WHERE canonical=? AND channel=?", (canon, channel)).fetchone()
            if row:
                return row["id"], False
            cid = self.next_id(c)
            host = host_of(url)
            c.execute("""INSERT INTO candidates(id, url, url_redacted, canonical, host, domain, channel, channel_detail,
                         query, rank, is_ad, listing_json, imitates, first_seen, discovered_at)
                         VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (cid, url, redact(url), canon, host, registered_domain(host), channel, channel_detail, query,
                       rank, int(is_ad), json.dumps(listing) if listing else None, imitates, first_seen, now()))
            return cid, True

    def set_first_seen(self, cid: str, first_seen: str | None) -> None:
        if first_seen:
            with self.conn() as c:
                c.execute("UPDATE candidates SET first_seen=? WHERE id=?", (first_seen, cid))

    def save_score(self, cid: str, risk: float, model_mean: float, votes: dict, reasons: list, rules: list,
                   threshold: float, scoring_ms: float) -> None:
        with self.conn() as c:
            c.execute("""INSERT OR REPLACE INTO scores VALUES (?,?,?,?,?,?,?,?,?)""",
                      (cid, risk, model_mean, json.dumps(votes), json.dumps(reasons), json.dumps(rules),
                       threshold, scoring_ms, now()))

    def add_evidence(self, cid: str, kind: str, label: str, source: str, value: dict | None = None,
                     observed_at: str | None = None) -> None:
        with self.conn() as c:
            exists = c.execute("SELECT 1 FROM evidence WHERE candidate_id=? AND kind=? AND label=?",
                               (cid, kind, label)).fetchone()
            if not exists:
                c.execute("INSERT INTO evidence(candidate_id, kind, label, source, value_json, observed_at) VALUES (?,?,?,?,?,?)",
                          (cid, kind, label, source, json.dumps(value or {}), observed_at or now()))

    def save_capture(self, cid: str, screenshot: str | None, title: str, final_url: str, forms: list,
                     text_excerpt: str, brand: dict | None) -> None:
        with self.conn() as c:
            c.execute("INSERT OR REPLACE INTO captures VALUES (?,?,?,?,?,?,?,?)",
                      (cid, screenshot, title, final_url, json.dumps(forms), text_excerpt[:4000],
                       json.dumps(brand or {}), now()))

    def save_summary(self, cid: str, model: str, en: str, ar: str) -> None:
        with self.conn() as c:
            c.execute("INSERT OR REPLACE INTO summaries VALUES (?,?,?,?,?)", (cid, model, en, ar, now()))

    def decide(self, cid: str, action: str, analyst: str, note: str = "") -> None:
        status = {"confirm": "confirmed", "dismiss": "dismissed", "reviewing": "reviewing", "assign": "reviewing"}[action]
        with self.conn() as c:
            c.execute("UPDATE candidates SET status=?, assigned_to=COALESCE(?, assigned_to) WHERE id=?",
                      (status, analyst if action == "assign" else None, cid))
            c.execute("INSERT INTO decisions(candidate_id, action, analyst, note, at) VALUES (?,?,?,?,?)",
                      (cid, action, analyst, note, now()))
        self.audit(analyst, f"decision:{action}", cid, note)

    def start_run(self, channel: str) -> int:
        with self.conn() as c:
            cur = c.execute("INSERT INTO runs(channel, started, state) VALUES (?,?,?)", (channel, now(), "running"))
            return int(cur.lastrowid)

    def finish_run(self, run_id: int, items: int, flagged: int, state: str, detail: str) -> None:
        with self.conn() as c:
            c.execute("UPDATE runs SET finished=?, items=?, flagged=?, state=?, detail=? WHERE id=?",
                      (now(), items, flagged, state, detail, run_id))

    def count_screened(self, channel: str, n: int) -> None:
        day = now()[:10]
        with self.conn() as c:
            c.execute("""INSERT INTO screened(day, channel, count) VALUES (?,?,?)
                         ON CONFLICT(day, channel) DO UPDATE SET count = count + excluded.count""", (day, channel, n))

    # ---- reads --------------------------------------------------------------------------
    def rows(self, sql: str, args: tuple = ()) -> list[dict]:
        with self.conn() as c:
            return [dict(r) for r in c.execute(sql, args).fetchall()]

    def one(self, sql: str, args: tuple = ()) -> dict | None:
        r = self.rows(sql, args)
        return r[0] if r else None
