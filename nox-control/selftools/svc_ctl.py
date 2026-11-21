"""svc_ctl: supervisorctl wrapper with service allowlist."""
import os
import registry as R


def allowed():
    env = os.environ.get("NOX_SVC_ALLOW")
    return [x for x in env.split(",") if x] if env else ["nox-*", "llama-*", "bge-*", "nox_*"]


def ok_name(n):
    import fnmatch
    return any(fnmatch.fnmatch(n, p) for p in allowed())


@R.register("svc_ctl", "write", {"properties": {
    "action": {"type": "string", "enum": ["status", "start", "stop", "restart"]}, "name": {"type": "string"}},
    "required": ["action"]}, "supervisorctl status/start/stop/restart for allowlisted services (env NOX_SVC_ALLOW globs).",
    action_modes={"status": "read", "stop": "danger"})
def svc_ctl(a):
    act, name = a["action"], a.get("name")
    if act != "status" or name:
        if not name:
            return R.fail("name required")
        if not ok_name(name):
            raise R.Denied("service not in allowlist: %s (allow: %s)" % (name, allowed()))
    cmd = ["supervisorctl", act] + ([name] if name else [])
    if a.get("dry_run"):
        return {"ok": True, "dry_run": True, "would_run": cmd}
    r = R.run(cmd, timeout=90)
    if r.get("missing"):
        return R.blocked("supervisorctl not installed", "run on the NOX server (supervisor)")
    return {"ok": r["rc"] == 0 or act == "status" and bool(r["out"]), "rc": r["rc"], "out": r["out"][-3000:], "err": r["err"][-500:]}
