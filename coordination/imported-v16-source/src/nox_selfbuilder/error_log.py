"""Append-only error log. Does not claim a sealed journal."""
from datetime import datetime, timezone
from pathlib import Path

def append_error(path: str, code: str, detail: str) -> dict:
    line = f"{datetime.now(timezone.utc).isoformat()} {code} {detail}\n"
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line)
    return {"status": "LOGGED", "code": code}
