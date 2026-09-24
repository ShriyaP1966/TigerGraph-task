import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "ledger.sqlite3"

SCHEMA = """
CREATE TABLE IF NOT EXISTS actions (
    action_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    action TEXT NOT NULL,
    route TEXT NOT NULL,
    reason TEXT,
    status TEXT NOT NULL,
    actor TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(SCHEMA)
    conn.row_factory = sqlite3.Row
    return conn


def log_action(action_id: str, case_id: str, action: str, route: str, reason: str, status: str, actor: str, now: str) -> None:
    conn = _conn()
    conn.execute(
        "INSERT OR REPLACE INTO actions (action_id, case_id, action, route, reason, status, actor, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (action_id, case_id, action, route, reason, status, actor, now, now),
    )
    conn.commit()
    conn.close()


def update_status(action_id: str, status: str, actor: str, now: str) -> bool:
    conn = _conn()
    cur = conn.execute("UPDATE actions SET status=?, actor=?, updated_at=? WHERE action_id=?", (status, actor, now, action_id))
    conn.commit()
    updated = cur.rowcount > 0
    conn.close()
    return updated


def get_action(action_id: str) -> dict | None:
    conn = _conn()
    row = conn.execute("SELECT * FROM actions WHERE action_id=?", (action_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_pending() -> list[dict]:
    conn = _conn()
    rows = conn.execute("SELECT * FROM actions WHERE status IN ('pending_approval','recommended') ORDER BY created_at").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def list_for_case(case_id: str) -> list[dict]:
    conn = _conn()
    rows = conn.execute("SELECT * FROM actions WHERE case_id=? ORDER BY created_at", (case_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
