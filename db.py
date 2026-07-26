"""SQLite persistence layer for medicine schedules."""

import sqlite3
from contextlib import contextmanager

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_phone TEXT NOT NULL,
    medicine_name TEXT NOT NULL,
    dosage TEXT NOT NULL,
    timing_label TEXT NOT NULL,
    alert_time_24 TEXT NOT NULL,
    alert_time_display TEXT NOT NULL,
    benefits TEXT NOT NULL DEFAULT '',
    precautions TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    last_sent_date TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_schedules_alert_time ON schedules (alert_time_24);
"""


@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_connection() as conn:
        conn.executescript(SCHEMA)


def insert_schedule(
    parent_phone,
    medicine_name,
    dosage,
    timing_label,
    alert_time_24,
    alert_time_display,
    benefits="",
    precautions="",
):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO schedules
                (parent_phone, medicine_name, dosage, timing_label, alert_time_24,
                 alert_time_display, benefits, precautions)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                parent_phone, medicine_name, dosage, timing_label, alert_time_24,
                alert_time_display, benefits, precautions,
            ),
        )


def get_due_schedules(current_time_24, today):
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM schedules
            WHERE active = 1
              AND alert_time_24 = ?
              AND (last_sent_date IS NULL OR last_sent_date != ?)
            """,
            (current_time_24, today),
        ).fetchall()
        return [dict(row) for row in rows]


def mark_sent(schedule_id, today):
    with get_connection() as conn:
        conn.execute(
            "UPDATE schedules SET last_sent_date = ? WHERE id = ?",
            (today, schedule_id),
        )


def deactivate_schedule(schedule_id):
    with get_connection() as conn:
        conn.execute("UPDATE schedules SET active = 0 WHERE id = ?", (schedule_id,))


def list_schedules(parent_phone=None):
    with get_connection() as conn:
        if parent_phone:
            rows = conn.execute(
                "SELECT * FROM schedules WHERE parent_phone = ? ORDER BY alert_time_24",
                (parent_phone,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM schedules ORDER BY alert_time_24").fetchall()
        return [dict(row) for row in rows]
