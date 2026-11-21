"""NOX selftools registry. Stdlib only.

Each tool: name -> function(args)->dict, JSON-schema (subset) for args,
mode read|write|danger, path/command allowlists, JSONL audit log.
  read   : no side effects.
  write  : dry_run=True by default; real write makes a .bak backup first.
  danger : needs confirm=true.
Result: {"ok":true,...} | {"ok":false,"error":..} | {"ok":false,"blocked":why,"need":what}.
"""
import hashlib
import importlib
import json
import os
import shutil
import subprocess
import sys
import time

if __name__ == "__main__":
    sys.modules["registry"] = sys.modules[__name__]
if os.path.dirname(os.path.abspath(__file__)) not in sys.path:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
MODULES = [
    "repo_read", "repo_grep", "self_map", "task_board", "log_tail", "patch_apply",
    "branch_pr", "backup_before_edit", "rollback", "sandbox_run", "test_runner",
    "eval_gate", "lint_syntax", "health_probe", "speed_bench", "svc_ctl",
    "disk_guard", "gpu_alloc", "mem_alloc", "priority_ctl", "corpus_build",
    "train_ctl", "judge_run", "rag_index", "lora_swap", "advisor_ask",
    "web_fetch", "pc_pull", "model_dl", "inspector_hook"]
ALLOW_CMDS = {"git", "gh", "python3", "node", "bash", "sh", "supervisorctl", "ionice",
              "rsync", "ssh", "nvidia-smi", "df", "du", "unshare", "nice"}
TOOLS = {}


class Denied(Exception):
    pass


def roots():
    env = os.environ.get("NOX_ALLOW_ROOTS")
    r = env.split(os.pathsep) if env else [REPO, "/root/nox", "/tmp", "/var/log"]
    return [os.path.realpath(x) for x in r if x]


def safe_path(p, must_exist=False, allow=None, nofollow=False):
    """Resolve p (relative to REPO) and require it to sit inside an allowed root."""
    if not isinstance(p, str) or not p or "\0" in p:
        raise Denied("bad path")
    full = p if os.path.isabs(p) else os.path.join(REPO, p)
    full = os.path.join(os.path.realpath(os.path.dirname(full)), os.path.basename(full)) if nofollow else os.path.realpath(full)
    for r in (allow or roots()):
        if full == r or full.startswith(r.rstrip(os.sep) + os.sep):
            if must_exist and not os.path.exists(full):
                raise Denied("not found: " + p)
            return full
    raise Denied("path outside allowlist: " + p)


def blocked(why, need):
    return {"ok": False, "blocked": why, "need": need}


def fail(msg, **kw):
    d = {"ok": False, "error": str(msg)}
    d.update(kw)
    return d


def run(argv, timeout=60, cwd=None, env=None, input=None):
    """Run allowlisted command without shell. Returns dict rc/out/err."""
    if not argv or os.path.basename(argv[0]) not in ALLOW_CMDS:
        raise Denied("command not allowed: %s" % (argv[:1],))
    if shutil.which(argv[0]) is None:
        return {"rc": 127, "out": "", "err": "not installed: " + argv[0], "missing": True}
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                           cwd=cwd, env=env, input=input)
        return {"rc": p.returncode, "out": p.stdout, "err": p.stderr}
    except subprocess.TimeoutExpired as e:
        return {"rc": 124, "out": (e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or ""),
                "err": "timeout", "timeout": True}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def backup_file(path):
    """Copy path to <path>.<ts>.bak. Returns backup path or None if file absent."""
    if not os.path.isfile(path):
        return None
    ts = time.strftime("%Y%m%dT%H%M%S") + "%03d" % (int(time.time() * 1000) % 1000)
    dst = "%s.%s.bak" % (path, ts)
    shutil.copy2(path, dst)
    return dst


def http_json(url, payload=None, timeout=30, headers=None):
    """GET (payload None) or POST JSON. Returns (status, parsed_or_text). status 0 = unreachable."""
    import urllib.error
    import urllib.request
    h = {"Content-Type": "application/json", "User-Agent": "nox-selftools"}
    h.update(headers or {})
    req = urllib.request.Request(url, data=None if payload is None else json.dumps(payload).encode(),
                                 headers=h, method="GET" if payload is None else "POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            status = r.status
    except urllib.error.HTTPError as e:
        raw, status = e.read().decode("utf-8", "replace"), e.code
    except (urllib.error.URLError, OSError, ValueError) as e:
        return 0, str(getattr(e, "reason", e))
    try:
        return status, json.loads(raw)
    except ValueError:
        return status, raw


def extract_json(text):
    """First JSON object found in text (model output), or None."""
    dec = json.JSONDecoder()
    for i, ch in enumerate(text or ""):
        if ch == "{":
            try:
                return dec.raw_decode(text[i:])[0]
            except ValueError:
                continue
    return None


def audit_path():
    p = os.environ.get("NOX_AUDIT_LOG", "/root/nox/state/selftools/audit.jsonl")
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "a"):
            pass
        return p
    except OSError:
        fb = os.path.join("/tmp", "nox_selftools_audit.jsonl")
        return fb


def audit(entry):
    try:
        with open(audit_path(), "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except OSError:
        pass


def register(name, mode, schema, doc, action_modes=None, dry_default=True):
    def deco(fn):
        TOOLS[name] = {"name": name, "mode": mode, "schema": schema, "doc": doc,
                       "action_modes": action_modes or {}, "dry_default": dry_default, "fn": fn}
        return fn
    return deco


_TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool,
          "array": list, "object": dict}


def validate(schema, args):
    """Validate+fill defaults. Returns (args, error)."""
    props = schema.get("properties", {})
    out = dict(args)
    for k in schema.get("required", []):
        if k not in out:
            return None, "missing required arg: " + k
    for k, v in list(out.items()):
        if k in ("confirm", "dry_run"):
            continue
        if k not in props:
            if schema.get("additionalProperties", False) is False:
                return None, "unknown arg: " + k
            continue
        t = props[k].get("type")
        if t and (not isinstance(v, _TYPES[t]) or (t in ("integer", "number") and isinstance(v, bool))):
            return None, "arg %s must be %s" % (k, t)
        if "enum" in props[k] and v not in props[k]["enum"]:
            return None, "arg %s must be one of %s" % (k, props[k]["enum"])
    for k, p in props.items():
        if k not in out and "default" in p:
            out[k] = p["default"]
    return out, None


def effective_mode(t, args):
    return t["action_modes"].get(args.get("action"), t["mode"])


def call(name, args=None, confirm=False):
    t0 = time.time()
    args = dict(args or {})
    t = TOOLS.get(name)
    if t is None:
        return fail("unknown tool: " + name)
    confirm = bool(confirm or args.pop("confirm", False))
    clean, err = validate(t["schema"], args)
    if err:
        res = fail(err)
        mode = t["mode"]
    else:
        mode = effective_mode(t, clean)
        if mode == "danger" and not confirm:
            res = blocked("danger tool %s/%s requires confirm=true" % (name, clean.get("action", "")),
                          "explicit owner confirmation (confirm=true)")
        else:
            if mode == "write":
                clean["dry_run"] = bool(clean.get("dry_run", t["dry_default"]))
            clean["_mode"] = mode
            try:
                res = t["fn"](clean)
            except Denied as e:
                res = fail(e, denied=True)
            except Exception as e:  # tool bug or env error: report, never crash caller
                res = fail("%s: %s" % (type(e).__name__, e))
    audit({"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "tool": name, "mode": mode,
           "args": {k: (v if len(json.dumps(v, default=str)) < 300 else "<big>") for k, v in args.items()},
           "ok": res.get("ok"), "blocked": res.get("blocked"), "ms": int((time.time() - t0) * 1000)})
    return res


def load_all():
    for m in MODULES:
        importlib.import_module(m)
    return TOOLS


def describe():
    return [{"name": t["name"], "mode": t["mode"], "action_modes": t["action_modes"],
             "doc": t["doc"], "schema": t["schema"]} for t in TOOLS.values()]


def main(argv=None):
    import argparse
    a = argparse.ArgumentParser(prog="selftools")
    a.add_argument("tool", nargs="?")
    a.add_argument("--args", default="{}", help="JSON args")
    a.add_argument("--confirm", action="store_true")
    ns = a.parse_args(argv)
    load_all()
    if not ns.tool or ns.tool == "list":
        print(json.dumps(describe(), ensure_ascii=False, indent=1))
        return 0
    r = call(ns.tool, json.loads(ns.args), confirm=ns.confirm)
    print(json.dumps(r, ensure_ascii=False, indent=1, default=str))
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
