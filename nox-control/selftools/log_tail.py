"""log_tail: last N lines of a log (reads from the end), optional regex filter."""
import os
import re
import registry as R


@R.register("log_tail", "read", {"properties": {
    "path": {"type": "string"}, "lines": {"type": "integer", "default": 100},
    "grep": {"type": "string"}}, "required": ["path"]}, "Tail a log file with optional regex filter.")
def log_tail(a):
    p = R.safe_path(a["path"], must_exist=True)
    n = max(1, min(a["lines"], 5000))
    rx = re.compile(a["grep"]) if a.get("grep") else None
    with open(p, "rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        buf, pos = b"", size
        while pos > 0 and buf.count(b"\n") <= n * (1 if not rx else 20) and len(buf) < 8 << 20:
            step = min(65536, pos)
            pos -= step
            f.seek(pos)
            buf = f.read(step) + buf
    ls = buf.decode("utf-8", "replace").splitlines()
    if pos > 0:
        ls = ls[1:]
    if rx:
        ls = [l for l in ls if rx.search(l)]
    return {"ok": True, "path": p, "size": size, "lines": ls[-n:]}
