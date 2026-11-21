"""task_board: dispatcher state.json + queue.jsonl with flock file locks."""
import fcntl
import json
import os
import time
import registry as R


def ddir():
    return os.environ.get("NOX_DISPATCH_DIR", "/root/nox/state/dispatcher")


class Lock:
    def __init__(self, d):
        self.path = os.path.join(d, ".lock")

    def __enter__(self):
        self.f = open(self.path, "a")
        fcntl.flock(self.f, fcntl.LOCK_EX)
        return self

    def __exit__(self, *x):
        fcntl.flock(self.f, fcntl.LOCK_UN)
        self.f.close()


def _read_queue(p):
    if not os.path.exists(p):
        return []
    out = []
    for l in open(p, encoding="utf-8"):
        l = l.strip()
        if l:
            try:
                out.append(json.loads(l))
            except ValueError:
                pass
    return out


def _write_atomic(p, text):
    tmp = p + ".tmp%d" % os.getpid()
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, p)


@R.register("task_board", "write", {"properties": {
    "action": {"type": "string", "enum": ["list", "get", "add", "update", "pop", "set_state"]},
    "id": {"type": "string"}, "task": {"type": "object"}, "fields": {"type": "object"},
    "key": {"type": "string"}, "value": {}, "status": {"type": "string"}}, "required": ["action"]},
    "Dispatcher board: queue.jsonl tasks (list/get/add/update/pop) and state.json keys (set_state). Locked, atomic.",
    action_modes={"list": "read", "get": "read"})
def task_board(a):
    d = ddir()
    act = a["action"]
    if not os.path.isdir(d):
        if act in ("list", "get"):
            return R.blocked("dispatcher dir missing: " + d, "run on the NOX server or set NOX_DISPATCH_DIR")
        if not a.get("dry_run", True):
            return R.blocked("dispatcher dir missing: " + d, "run on the NOX server or set NOX_DISPATCH_DIR")
        d = None
    qp = os.path.join(d or "/nonexistent", "queue.jsonl")
    sp = os.path.join(d or "/nonexistent", "state.json")
    dry = a.get("dry_run", False)
    lock = Lock(d) if d else None
    if lock and not dry:
        lock.__enter__()
    try:
        q = _read_queue(qp)
        state = json.load(open(sp, encoding="utf-8")) if d and os.path.exists(sp) else {}
        if act == "list":
            st = a.get("status")
            return {"ok": True, "tasks": [t for t in q if not st or t.get("status") == st], "state": state}
        if act == "get":
            t = [t for t in q if t.get("id") == a.get("id")]
            return {"ok": True, "task": t[0]} if t else R.fail("no such task")
        if act == "add":
            t = dict(a.get("task") or {})
            if not t.get("id"):
                return R.fail("task.id required")
            if any(x.get("id") == t["id"] for x in q):
                return R.fail("duplicate id")
            t.setdefault("status", "queued")
            t.setdefault("ts", time.time())
            q.append(t)
            res = {"ok": True, "added": t}
        elif act == "update":
            for t in q:
                if t.get("id") == a.get("id"):
                    t.update(a.get("fields") or {})
                    res = {"ok": True, "updated": t}
                    break
            else:
                return R.fail("no such task")
        elif act == "pop":
            idx = next((i for i, t in enumerate(q) if t.get("status", "queued") == "queued"), None)
            if idx is None:
                return {"ok": True, "task": None}
            q[idx]["status"] = "running"
            q[idx]["started"] = time.time()
            res = {"ok": True, "task": q[idx]}
        else:  # set_state
            if not a.get("key"):
                return R.fail("key required")
            state[a["key"]] = a.get("value")
            res = {"ok": True, "state": state}
        res["dry_run"] = dry
        if not dry:
            if act == "set_state":
                _write_atomic(sp, json.dumps(state, ensure_ascii=False, indent=1))
            else:
                _write_atomic(qp, "".join(json.dumps(t, ensure_ascii=False) + "\n" for t in q))
        return res
    finally:
        if lock and not dry:
            lock.__exit__()
