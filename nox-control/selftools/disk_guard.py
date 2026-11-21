"""disk_guard: disk report + cleanup limited to a whitelist."""
import fnmatch
import os
import shutil
import time
import registry as R

# (dir glob-able prefix, filename pattern) cleanup whitelist; env NOX_CLEAN_ROOTS adds dirs (all *.tmp, *.bak older than N days)
PATTERNS = ["*.bak", "*.tmp", "*.part", "*.pyc", "core.*"]


def clean_roots():
    env = os.environ.get("NOX_CLEAN_ROOTS")
    return [os.path.realpath(x) for x in env.split(os.pathsep)] if env else [
        os.path.realpath(x) for x in ("/tmp", "/root/nox/tmp", "/root/nox/cache", "/root/nox/state/backups")]


def candidates(older_days):
    cut = time.time() - older_days * 86400
    out = []
    for root in clean_roots():
        for d, ds, fs in os.walk(root):
            for f in fs:
                if any(fnmatch.fnmatch(f, p) for p in PATTERNS):
                    fp = os.path.join(d, f)
                    try:
                        st = os.lstat(fp)
                    except OSError:
                        continue
                    if st.st_mtime < cut and not os.path.islink(fp):
                        out.append((fp, st.st_size))
    return out


@R.register("disk_guard", "danger", {"properties": {
    "action": {"type": "string", "enum": ["report", "plan_clean", "clean"]},
    "paths": {"type": "array"}, "older_days": {"type": "integer", "default": 7}, "top": {"type": "integer", "default": 15},
    "warn_pct": {"type": "number", "default": 85}}, "required": ["action"]},
    "report: usage + biggest dirs. plan_clean: what the whitelist would delete. clean: delete (needs confirm; whitelist only).",
    action_modes={"report": "read", "plan_clean": "read"})
def disk_guard(a):
    act = a["action"]
    if act == "report":
        out = []
        for p in a.get("paths") or ["/", "/root/nox", "/tmp"]:
            if not os.path.exists(p):
                continue
            u = shutil.disk_usage(p)
            pct = round(100 * u.used / u.total, 1)
            out.append({"path": p, "total_gb": round(u.total / 2**30, 1), "free_gb": round(u.free / 2**30, 1),
                        "used_pct": pct, "warn": pct >= a["warn_pct"]})
        big = []
        base = R.safe_path(a["paths"][0]) if a.get("paths") else None
        if base and os.path.isdir(base):
            sizes = []
            for e in os.scandir(base):
                try:
                    if e.is_dir(follow_symlinks=False):
                        t = sum(os.lstat(os.path.join(d, f)).st_size for d, _, fs in os.walk(e.path) for f in fs if os.path.lexists(os.path.join(d, f)))
                    else:
                        t = e.stat(follow_symlinks=False).st_size
                    sizes.append((t, e.name))
                except OSError:
                    pass
            big = [{"name": n, "mb": round(s / 2**20, 1)} for s, n in sorted(sizes, reverse=True)[:a["top"]]]
        return {"ok": True, "disks": out, "biggest": big}
    cands = candidates(a["older_days"])
    total = sum(s for _, s in cands)
    if act == "plan_clean":
        return {"ok": True, "files": [f for f, _ in cands[:200]], "count": len(cands), "mb": round(total / 2**20, 2)}
    removed = 0
    for fp, _ in cands:
        try:
            os.remove(fp)
            removed += 1
        except OSError:
            pass
    return {"ok": True, "removed": removed, "freed_mb": round(total / 2**20, 2)}
