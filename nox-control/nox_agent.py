#!/usr/bin/env python3
"""NOX control-plane polling agent, v1. Read-only allowlisted actions only.
Usage: python3 nox_agent.py --target runpod-a40
Requires Python 3.9+, network access to GitHub. No third-party dependencies.
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import platform
import subprocess
import time
import urllib.request

URL = "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/NOX_MASTER.json"
ACTIONS = {"health", "gpu_status", "nox_status"}
MAX_OUTPUT = 3000

def now():
    return dt.datetime.now(dt.timezone.utc)

def parse_time(value):
    if not isinstance(value, str):
        raise ValueError("missing ISO timestamp")
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(dt.timezone.utc)

def run_action(action):
    if action == "health":
        return {"ok": True, "platform": platform.system(), "machine": platform.machine()}
    if action == "gpu_status":
        try:
            p = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,memory.used,temperature.gpu,utilization.gpu", "--format=csv,noheader"], capture_output=True, text=True, timeout=10, check=False, shell=False)
            return {"ok": p.returncode == 0, "output": (p.stdout or p.stderr)[:MAX_OUTPUT]}
        except (OSError, subprocess.TimeoutExpired) as e:
            return {"ok": False, "error": str(e)[:250]}
    if action == "nox_status":
        return {"ok": True, "message": "Agent online. Detailed NOX process checks are not enabled in safe v1."}
    raise ValueError("action not allowlisted")

def fetch_manifest():
    req = urllib.request.Request(URL, headers={"User-Agent": "NOX-Safe-Agent/1", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=20) as res:
        data = res.read(250000)
    obj = json.loads(data)
    if obj.get("protocol") != "NOX_CONTROL_V1" or obj.get("schema_version") != 1:
        raise ValueError("unsupported protocol")
    return obj

def save_json(path, obj):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)

def poll(target, state_dir):
    state_dir.mkdir(parents=True, exist_ok=True)
    state_file = state_dir / "completed.json"
    try:
        completed = json.loads(state_file.read_text(encoding="utf-8"))
        if not isinstance(completed, dict):
            completed = {}
    except (OSError, ValueError):
        completed = {}
    print(f"NOX_AGENT_ONLINE target={target} interval=180s actions=read-only", flush=True)
    while True:
        try:
            manifest = fetch_manifest()
            if manifest.get("enabled") is True:
                tasks = manifest.get("tasks", [])
                if not isinstance(tasks, list) or len(tasks) > 100:
                    raise ValueError("invalid task list")
                for task in tasks:
                    if not isinstance(task, dict):
                        continue
                    task_id = task.get("id")
                    action = task.get("action")
                    task_target = task.get("target")
                    if not isinstance(task_id, str) or not (1 <= len(task_id) <= 100):
                        continue
                    if task_id in completed or action not in ACTIONS or task_target not in (target, "all"):
                        continue
                    try:
                        if now() >= parse_time(task.get("expires_at")):
                            continue
                    except (ValueError, TypeError):
                        continue
                    result = run_action(action)
                    result.update({"id": task_id, "target": target, "action": action, "finished_at": now().isoformat()})
                    completed[task_id] = result
                    save_json(state_file, completed)
                    print("NOX_RESULT " + json.dumps(result, ensure_ascii=False), flush=True)
            else:
                print("NOX_AGENT_DISABLED", flush=True)
        except Exception as e:
            print("NOX_AGENT_ERROR " + repr(e)[:300], flush=True)
        time.sleep(180)

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--target", required=True, help="Unique machine identity, e.g. runpod-a40")
    p.add_argument("--state-dir", default=str(Path.home() / ".nox-control"))
    args = p.parse_args()
    if not args.target or len(args.target) > 80:
        p.error("invalid target")
    poll(args.target, Path(args.state_dir))
