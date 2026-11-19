"""NOX V38 read-only operational audit using existing Linux tools.

No new daemon, no open ports, no dependency install, no process mutation.
No telemetry value is manufactured when a native command is missing or fails.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any

SENSITIVE = re.compile(r"(password|api[_-]?key|secret|token|authorization|cookie|private[_-]?key)", re.I)
ROLE = re.compile(r"\b(nox|train|distill|llama|cuda|inference|vllm|ollama|python)\b", re.I)
GPU_COMMAND = ["nvidia-smi", "--query-gpu=index,name,uuid,memory.total,memory.used,utilization.gpu,temperature.gpu", "--format=csv,noheader,nounits"]
APP_COMMAND = ["nvidia-smi", "--query-compute-apps=pid,process_name,used_gpu_memory", "--format=csv,noheader,nounits"]


def command(argv: list[str], *, timeout: float=6.0, limit: int=40000) -> dict[str, Any]:
    if not argv or not all(isinstance(x,str) and x for x in argv):
        return {"state":"BAD_COMMAND"}
    if shutil.which(argv[0]) is None:
        return {"state":"NOT_INSTALLED", "tool":argv[0]}
    try:
        r=subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return {"state":"TIMEOUT", "tool":argv[0]}
    except OSError:
        return {"state":"IO_ERROR", "tool":argv[0]}
    # Avoid displaying arbitrary stderr (may contain command-line credentials).
    return {"state":"OK" if r.returncode==0 else "ERROR", "exit_code":r.returncode,
            "stdout":r.stdout[:limit]}


def gpu_rows(stdout: str) -> list[dict[str, Any]]:
    rows=[]
    for row in csv.reader(stdout.splitlines(),skipinitialspace=True):
        if len(row)!=7: continue
        try:
            idx=int(row[0]);total=int(row[3]);used=int(row[4]);util=int(row[5]);temp=int(row[6])
        except (ValueError,TypeError):continue
        if idx<0 or total<=0 or used<0 or not 0<=util<=100 or not -10<=temp<=120:continue
        rows.append({"index":idx,"name":row[1].strip()[:90],"gpu_uuid":row[2].strip()[:80],
                     "vram_total_mib":total,"vram_used_mib":used,"compute_util_pct":util,
                     "temp_core_c":temp})
    return sorted(rows,key=lambda x:x["index"])


def gpu_apps(stdout:str)->list[dict[str,Any]]:
    rows=[]
    for row in csv.reader(stdout.splitlines(),skipinitialspace=True):
        if len(row)<3:continue
        try:
            pid=int(row[0]);used=int(row[-1])
        except ValueError:continue
        if pid<=0 or used<0:continue
        # Process name is basename only, never full commandline/secret paths.
        process=os.path.basename(row[1].strip())[:80]
        rows.append({"pid":pid,"name":process,"gpu_memory_mib":used})
    return rows[:100]


def supervisor_rows(stdout:str)->list[dict[str,Any]]:
    statuses=("RUNNING","STOPPED","FATAL","BACKOFF","EXITED","STARTING","STOPPING","UNKNOWN")
    results=[]
    for line in stdout.splitlines()[:500]:
        parts=line.split(None,2)
        if len(parts)<2 or parts[1] not in statuses:continue
        if not re.fullmatch(r"[A-Za-z0-9_.:@+-]{1,125}",parts[0]):continue
        rest=parts[2] if len(parts)>2 else ""
        pid=re.search(r"\bpid\s+(\d+)\b",rest)
        up=re.search(r"\b(?:uptime|uptime:|uptime\s+)\s*(\S+)",rest)
        results.append({"service":parts[0],"state":parts[1],"pid":int(pid.group(1)) if pid else None,
                        "uptime":up.group(1)[:40] if up else None})
    return results


def disk_usage(path: str="/") -> dict[str,Any]:
    try:
        d=shutil.disk_usage(path)
        return {"path":path,"total_bytes":d.total,"used_bytes":d.used,"free_bytes":d.free,
                "used_pct":round(100*d.used/d.total,1) if d.total else None}
    except OSError:
        return {"state":"NOT_AVAILABLE","path":path}


def meminfo() -> dict[str,Any]:
    try:lines=Path('/proc/meminfo').read_text('utf8').splitlines()
    except OSError:return {"state":"NO_PROC_MEMINFO"}
    raw={}
    for line in lines:
        if ':' not in line:continue
        key,_,v=line.partition(':');m=re.match(r"\s*(\d+)\s+kB",v)
        if m and key in ('MemTotal','MemAvailable','MemFree','SwapTotal','SwapFree'):
            raw[key]=int(m.group(1))//1024
    return {k.lower()+"_mib":v for k,v in raw.items()}


def processes() -> dict[str,Any]:
    # /proc stat avoids exposing full argv and confidential environment settings.
    rows=[]
    try:pids=[p for p in Path('/proc').iterdir() if p.name.isdigit()]
    except OSError:return {"state":"PROC_NOT_AVAILABLE","items":[]}
    for p in pids[:10000]:
        try:name=(p/'comm').read_text().strip()[:65]
        except OSError:continue
        if not ROLE.search(name):continue
        rows.append({"pid":int(p.name),"executable":name})
    return {"state":"OK","items":sorted(rows,key=lambda x:x['pid'])[:100]}


def inventory() -> dict[str,Any]:
    gpu=command(GPU_COMMAND);apps=command(APP_COMMAND)
    sv=command(["supervisorctl","status"],timeout=8)
    values={"schema":"NOX_V38_READONLY_AUDIT","utc":datetime.now(timezone.utc).isoformat(),
            "instance_id_expected":"60509551", "hostname":os.uname().nodename[:120] if hasattr(os,"uname") else "UNKNOWN",
            "gpu_state":gpu['state'],"gpus":gpu_rows(gpu.get('stdout','')),
            "compute_apps_state":apps['state'],"compute_apps":gpu_apps(apps.get('stdout','')),
            "supervisor_state":sv['state'],"services":supervisor_rows(sv.get('stdout','')),
            "memory":meminfo(),"disk_root":disk_usage('/'),"disk_workspace":disk_usage('/workspace') if Path('/workspace').exists() else {'state':'NOT_MOUNTED'},
            "processes":processes(),"student_model_sha":"UNVERIFIED",
            "optimizer_step":"UNVERIFIED","training_loss":"UNVERIFIED",
            "s03_revision":"UNVERIFIED","cores_c01_c08":"UNVERIFIED"}
    rootfree=values['disk_root'].get('free_bytes',0)
    disk_holds=[]
    if rootfree<20_000_000_000:disk_holds.append('DISK_HEADROOM_LT_20GB')
    w=values['disk_workspace'];workspacefree=w.get('free_bytes',0)
    if w.get('state')!='NOT_MOUNTED' and workspacefree<20_000_000_000:disk_holds.append('WORKSPACE_HEADROOM_LT_20GB')
    values['admission']={'new_model_download':"HOLD" if disk_holds else "NATIVE_APPROVAL_REQUIRED",
                         'new_gpu_training':"HOLD_TRAINING_PROVENANCE_AND_BACKUP_REQUIRED",
                         'disk_holds':disk_holds,
                         'stop_mechanism':'EXISTING_NOX_ONLY_NOT_MODIFIED'}
    return values


def path_allowed(path:Path,roots:list[Path])->bool:
    p=path.resolve()
    return any(p.is_relative_to(root.resolve()) for root in roots)


def cleanup_candidates(roots:list[Path], *, max_entries:int=10000, max_items:int=250)->dict[str,Any]:
    """Inventory ONLY. Never deletes. Cache roots are opt-in; weight folders prohibited."""
    risky=re.compile(r"(checkpoint|\.gguf|safetensors|optimizer|\bs03\b|\.sqlite|\.db\b|model|weight|birth|ledger)",re.I)
    results=[];visited=0;bytes_total=0
    allowed=[Path('/tmp'),Path('/root/.cache/pip'),Path('/workspace/.cache/pip')]
    for root in roots:
        if not root.exists() or not path_allowed(root,allowed):continue
        # Restrict traversal to selected root. No symlinks followed.
        for base,dirs,files in os.walk(root,followlinks=False):
            dirs[:]=[d for d in dirs if not risky.search(d) and not (Path(base)/d).is_symlink()]
            for name in files:
                visited+=1
                if visited>max_entries:break
                path=Path(base)/name
                if path.is_symlink() or risky.search(str(path)):continue
                try:st=path.stat()
                except OSError:continue
                if st.st_size<=0:continue
                if (datetime.now(timezone.utc).timestamp()-st.st_mtime)<7*86400:continue
                results.append({'path':str(path)[:350], 'bytes':st.st_size, 'age_days':round((datetime.now(timezone.utc).timestamp()-st.st_mtime)/86400,1)})
                bytes_total+=st.st_size
                if len(results)>=max_items:break
            if visited>max_entries or len(results)>=max_items:break
    return {'schema':'NOX_V38_CLEANUP_PREVIEW_ONLY','delete_executed':False,
            'candidate_count':len(results),'candidate_bytes':bytes_total,
            'traversed':min(visited,max_entries),'items':results}


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(description='NOX V38 read-only server control (no mutation)')
    sub=p.add_subparsers(dest='mode',required=True)
    sub.add_parser('status',help='GPU/CPU/VRAM/RAM/disk/NOX services inventory; JSON stdout')
    cl=sub.add_parser('cleanup-plan',help='dry-run list of aged cache files: never deletes')
    cl.add_argument('--root',action='append',choices=['/tmp','/root/.cache/pip','/workspace/.cache/pip'])
    args=p.parse_args(argv)
    data=inventory() if args.mode=='status' else cleanup_candidates([Path(x) for x in (args.root or ['/root/.cache/pip'])])
    print(json.dumps(data,ensure_ascii=False,indent=2,default=str))
    return 0

if __name__=='__main__':raise SystemExit(main())
