#!/usr/bin/env python3
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
    pins = {
        "slim_chat_t885u.py":"82412dcfb1868c1ce8cfc9f4a0df22054dec16784e9e43d349901fec7ef1f227",
        "common.py":"177fbe5df042ba75a94cf9b7c03c8ffe58bde99f12599193db0cf383cc1305dd",
        "chat_proxy.py":"cc1437ce8c3bfbbc4259ffdbe299bf3b8721d4b1bb09c88565ccb6cb9fdb95eb",
    }
    for name,wanted in pins.items():
        path=ROOT/"scripts"/name
        if path.is_symlink() or not path.is_file() or path.stat().st_size>150000:
            raise RuntimeError("HOLD_LIVE_SMOKE_SOURCE_SCOPE")
        if hashlib.sha256(path.read_bytes()).hexdigest()!=wanted:
            raise RuntimeError("HOLD_LIVE_SMOKE_SOURCE_PIN")
    return True

def process_same(pid, ticks):
    try:
        raw=(Path("/proc")/str(pid)/"stat").read_bytes()
        fields=raw.rsplit(b") ",1)[1].split()
        return len(raw)<=8192 and fields[0] not in (b"Z",b"X") and int(fields[19])==ticks
    except (OSError,ValueError,IndexError):
        return False

def guards():
    if any(os.path.lexists(p) for p in STOP_FILES):
        raise RuntimeError("HOLD_LIVE_SMOKE_STOP")
    if not source_status():
        raise RuntimeError("HOLD_LIVE_SMOKE_SOURCE")
    stable=((106058,181620214),(106174,181621423),(106175,181621423),
            (106176,181621423),(3266857,172046662),(242298,183262723))
    if not all(process_same(*item) for item in stable):
        raise RuntimeError("HOLD_LIVE_SMOKE_PROCESS_CHANGE")
    r=subprocess.run(["supervisorctl","status","nox-proxy","nox-ds41-8098",
                      "nox-dispatcher-t855u"],text=True,capture_output=True,timeout=7)
    if r.returncode or len(r.stdout)>4000 or len(re.findall(r"\sRUNNING\s",r.stdout))!=3:
        raise RuntimeError("HOLD_LIVE_SMOKE_SERVICES")
    conn=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with conn.open("http://127.0.0.1:8080/health",timeout=5) as response:
            if response.status!=200:raise RuntimeError("HOLD_LIVE_SMOKE_HEALTH")
            response.read(4097)
    except urllib.error.URLError:
        raise RuntimeError("HOLD_LIVE_SMOKE_PROXY_UNREACHABLE") from None
    slots, slot_port = None, None
    # Both are existing owner-observed local inference endpoints. Do not start a
    # model or choose an external host when the legacy llama port is unavailable.
    for port in (8081, 8098):
        try:
            with conn.open("http://127.0.0.1:%d/slots" % port,timeout=5) as response:
                if response.status!=200:
                    continue
                raw=response.read(15001)
            if len(raw)>15000:
                continue
            candidate=json.loads(raw)
            if not isinstance(candidate,list) or len(candidate)>10 or any(
                    not isinstance(row,dict) for row in candidate):
                continue
            slots, slot_port = candidate, port
            break
        except (urllib.error.URLError,ValueError):
            continue
    if slots is None:
        raise RuntimeError("HOLD_LIVE_SMOKE_NO_LOCAL_MODEL_SLOTS")
    if any(bool(row.get("is_processing",row.get("processing",False))) for row in slots):
        raise RuntimeError("HOLD_LIVE_SMOKE_MODEL_BUSY")
    return {"stable_pids":6,"slots":len(slots),"slot_port":slot_port,"source_pins":3}

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
                frame=json.loads(line)
                if not isinstance(frame,dict):raise RuntimeError("HOLD_LIVE_SMOKE_FRAME")
                kind=frame.get("type")
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
        saved=bool(done.get("saved") is True and done.get("s03_integrated") is True
                   and isinstance(items,list) and len(items)>=2
                   and items[-2].get("content")==SYNTHETIC and items[-1].get("content")==result)
        record["saved_verified"]=saved
        record["planning_format_pass"]=bool(bullets>=3 and "?" not in result)
        record["status"]="LIVE_SMOKE_S03_VERIFIED" if saved else "HOLD_S03_UNVERIFIED"
        if not saved:raise RuntimeError("HOLD_LIVE_SMOKE_S03")
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
    okay=record["status"]=="LIVE_SMOKE_S03_VERIFIED"
    print("NOX_MAINT_REPAIR_COMPLETE="+str(okay).lower(),flush=True)
    return 0 if okay else 2

if __name__=="__main__":
    raise SystemExit(main())
