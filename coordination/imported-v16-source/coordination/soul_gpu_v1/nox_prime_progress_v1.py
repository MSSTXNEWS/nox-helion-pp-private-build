"""NOX PRIME live progress journal, read by the EXISTING FORGE dashboard.

Only real state changes and real GPU step records. Not a scheduler/trainer,
not an additional server, not a second memory/S03 database. Fail closed on
unreadable telemetry instead of inventing percentages or success.
"""
from __future__ import annotations
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import re
import threading

PHASES=("DISCOVER","DOWNLOAD","TEACHER_DISTILL","DATASET_PREP",
        "SOUL_TRAIN","GPU_TRAIN","EVALUATE","INTEGRATE","READY","HOLD")
MAX_EVENTS=80
_ALLOWED_STATUSES=("START","RUNNING","SAVED","PASS","HOLD","FAILED","DONE")
_LOCK=threading.Lock()
_STEP=re.compile(r"^step-[0-9]{4,8}$")

def _journal(root):
    return Path(root)/"brain"/"telemetry"/"prime_pipeline.jsonl"

def log_event(root,phase,status,detail,actual=None,total=None,artifact=None):
    """Source event, not progress theater. No synthetic counts or estimated success."""
    if phase not in PHASES or status not in _ALLOWED_STATUSES:
        raise ValueError("INVALID_PHASE_OR_STATUS")
    if not isinstance(detail,str) or not detail:
        raise ValueError("MISSING_REAL_EVENT_DESCRIPTION")
    if actual is not None and (type(actual) is not int or actual<0):
        raise ValueError("INVALID_ACTUAL")
    if total is not None and (type(total) is not int or total<1):
        raise ValueError("INVALID_TOTAL")
    if actual is not None and total is not None and actual>total:
        raise ValueError("PROGRESS_EXCEEDS_TOTAL")
    event={"at_utc":datetime.now(timezone.utc).isoformat(),
           "phase":phase,"status":status,"detail":detail[:190]}
    if actual is not None:event["actual"]=actual
    if total is not None:event["total"]=total
    if artifact is not None:
        # An artifact is only a bounded relative tag, never expose arbitrary paths.
        if not isinstance(artifact,str) or not re.fullmatch(r"[a-zA-Z0-9_.-]{1,80}",artifact):
            raise ValueError("INVALID_ARTIFACT_TAG")
        event["artifact"]=artifact
    p=_journal(root)
    p.parent.mkdir(parents=True,exist_ok=True)
    with _LOCK:
        with p.open("a",encoding="utf-8",newline="\n") as f:
            f.write(json.dumps(event,ensure_ascii=False)+"\n")
            f.flush()
            os.fsync(f.fileno())
    return event

def _tail(path,max_bytes=120_000):
    if not path.is_file() or path.is_symlink():
        return []
    with path.open("rb") as f:
        f.seek(0,os.SEEK_END)
        size=f.tell()
        f.seek(max(0,size-max_bytes))
        if size>max_bytes:f.readline()
        return f.read(max_bytes).splitlines()

def _read_events(root):
    result=[]
    for raw in _tail(_journal(root)):
        try:
            evt=json.loads(raw)
            if not isinstance(evt,dict) or evt.get("phase") not in PHASES or evt.get("status") not in _ALLOWED_STATUSES:continue
            safe={"at_utc":str(evt.get("at_utc") or "")[:48],
                  "phase":evt["phase"],"status":evt["status"],
                  "detail":str(evt.get("detail") or "")[:190]}
            for k in ("actual","total"):
                if type(evt.get(k)) is int and 0<=evt[k]<=1_000_000:
                    safe[k]=evt[k]
            result.append(safe)
        except (ValueError,TypeError,UnicodeError):pass
    return result[-MAX_EVENTS:]

def _read_gpu_steps(root):
    """Parses only actual worker JSON lines from bounded recent adapter logs."""
    base=Path(root)/"brain"/"intelligence"/"adapters"
    if not base.is_dir():return []
    dirs=[]
    for run in base.iterdir():
        if not run.is_dir() or run.is_symlink() or not run.name.startswith(("NOX_RESUME_","NOX_GPU_","GPU_","SAFE65_")):continue
        p=run/"training.log"
        if p.is_file() and not p.is_symlink():
            try:dirs.append((p.stat().st_mtime,p))
            except OSError:pass
    dirs.sort(reverse=True)
    steps={}
    for _,log in dirs[:4]:
        for raw in _tail(log,64_000):
            try:
                event=json.loads(raw)
                step=event.get("step")
                loss=event.get("loss")
                if type(step) is not int or not 0<step<=10_000_000:continue
                if not isinstance(loss,(int,float)) or not -1e8<float(loss)<1e8:continue
                steps[step]={"step":step,"loss":round(float(loss),6),"device":str(event.get("device") or "unknown")[:30]}
            except (ValueError,TypeError,UnicodeError,AttributeError):pass
    return [steps[k] for k in sorted(steps)[-30:]]

def read_progress(root):
    events=_read_events(root)
    steps=_read_gpu_steps(root)
    # Dashboard records the real known checkpoint only when a file is present.
    return {
      "schema":"NOX_PRIME_PROGRESS_V1",
      "events":events[-40:],
      "current":events[-1] if events else None,
      "actual_gpu_steps":steps,
      "last_gpu_step":steps[-1] if steps else None,
      "event_count_visible":len(events),
      "gpu_step_count_visible":len(steps),
      "training_source":"LOCAL_WORKER_LOG_NOT_SIMULATED",
      "source":"NOX_EXISTING_BRAIN_TELEMETRY",
      "s03_written":False
    }
if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=Path(r"C:\NOX_HELION\NOX_NEW"))
    p.add_argument("--phase",choices=PHASES)
    p.add_argument("--status",choices=_ALLOWED_STATUSES)
    p.add_argument("--detail")
    p.add_argument("--actual",type=int)
    p.add_argument("--total",type=int)
    a=p.parse_args()
    if a.phase:
        print(json.dumps(log_event(a.root,a.phase,a.status,a.detail,
                    actual=a.actual,total=a.total),ensure_ascii=False))
    else:
        print(json.dumps(read_progress(a.root),ensure_ascii=False,indent=2))
