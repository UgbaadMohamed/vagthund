"""Log over hændelser og godkendelsesliste (SQLite).

Dataminimering (GDPR): vi gemmer KUN type, zone, begrundelse, tidspunkt
og navnet på evt. handling. Aldrig selve beskederne.
"""

import json
import sqlite3
import threading
from datetime import datetime, timezone

_lock = threading.Lock()


class EventLog:
    def __init__(self, path: str):
        self.path = path
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with _lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    time TEXT NOT NULL,
                    layer TEXT NOT NULL,
                    zone TEXT NOT NULL,
                    action_taken TEXT NOT NULL,
                    reasons TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS approvals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    time TEXT NOT NULL,
                    tool TEXT NOT NULL,
                    reasons TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'afventer'
                );
                """
            )
            self._conn.commit()

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def event(self, layer: str, zone: str, action_taken: str, reasons: list[str]):
        with _lock:
            self._conn.execute(
                "INSERT INTO events (time, layer, zone, action_taken, reasons) VALUES (?,?,?,?,?)",
                (self._now(), layer, zone, action_taken, json.dumps(reasons, ensure_ascii=False)),
            )
            self._conn.commit()

    def add_approval(self, tool: str, reasons: list[str]) -> int:
        with _lock:
            cur = self._conn.execute(
                "INSERT INTO approvals (time, tool, reasons) VALUES (?,?,?)",
                (self._now(), tool, json.dumps(reasons, ensure_ascii=False)),
            )
            self._conn.commit()
            return cur.lastrowid

    def set_approval(self, approval_id: int, status: str) -> bool:
        with _lock:
            cur = self._conn.execute(
                "UPDATE approvals SET status=? WHERE id=? AND status='afventer'", (status, approval_id)
            )
            self._conn.commit()
            return cur.rowcount == 1

    def list_events(self, limit: int = 100):
        with _lock:
            rows = self._conn.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r, reasons=json.loads(r["reasons"])) for r in rows]

    def list_approvals(self):
        with _lock:
            rows = self._conn.execute("SELECT * FROM approvals ORDER BY id DESC").fetchall()
        return [dict(r, reasons=json.loads(r["reasons"])) for r in rows]
