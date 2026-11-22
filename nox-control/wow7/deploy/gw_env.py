#!/usr/bin/env python3
"""gw_env.py: флаги NOX v7 для шлюза/CORE/RTE без правки чужих скриптов запуска (только stdlib).
Единый источник флагов: $V7_STATE/v7_flags.json ({"NOX_PRIME":"0",...}). Команды:
  flags get | flags set K=V [K=V...] | flags unset K [K...]
  capture --match 'python3 .*gateway\\.py'          -> JSON-окружение живого процесса (/proc/PID/environ), только NOX_*, PYTHONPATH, LD_LIBRARY_PATH
  restart --match REGEX --cwd DIR --log FILE [--env-default K=V] [--env-add K=V] [-- ARGV...] : убить процессы по REGEX, поднять ARGV (без ARGV - прежняя командная строка и cwd)
      с окружением: --env-default < окружение старого процесса < v7_flags.json < --env-add; ждать --health URL
  local-json --services-json F --local-json F --apply   : вшить флаги и сервисы core/rte в /root/nox/dsp/local.json (DSP), сохранив остальное
  local-json ... --unapply                               : убрать вшитое (откат)
Флаги попадают в env сервисов gateway/core/rte. Тихие правки: остальные ключи local.json не трогаются."""
import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.request

STATE = os.environ.get("V7_STATE", "/root/nox/state")
FLAGS = os.path.join(STATE, "v7_flags.json")
KEEP = re.compile(r"^(NOX_|PYTHONPATH=|LD_LIBRARY_PATH=)")
MARK = "_v7"


def load(p, d):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return d


def save(p, obj):
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    tmp = p + ".tmp%d" % os.getpid()
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def pids(regex, exclude_self=True):
    me = {os.getpid(), os.getppid()}
    out = []
    for d in os.listdir("/proc"):
        if not d.isdigit() or (exclude_self and int(d) in me):
            continue
        try:
            cl = open("/proc/%s/cmdline" % d, "rb").read().replace(b"\0", b" ").decode("utf-8", "replace").strip()
        except OSError:
            continue
        if cl and re.search(regex, cl) and "gw_env.py" not in cl:
            out.append(int(d))
    return out


def capture(regex):
    for pid in pids(regex):
        try:
            raw = open("/proc/%d/environ" % pid, "rb").read().split(b"\0")
            argv = [x.decode("utf-8", "replace") for x in open("/proc/%d/cmdline" % pid, "rb").read().split(b"\0") if x]
            cwd = os.readlink("/proc/%d/cwd" % pid)
        except OSError:
            continue
        env = {}
        for kv in raw:
            s = kv.decode("utf-8", "replace")
            if KEEP.match(s) and "=" in s:
                k, v = s.split("=", 1)
                env[k] = v
        return {"pid": pid, "env": env, "argv": argv, "cwd": cwd}
    return {"pid": None, "env": {}, "argv": [], "cwd": None}


def restart(regex, cwd, log, argv, env_add, health, timeout, base_env=None):
    cap = capture(regex)
    if not argv:
        argv, cwd = cap["argv"], cap["cwd"] or cwd
        if not argv:
            return {"pid": None, "healthy": False, "exited": None, "had_old_env": False, "error": "нет процесса и не задан argv"}
    env = dict(os.environ)
    env.update(base_env or {})
    env.update(cap["env"])
    env.update(load(FLAGS, {}))
    env.update(env_add)
    for pid in pids(regex):
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    for _ in range(50):
        if not pids(regex):
            break
        time.sleep(0.2)
    for pid in pids(regex):
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    os.makedirs(os.path.dirname(log) or ".", exist_ok=True)
    lf = open(log, "ab")
    p = subprocess.Popen(argv, cwd=cwd, env=env, stdout=lf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    ok = health is None
    t0 = time.time()
    while health and time.time() - t0 < timeout:
        if p.poll() is not None:
            break
        try:
            with urllib.request.urlopen(health, timeout=2) as r:
                if r.status == 200:
                    ok = True
                    break
        except Exception:
            time.sleep(0.5)
    return {"pid": p.pid, "healthy": ok, "exited": p.poll(), "had_old_env": bool(cap["env"])}


def core_service(ctl, port=8090):
    return {"name": "core", "res": {"nice": 0, "oom_score_adj": -100}, "group": "chat", "port": port, "prio": 35,
            "argv": ["python3", "@CTL@/wow7/brain/nox_core.py"], "cwd": "@CTL@/wow7/brain",
            "env": {"NOX_CORE_PORT": str(port), "NOX_FAST_URL": "http://127.0.0.1:8083", "NOX_GLM_URL": "http://127.0.0.1:8081",
                    "NOX_STATE": "@HOME@/state", "NOX_RECEIPTS": "@HOME@/receipts", "NOX_TRACE_DIR": "@HOME@/state/core_trace",
                    "NOX_CONSCIENCE": "shadow", "NOX_WOW7": "@CTL@/wow7"},
            "after": ["fast", "recall"], "match": "wow7/brain/nox_core\\.py", "health": {"path": "/health", "ok": [200], "loading": []},
            "start_timeout_s": 30, "load_grace_s": 30, "log": "core.log"}


def merge_local(services, local, flags, unapply=False):
    """Возвращает новый local (dict). services - список из services.json. Вшивает flags в env gateway и (если есть) core; добавляет core."""
    loc = json.loads(json.dumps(local or {}))
    ov = loc.setdefault("services", {})
    by = {s["name"]: s for s in services}
    if unapply:
        for n in ("gateway", "core"):
            if n in ov and ov[n].get(MARK):
                del ov[n]
        loc["add_services"] = [s for s in loc.get("add_services", []) if not s.get(MARK)]
        if not ov:
            loc.pop("services", None)
        if not loc.get("add_services"):
            loc.pop("add_services", None)
        return loc
    if "gateway" in by:
        env = dict(by["gateway"].get("env", {}))
        env.update((ov.get("gateway") or {}).get("env", {}))
        env.update(flags)
        ov["gateway"] = dict(ov.get("gateway") or {}, env=env)
        ov["gateway"][MARK] = True
    adds = [s for s in loc.get("add_services", []) if s.get("name") != "core" or not s.get(MARK)]
    if "core" not in by and not any(s.get("name") == "core" for s in adds):
        cs = core_service(None)
        cs["env"].update({k: v for k, v in flags.items() if k in ("NOX_CONSCIENCE", "NOX_BG_DEEP")})
        cs[MARK] = True
        adds.append(cs)
    loc["add_services"] = adds
    return loc


def local_env(local, service, setv, clear=False):
    """services.<service>.env в local.json DSP (полная замена env сервиса не нужна: берём только то, что вшито нами, метка _v7env)."""
    loc = json.loads(json.dumps(local or {}))
    ov = loc.setdefault("services", {})
    cur = ov.get(service) or {}
    if clear:
        if cur.get("_v7env"):
            cur = {k: v for k, v in cur.items() if k not in ("env", "_v7env")}
        if cur:
            ov[service] = cur
        else:
            ov.pop(service, None)
        if not ov:
            loc.pop("services", None)
        return loc
    env = dict(cur.get("env") or {})
    env.update(setv)
    ov[service] = dict(cur, env=env, _v7env=True)
    return loc


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    f = sp.add_parser("flags"); f.add_argument("op", choices=["get", "set", "unset"]); f.add_argument("items", nargs="*")
    c = sp.add_parser("capture"); c.add_argument("--match", required=True)
    r = sp.add_parser("restart"); r.add_argument("--match", required=True); r.add_argument("--cwd", default="."); r.add_argument("--log", required=True)
    r.add_argument("--env-add", action="append", default=[]); r.add_argument("--health"); r.add_argument("--env-default", action="append", default=[]); r.add_argument("--timeout", type=float, default=40); r.add_argument("argv", nargs="*")
    l = sp.add_parser("local-json"); l.add_argument("--services-json", required=True); l.add_argument("--local-json", required=True)
    l.add_argument("--apply", action="store_true"); l.add_argument("--unapply", action="store_true")
    e = sp.add_parser("local-env"); e.add_argument("--local-json", required=True); e.add_argument("--service", required=True)
    e.add_argument("--set", action="append", default=[]); e.add_argument("--clear", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "local-env":
        new = local_env(load(a.local_json, {}), a.service, dict(kv.split("=", 1) for kv in a.set), a.clear)
        save(a.local_json, new)
        print(json.dumps((new.get("services") or {}).get(a.service, {}), ensure_ascii=False))
        return 0
    if a.cmd == "flags":
        fl = load(FLAGS, {})
        if a.op == "set":
            for kv in a.items:
                k, _, v = kv.partition("=")
                fl[k] = v
            save(FLAGS, fl)
        elif a.op == "unset":
            for k in a.items:
                fl.pop(k, None)
            save(FLAGS, fl)
        print(json.dumps(fl, ensure_ascii=False))
    elif a.cmd == "capture":
        print(json.dumps(capture(a.match), ensure_ascii=False))
    elif a.cmd == "restart":
        add = dict(kv.split("=", 1) for kv in a.env_add)
        res = restart(a.match, a.cwd, a.log, a.argv, add, a.health, a.timeout, dict(kv.split("=", 1) for kv in a.env_default))
        print(json.dumps(res))
        return 0 if res["healthy"] else 1
    elif a.cmd == "local-json":
        reg = load(a.services_json, {})
        loc = load(a.local_json, {})
        new = merge_local(reg.get("services", []), loc, load(FLAGS, {}), unapply=a.unapply)
        save(a.local_json, new)
        print(json.dumps({"services": sorted((new.get("services") or {}).keys()), "add": [s["name"] for s in new.get("add_services", [])]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
