"""rollback: restore a file from its newest (or named) .bak, or from a git ref."""
import glob
import os
import shutil
import registry as R


@R.register("rollback", "write", {"properties": {
    "path": {"type": "string"}, "backup": {"type": "string"}, "git_ref": {"type": "string"}}, "required": ["path"]},
    "Restore file from .bak (latest unless named) or `git checkout <ref> -- path`. Current file is backed up first.")
def rollback(a):
    p = R.safe_path(a["path"])
    if a.get("git_ref"):
        if not a["git_ref"].replace("/", "").replace("-", "").replace("_", "").replace(".", "").isalnum():
            return R.fail("bad git ref")
        cmd = ["git", "checkout", a["git_ref"], "--", p]
        if a["dry_run"]:
            return {"ok": True, "dry_run": True, "would_run": cmd}
        bak = R.backup_file(p)
        r = R.run(cmd, cwd=os.path.dirname(p))
        return {"ok": r["rc"] == 0, "backup_of_current": bak, "git": r}
    if a.get("backup"):
        b = R.safe_path(a["backup"], must_exist=True)
    else:
        c = sorted(glob.glob(glob.escape(p) + ".*.bak"))
        if not c:
            return R.fail("no .bak for " + p)
        b = c[-1]
    if a["dry_run"]:
        return {"ok": True, "dry_run": True, "restore_from": b}
    cur = R.backup_file(p)
    shutil.copy2(b, p)
    return {"ok": True, "dry_run": False, "restored_from": b, "backup_of_current": cur}
