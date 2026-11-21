"""lora_swap: atomically repoint a LoRA symlink, restart service, health-check, auto-rollback on failure."""
import os
import time
import registry as R
import svc_ctl
import health_probe


def _restart(name):
    return R.run(["supervisorctl", "restart", name], timeout=120)


def _healthy(url, wait_s, interval=2.0):
    end = time.time() + wait_s
    while True:
        st, _ = R.http_json(url, timeout=3)
        if 200 <= st < 300:
            return True
        if time.time() >= end:
            return False
        time.sleep(interval)


def _rd(p):
    if not os.path.exists(p):
        return None
    with open(p) as f:
        return f.read()


def _relink(link, target):
    tmp = link + ".new%d" % os.getpid()
    if os.path.lexists(tmp):
        os.remove(tmp)
    os.symlink(target, tmp)
    os.replace(tmp, link)


@R.register("lora_swap", "write", {"properties": {
    "action": {"type": "string", "enum": ["status", "swap", "rollback"]}, "link": {"type": "string", "description": "symlink path the server loads"},
    "adapter": {"type": "string", "description": "new adapter .gguf path"}, "service": {"type": "string"},
    "health_url": {"type": "string", "default": "http://127.0.0.1:8098/health"}, "wait_s": {"type": "integer", "default": 60}},
    "required": ["action", "link"]},
    "Swap LoRA adapter behind a symlink: record previous target, repoint, restart svc, health-check; on failure restore previous and restart.",
    action_modes={"status": "read"})
def lora_swap(a):
    link = R.safe_path(a["link"], nofollow=True)
    cur = os.readlink(link) if os.path.islink(link) else None
    prevf = link + ".prev"
    if a["action"] == "status":
        return {"ok": True, "link": link, "target": cur, "previous": _rd(prevf)}
    if not a.get("service"):
        return R.fail("service required")
    if not svc_ctl.ok_name(a["service"]):
        raise R.Denied("service not in allowlist")
    if a["action"] == "swap":
        if not a.get("adapter"):
            return R.fail("adapter required")
        new = R.safe_path(a["adapter"], must_exist=True)
    else:
        if not os.path.exists(prevf):
            return R.fail("no previous adapter recorded")
        new = _rd(prevf)
    if a["dry_run"]:
        return {"ok": True, "dry_run": True, "would_point": new, "from": cur, "restart": a["service"]}
    if cur is not None:
        with open(prevf, "w") as f:
            f.write(cur)
    _relink(link, new)
    r = _restart(a["service"])
    if r.get("missing"):
        if cur is not None:
            _relink(link, cur)
        return R.blocked("supervisorctl not installed (link restored)", "run on the NOX server")
    if r["rc"] == 0 and _healthy(a["health_url"], a["wait_s"]):
        return {"ok": True, "dry_run": False, "now": new, "previous": cur}
    rolled = False
    if cur is not None:
        _relink(link, cur)
        _restart(a["service"])
        rolled = _healthy(a["health_url"], a["wait_s"])
    return {"ok": False, "error": "service unhealthy after swap", "rolled_back": cur is not None, "rollback_healthy": rolled}
