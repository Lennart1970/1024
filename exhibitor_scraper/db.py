from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable


SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_url TEXT NOT NULL UNIQUE,
    directory_url TEXT,
    status TEXT NOT NULL,
    extraction_method TEXT,
    expected_count INTEGER,
    actual_count INTEGER,
    pilot_count INTEGER,
    pilot_passed INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    confidence_avg REAL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS exhibitors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    exhibitor_name TEXT NOT NULL,
    official_domain TEXT,
    source_url TEXT,
    confidence REAL NOT NULL,
    raw_payload TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(event_id, exhibitor_name, official_domain),
    FOREIGN KEY(event_id) REFERENCES events(id)
);

CREATE TABLE IF NOT EXISTS event_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER,
    level TEXT NOT NULL,
    step TEXT NOT NULL,
    message TEXT NOT NULL,
    payload TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(event_id) REFERENCES events(id)
);
"""


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    def upsert_event(self, event_url: str, status: str) -> int:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO events(event_url, status)
                VALUES(?, ?)
                ON CONFLICT(event_url) DO UPDATE SET
                    status=excluded.status,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (event_url, status),
            )
            row = conn.execute("SELECT id FROM events WHERE event_url = ?", (event_url,)).fetchone()
            return int(row["id"])

    def update_event(self, event_id: int, **fields) -> None:
        if not fields:
            return
        assignments = ", ".join(f"{key} = ?" for key in fields)
        values = list(fields.values()) + [event_id]
        with self.connect() as conn:
            conn.execute(f"UPDATE events SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE id = ?", values)

    def log(self, event_id: int | None, level: str, step: str, message: str, payload: str | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO event_logs(event_id, level, step, message, payload) VALUES (?, ?, ?, ?, ?)",
                (event_id, level, step, message, payload),
            )

    def replace_exhibitors(self, event_id: int, exhibitors: Iterable[tuple[str, str | None, str | None, float, str | None]]) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM exhibitors WHERE event_id = ?", (event_id,))
            conn.executemany(
                """
                INSERT OR IGNORE INTO exhibitors(event_id, exhibitor_name, official_domain, source_url, confidence, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                ((event_id, *row) for row in exhibitors),
            )

    def failed_event_urls(self) -> list[str]:
        with self.connect() as conn:
            rows = conn.execute("SELECT event_url FROM events WHERE status = 'failed' ORDER BY updated_at DESC").fetchall()
            return [str(row["event_url"]) for row in rows]

    def successful_event_exists(self, event_url: str) -> bool:
        with self.connect() as conn:
            row = conn.execute("SELECT 1 FROM events WHERE event_url = ? AND status = 'completed' LIMIT 1", (event_url,)).fetchone()
            return row is not None

    def summary_rows(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT event_url, status, extraction_method, pilot_passed, expected_count, actual_count, last_error, updated_at
                FROM events
                ORDER BY updated_at DESC
                """
            ).fetchall()

    def export_rows(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT e.event_url, e.directory_url, e.extraction_method,
                       x.exhibitor_name, x.official_domain, x.confidence, x.source_url
                FROM exhibitors x
                JOIN events e ON e.id = x.event_id
                WHERE e.status = 'completed'
                ORDER BY e.event_url, x.exhibitor_name
                """
            ).fetchall()
