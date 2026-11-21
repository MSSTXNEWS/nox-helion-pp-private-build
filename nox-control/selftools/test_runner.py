"""test_runner: run unittest discovery (or pytest if present) and parse the summary."""
import re
import sys
import registry as R


@R.register("test_runner", "read", {"properties": {
    "start_dir": {"type": "string", "default": "nox-control"}, "pattern": {"type": "string", "default": "test*.py"},
    "timeout": {"type": "integer", "default": 300}, "top_level": {"type": "string"}},},
    "Run `python3 -m unittest discover`; returns ran/failures/errors and output tail. Does not modify the repo.")
def test_runner(a):
    d = R.safe_path(a["start_dir"], must_exist=True)
    cmd = ["python3", "-m", "unittest", "discover", "-s", d, "-p", a["pattern"]]
    if a.get("top_level"):
        cmd += ["-t", R.safe_path(a["top_level"], must_exist=True)]
    r = R.run(cmd, timeout=a["timeout"], cwd=R.REPO)
    if r.get("missing"):
        return R.blocked("python3 missing", "install python3")
    txt = r["err"] + r["out"]
    m = re.search(r"Ran (\d+) tests? in", txt)
    f = re.search(r"failures=(\d+)", txt)
    e = re.search(r"errors=(\d+)", txt)
    return {"ok": r["rc"] == 0 and bool(m), "ran": int(m.group(1)) if m else 0,
            "failures": int(f.group(1)) if f else 0, "errors": int(e.group(1)) if e else 0,
            "rc": r["rc"], "tail": txt[-3000:]}
