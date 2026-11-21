"""backup_before_edit: timestamped .bak copy of a file (+sha256)."""
import registry as R


@R.register("backup_before_edit", "write", {"properties": {"path": {"type": "string"}}, "required": ["path"]},
            "Create <file>.<ts>.bak before an edit. dry_run reports only.")
def backup_before_edit(a):
    p = R.safe_path(a["path"], must_exist=True)
    sha = R.sha256_file(p)
    if a["dry_run"]:
        return {"ok": True, "dry_run": True, "path": p, "sha256": sha}
    return {"ok": True, "dry_run": False, "backup": R.backup_file(p), "sha256": sha}
