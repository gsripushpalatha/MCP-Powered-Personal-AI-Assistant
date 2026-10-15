import datetime
import json
from pathlib import Path
import sqlite3
import uuid

DB_PATH = Path(__file__).resolve().parent / "chat_history.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_chat_db():
    """Initialize chat persistence tables (conversations and chat_messages) and migrate."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        
        # Check if legacy 'messages' table exists and rename/migrate to 'chat_messages'
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='messages'")
        legacy_table = cursor.fetchone() is not None
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='chat_messages'")
        chat_table = cursor.fetchone() is not None

        if legacy_table and not chat_table:
            cursor.execute("ALTER TABLE messages RENAME TO chat_messages")
        else:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tools_json TEXT,
                    image_b64 TEXT,
                    thought TEXT,
                    feedback TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (conversation_id) REFERENCES conversations (id) ON DELETE CASCADE
                )
                """
            )

        # Handle migration for extra columns if needed
        for col in ["thought", "feedback"]:
            try:
                cursor.execute(f"ALTER TABLE chat_messages ADD COLUMN {col} TEXT")
            except Exception:
                pass

        # Maintain backward compatibility view for any legacy scripts querying 'messages'
        cursor.execute("DROP VIEW IF EXISTS messages")
        cursor.execute(
            """
            CREATE VIEW IF NOT EXISTS messages AS
            SELECT id, conversation_id, role, content, tools_json, image_b64, thought, feedback, created_at
            FROM chat_messages
            """
        )

        conn.commit()


# Ensure tables exist
init_chat_db()


def create_conversation(title: str = "New Chat") -> str:
    """Create a new conversation thread and return its ID."""
    conv_id = f"conv_{uuid.uuid4().hex[:10]}"
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (conv_id, title, now, now),
        )
        conn.commit()
    return conv_id


def list_conversations() -> list[dict]:
    """Retrieve all conversations ordered by recent activity."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, title, created_at, updated_at FROM conversations ORDER BY updated_at DESC"
        )
        rows = cursor.fetchall()
    return [
        {"id": r[0], "title": r[1], "created_at": r[2], "updated_at": r[3]}
        for r in rows
    ]


def get_conversation_messages(conv_id: str) -> list[dict]:
    """Get all messages for a specific conversation in chronological order."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, role, content, tools_json, image_b64, thought, feedback, created_at
            FROM chat_messages
            WHERE conversation_id = ?
            ORDER BY id ASC
            """,
            (conv_id,),
        )
        rows = cursor.fetchall()

    messages = []
    for r in rows:
        tools = None
        if r[3]:
            try:
                tools = json.loads(r[3])
            except Exception:
                tools = None
        messages.append(
            {
                "id": r[0],
                "role": r[1],
                "content": r[2],
                "tools": tools,
                "image_b64": r[4],
                "thought": r[5],
                "feedback": r[6],
                "created_at": r[7],
            }
        )
    return messages


def add_message(
    conv_id: str,
    role: str,
    content: str,
    tools: list = None,
    image_b64: str = None,
    thought: str = None,
    feedback: str = None,
    **kwargs,
) -> int:
    """Append a message to a conversation thread and update timestamp."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tools_str = json.dumps(tools) if tools else None

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO chat_messages (conversation_id, role, content, tools_json, image_b64, thought, feedback, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (conv_id, role, content, tools_str, image_b64, thought, feedback, now),
        )
        msg_id = cursor.lastrowid
        cursor.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (now, conv_id),
        )
        conn.commit()
    return msg_id


def set_message_feedback(msg_id: int, feedback: str):
    """Set feedback ('positive' or 'negative') on a message."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE chat_messages SET feedback = ? WHERE id = ?",
            (feedback, msg_id),
        )
        conn.commit()


def delete_last_assistant_message(conv_id: str):
    """Delete the last assistant message in a thread (for Regenerate)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id FROM chat_messages
            WHERE conversation_id = ? AND role = 'assistant'
            ORDER BY id DESC LIMIT 1
            """,
            (conv_id,),
        )
        row = cursor.fetchone()
        if row:
            cursor.execute("DELETE FROM chat_messages WHERE id = ?", (row[0],))
            conn.commit()


def delete_last_turn(conv_id: str) -> str:
    """Delete the last assistant response and user message, returning the user prompt."""
    with get_connection() as conn:
        cursor = conn.cursor()
        # Find last assistant message
        cursor.execute(
            """
            SELECT id FROM chat_messages
            WHERE conversation_id = ? AND role = 'assistant'
            ORDER BY id DESC LIMIT 1
            """,
            (conv_id,),
        )
        row = cursor.fetchone()
        if row:
            cursor.execute("DELETE FROM chat_messages WHERE id = ?", (row[0],))

        # Find last user message
        cursor.execute(
            """
            SELECT id, content FROM chat_messages
            WHERE conversation_id = ? AND role = 'user'
            ORDER BY id DESC LIMIT 1
            """,
            (conv_id,),
        )
        user_row = cursor.fetchone()
        user_text = ""
        if user_row:
            user_text = user_row[1]
            cursor.execute("DELETE FROM chat_messages WHERE id = ?", (user_row[0],))

        conn.commit()
    return user_text


def update_conversation_title(conv_id: str, title: str):
    """Update conversation display title."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE conversations SET title = ? WHERE id = ?",
            (title.strip(), conv_id),
        )
        conn.commit()


def delete_conversation(conv_id: str):
    """Delete a conversation and all its messages."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM chat_messages WHERE conversation_id = ?", (conv_id,))
        cursor.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
        conn.commit()


def search_conversations(query: str) -> list[dict]:
    """Search conversations where title or message content matches the keyword."""
    if not query.strip():
        return list_conversations()

    term = f"%{query.strip().lower()}%"
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT DISTINCT c.id, c.title, c.created_at, c.updated_at
            FROM conversations c
            LEFT JOIN chat_messages m ON c.id = m.conversation_id
            WHERE LOWER(c.title) LIKE ? OR LOWER(m.content) LIKE ?
            ORDER BY c.updated_at DESC
            """,
            (term, term),
        )
        rows = cursor.fetchall()
    return [
        {"id": r[0], "title": r[1], "created_at": r[2], "updated_at": r[3]}
        for r in rows
    ]


def group_conversations_by_date(conv_list: list[dict]) -> dict[str, list[dict]]:
    """Group conversations into 'Today', 'Yesterday', 'Previous 7 Days', and 'Older'."""
    today = datetime.datetime.now().date()
    groups = {
        "Today": [],
        "Yesterday": [],
        "Previous 7 Days": [],
        "Older": [],
    }
    for c in conv_list:
        try:
            c_date = datetime.datetime.strptime(c["updated_at"], "%Y-%m-%d %H:%M:%S").date()
        except Exception:
            c_date = today
        diff = (today - c_date).days
        if diff <= 0:
            groups["Today"].append(c)
        elif diff == 1:
            groups["Yesterday"].append(c)
        elif 2 <= diff <= 7:
            groups["Previous 7 Days"].append(c)
        else:
            groups["Older"].append(c)
    return {k: v for k, v in groups.items() if v}

