"""
Plain sqlite3 access layer -- deliberately dependency-free (mirrors
OpenClip's approach: local SQLite file, no ORM, no external DB server).
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from typing import Any, Iterator

from .config import settings

_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    source_url TEXT,
    title TEXT,
    status TEXT NOT NULL DEFAULT 'queued',
    error TEXT,
    source_path TEXT,
    duration REAL,
    transcript_json TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS clips (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    start_s REAL NOT NULL,
    end_s REAL NOT NULL,
    aspect TEXT NOT NULL DEFAULT '9:16',
    title TEXT,
    hook_text TEXT,
    scores_json TEXT,
    total_score REAL,
    output_path TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    error TEXT,
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_clips_project ON clips(project_id);
"""


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(str(settings.DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _lock, get_conn() as conn:
        conn.executescript(SCHEMA)


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    for key in ("transcript_json", "scores_json"):
        if key in d and d[key]:
            try:
                d[key.replace("_json", "")] = json.loads(d.pop(key))
            except (json.JSONDecodeError, TypeError):
                d[key.replace("_json", "")] = None
        elif key in d:
            d[key.replace("_json", "")] = None
            d.pop(key, None)
    return d


# ---------------- projects ----------------

def create_project(source_url: str, title: str | None = None) -> str:
    pid = new_id()
    now = time.time()
    with _lock, get_conn() as conn:
        conn.execute(
            "INSERT INTO projects (id, source_url, title, status, created_at, updated_at) "
            "VALUES (?, ?, ?, 'queued', ?, ?)",
            (pid, source_url, title, now, now),
        )
    return pid


def update_project(pid: str, **fields: Any) -> None:
    if not fields:
        return
    fields["updated_at"] = time.time()
    if "transcript" in fields:
        fields["transcript_json"] = json.dumps(fields.pop("transcript"))
    cols = ", ".join(f"{k} = ?" for k in fields)
    with _lock, get_conn() as conn:
        conn.execute(f"UPDATE projects SET {cols} WHERE id = ?", (*fields.values(), pid))


def get_project(pid: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (pid,)).fetchone()
    return row_to_dict(row) if row else None


def list_projects() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
    return [row_to_dict(r) for r in rows]


def delete_project(pid: str) -> None:
    with _lock, get_conn() as conn:
        conn.execute("DELETE FROM projects WHERE id = ?", (pid,))


# ---------------- clips ----------------

def create_clip(project_id: str, start_s: float, end_s: float, **fields: Any) -> str:
    cid = new_id()
    now = time.time()
    scores = fields.pop("scores", None)
    with _lock, get_conn() as conn:
        conn.execute(
            "INSERT INTO clips (id, project_id, start_s, end_s, aspect, title, hook_text, "
            "scores_json, total_score, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)",
            (
                cid,
                project_id,
                start_s,
                end_s,
                fields.get("aspect", settings.DEFAULT_ASPECT),
                fields.get("title"),
                fields.get("hook_text"),
                json.dumps(scores) if scores else None,
                fields.get("total_score"),
                now,
            ),
        )
    return cid


def update_clip(cid: str, **fields: Any) -> None:
    if not fields:
        return
    if "scores" in fields:
        fields["scores_json"] = json.dumps(fields.pop("scores"))
    cols = ", ".join(f"{k} = ?" for k in fields)
    with _lock, get_conn() as conn:
        conn.execute(f"UPDATE clips SET {cols} WHERE id = ?", (*fields.values(), cid))


def list_clips(project_id: str) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM clips WHERE project_id = ? ORDER BY total_score DESC NULLS LAST, created_at",
            (project_id,),
        ).fetchall()
    return [row_to_dict(r) for r in rows]


def get_clip(cid: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM clips WHERE id = ?", (cid,)).fetchone()
    return row_to_dict(row) if row else None
