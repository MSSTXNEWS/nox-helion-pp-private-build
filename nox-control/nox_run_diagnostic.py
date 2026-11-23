#!/usr/bin/env python3
"""NOX run-state diagnosis. Read-only; never opens model weights or modifies processes."""
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path("/workspace/nox")
SUFFIXES = {".safetensors", ".pt", ".pth", ".bin", ".ckpt"}
STATE_NAMES = {"trainer_state.json", "training_state.json", "optimizer.pt", "optimizer.bin", "scheduler.pt", "adapter_model.safetensors", "adapter_model.bin", "pytorch_model.bin"}
SKIP = {".git", "node_modules", "site-packages", "__pycache__", "venv", "prime9b-venv", "datasets", "THREE_TEACHERS", "cache"}
def run(args):
    try:
        p=subprocess.run(args,capture_output=True,text=True,timeout=12,check=False)
        return {"exit":p.returncode,"output":(p.stdout or p.stderr)[-3500:]}
    except Exception as exc: return {"error":str(exc)[:300]}
def process_info():
    result=[]
    for p in Path("/proc").iterdir():
        if not p.name.isdigit(): continue
        try:
            cmd=(p/"cmdline").read_bytes().replace(b"\0",b" ").decode("utf-8","replace")
            if not any(x in cmd.lower() for x in ("train", "distill", "accelerate", "deepspeed", "torchrun")): continue
            if "nox_run_diagnostic.py" in cmd: continue
            cmd=cmd[:450]
            result.append({"pid":int(p.name),"command":cmd})
        except (OSError,PermissionError): continue
    return result[:50]
def inventory():
    files=[]
    if not ROOT.is_dir(): return files
    for base,dirs,names in os.walk(ROOT):
        depth=len(Path(base).relative_to(ROOT).parts)
        dirs[:]=[d for d in dirs if d not in SKIP and not d.startswith(".")] if depth<7 else []
        for name in names:
            if not (name in STATE_NAMES or "checkpoint" in name.lower() or ("adapter" in name.lower() and Path(name).suffix in SUFFIXES)): continue
            p=Path(base)/name
            try:
                st=p.stat()
                files.append({"path":str(p.relative_to(ROOT)),"bytes":st.st_size,"mtime_utc":dt.datetime.fromtimestamp(st.st_mtime,dt.timezone.utc).isoformat()})
            except OSError: pass
    return sorted(files,key=lambda f:f["mtime_utc"],reverse=True)[:70]

# Optional, bounded host facts for original RELAY35 2A01.  Never admits work.
def hardware_2a01_snapshot():
    import csv
    import re

    def command(argv):
        try:
            result = subprocess.run(argv, capture_output=True, text=True, timeout=8, check=False)
            if result.returncode != 0 or len(result.stdout) > 16384:
                return None
            return result.stdout
        except (OSError, subprocess.TimeoutExpired, UnicodeError):
            return None

    holds = []
    fields = ("index", "uuid", "name", "pci.bus_id", "memory.total",
              "memory.free", "temperature.gpu", "driver_version",
              "compute_cap", "pcie.link.gen.current", "pcie.link.width.current")
    raw = command(["nvidia-smi", "--query-gpu=" + ",".join(fields),
                   "--format=csv,noheader,nounits"])
    gpu = []
    if raw is not None:
        for values in csv.reader(raw.splitlines()):
            if len(values) != len(fields):
                gpu = []
                break
            row = dict(zip(fields, (value.strip() for value in values)))
            if any(not value or value in ("N/A", "[Not Supported]") or len(value) > 120
                   for value in row.values()):
                gpu = []
                break
            gpu.append(row)
    if len(gpu) != 2 or {row["index"] for row in gpu} != {"0", "1"}:
        holds.append("HOLD_2A01_EXACT_TWO_GPU_FIELDS")
    if not gpu or any(row["compute_cap"] != "7.0" for row in gpu):
        holds.append("HOLD_2A01_SM70_UNVERIFIED")

    topology = command(["nvidia-smi", "topo", "-m"])
    link = None
    if topology:
        for line in topology.splitlines():
            columns = line.split()
            if len(columns) >= 3 and columns[0] == "GPU0":
                link = columns[2] if re.fullmatch(r"(NV[0-9]+|SYS|NODE|PHB|PXB|PIX)", columns[2]) else None
                break
    if link is None:
        holds.append("HOLD_2A01_GPU_TOPOLOGY_UNVERIFIED")

    def cgroup_number(filename):
        try:
            value = (Path("/sys/fs/cgroup") / filename).read_text(encoding="ascii").strip()
            return int(value) if value.isdecimal() else None
        except (OSError, ValueError, UnicodeError):
            return None

    memory_current = cgroup_number("memory.current")
    memory_max = cgroup_number("memory.max")
    if (memory_current is None or memory_max is None
            or memory_current > memory_max):
        holds.append("HOLD_2A01_CGROUP_MEMORY_UNVERIFIED")
    headroom = (memory_max - memory_current
                if memory_current is not None and memory_max is not None
                   and memory_current <= memory_max else None)

    disk = None
    try:
        info = os.statvfs("/root/nox")
        disk = {"available_bytes": info.f_bavail * info.f_frsize,
                "total_bytes": info.f_blocks * info.f_frsize}
    except OSError:
        holds.append("HOLD_2A01_SSD_CAPACITY_UNVERIFIED")
    # Do not infer throughput from statvfs or a single /proc/diskstats sample.
    holds.extend(["HOLD_2A01_SSD_IO_UNMEASURED",
                  "HOLD_2A01_CUDA_RUNTIME_UNVERIFIED",
                  "HOLD_2A01_MAYA_BUILD_PIN_UNVERIFIED",
                  "HOLD_2A01_OWNER_LEASE_CAS_UNVERIFIED"])
    return {"schema": "NOX_2A01_READONLY_HOST_FACTS_V1",
            "gpu": gpu, "gpu0_to_gpu1_topology_class": link,
            "cgroup": {"memory_current_bytes": memory_current,
                       "memory_max_bytes": memory_max,
                       "headroom_bytes": headroom},
            "ssd": disk, "hold_codes": sorted(set(holds)),
            "native_accepted": False, "may_activate": False,
            "note": "Untrusted read-only host facts. No GPU, SSD benchmark, process, lease or model change. Never source-only PASS."}

if __name__=="__main__":
    if sys.argv[1:] == ["--hardware-2a01"]:
        print("NOX_2A01_HARDWARE " + json.dumps(hardware_2a01_snapshot(), ensure_ascii=False, sort_keys=True))
        raise SystemExit(0)
    if "--hardware-2a01" in sys.argv[1:]:
        raise SystemExit("HOLD_2A01_UNRECOGNIZED_OPTIONS")
    info={"checked_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
    "root":str(ROOT),"training_process_candidates":process_info(),
    "weight_or_trainer_state_files":inventory(),
    "gpu":run(["nvidia-smi","--query-compute-apps=pid,used_gpu_memory","--format=csv,noheader,nounits"])}
    info["training_verified"]=False
    info["note"]="Process existence and file names do not prove optimizer updates. Inspect trainer_state and checkpoint contents separately; no changes were made."
    print("NOX_RUN_DIAGNOSTIC "+json.dumps(info,ensure_ascii=False))
