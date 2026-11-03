"""One SQLite chat history. Local file, not a live Ollama session."""
import sqlite3
from pathlib import Path

def open_db(path: str) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY, role TEXT, body TEXT, ts TEXT)")
    db.commit()
    return db

def add(db, role: str, body: str, ts: str) -> int:
    cur = db.execute("INSERT INTO messages (role, body, ts) VALUES (?,?,?)", (role, body, ts))
    db.commit()
    return cur.lastrowid
