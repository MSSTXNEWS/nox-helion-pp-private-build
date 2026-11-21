"""repo_read: read a file slice (numbered lines) or list a directory."""
import os
import registry as R


@R.register("repo_read", "read", {"properties": {
    "path": {"type": "string"}, "start": {"type": "integer", "default": 1},
    "end": {"type": "integer", "default": 200}, "max_bytes": {"type": "integer", "default": 200000}},
    "required": ["path"]}, "Read file lines [start,end] with numbers, or list a directory.")
def repo_read(a):
    p = R.safe_path(a["path"], must_exist=True)
    if os.path.isdir(p):
        return {"ok": True, "type": "dir", "entries": sorted(
            e + ("/" if os.path.isdir(os.path.join(p, e)) else "") for e in os.listdir(p))[:500]}
    with open(p, "rb") as f:
        raw = f.read(a["max_bytes"] + 1)
    if b"\0" in raw[:4096]:
        return R.fail("binary file")
    trunc = len(raw) > a["max_bytes"]
    lines = raw[:a["max_bytes"]].decode("utf-8", "replace").splitlines()
    s, e = max(1, a["start"]), max(a["start"], a["end"])
    return {"ok": True, "type": "file", "path": p, "total_lines": len(lines), "truncated": trunc,
            "text": "\n".join("%d\t%s" % (i + s, l) for i, l in enumerate(lines[s - 1:e]))}
