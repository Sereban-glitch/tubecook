"""SQLite-хранилище Tubecook v4 (WAL, транзакции, аудит).

Почему SQLite, а не файлы/Redis/PostgreSQL:
- транзакционность и атомарный ACK нужны ТЗ, при этом один процесс-исполнитель;
- один файл = тривиальный бэкап/откат (копия data/tubecook.db);
- SQLite ubiquitous на Mint, нулевая инфраструктура, WAL даёт читателей без блокировок.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
  job_id TEXT PRIMARY KEY,
  dedupe_key TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  state TEXT NOT NULL,
  priority TEXT NOT NULL DEFAULT 'auto',
  payload TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  scheduled_slot TEXT,
  due_at REAL,
  attempts INTEGER NOT NULL DEFAULT 0,
  lease_until REAL,
  lease_owner TEXT,
  supersedes_job_id TEXT,
  error TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_dedupe ON jobs (dedupe_key);

CREATE TABLE IF NOT EXISTS inbox (
  job_id TEXT NOT NULL,
  sender_id INTEGER NOT NULL,
  part INTEGER NOT NULL,
  total INTEGER NOT NULL,
  text TEXT NOT NULL,
  received_at TEXT NOT NULL,
  PRIMARY KEY (job_id, part)
);

CREATE TABLE IF NOT EXISTS publish_targets (
  job_id TEXT NOT NULL,
  target TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'pending',
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  result_ref TEXT,
  detail TEXT,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (job_id, target)
);

CREATE TABLE IF NOT EXISTS assets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  url TEXT,
  author TEXT,
  license TEXT,
  attribution TEXT,
  fetched_at TEXT,
  local_path TEXT,
  status TEXT,
  transforms TEXT
);

CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  job_id TEXT,
  kind TEXT NOT NULL,
  data TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_job ON events (job_id);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    # NB: executescript() неявно COMMIT-ит, поэтому держим его вне tx()
    conn.executescript(SCHEMA)
    conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', ?)",
                 (str(SCHEMA_VERSION),))


@contextmanager
def tx(conn: sqlite3.Connection):
    """Транзакция: COMMIT при успехе, ROLLBACK при исключении."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def event(conn: sqlite3.Connection, kind: str, job_id: str | None = None,
          data: dict | None = None, ts: str | None = None) -> None:
    """Аудит (append-only). Отмена задания ничего не стирает."""
    from tubecook.models import now_iso
    conn.execute(
        "INSERT INTO events(ts, job_id, kind, data) VALUES (?,?,?,?)",
        (ts or now_iso(), job_id, kind, json.dumps(data or {}, ensure_ascii=False)))


def get_meta(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT INTO meta(key, value) VALUES (?,?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
