"""repo_grep: regex search over text files under an allowed root."""
import fnmatch
import os
import re
import registry as R

SKIP = {".git", "__pycache__", "node_modules", ".venv"}


def _walk(root):
    if os.path.isfile(root):
        yield root
        return
    for d, ds, fs in os.walk(root):
        ds[:] = [x for x in ds if x not in SKIP]
        for f in fs:
            yield os.path.join(d, f)


@R.register("repo_grep", "read", {"properties": {
    "pattern": {"type": "string"}, "path": {"type": "string", "default": "."},
    "glob": {"type": "string", "default": "*"}, "ignore_case": {"type": "boolean", "default": False},
    "max_results": {"type": "integer", "default": 100}}, "required": ["pattern"]},
    "Regex search in files (glob filter), returns file:line:text.")
def repo_grep(a):
    root = R.safe_path(a["path"], must_exist=True)
    try:
        rx = re.compile(a["pattern"], re.I if a["ignore_case"] else 0)
    except re.error as e:
        return R.fail("bad regex: %s" % e)
    hits, files = [], 0
    for fp in _walk(root):
        if not fnmatch.fnmatch(os.path.basename(fp), a["glob"]):
            continue
        try:
            with open(fp, "rb") as f:
                if b"\0" in f.read(2048):
                    continue
            files += 1
            with open(fp, encoding="utf-8", errors="replace") as f:
                for i, l in enumerate(f, 1):
                    if rx.search(l):
                        hits.append({"file": os.path.relpath(fp, R.REPO), "line": i, "text": l.rstrip()[:300]})
                        if len(hits) >= a["max_results"]:
                            return {"ok": True, "hits": hits, "files_scanned": files, "truncated": True}
        except OSError:
            continue
    return {"ok": True, "hits": hits, "files_scanned": files, "truncated": False}
