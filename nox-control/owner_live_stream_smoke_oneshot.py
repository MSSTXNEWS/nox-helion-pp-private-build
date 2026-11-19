#!/usr/bin/env python3
"""One-shot source-pinned direct chat smoke in existing serving venv, not browser."""
from __future__ import annotations
import ast
import os
import subprocess

SOURCE = r'''#!/usr/bin/env python3
"""One owner-authorized live NOX chat/S03 smoke; no server source or service writes.

A single synthetic QA dialog can be persisted in the existing S03.  No raw
model/user content, credentials, cookies or chat excerpts leave the host.
"""
from __future__ import annotations

import hashlib
import http.cookiejar
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.request
import urllib.error

sys.dont_write_bytecode = True

ROOT = Path("/root/nox")
STOP_FILES = (
    ROOT / "STOP", ROOT / "STOP.flag", ROOT / "stop.flag", ROOT / ".stop",
    ROOT / "program/STOP", ROOT / "state/STOP", ROOT / "state/STOP.flag",
    Path("/workspace/NOX_STOP"), ROOT / "state/OWNER_MAINTENANCE.flag",
)
SYNTHETIC = (
    "QA NOX: составь ровно три понятных шага подготовки пустого проекта "
    "Python с README и одним тестом. Не задавай уточняющих вопросов."
)

def output(data):
    print("NOX_MAINT_REPAIR=" + json.dumps({"kind":"chat_policy_live_smoke",
          "data":data},sort_keys=True,separators=(",",":"),ensure_ascii=False,
          allow_nan=False),flush=True)

def source_status():
    # Exact source observed on the owner host; no untrusted script injection.
    path=ROOT/"scripts"/"chat_proxy.py"
    pin="9fedaefbe39f4cac8a47d77bb0dada2ccf09c43ec38a5624869d3a00c0fbe5a3"
    if path.is_symlink() or not path.is_file() or path.stat().st_size>150000:
        raise RuntimeError("HOLD_LIVE_SMOKE_SOURCE_SCOPE")
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    if digest!=pin:
        raise RuntimeError("HOLD_LIVE_SMOKE_SOURCE_PIN")
    return digest

def process_identity(pid):
    try:
        raw=(Path('/proc')/str(pid)/'stat').read_bytes()
        values=raw.rsplit(b') ',1)[1].split()
        if len(raw)>8192 or values[0] in (b'Z',b'X'):
            return None
        return {'pid':pid,'start_ticks':int(values[19])}
    except (OSError,ValueError,IndexError):
        return None

def guards():
    if any(os.path.lexists(p) for p in STOP_FILES):
        raise RuntimeError("HOLD_LIVE_SMOKE_STOP")
    source_status()
    # No second model or browser is launched. Keep a real 512 MiB raw buffer,
    # and require zero PSI/OOM plus a conservative unused file-cache floor.
    cg=Path('/sys/fs/cgroup')
    try:
        maximum=(cg/'memory.max').read_text().strip()
        current=(cg/'memory.current').read_text().strip()
        stats=dict((line.split()[0],int(line.split()[1]))
                   for line in (cg/'memory.stat').read_text().splitlines())
        events=dict((line.split()[0],int(line.split()[1]))
                    for line in (cg/'memory.events').read_text().splitlines())
        pressure=(cg/'memory.pressure').read_text().splitlines()
    except (OSError,IndexError,ValueError):
        raise RuntimeError("HOLD_LIVE_SMOKE_CGROUP_UNKNOWN") from None
    if not maximum.isdigit() or not current.isdigit():
        raise RuntimeError("HOLD_LIVE_SMOKE_CGROUP_UNBOUNDED")
    free=int(maximum)-int(current)
    cold=max(0,min(stats.get('inactive_file',0),
              max(0,stats.get('file',0)-stats.get('shmem',0)))-stats.get('shmem',0))
    # Reclaimable cold page-cache can safely satisfy a single EXISTING model
    # POST with no new model/browser/weights. The low-raw profile needs a larger
    # cold-cache reserve; PSI/OOM and current service/model-slot checks remain.
    normal = free>=512*1024**2 and cold>=4*1024**3
    cold_cache_profile = free>=256*1024**2 and cold>=12*1024**3
    if not (normal or cold_cache_profile):
        raise RuntimeError("HOLD_LIVE_SMOKE_MEMORY")
    if events.get('oom',1)!=0 or events.get('oom_kill',1)!=0:
        raise RuntimeError("HOLD_LIVE_SMOKE_OOM")
    if len(pressure)!=2 or any(
            re.search(r'avg10=0\.00(?:\s|$)',row) is None for row in pressure):
        raise RuntimeError("HOLD_LIVE_SMOKE_PRESSURE")
    names=('nox-proxy','nox-ds41-8098','nox-dispatcher-t855u')
    identities={}
    for name in names:
        p=subprocess.run(['supervisorctl','status',name],text=True,capture_output=True,timeout=7)
        match=re.match(r'^'+re.escape(name)+r'\s+RUNNING\s+pid\s+([0-9]+),',p.stdout.strip())
        if p.returncode!=0 or not match:
            raise RuntimeError("HOLD_LIVE_SMOKE_SERVICES")
        identity=process_identity(int(match.group(1)))
        if identity is None:
            raise RuntimeError("HOLD_LIVE_SMOKE_PID")
        identities[name]=identity
    conn=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with conn.open("http://127.0.0.1:8080/health",timeout=5) as response:
            if response.status!=200:raise RuntimeError("HOLD_LIVE_SMOKE_HEALTH")
            response.read(4097)
    except urllib.error.URLError:
        raise RuntimeError("HOLD_LIVE_SMOKE_PROXY_UNREACHABLE") from None
    if identities!={name:process_identity(row['pid']) for name,row in identities.items()}:
        raise RuntimeError("HOLD_LIVE_SMOKE_PROCESS_CHANGED")
    slots, slot_port = None, None
    for port in (8081,8098):
        try:
            with conn.open("http://127.0.0.1:%d/slots" % port,timeout=5) as response:
                if response.status!=200:continue
                raw=response.read(15001)
            if len(raw)>15000:continue
            candidate=json.loads(raw)
            if not isinstance(candidate,list) or len(candidate)>10 or any(
                    not isinstance(row,dict) for row in candidate):continue
            slots,slot_port=candidate,port
            break
        except (urllib.error.URLError,ValueError):
            continue
    if slots is None:
        raise RuntimeError("HOLD_LIVE_SMOKE_NO_LOCAL_MODEL_SLOTS")
    if any(bool(row.get("is_processing",row.get("processing",False))) for row in slots):
        raise RuntimeError("HOLD_LIVE_SMOKE_MODEL_BUSY")
    return {"stable_services":len(identities),"slots":len(slots),
            "slot_port":slot_port,"source_pin":True,
            "admission_profile":"COLD_CACHE_256M_12G" if not normal else "RAW_512M_4G",
            "raw_headroom_bytes":free,"cold_lower_bound_bytes":cold}

def parse_frame_line(raw):
    """Accept the existing NOX browser SSE data frames or legacy NDJSON."""
    if not isinstance(raw,bytes) or len(raw)>100000:
        raise RuntimeError("HOLD_LIVE_SMOKE_FRAME_LENGTH")
    line=raw.strip()
    if not line or line.startswith((b":",b"event:",b"id:",b"retry:")):
        return None
    if line.startswith(b"data:"):
        line=line[5:].strip()
    if line==b"[DONE]":
        return {"type":"sentinel"}
    try:
        result=json.loads(line)
    except (ValueError,UnicodeError):
        raise RuntimeError("HOLD_LIVE_SMOKE_SSE_JSON") from None
    if not isinstance(result,dict):
        raise RuntimeError("HOLD_LIVE_SMOKE_FRAME")
    return result


def main():
    record={"schema":"NOX_CHAT_POLICY_LIVE_SMOKE_V1","native_source_writes":0,
            "service_restarts":0,"model_loads":0,"raw_content_exported":False,
            "credentials_exported":False,"s03_qa_dialog_may_be_created":False,
            "started_at":time.time(),"status":"PRECHECK"}
    client=None
    try:
        record["precheck"]=guards()
        sys.path.insert(0,str(ROOT/"scripts"))
        import chat_proxy
        password=chat_proxy._read_chat_password()
        if not isinstance(password,str) or len(password)<6:
            raise RuntimeError("HOLD_LIVE_SMOKE_OWNER_PASSWORD")
        jar=http.cookiejar.CookieJar()
        client=urllib.request.build_opener(
            urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(jar))
        from urllib.parse import urljoin
        def call(path,method="GET",value=None,timeout=12):
            raw=None if value is None else json.dumps(value,ensure_ascii=False).encode()
            req=urllib.request.Request("http://127.0.0.1:8080"+path,data=raw,
                      method=method,headers={"Content-Type":"application/json"})
            return client.open(req,timeout=timeout)
        with call("/chat/login","POST",{"password":password}) as login:
            if login.status!=200:
                raise RuntimeError("HOLD_LIVE_SMOKE_LOGIN")
        password=None
        if not any(True for _ in jar):
            raise RuntimeError("HOLD_LIVE_SMOKE_SESSION_COOKIE")
        with call("/chat/session") as session:
            if json.loads(session.read(8192)).get("ok") is not True:
                raise RuntimeError("HOLD_LIVE_SMOKE_SESSION")
        record["session_authenticated"]=True
        # Recheck right before the single model request.
        guards()
        qa_id="nox_policy_qa_"+str(int(time.time()))
        with call("/api/ui/memory/dialogs/create","POST",
                  {"title":"NOX QA "+qa_id,"confirmed":True}) as response:
            dialog=json.loads(response.read(8192))
        did=dialog.get("dialog_id")
        if not isinstance(did,str) or not re.fullmatch(r"[a-f0-9]{32}",did):
            raise RuntimeError("HOLD_LIVE_SMOKE_DIALOG")
        record["s03_qa_dialog_may_be_created"]=True
        start=time.monotonic()
        with call("/api/nox/chat/stream","POST",
                  {"message":SYNTHETIC,"history":[],"task":"general","dialog_id":did},timeout=100) as response:
            if response.status!=200:raise RuntimeError("HOLD_LIVE_SMOKE_HTTP")
            result=""; done=None; deltas=0
            for i,line in enumerate(response):
                if i>=500 or len(line)>100000 or time.monotonic()-start>105:
                    raise RuntimeError("HOLD_LIVE_SMOKE_BUDGET")
                frame=parse_frame_line(line)
                if frame is None:
                    continue
                kind=frame.get("type")
                if kind=="sentinel":
                    break
                if kind=="delta":
                    token=frame.get("text")
                    if not isinstance(token,str):raise RuntimeError("HOLD_LIVE_SMOKE_DELTA")
                    result+=token
                    if len(result)>12000:raise RuntimeError("HOLD_LIVE_SMOKE_RESULT_LENGTH")
                    deltas+=1
                elif kind=="done":
                    done=frame
                    break
                elif kind=="error":
                    raise RuntimeError("HOLD_LIVE_SMOKE_MODEL_ERROR")
        substantive=bool(result.strip() and not re.fullmatch(r"[\s\-\u2013\u2014]+",result))
        bullets=len(re.findall(r"(?m)^\s*(?:\d+[.)]|[-*])\s+",result))
        record.update(delta_count=deltas,chars=len(result),answer_sha256=hashlib.sha256(result.encode()).hexdigest(),
                      substantive=substantive,steps_detected=bullets,asked_question="?" in result,
                      terminal_done=isinstance(done,dict),total_ms=round((time.monotonic()-start)*1000))
        if not substantive or not isinstance(done,dict):
            raise RuntimeError("HOLD_LIVE_SMOKE_NONEMPTY_TERMINAL")
        with call("/api/ui/memory/dialogs/history?dialog_id="+did+"&limit=6") as response:
            history=json.loads(response.read(256000))
        items=history.get("messages",[])
        saved=bool(isinstance(items,list) and len(items)>=2
                   and items[-2].get("content")==SYNTHETIC and items[-1].get("content")==result)
        record["owner_dialog_pair_verified"]=saved
        record["canonical_s03_write_verified"]=False  # not proven by owner-dialog history
        record["model_claimed_s03_integrated_unverified"]=done.get("s03_integrated") is True
        record["canonical_s03_integration_accepted"]=False
        record["s03_integration_status"]="UNVERIFIED"
        record["planning_format_pass"]=bool(bullets>=3 and "?" not in result)
        record["status"]="LIVE_STREAM_OWNER_DIALOG_VERIFIED" if saved else "HOLD_OWNER_DIALOG_HISTORY"
        if not saved:raise RuntimeError("HOLD_LIVE_SMOKE_OWNER_DIALOG")
    except Exception as exc:
        reason=str(exc)
        record["status"]="HOLD_LIVE_SMOKE"
        record["reason"]=reason if re.fullmatch(r"HOLD_[A-Z0-9_]{1,90}",reason) else type(exc).__name__
    finally:
        if client is not None:
            try:
                req=urllib.request.Request("http://127.0.0.1:8080/chat/logout",
                   data=b"{}",method="POST",headers={"Content-Type":"application/json"})
                with client.open(req,timeout=5) as response:response.read(4097)
            except Exception:pass
        record["finished_at"]=time.time()
    output(record)
    okay=record["status"]=="LIVE_STREAM_OWNER_DIALOG_VERIFIED"
    print("NOX_MAINT_REPAIR_COMPLETE="+str(okay).lower(),flush=True)
    return 0 if okay else 2

if __name__=="__main__":
    raise SystemExit(main())
'''
if not SOURCE.startswith("#!/usr/bin/env python3\n"):
    # Source is embedded as an owner-pinned literal, not fetched at runtime.
    raise SystemExit("HOLD_SMOKE_ENTRY_SOURCE")
ast.parse(SOURCE)
env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", CUDA_VISIBLE_DEVICES="")
process = subprocess.run(["/root/nox/venv/bin/python", "-"], input=SOURCE.encode("utf-8"),
                         capture_output=True, timeout=160, env=env)
for line in process.stdout.decode("utf-8", "replace").splitlines():
    if line.startswith("NOX_MAINT_") and len(line) <= 12000:
        print(line, flush=True)
if process.returncode:
    print("NOX_MAINT_SMOKE_CHILD_EXIT=" + str(process.returncode), flush=True)
raise SystemExit(0 if process.returncode == 0 else 2)
