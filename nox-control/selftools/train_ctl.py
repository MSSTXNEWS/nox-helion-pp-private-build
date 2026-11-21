"""train_ctl: start/stop/retrain a training job via config + STOP flag files + pidfile."""
import json
import os
import signal
import subprocess
import time
import registry as R


def tdir():
    return os.environ.get("NOX_TRAIN_DIR", "/root/nox/state/train")


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _put(fp):
    with open(fp, "w") as f:
        f.write(time.strftime("%FT%T"))


def read_pid(d):
    try:
        with open(os.path.join(d, "train.pid")) as f:
            return int(f.read())
    except (OSError, ValueError):
        return None


@R.register("train_ctl", "write", {"properties": {
    "action": {"type": "string", "enum": ["status", "start", "retrain", "stop", "set_stop_flag", "clear_stop_flag"]},
    "flag": {"type": "string", "default": "STOP"}}, "required": ["action"]},
    "Training control. Config <dir>/train.json {cmd:[...], cwd, env}. STOP flags are files in <dir>/. stop = flag + SIGTERM (danger).",
    action_modes={"status": "read", "stop": "danger"})
def train_ctl(a):
    d, act = tdir(), a["action"]
    flag = a["flag"]
    if "/" in flag or flag.startswith("."):
        raise R.Denied("bad flag name")
    if act in ("status",):
        pid = read_pid(d)
        return {"ok": True, "running": bool(pid and alive(pid)), "pid": pid,
                "flags": sorted(f for f in os.listdir(d) if f.isupper()) if os.path.isdir(d) else []}
    if act in ("set_stop_flag", "clear_stop_flag"):
        fp = os.path.join(d, flag)
        if a["dry_run"]:
            return {"ok": True, "dry_run": True, "flag": fp, "action": act}
        os.makedirs(d, exist_ok=True)
        if act == "set_stop_flag":
            _put(fp)
        elif os.path.exists(fp):
            os.remove(fp)
        return {"ok": True, "flag": fp, "action": act}
    if act == "stop":
        pid = read_pid(d)
        os.makedirs(d, exist_ok=True)
        _put(os.path.join(d, "STOP"))
        if pid and alive(pid):
            os.kill(pid, signal.SIGTERM)
            return {"ok": True, "stopped_pid": pid, "flag_set": True}
        return {"ok": True, "stopped_pid": None, "flag_set": True, "note": "no running job"}
    # start / retrain
    cfgp = os.path.join(d, "train.json")
    if not os.path.exists(cfgp):
        return R.blocked("no train config at " + cfgp, "owner provides train.json {cmd:[...], cwd} for the training script")
    with open(cfgp) as f:
        cfg = json.load(f)
    cmd = cfg.get("cmd")
    if not cmd or not isinstance(cmd, list):
        return R.fail("train.json needs cmd list")
    pid = read_pid(d)
    if pid and alive(pid):
        return R.fail("job already running pid %d" % pid)
    if act == "retrain":
        cmd = cmd + list(cfg.get("retrain_args", ["--retrain"]))
    if a["dry_run"]:
        return {"ok": True, "dry_run": True, "would_run": cmd, "cwd": cfg.get("cwd")}
    stopf = os.path.join(d, "STOP")
    if os.path.exists(stopf):
        return R.blocked("STOP flag present: " + stopf, "clear_stop_flag first")
    env = dict(os.environ, **{str(k): str(v) for k, v in (cfg.get("env") or {}).items()})
    with open(os.path.join(d, "train.log"), "ab") as log:
        p = subprocess.Popen(cmd, cwd=cfg.get("cwd") or d, stdout=log, stderr=log, env=env, start_new_session=True)
    with open(os.path.join(d, "train.pid"), "w") as f:
        f.write(str(p.pid))
    return {"ok": True, "dry_run": False, "pid": p.pid, "log": os.path.join(d, "train.log")}
