"""ذاكرة العملية — Process Memory + Decision Provenance (القسمان 9.6 و9.12).

تحفظ الذاكرة: القرار، مبرره، البدائل التي نوقشت، النتيجة، الدرس
المستخلص، التغيير الذي نتج عنه، من اتخذ القرار (شخص أو وكيل)،
والسياق والأدلة — وتجيب عن أسئلة مثل: لماذا أُضيفت خطوة موافقة قبل
سنوات؟ ما الحادثة التي أدت إلى هذه السياسة؟ ما التغيير الذي نجح أو فشل؟

تخزين SQLite محلي — سجل غير قابل للتلاعب عبر تسلسل تجزئة (hash chain)
على نمط Immutable Audit Logs.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional

from .models import Decision, Event, ExceptionCase


class ProcessMemory:
    """ذاكرة قرارات وأحداث ودروس مع سجل تدقيق غير قابل للتلاعب."""

    def __init__(self, db_path: str | Path = ":memory:"):
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    # --------------------------------------------------------------
    def _init_schema(self) -> None:
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS decisions (
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            id TEXT, subject TEXT, outcome TEXT, kind TEXT,
            actor TEXT, rationale TEXT, alternatives TEXT,
            sources TEXT, policies TEXT, model TEXT,
            confidence REAL, approved_by TEXT,
            timestamp REAL, payload TEXT, prev_hash TEXT, hash TEXT
        );
        CREATE TABLE IF NOT EXISTS events (
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            id TEXT, case_id TEXT, step TEXT, actor TEXT, action TEXT,
            timestamp REAL, payload TEXT, prev_hash TEXT, hash TEXT
        );
        CREATE TABLE IF NOT EXISTS lessons (
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT, lesson TEXT, source_decision TEXT,
            change_result TEXT, timestamp REAL
        );
        """)

    # --------------------------------------------------------------
    def _chain(self, table: str, payload: str) -> tuple[str, str]:
        row = self.conn.execute(
            f"SELECT hash FROM {table} ORDER BY seq DESC LIMIT 1").fetchone()
        prev = row["hash"] if row else "GENESIS"
        digest = hashlib.sha256((prev + payload).encode()).hexdigest()
        return prev, digest

    # --------------------------------------------------------------
    def store_decision(self, d: Decision) -> str:
        payload = json.dumps(asdict(d), ensure_ascii=False, default=str)
        prev, digest = self._chain("decisions", payload)
        self.conn.execute(
            """INSERT INTO decisions
            (id, subject, outcome, kind, actor, rationale, alternatives,
             sources, policies, model, confidence, approved_by,
             timestamp, payload, prev_hash, hash)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (d.id, d.subject, json.dumps(d.outcome, ensure_ascii=False,
                                         default=str),
             d.kind.value, d.actor, d.rationale,
             json.dumps(d.alternatives, ensure_ascii=False, default=str),
             json.dumps(d.sources, ensure_ascii=False),
             json.dumps(d.policies, ensure_ascii=False),
             d.model, d.confidence, d.approved_by,
             d.timestamp, payload, prev, digest))
        self.conn.commit()
        return digest

    # --------------------------------------------------------------
    def store_event(self, e: Event) -> str:
        payload = json.dumps(asdict(e), ensure_ascii=False, default=str)
        prev, digest = self._chain("events", payload)
        self.conn.execute(
            """INSERT INTO events
            (id, case_id, step, actor, action, timestamp,
             payload, prev_hash, hash)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (e.id, e.case_id, e.step, e.actor, e.action,
             e.timestamp, payload, prev, digest))
        self.conn.commit()
        return digest

    # --------------------------------------------------------------
    def store_lesson(self, topic: str, lesson: str,
                     source_decision: str = "",
                     change_result: str = "") -> None:
        self.conn.execute(
            "INSERT INTO lessons (topic, lesson, source_decision,"
            " change_result, timestamp) VALUES (?,?,?,?,?)",
            (topic, lesson, source_decision, change_result, time.time()))
        self.conn.commit()

    # --------------------------------------------------------------
    def why(self, subject_fragment: str) -> list[dict]:
        """لماذا اتُّخذ هذا القرار؟ استعلام في أصل القرارات."""
        rows = self.conn.execute(
            "SELECT * FROM decisions WHERE subject LIKE ? OR rationale LIKE ?"
            " ORDER BY timestamp DESC",
            (f"%{subject_fragment}%", f"%{subject_fragment}%")).fetchall()
        return [dict(r) for r in rows]

    # --------------------------------------------------------------
    def exceptions_for(self, step: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM events WHERE step = ? AND action = 'exception'"
            " ORDER BY timestamp DESC", (step,)).fetchall()
        return [dict(r) for r in rows]

    # --------------------------------------------------------------
    def verify_integrity(self) -> bool:
        """يتحقق من سلامة سلسلة التجزئة — أي عبث يكسر السلسلة."""
        for table in ("decisions", "events"):
            rows = self.conn.execute(
                f"SELECT payload, prev_hash, hash FROM {table}"
                " ORDER BY seq").fetchall()
            prev = "GENESIS"
            for r in rows:
                if r["prev_hash"] != prev:
                    return False
                if hashlib.sha256(
                        (prev + r["payload"]).encode()).hexdigest() != r["hash"]:
                    return False
                prev = r["hash"]
        return True

    # --------------------------------------------------------------
    def stats(self) -> dict:
        def count(t: str) -> int:
            return self.conn.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"]
        return {"decisions": count("decisions"),
                "events": count("events"),
                "lessons": count("lessons"),
                "integrity_ok": self.verify_integrity()}
