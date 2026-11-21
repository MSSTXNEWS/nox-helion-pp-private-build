"""inspector_hook: read coordination/inspector (INSPECTOR.md + HISTORY.jsonl) -> last runs, staleness."""
import datetime
import json
import os
import time
import registry as R


@R.register("inspector_hook", "read", {"properties": {
    "dir": {"type": "string", "default": "coordination/inspector"}, "last": {"type": "integer", "default": 5},
    "stale_after_s": {"type": "integer", "default": 7200}}},
    "Read inspector history: last N entries, age of newest, stale flag; plus first lines of INSPECTOR.md.")
def inspector_hook(a):
    d = R.safe_path(a["dir"], must_exist=True)
    hp = os.path.join(d, "HISTORY.jsonl")
    entries, bad = [], 0
    if os.path.exists(hp):
        for l in open(hp, encoding="utf-8"):
            if l.strip():
                try:
                    entries.append(json.loads(l))
                except ValueError:
                    bad += 1
    last = entries[-a["last"]:]
    age = None
    if entries:
        newest = entries[-1]
        t = newest.get("ts") or newest.get("time") or newest.get("t")
        if isinstance(t, (int, float)):
            age = int(time.time() - t)
        elif isinstance(t, str):
            try:
                dt = datetime.datetime.fromisoformat(t.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.astimezone()
                age = int(time.time() - dt.timestamp())
            except ValueError:
                age = None
        if age is None:
            age = int(time.time() - os.path.getmtime(hp))
    mp = os.path.join(d, "INSPECTOR.md")
    head = open(mp, encoding="utf-8").read(1500) if os.path.exists(mp) else ""
    return {"ok": True, "count": len(entries), "bad_lines": bad, "last": last, "newest_age_s": age,
            "stale": age is None or age > a["stale_after_s"], "readme_head": head}
