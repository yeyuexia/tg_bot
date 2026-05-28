"""SQLite persistence for chat state that needs to survive launchd restarts.

Stores two things:
  - claude_sessions: per-user current Claude CLI --resume session id
  - msg_responses:   recent bot responses keyed by Telegram message_id, so the
                     reply-thread context in core/chat.py keeps working after
                     a process restart
"""
import sqlite3
import time
from pathlib import Path
from typing import Iterable, Optional

_DB_PATH = Path(__file__).parent.parent / "sessions.db"
_MSG_RESPONSES_CAP = 200


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS claude_sessions (
                user_id    INTEGER PRIMARY KEY,
                session_id TEXT    NOT NULL,
                updated_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS msg_responses (
                message_id INTEGER PRIMARY KEY,
                response   TEXT    NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_msg_responses_created
                ON msg_responses(created_at);
        """)


def get_session(user_id: int) -> Optional[str]:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT session_id FROM claude_sessions WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    return row["session_id"] if row else None


def set_session(user_id: int, session_id: str) -> None:
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO claude_sessions (user_id, session_id, updated_at) "
            "VALUES (?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET "
            "  session_id = excluded.session_id, "
            "  updated_at = excluded.updated_at",
            (user_id, session_id, int(time.time())),
        )


def clear_session(user_id: int) -> None:
    with _get_conn() as conn:
        conn.execute("DELETE FROM claude_sessions WHERE user_id = ?", (user_id,))


def get_response(message_id: int) -> Optional[str]:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT response FROM msg_responses WHERE message_id = ?",
            (message_id,),
        ).fetchone()
    return row["response"] if row else None


def add_response(message_ids: Iterable[int], response: str) -> None:
    """Cache a bot response under one or more message_ids; prune to the cap."""
    now = int(time.time())
    with _get_conn() as conn:
        for mid in message_ids:
            conn.execute(
                "INSERT OR REPLACE INTO msg_responses (message_id, response, created_at) "
                "VALUES (?, ?, ?)",
                (mid, response, now),
            )
        conn.execute(
            "DELETE FROM msg_responses WHERE message_id NOT IN "
            "(SELECT message_id FROM msg_responses ORDER BY created_at DESC LIMIT ?)",
            (_MSG_RESPONSES_CAP,),
        )


init_db()
