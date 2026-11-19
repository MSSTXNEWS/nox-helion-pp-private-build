#!/usr/bin/env python3
"""Owner-only correction NORMAL=3, FORSAZH=6 to an already-staged V15 mode intent.

Does not start processes or release NOX's MODEL_UPDATE/STOP. It only updates the
private owner intent under a pinned old SHA with exact-readback and rollback.
"""
from __future__ import annotations
import fcntl, hashlib, json, os, re, stat, subprocess, tempfile
from pathlib import Path

ROOT=Path("/root/nox")
STATE=ROOT/"state"
TARGET=STATE/"owner_autonomy_mode_v15.json"
LOCK=STATE/"owner_maintenance.lock"
SCHEMA="NOX_OWNER_MODE_INTENT_V15"
OLD_SHA="98e6c11d26d86c012a20aa823fb4407262b171ab92bd8d1e30f047274cfdc5c4"
SHA40=re.compile(r"^[a-f0-9]{40}$")
NOX_SERVICES=("nox-dispatcher-t855u","nox-chat-8081","nox-priority-scheduler","nox-selfheal")

class OwnerHold(RuntimeError):pass
def require(ok,code):
    if not ok:raise OwnerHold("HOLD_V16_"+code)
def checksum(blob):return hashlib.sha256(blob).hexdigest()
def safe_path(p):
    require(p.is_absolute(),"PATH")
    require(not any(q.is_symlink() for q in (p,*p.parents)),"PATH_SYMLINK")
def read_owned(p):
    safe_path(p)
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        a=os.fstat(fd)
        require(stat.S_ISREG(a.st_mode) and a.st_uid==os.geteuid()
                and a.st_size<=16384 and a.st_nlink==1
                and not (stat.S_IMODE(a.st_mode)&0o077),"FILE_IDENTITY")
        b=os.read(fd,16385);c=os.fstat(fd)
        require(len(b)==a.st_size and (a.st_ino,a.st_mtime_ns,a.st_size)==(c.st_ino,c.st_mtime_ns,c.st_size),"RACE")
        return b
    finally:os.close(fd)
def services_stopped():
    for name in NOX_SERVICES:
        p=subprocess.run(["supervisorctl","status",name],capture_output=True,text=True,timeout=10,shell=False)
        chunks=p.stdout.split()
        require(len(chunks)>=2 and chunks[0]==name and chunks[1] in ("STOPPED","FATAL","EXITED"),"SERVICE_ACTIVE")
def check_stop():
    for flag in (ROOT/"STOP",STATE/"OWNER_MAINTENANCE.flag"):
        safe_path(flag)
        s=flag.stat(follow_symlinks=False)
        require(stat.S_ISREG(s.st_mode) and s.st_uid==os.geteuid(),"STOP_NOT_VERIFIED")
    services_stopped()
def create_no_clobber(p,b):
    safe_path(p)
    fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,"wb") as f:f.write(b);f.flush();os.fsync(f.fileno())
def replace_atomic(p,b):
    fd,temp=tempfile.mkstemp(prefix=".mode-v16-",dir=p.parent)
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,"wb") as f:f.write(b);f.flush();os.fsync(f.fileno())
        os.replace(temp,p)
        with os.fdopen(os.open(p.parent,os.O_RDONLY|os.O_DIRECTORY),"rb") as d:os.fsync(d.fileno())
    finally:
        if os.path.exists(temp):os.unlink(temp)
def main():
    request=os.getenv("NOX_OWNER_REQUEST_ID","")
    sha=os.getenv("NOX_OWNER_SOURCE_SHA","")
    require(os.geteuid()==0 and request.isdigit() and SHA40.fullmatch(sha or ""),"OWNER_CONTEXT")
    require(ROOT.is_dir() and STATE.is_dir(),"ORIGINAL_HOST")
    check_stop()
    safe_path(LOCK)
    fd=os.open(LOCK,os.O_RDWR|os.O_NOFOLLOW)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        blob=read_owned(TARGET)
        value=json.loads(blob)
        require(value.get("schema")==SCHEMA and value.get("instance")==60509551
                and value.get("selected")=="FORSAZH"
                and value.get("mode_workers",{}).get("FORSAZH")==6
                and value.get("production_processes_started") is False
                and value.get("native_binding_active_verified") is False,"MODE_INTENT_SCOPE")
        if value.get("mode_workers",{}).get("NORMAL")==3:
            result={"state":"ALREADY_NORMAL_3_FORSAZH_6","sha256":checksum(blob)}
        else:
            require(value["mode_workers"].get("NORMAL")==2 and checksum(blob)==OLD_SHA,"PINNED_MODE_PREIMAGE")
            before=value["mode_workers"].copy()
            value["mode_workers"]={"NORMAL":3,"FORSAZH":6}
            value["owner_corrected_request"]=request
            value["owner_corrected_source"]=sha
            value["correction"]="NORMAL 3 + NOX coordinator, FORSAZH 6 + NOX coordinator; no process activation"
            output=(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False)+"\n").encode()
            backup=TARGET.with_suffix(".v15-source-2.bak")
            require(not backup.exists() and not backup.is_symlink(),"BACKUP_ALREADY_EXISTS")
            create_no_clobber(backup,blob)
            require(read_owned(TARGET)==blob,"PRE_COMMIT_DRIFT")
            check_stop()
            replace_atomic(TARGET,output)
            require(read_owned(TARGET)==output,"READBACK_MISMATCH")
            result={"state":"NORMAL_3_FORSAZH_6_STAGED_UNDER_STOP",
                "before":before,"after":value["mode_workers"],
                "previous_sha256":checksum(blob),"sha256":checksum(output),
                "backup_sha256":checksum(read_owned(backup))}
        check_stop()
        result.update(kind="nox_autonomy_owner_mode_correct_v16",selected="FORSAZH",
                      real_workers_started=0,stop_preserved=True,live_binding_verified=False)
        print("NOX_MAINT_REPAIR="+json.dumps(result,sort_keys=True),flush=True)
        print("NOX_MAINT_REPAIR_COMPLETE=true",flush=True)
        return 0
    finally:os.close(fd)
if __name__=="__main__":
    try:raise SystemExit(main())
    except Exception as e:
        print("NOX_MAINT_REPAIR="+json.dumps({"kind":"nox_autonomy_owner_mode_correct_v16",
               "state":"HOLD","reason":str(e) if isinstance(e,OwnerHold) else type(e).__name__,
               "workers_claimed":0}),flush=True)
        raise SystemExit(2)
