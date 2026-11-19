"""V72 ONEPASS: one authorized live Vast session, health/RAM/S03 + safe CPU priority.

Uses existing NOX2 + V60/V51 one-time per-instance SSH. No model or chat
restart, no new backend or dispatcher, no new weights, no S03 writes.
If CAP_SYS_NICE is available, raise CPU scheduling priority of exactly the
existing authenticated chat proxy and current.gguf llama-server with rollback
on health failures. No generic process commands or user-content export.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as v51
from nox_runpod.teacher_mesh.v60 import encrypted_backup as v60

REMOTE = r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import json
import os
import re
import socket
import sqlite3
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

R={
 "schema":"NOX_V72_ONEPASS_NATIVE_RECEIPT_V1",
 "instance_id":60509551,
 "instance_production_changed":False,
 "active_student_switched":False,
 "s03_source_changed":False,
 "checkpoint_changed":False,
 "onehost_scheduler_replaced":False,
 "native_oneprime_bound":False,
 "new_optimizer_steps_verified":False,
 "cpu_priority_applied":False,
 "cpu_priority_state":"NOT_ATTEMPTED",
 "s03_ram_backup_pass":False,
 "main_model_healthy":False,
 "proxy_health_ok":False,
 "s03_persistent":True,
 "messages_exposed":False,
 "authenticated_end_to_end_tested":False
}
def final(state):
    R['state']=state
    print("NATIVE_V72_JSON="+json.dumps(R,sort_keys=True,separators=(',',':')))
    return 0 if state.startswith("LIVE_CHECKS_PASS") else 2

def health(port, path, timeout=3):
    try:
        req=urllib.request.Request('http://127.0.0.1:'+str(port)+path,
           headers={'Accept':'application/json','Connection':'close'},
           method='GET')
        with urllib.request.urlopen(req,timeout=timeout) as s:
            return s.status,s.read(100000)
    except urllib.error.HTTPError as e:
        return e.code,b''
    except (OSError,TimeoutError,ValueError):
        return 0,b''

def small_model_test():
    status,body=health(8081,'/v1/models',3)
    if status!=200:return None
    try:
        models=json.loads(body).get('data',[])
        name=models[0].get('id','') if models else ''
        if not isinstance(name,str) or not name.endswith('/models/current.gguf'):
            return None
    except (ValueError,TypeError,KeyError):return None
    request=json.dumps({"model":name,"messages":[{"role":"user",
      "content":"Ответь одним словом: готово."}],"stream":True,
      "max_tokens":16,"temperature":0},ensure_ascii=False).encode()
    q=urllib.request.Request('http://127.0.0.1:8081/v1/chat/completions',
        data=request,method='POST',headers={'Content-Type':'application/json',
                                            'Accept':'text/event-stream'})
    begin=time.monotonic()
    first=None
    ended=False
    try:
        with urllib.request.urlopen(q,timeout=12) as resp:
            if resp.status!=200:return None
            for raw in resp:
                if time.monotonic()-begin>15:break
                if len(raw)>15000:continue
                item=raw.decode('utf-8','replace').strip()
                if not item.startswith('data:'):continue
                s=item[5:].strip()
                if s=='[DONE]':ended=True;break
                try:val=json.loads(s)
                except ValueError:continue
                for c in (val.get('choices') or []):
                    if not isinstance(c,dict):continue
                    d=c.get('delta') or {}
                    if isinstance(d,dict) and d.get('content') and first is None:
                        first=time.monotonic()
        end=time.monotonic()
        if first is None or not ended:return None
        return {"ttft_ms":round(1000*(first-begin),1),
                "e2e_ms":round(1000*(end-begin),1)}
    except (OSError,TimeoutError,urllib.error.URLError,ValueError):
        return None

def target_pids():
    found={}
    out=subprocess.run(['ss','-H','-ltnp'],capture_output=True,text=True,timeout=6)
    if out.returncode!=0:return None
    for line in out.stdout.splitlines():
        pm=re.search(r':([0-9]{2,5})\s',line)
        pid=re.search(r'pid=([0-9]+)',line)
        if not pm or not pid or int(pm.group(1)) not in (8080,8081):continue
        port=int(pm.group(1));p=int(pid.group(1))
        try:comm=(Path('/proc')/str(p)/'cmdline').read_bytes().lower()
        except OSError:continue
        if port==8080 and b'chat_proxy.py' in comm:found['proxy']=p
        if port==8081 and b'llama-server' in comm:found['student']=p
    return found if set(found)=={'proxy','student'} and found['proxy']!=found['student'] else None

# Preflight avoids any process priority change when owner STOP is active.
stop_files=('/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag',
            '/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP')
if any(Path(p).exists() for p in stop_files):
    raise SystemExit(final('HOLD_STOP_ACTIVE'))

try:
    st=os.statvfs('/workspace')
    R['workspace_free_bytes']=st.f_frsize*st.f_bavail
    R['chat_allowed_below_10gb']=True
except OSError:
    raise SystemExit(final('HOLD_DISK_TELEMETRY'))

mem={}
for ln in Path('/proc/meminfo').read_text().splitlines():
    if ':' not in ln:continue
    k,v=ln.split(':',1)
    if k in ('MemAvailable','MemTotal'):mem[k]=int(v.strip().split()[0])*1024
R['ram_available_bytes']=mem.get('MemAvailable')
shm=os.statvfs('/dev/shm')
R['shm_free_bytes']=shm.f_bavail*shm.f_frsize
if not R['ram_available_bytes'] or R['ram_available_bytes']<32*1024**3:
    raise SystemExit(final('HOLD_RAM_HEADROOM'))

# Read-only online backup to SQLite :memory:, validate all three and discard.
dbs=(('/root/nox/kb/pc_safe70/nox_seed_memory.sqlite3','SEED'),
     ('/root/nox/memory/infinite/nox_infinite_memory.sqlite3','INFINITE'),
     ('/root/nox/memory/pc_t809u/nox_seed_memory.sqlite3','COPY'))
counts={}
for path,label in dbs:
    db=Path(path)
    if not db.is_file() or db.is_symlink() or db.stat().st_size>100_000_000:
        raise SystemExit(final('HOLD_S03_PATH_'+label))
    src=dst=None
    try:
        src=sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True,timeout=6)
        src.execute('PRAGMA query_only=ON')
        dst=sqlite3.connect(':memory:')
        src.backup(dst,pages=512,sleep=.02)
        row=dst.execute('PRAGMA quick_check').fetchone()
        if not row or row[0]!='ok':
            raise ValueError('HOLD_S03_QUICK_CHECK')
        tables=dst.execute('SELECT count(*) FROM sqlite_master WHERE type="table"').fetchone()[0]
        if tables<1:raise ValueError('HOLD_S03_TABLE_COUNT')
        counts[label]=tables
    except (OSError,sqlite3.Error,ValueError):
        raise SystemExit(final('HOLD_S03_RAM_SNAPSHOT_'+label))
    finally:
        if dst is not None:dst.close()
        if src is not None:src.close()
R['s03_ram_backup_pass']=len(counts)==3
R['s03_verified_db_count']=len(counts)
R['s03_tables_counts']=counts

hs={str(port):health(port,'/health')[0] for port in (8080,8081,8095)}
R['http_health']=hs
R['main_model_healthy']=hs['8081']==200
R['proxy_health_ok']=hs['8080']==200
if not R['main_model_healthy'] or not R['proxy_health_ok']:
    raise SystemExit(final('HOLD_LIVE_CHAT_OR_MODEL_HEALTH'))

# No sample request while slots already busy, to preserve current user turns.
slot_status,blob=health(8081,'/slots')
active=None
if slot_status==200:
    try:
        slots=json.loads(blob)
        if isinstance(slots,list):
            active=sum(bool(x.get('is_processing')) for x in slots if isinstance(x,dict))
            R['student_slots_total']=len(slots)
            R['student_slots_active']=active
    except (TypeError,ValueError):pass
if active==0:
    baseline=small_model_test()
    R['direct_model_baseline']=baseline or {"state":"HOLD_SYNTHETIC_TEST"}
else:
    R['direct_model_baseline']={"state":"SKIP_TO_PROTECT_ACTIVE_CHAT"}

# GPU inventory, two physical V100 expected, no GPU process changes.
try:
    n=subprocess.run(['nvidia-smi','--query-gpu=index,name,utilization.gpu,memory.used,memory.free',
                      '--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=8)
    if n.returncode==0:
        lines=n.stdout.splitlines()[:2]
        R['gpu_count_reported']=len(lines)
        R['gpus_v100']=len(lines)==2 and all('V100' in x for x in lines)
        R['gpu_status']=["GPU"+str(i)+"_GPUUTIL_"+x.split(',')[2].strip() for i,x in enumerate(lines) if len(x.split(','))>=5]
except (OSError,subprocess.TimeoutExpired):pass

# Live runtime bind test: NOX PRIME V71 must NOT be claimed until already
# running authenticated proxy imports actual OnePrime, with S03 native callbacks.
pids=target_pids()
R['exact_processes_verified']=pids is not None
if pids is None:
    R['cpu_priority_state']='HOLD_PID_IDENTITY'
    raise SystemExit(final('LIVE_CHECKS_PASS_NO_CPU_PRIORITY'))

R['process_kinds']=['EXISTING_CHAT_PROXY_8080','EXISTING_STUDENT_LLAMA_8081']

# CAP_SYS_NICE is required to lower nice. If absent, skip without mutating.
try:
    capline=next(x for x in Path('/proc/self/status').read_text().splitlines()
                 if x.startswith('CapEff:'))
    cap=int(capline.split(':',1)[1].strip(),16)
except (ValueError,StopIteration,OSError):
    cap=0
R['cap_sys_nice']=bool(cap & (1<<23))
if not R['cap_sys_nice']:
    R['cpu_priority_state']='HOLD_CONTAINER_CAP_SYS_NICE'
    raise SystemExit(final('LIVE_CHECKS_PASS_NO_CPU_PRIORITY'))

orig={}
changed=[]
try:
    for label,pid in pids.items():
        old=os.getpriority(os.PRIO_PROCESS,pid)
        orig[label]=old
        target=min(old,-3)
        if target!=old:
            os.setpriority(os.PRIO_PROCESS,pid,target)
            changed.append(label)
        if os.getpriority(os.PRIO_PROCESS,pid)!=target:
            raise OSError('priority_not_applied')
    # Health readback after the *single* scheduling mutation.
    h0=health(8080,'/health')[0]
    h1=health(8081,'/health')[0]
    if h0!=200 or h1!=200:
        raise OSError('post_health_failed')
    if active==0:
        after=small_model_test()
        if after is None:
            raise OSError('post_model_smoke_failed')
        R['direct_model_after']=after
    R['cpu_priority_applied']=bool(changed)
    R['cpu_priority_state']='VERIFIED' if changed else 'ALREADY_AT_PRIORITY'
    R['process_nice_levels']={k:os.getpriority(os.PRIO_PROCESS,p) for k,p in pids.items()}
    R['instance_production_changed']=bool(changed)
except (OSError,PermissionError):
    rollback_ok=True
    for label in reversed(changed):
        try:
            os.setpriority(os.PRIO_PROCESS,pids[label],orig[label])
            if os.getpriority(os.PRIO_PROCESS,pids[label])!=orig[label]:
                rollback_ok=False
        except (OSError,PermissionError):
            rollback_ok=False
    R['cpu_priority_applied']=False if rollback_ok else 'UNKNOWN'
    R['cpu_priority_state']='ROLLBACK_VERIFIED' if rollback_ok else 'HOLD_ROLLBACK_UNVERIFIED'
    R['instance_production_changed']=not rollback_ok
    if not rollback_ok:
        raise SystemExit(final('HOLD_PRIORITY_ROLLBACK_UNVERIFIED'))
    raise SystemExit(final('LIVE_CHECKS_PASS_PRIORITY_SKIPPED'))

raise SystemExit(final('LIVE_CHECKS_PASS_CPU_PRIORITY_VERIFIED'))
PYREMOTE
"""

def ssh_run(*,host:str,port:int,key:Path,known:Path,script:str,limit:int):
    base=["ssh","-T","-i",str(key),"-p",str(port),"-o","BatchMode=yes",
          "-o","IdentitiesOnly=yes","-o","ConnectTimeout=12",
          "-o","NumberOfPasswordPrompts=0","-o","UserKnownHostsFile="+str(known),
          "-o","StrictHostKeyChecking=yes","root@"+host,"bash","-se"]
    return subprocess.run(base,input=script,text=True,capture_output=True,timeout=limit)

def _onepass_attempt() -> dict:
    receipt={"schema":"NOX_V72_RUNNER_RECEIPT_V1","instance_id":60509551,
             "remote_attempts":0,"onehost_replaced":False,
             "new_llm":False,"new_scheduler":False,"new_optimizer_steps_verified":False}
    if not os.environ.get("NOX2"):
        return {**receipt,"state":"HOLD_NOX2"}
    attached=False
    try:
        # Exactly one authorized SSH session, one mutable remote script invocation.
        host,port=v60.live_direct_route()
        v60.attach_temporary_key()
        attached=True
        key=v51.KEY
        known=v60.RUN/"known_hosts"
        base=["ssh","-T","-i",str(key),"-p",str(port),
              "-o","BatchMode=yes","-o","IdentitiesOnly=yes",
              "-o","ConnectTimeout=12","-o","NumberOfPasswordPrompts=0",
              "-o","UserKnownHostsFile="+str(known)]
        authed=False
        for i in range(4):
            try:
                p=subprocess.run(base+["-o","StrictHostKeyChecking=accept-new",
                      "root@"+host,"bash","-se"],input=":\n",
                      text=True,capture_output=True,timeout=23)
            except subprocess.TimeoutExpired:
                p=None
            if p is not None and p.returncode==0:
                authed=True
                break
            time.sleep(4)
        if not authed:
            return {**receipt,"state":"HOLD_NATIVE_AUTHENTICATION"}
        receipt["ssh_authenticated"]=True
        receipt["remote_attempts"]=1
        try:
            proc=ssh_run(host=host,port=port,key=key,known=known,script=REMOTE,limit=70)
        except subprocess.TimeoutExpired:
            return {**receipt,"state":"HOLD_REMOTE_OUTCOME_UNKNOWN_NO_RETRY"}
        matches=[x.split("=",1)[1] for x in proc.stdout.splitlines()
                 if x.startswith("NATIVE_V72_JSON=") and len(x)<3500]
        if len(matches)!=1:
            return {**receipt,"state":"HOLD_NATIVE_RECEIPT_MISSING",
                    "remote_exit_code":proc.returncode,
                    "stdout_sha256":hashlib.sha256(proc.stdout.encode()).hexdigest()}
        data=json.loads(matches[0])
        if (not isinstance(data,dict) or data.get('schema')!='NOX_V72_ONEPASS_NATIVE_RECEIPT_V1'
            or data.get('instance_id')!=60509551):
            return {**receipt,"state":"HOLD_NATIVE_RECEIPT_SCHEMA"}
        return {**receipt,"state":data.get("state","HOLD_NO_STATE"),
                "remote_exit_code":proc.returncode,"native":data,
                "native_receipt_sha256":hashlib.sha256(matches[0].encode()).hexdigest()}
    except Exception as ex:
        val=str(ex)
        return {**receipt,"state":val if val.startswith("HOLD_") and len(val)<90
                else "HOLD_ONEPASS_EXCEPTION"}
    finally:
        if attached or v51.TRACK.exists():
            try:
                receipt["temp_ssh_key_revoked"]=v51.cleanup() is True
            except Exception:
                receipt["temp_ssh_key_revoked"]=False
        else:
            receipt["temp_ssh_key_revoked"]=True

def onepass() -> dict:
    """Return after the finally cleanup, not before it has executed."""
    outcome=_onepass_attempt()
    # Existing V51 removes the TRACK file *only* after remote key absence is
    # read back from the authorized Vast key registry.
    outcome["temp_ssh_key_revoked"]=not v51.TRACK.exists()
    return outcome

def main()->int:
    result=onepass()
    # redact all future unexpected fields, output only bounded verified receipt
    if result.get("temp_ssh_key_revoked") is not True:
        result["state"]="HOLD_TEMP_SSH_KEY_CLEANUP"
    native=result.get("native",{})
    trimmed={"schema":result["schema"],"instance_id":result["instance_id"],
             "state":result.get("state"),"ssh_authenticated":result.get("ssh_authenticated",False),
             "temp_ssh_key_revoked":result.get("temp_ssh_key_revoked"),
             "remote_attempts":result.get("remote_attempts",0),
             "native_receipt_sha256":result.get("native_receipt_sha256"),
             "native":native}
    Path("NOX_V72_SINGLE_RUN_RECEIPT.json").write_text(
        json.dumps(trimmed,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    for k in ("state","temp_ssh_key_revoked","ssh_authenticated"):
        print("NOX_V72_"+k.upper()+"="+str(trimmed.get(k)))
    for k in ("workspace_free_bytes","ram_available_bytes","shm_free_bytes",
              "s03_ram_backup_pass","main_model_healthy","proxy_health_ok",
              "cpu_priority_state","cpu_priority_applied",
              "direct_model_baseline","direct_model_after","native_oneprime_bound"):
        if k in native:
            print("NOX_V72_"+k.upper()+"="+str(native[k])[:150])
    print("NOX_V72_NATIVE_RECEIPT_SHA256="+str(trimmed["native_receipt_sha256"]))
    return 0 if str(trimmed["state"]).startswith("LIVE_CHECKS_PASS") and trimmed["temp_ssh_key_revoked"] else 2

if __name__=="__main__":
    raise SystemExit(main())
