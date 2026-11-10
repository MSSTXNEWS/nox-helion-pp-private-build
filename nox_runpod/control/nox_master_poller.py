#!/usr/bin/env python3
"""NOX safe control polling. Standard library, no arbitrary remote shell execution."""
import argparse, datetime, fcntl, json, os, pathlib, subprocess, sys, time, urllib.request

ROOT = pathlib.Path("/workspace/nox")
CONTROL = ROOT / "dispatcher" / "nox_master_control"
URL = "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox_runpod/control/NOX_MASTER_CONTROL.json"

def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def atomic(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".new")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)

def processes():
    found = []
    for p in pathlib.Path("/proc").iterdir():
        if not p.name.isdigit():
            continue
        try:
            args = [v.decode(errors="replace") for v in (p / "cmdline").read_bytes().split(bytes([0])) if v]
            if args and "python" in pathlib.Path(args[0]).name:
                for label in ("a40_cuda_distillation_direct.py", "a40_full_parameter_distill_cycle.py",
                              "a5000_cuda_secondary_direct.py", "a5000_cuda_distillation_direct.py"):
                    if any(pathlib.Path(a).name == label for a in args[1:]):
                        found.append({"pid": int(p.name), "script": label})
        except OSError:
            pass
    return found

def checkpoint_receipts():
    root = pathlib.Path("/opt/nox_full_parameter_A40")
    output = []
    if not root.exists():
        return output
    for path in sorted(root.glob("*/NOX_FULL_TRAIN_RECEIPT.json"))[-10:]:
        try:
            receipt = json.loads(path.read_text())
            shards = receipt.get("shards", [])
            sizes_match = bool(shards) and all(
                (path.parent / s["file"]).is_file()
                and (path.parent / s["file"]).stat().st_size == int(s.get("bytes", s.get("size", -1)))
                for s in shards)
            output.append({"path": str(path.parent), "steps": receipt.get("steps"),
                           "teachers": receipt.get("teacher_counts"), "sizes_match": sizes_match,
                           "sha_verified_here": False})
        except (OSError, ValueError, KeyError, TypeError):
            output.append({"path": str(path.parent), "error": "receipt_unreadable"})
    return output

def read_policy():
    request = urllib.request.Request(URL, headers={"User-Agent": "NOX-master-control/1"})
    with urllib.request.urlopen(request, timeout=20) as response:
        data = response.read(32769)
    if len(data) > 32768:
        raise ValueError("policy_too_large")
    policy = json.loads(data)
    if policy.get("schema") != "nox-control-v1" or policy.get("mode") not in ("observe", "safe_transition"):
        raise ValueError("invalid_policy")
    if policy.get("no_loss") is not True or policy.get("allow_remote_delete") is not False:
        raise ValueError("unsafe_policy")
    if policy.get("allow_arbitrary_shell") is not False:
        raise ValueError("shell_not_allowed")
    if policy.get("poll_seconds") != 180:
        raise ValueError("unexpected_poll_period")
    return policy

def pause_known_a40_teacher(policy):
    # One-way request to finish its current example; never sends SIGKILL.
    node = policy["nodes"]["A40"]
    if node.get("legacy_action") != "request_graceful_stop":
        return "not_requested"
    dist = ROOT / "distillation" / "NOX_A40_CUDA_DISTILLATION.jsonl"
    if not dist.is_file() or dist.stat().st_size == 0:
        return "HOLD_no_saved_teacher_data"
    state = ROOT / "dispatcher" / "a40_direct"
    state.mkdir(parents=True, exist_ok=True)
    (state / "STOP").touch()
    # Existing known watchdog checks STOP. We do NOT modify cron or other supervisors
    # without verifying and backing up their exact configuration.
    return "stop_marker_set_no_process_kill"

def tick(node):
    policy = read_policy()
    state = {"utc": utc(), "node": node, "policy_revision": policy["revision"],
             "mode": policy["mode"], "role": policy["nodes"][node]["role"],
             "processes": processes(),
             "s03_exists": (ROOT / "memory/NOX_UNIFIED_S03/unified_nox_knowledge.sqlite3").is_file(),
             "checkpoints": checkpoint_receipts() if node == "A40" else [],
             "remote_delete": False}
    try:
        gpu = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.free,temperature.gpu",
             "--format=csv,noheader"], capture_output=True, text=True, timeout=10)
        state["gpu"] = gpu.stdout.strip() if gpu.returncode == 0 else "HOLD_GPU_TELEMETRY"
    except (OSError, subprocess.TimeoutExpired):
        state["gpu"] = "HOLD_GPU_TELEMETRY"
    try:
        status = os.statvfs("/workspace")
        state["workspace_free_gib"] = round(status.f_bavail * status.f_frsize / 1024**3, 2)
    except OSError:
        state["workspace_free_gib"] = None
    progress = ROOT / "dispatcher/a40_full_parameter/progress.json"
    if node == "A40" and progress.is_file():
        try:
            d = json.loads(progress.read_text())
            state["trainer"] = {k: d.get(k) for k in
                ("status", "stage", "steps_executed_this_cycle", "target_steps_this_cycle", "reason", "utc")}
        except (OSError, ValueError):
            state["trainer"] = {"status": "UNKNOWN"}
    if node == "A40" and policy["mode"] == "safe_transition":
        state["legacy_action_result"] = pause_known_a40_teacher(policy)
    atomic(CONTROL / ("status_" + node + ".json"), state)
    print(json.dumps({"event": "NOX_CONTROL_TICK", **state}, ensure_ascii=False), flush=True)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--node", choices=["A40", "A5000"], required=True)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    CONTROL.mkdir(parents=True, exist_ok=True)
    lock = (CONTROL / ("poller_" + args.node + ".lock")).open("a+")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("NOX_CONTROL_ALREADY_RUNNING", args.node, flush=True)
        return 0
    while True:
        try:
            tick(args.node)
        except Exception as exc:
            atomic(CONTROL / ("status_" + args.node + ".json"),
                   {"utc": utc(), "node": args.node, "status": "HOLD_CONTROL_ERROR",
                    "reason": str(exc)[:250], "no_changes": True})
            print("HOLD_CONTROL_ERROR", type(exc).__name__, str(exc)[:250], flush=True)
        if args.once:
            return 0
        time.sleep(180)

if __name__ == "__main__":
    sys.exit(main())
