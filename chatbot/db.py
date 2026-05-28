"""
chatbot/db.py
=============
PostgreSQL-backed storage — users, chats, messages, sessions.

Tables:
  users    — our app users (email + bcrypt password)
  chats    — chat sessions owned by a user
  messages — all messages per chat (user, assistant, tool)
  sessions — AllMasters JWT per user per chat
"""

import os
import json
import psycopg2
from psycopg2 import pool
from dotenv import load_dotenv

load_dotenv()

_pool: pool.ThreadedConnectionPool = None


def init_db():
    """Initialize connection pool and create tables. Called once on startup."""
    global _pool
    _pool = pool.ThreadedConnectionPool(
        minconn=2,
        maxconn=10,
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 5432)),
        dbname=os.getenv("DB_NAME", "am_chatbot"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", ""),
    )
    _create_tables()


def _get_conn():
    return _pool.getconn()


def _put_conn(conn):
    _pool.putconn(conn)


def _create_tables():
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    name          TEXT NOT NULL,
                    email         TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at    TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS chats (
                    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    title      TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id        SERIAL PRIMARY KEY,
                    chat_id   UUID NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
                    role      TEXT NOT NULL,
                    content   TEXT NOT NULL,
                    tool_name TEXT,
                    timestamp TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages(chat_id);

                CREATE TABLE IF NOT EXISTS sessions (
                    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    chat_id    UUID NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
                    jwt        TEXT,
                    expires_at TEXT,
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(user_id, chat_id)
                );
            """)
        conn.commit()
    finally:
        _put_conn(conn)


# ── Users ─────────────────────────────────────────────────────────────────────

def create_user(name: str, email: str, password_hash: str) -> dict:
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (name, email, password_hash)
                VALUES (%s, %s, %s)
                RETURNING id, name, email, created_at
                """,
                (name, email, password_hash)
            )
            row = cur.fetchone()
        conn.commit()
    finally:
        _put_conn(conn)
    return {"id": str(row[0]), "name": row[1], "email": row[2]}


def get_user_by_email(email: str) -> dict | None:
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, name, email, password_hash FROM users WHERE email = %s",
                (email,)
            )
            row = cur.fetchone()
    finally:
        _put_conn(conn)
    if not row:
        return None
    return {"id": str(row[0]), "name": row[1], "email": row[2], "password_hash": row[3]}


# ── Chats ─────────────────────────────────────────────────────────────────────

def create_chat(user_id: str) -> str:
    """Create a new chat for a user. Title set later on first message."""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO chats (user_id) VALUES (%s) RETURNING id",
                (user_id,)
            )
            chat_id = str(cur.fetchone()[0])
        conn.commit()
    finally:
        _put_conn(conn)
    return chat_id


def set_chat_title(chat_id: str, title: str):
    """Set title from first user message — only if not already set."""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE chats SET title = %s WHERE id = %s AND title IS NULL",
                (title, chat_id)
            )
        conn.commit()
    finally:
        _put_conn(conn)


def get_user_chats(user_id: str) -> list[dict]:
    """Return all chats for a user ordered by most recent."""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, title, created_at
                FROM chats
                WHERE user_id = %s
                ORDER BY created_at DESC
                """,
                (user_id,)
            )
            rows = cur.fetchall()
    finally:
        _put_conn(conn)
    return [
        {"id": str(r[0]), "title": r[1] or "New Chat", "created_at": str(r[2])}
        for r in rows
    ]


def get_chat_owner(chat_id: str) -> str | None:
    """Return user_id who owns this chat — used for ownership verification."""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id FROM chats WHERE id = %s", (chat_id,))
            row = cur.fetchone()
    finally:
        _put_conn(conn)
    return str(row[0]) if row else None


def clear_chat(chat_id: str):
    """Delete all messages and AM session for a chat."""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM messages WHERE chat_id = %s", (chat_id,))
            cur.execute("DELETE FROM sessions WHERE chat_id = %s", (chat_id,))
        conn.commit()
    finally:
        _put_conn(conn)


# ── Messages ──────────────────────────────────────────────────────────────────

def save_message(chat_id: str, role: str, content: str, tool_name: str = None):
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO messages (chat_id, role, content, tool_name) VALUES (%s, %s, %s, %s)",
                (chat_id, role, content, tool_name)
            )
        conn.commit()
    finally:
        _put_conn(conn)


def delete_trailing_turn(chat_id: str):
    """
    Delete all messages from the last user message onwards (inclusive).
    Used after a failed-auth flow to remove the poisoned tool_call/tool/assistant
    triplet so the auto-resend starts from clean history.
    """
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM messages WHERE chat_id = %s AND role = 'user' ORDER BY id DESC LIMIT 1",
                (chat_id,)
            )
            row = cur.fetchone()
            if not row:
                return
            last_user_id = row[0]
            cur.execute(
                "DELETE FROM messages WHERE chat_id = %s AND id >= %s",
                (chat_id, last_user_id)
            )
        conn.commit()
    finally:
        _put_conn(conn)


_INTERRUPTED_STUB = json.dumps({
    "error":   "tool_call_interrupted",
    "message": "Previous tool call was interrupted. Please retry."
})


def _sanitize_tool_pairs(messages: list[dict]) -> list[dict]:
    """
    Bedrock requires every tool_use to be followed by a matching tool_result
    before the next user/assistant turn. If a stream was cut between saving
    `assistant_tool_call` and saving the `tool` row, the loaded history will
    have an orphan tool_use. Insert a stub tool_result so the conversation
    is replayable.
    """
    sanitized: list[dict] = []
    pending: list[str]    = []   # tool_use IDs from the most recent assistant turn

    def _flush_orphans():
        for tid in pending:
            sanitized.append({
                "role":         "tool",
                "tool_call_id": tid,
                "content":      _INTERRUPTED_STUB,
            })
        pending.clear()

    for msg in messages:
        role = msg.get("role")
        if role == "assistant" and msg.get("tool_calls"):
            _flush_orphans()
            pending.extend(tc["id"] for tc in msg["tool_calls"])
            sanitized.append(msg)
        elif role == "tool":
            tcid = msg.get("tool_call_id")
            if tcid in pending:
                pending.remove(tcid)
                sanitized.append(msg)
            # tool message with no matching pending id is dropped — orphan result
        else:
            _flush_orphans()
            sanitized.append(msg)

    _flush_orphans()
    return sanitized


def load_history(chat_id: str, limit: int = 20) -> list[dict]:
    """
    Load last N messages for LLM context.
    Reconstructs proper tool_use / tool_result pairs for Bedrock.
    """
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT role, content, tool_name
                FROM (
                    SELECT id, role, content, tool_name
                    FROM messages
                    WHERE chat_id = %s
                    ORDER BY id DESC
                    LIMIT %s
                ) sub
                ORDER BY id ASC
                """,
                (chat_id, limit)
            )
            rows = cur.fetchall()
    finally:
        _put_conn(conn)

    messages = []
    for role, content, tool_name in rows:
        if role == "assistant_tool_call":
            # Restore full assistant message with tool_calls for Bedrock
            messages.append(json.loads(content))
        elif role == "tool":
            # tool_name column stores actual tc.id — must match assistant tool_calls
            messages.append({
                "role":         "tool",
                "content":      content,
                "tool_call_id": tool_name
            })
        else:
            messages.append({"role": role, "content": content})

    return _sanitize_tool_pairs(messages)


def load_display_history(chat_id: str) -> list[dict]:
    """Full user/assistant history for UI display on page load."""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT role, content, timestamp
                FROM messages
                WHERE chat_id = %s AND role IN ('user', 'assistant')
                ORDER BY id ASC
                """,
                (chat_id,)
            )
            rows = cur.fetchall()
    finally:
        _put_conn(conn)
    return [
        {"role": r[0], "content": r[1], "timestamp": str(r[2])}
        for r in rows
    ]


# ── AllMasters JWT Sessions ───────────────────────────────────────────────────

def save_am_jwt(user_id: str, chat_id: str, auth_response: dict):
    """Store AM JWT after successful AllMasters authentication."""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO sessions (user_id, chat_id, jwt, expires_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id, chat_id) DO UPDATE SET
                    jwt        = EXCLUDED.jwt,
                    expires_at = EXCLUDED.expires_at,
                    updated_at = NOW()
                """,
                (
                    user_id,
                    chat_id,
                    auth_response.get("jwt"),
                    auth_response.get("expires_at"),
                )
            )
        conn.commit()
    finally:
        _put_conn(conn)


def get_am_jwt(user_id: str, chat_id: str) -> str | None:
    """Retrieve stored AM JWT for this user+chat combination."""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT jwt FROM sessions WHERE user_id = %s AND chat_id = %s",
                (user_id, chat_id)
            )
            row = cur.fetchone()
    finally:
        _put_conn(conn)
    return row[0] if row else None


def clear_am_jwt(user_id: str, chat_id: str):
    """Remove expired/invalid AM JWT so the next request triggers re-authentication."""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM sessions WHERE user_id = %s AND chat_id = %s",
                (user_id, chat_id)
            )
        conn.commit()
    finally:
        _put_conn(conn)
