import datetime
import html
import math
import os
from pathlib import Path
import re
import sqlite3
import sys
import urllib.parse

import requests

BASE_DIR = Path(__file__).resolve().parent
NOTES_FILE = BASE_DIR / "notes.txt"
DB_FILE = BASE_DIR / "notes.db"


def init_db():
    """Initialize SQLite database for notes with automatic migration from notes.txt."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                category TEXT DEFAULT 'general',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()

        cursor.execute("SELECT COUNT(*) FROM notes")
        count = cursor.fetchone()[0]
        if count == 0 and NOTES_FILE.exists():
            for line in NOTES_FILE.read_text(encoding="utf-8").splitlines():
                text = line.strip()
                if text:
                    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                    cursor.execute(
                        "INSERT INTO notes (content, category, created_at) VALUES (?, ?, ?)",
                        (text, "imported", now_str),
                    )
            conn.commit()


# Ensure DB is ready
init_db()


def calculator(a: float, b: float = 0.0, operation: str = "add") -> float | str:
    """Perform mathematical calculations including basic arithmetic, powers, and roots."""
    op = operation.lower().strip()
    sys.stderr.write(f"[TOOL CALLED] calculator({a}, {b}, {op})\n")

    if op in ("add", "+", "sum"):
        return a + b
    elif op in ("subtract", "-", "minus", "sub"):
        return a - b
    elif op in ("multiply", "*", "mult", "product"):
        return a * b
    elif op in ("divide", "/", "div"):
        if b == 0:
            return "Error: Cannot divide by zero"
        return a / b
    elif op in ("power", "^", "pow", "exponent"):
        return math.pow(a, b)
    elif op in ("modulo", "%", "mod"):
        if b == 0:
            return "Error: Cannot modulo by zero"
        return a % b
    elif op in ("sqrt", "square_root"):
        if a < 0:
            return "Error: Cannot calculate square root of a negative number"
        return math.sqrt(a)
    else:
        return f"Error: Unknown operation '{operation}'. Supported: add, subtract, multiply, divide, power, modulo, sqrt."


def save_note(note: str, category: str = "general") -> str:
    """Save a note to the local SQLite database and append to notes.txt."""
    if not note.strip():
        return "Error: Note content cannot be empty."

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    cat = (category or "general").strip().lower()

    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO notes (content, category, created_at) VALUES (?, ?, ?)",
            (note.strip(), cat, now_str),
        )
        note_id = cursor.lastrowid
        conn.commit()

    # Keep notes.txt updated for backwards compatibility
    with NOTES_FILE.open("a", encoding="utf-8") as f:
        f.write(note.strip() + "\n")

    return f"Note #{note_id} saved successfully in category '{cat}'!"


def read_notes(category: str = "") -> str:
    """Read saved notes, optionally filtered by category."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        if category and category.strip():
            cursor.execute(
                "SELECT id, content, category, created_at FROM notes WHERE LOWER(category) = LOWER(?) ORDER BY id ASC",
                (category.strip(),),
            )
        else:
            cursor.execute(
                "SELECT id, content, category, created_at FROM notes ORDER BY id ASC"
            )
        rows = cursor.fetchall()

    if not rows:
        return "No notes found." if not category else f"No notes found in category '{category}'."

    formatted = []
    for r in rows:
        formatted.append(f"• [ID: {r[0]}] ({r[2]} | {r[3]}): {r[1]}")
    return "\n".join(formatted)


def search_notes(keyword: str) -> str:
    """Search saved notes by keyword in content or category."""
    if not keyword.strip():
        return "Error: Search keyword cannot be empty."

    search_term = f"%{keyword.strip().lower()}%"
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, content, category, created_at FROM notes
            WHERE LOWER(content) LIKE ? OR LOWER(category) LIKE ?
            ORDER BY id ASC
            """,
            (search_term, search_term),
        )
        rows = cursor.fetchall()

    if not rows:
        return f"No notes matching '{keyword}' were found."

    formatted = [f"Found {len(rows)} matching note(s):"]
    for r in rows:
        formatted.append(f"• [ID: {r[0]}] ({r[2]} | {r[3]}): {r[1]}")
    return "\n".join(formatted)


def delete_note(note_id: int) -> str:
    """Delete a note by its numerical ID."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        conn.commit()
        deleted = cursor.rowcount

    if deleted > 0:
        return f"Note #{note_id} was successfully deleted."
    return f"Note #{note_id} was not found."


def get_notes_data():
    """Retrieve raw notes records as a list of dicts for frontend rendering."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, content, category, created_at FROM notes ORDER BY id DESC")
        rows = cursor.fetchall()
    return [
        {"id": r[0], "content": r[1], "category": r[2], "created_at": r[3]}
        for r in rows
    ]


def get_current_time(timezone_str: str = "local") -> str:
    """Get the current local date, time, and day of week."""
    now = datetime.datetime.now()
    return now.strftime("Current date & time: %A, %B %d, %Y %I:%M:%S %p (%Z)")


def web_search(query: str, max_results: int = 4) -> str:
    """Search the web for up-to-date information on any topic."""
    q = query.strip()
    if not q:
        return "Error: Search query cannot be empty."

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
    }

    encoded = urllib.parse.quote_plus(q)
    results = []

    # 1. DuckDuckGo HTML Search
    try:
        url = f"https://html.duckduckgo.com/html/?q={encoded}"
        resp = requests.get(url, headers=headers, timeout=8)
        if resp.status_code == 200:
            snippets = re.findall(
                r'<a class="result__snippet[^>]*>(.*?)</a>', resp.text, re.DOTALL
            )
            for i, snip in enumerate(snippets[:max_results]):
                clean = re.sub(r"<[^>]+>", "", snip).strip()
                clean = html.unescape(clean)
                if clean:
                    results.append(f"Result {i+1}: {clean}")
    except Exception:
        pass

    # 2. Fallback to DuckDuckGo Instant Answer API
    if not results:
        try:
            api_url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1&skip_disambig=1"
            res = requests.get(api_url, headers=headers, timeout=6).json()
            abstract = res.get("AbstractText", "")
            if abstract:
                results.append(f"Summary: {abstract}")
            for item in res.get("RelatedTopics", [])[:max_results]:
                if isinstance(item, dict) and "Text" in item:
                    results.append(f"• {item['Text']}")
        except Exception:
            pass

    if results:
        return "\n\n".join(results)
    return f"No search results found for '{query}'. Please try rephrasing."


def fetch_web_page(url: str, max_chars: int = 2500) -> str:
    """Fetch and extract readable plain text from a webpage URL."""
    clean_url = url.strip()
    if not (clean_url.startswith("http://") or clean_url.startswith("https://")):
        return "Error: URL must start with http:// or https://"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
    }

    try:
        resp = requests.get(clean_url, headers=headers, timeout=10)
        resp.raise_for_status()

        text = re.sub(r"<script.*?</script>", "", resp.text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = html.unescape(text)
        text = re.sub(r"\s+", " ", text).strip()

        if len(text) > max_chars:
            text = text[:max_chars] + "... [truncated]"

        return text or "No readable text content found on the page."
    except Exception as e:
        return f"Error fetching {clean_url}: {e}"


def list_allowed_files() -> str:
    """List approved text files available in the project."""
    allowed_files = ["sample.txt", "notes.txt"]
    existing = [f for f in allowed_files if (BASE_DIR / f).is_file()]
    return "Allowed files:\n" + "\n".join(f"- {f}" for f in existing)


def read_file(filename: str) -> str:
    """Read an approved text file from the project directory."""
    allowed_files = {"sample.txt", "notes.txt"}
    fname = Path(filename).name

    if fname not in allowed_files:
        return f"Error: '{filename}' is not in the allowed files list ({', '.join(allowed_files)})."

    path = BASE_DIR / fname
    if not path.is_file():
        return f"Error: File '{fname}' does not exist."

    return path.read_text(encoding="utf-8")


def execute_python(code: str) -> str:
    """Execute Python code in an isolated subprocess and return printed output or evaluated results.
    Available preloaded libraries: math, datetime, re, json, pandas (as pd), numpy (as np).
    """
    clean_code = code.strip()
    if not clean_code:
        return "Error: No Python code provided to execute."

    # Prevent destructive filesystem or system operations
    blocked = [
        "shutil.rmtree",
        "os.remove",
        "win32",
        "format c:",
    ]
    for b in blocked:
        if b in clean_code.lower():
            return f"Error: '{b}' is restricted for safety reasons."

    import subprocess

    venv_py = BASE_DIR / ".venv" / "Scripts" / "python.exe"
    py_exe = str(venv_py) if venv_py.exists() else sys.executable

    try:
        proc = subprocess.run(
            [py_exe, "-"],
            input=clean_code,
            capture_output=True,
            text=True,
            timeout=25,
            cwd=str(BASE_DIR),
        )
        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()

        if proc.returncode != 0:
            error_msg = stderr or stdout or f"Process exited with code {proc.returncode}"
            return f"Python execution error:\n{error_msg}"

        output = stdout or stderr or "Code executed successfully (no standard output printed)."
        if len(output) > 3500:
            output = output[:3500] + "... [output truncated]"
        return output

    except subprocess.TimeoutExpired:
        return "Error: Code execution timed out (maximum 20 seconds allowed)."
    except Exception as e:
        return f"Python execution error: {type(e).__name__}: {e}"


