"""Local runtime without an EXE. Chat is local, not Ollama."""
import json
from datetime import datetime, timezone
from .chat_history import open_db, add
from .rag_index import index_chunks

def boot(db_path: str) -> dict:
    db = open_db(db_path)
    add(db, "system", "local boot", datetime.now(timezone.utc).isoformat())
    rag = index_chunks(["menu", "passport", "weights"])
    event = {"schema": "events.v3", "type": "BOOT", "live": False}
    return {"history": db_path, "rag": rag, "event": event, "ollama": False}
