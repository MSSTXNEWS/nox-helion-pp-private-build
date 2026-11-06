"""NOX FORGE GENESIS V8 / real read-only LOCAL dashboard.

Design mapped to Drive NOX_HELION_DESKTOP_CINEMATIC_V2.html and approved
NOX CONTROL CENTER spec; not the unmodified original HTML.
Bind ONLY to 127.0.0.1; never executes web-origin commands.
"""
from __future__ import annotations
import argparse
import ctypes
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
from datetime import datetime,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.request import urlopen

SCHEMA="NOX-GENESIS-FORGE-V8"
CODE=Path(__file__).resolve().parent
def read_json(path):
    try:
        if path.stat().st_size>2_000_000:return None
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError,UnicodeError,ValueError):return None

def battery():
    if os.name!="nt":return {"percent":None,"on_ac":None}
    class P(ctypes.Structure):
        _fields_=[("ACLineStatus",ctypes.c_byte),("BatteryFlag",ctypes.c_byte),
                  ("BatteryLifePercent",ctypes.c_byte),("SystemStatusFlag",ctypes.c_byte),
                  ("BatteryLifeTime",ctypes.c_uint),("BatteryFullLifeTime",ctypes.c_uint)]
    p=P()
    try:
        if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(p)):
            return {"percent":None,"on_ac":None}
        return {"percent":int(p.BatteryLifePercent) if 0<=p.BatteryLifePercent<=100 else None,
                "on_ac":bool(p.ACLineStatus) if p.ACLineStatus in (0,1) else None}
    except (OSError,AttributeError):return {"percent":None,"on_ac":None}

def temperature():
    try:
        p=subprocess.run(["nvidia-smi","--query-gpu=temperature.gpu",
                          "--format=csv,noheader,nounits"],capture_output=True,text=True,timeout=4,check=True)
        t=int(p.stdout.splitlines()[0].strip())
        return t if 0<=t<=110 else None
    except (ValueError,IndexError,OSError,subprocess.SubprocessError):
        return None

def models():
    try:
        with urlopen("http://127.0.0.1:11434/api/tags",timeout=2) as r:
            result=json.loads(r.read(1_000_000))
        return [{"name":str(x["name"]),"size":x.get("size"),"digest":x.get("digest")}
                for x in result.get("models",[]) if isinstance(x,dict) and x.get("name")]
    except (OSError,ValueError,KeyError,TypeError):return []

def sqlite_stats(path):
    if not path.is_file():return {"available":False}
    try:
        cx=sqlite3.connect("file:"+path.as_posix()+"?mode=ro",uri=True,timeout=2)
        out={"available":True}
        for table in ("memories","skills","nox_behavior_events"):
            if cx.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone():
                out[table]=cx.execute("SELECT COUNT(*) FROM "+table).fetchone()[0]
        cx.close()
        return out
    except (OSError,sqlite3.Error):return {"available":False}

def get_state(root):
    brain=root/"brain"; telemetry=brain/"telemetry"
    genesis=read_json(telemetry/"genesis_status.json") or {}
    cycle=read_json(telemetry/"genesis_live.json") or {}
    training=read_json(telemetry/"training.json") or {}
    receipt=read_json(brain/"RUN_RECEIPT.json") or {}
    catalog=read_json(brain/"MODEL_CATALOG.json") or {}
    worms=read_json(telemetry/"worms.json") or {}
    m=models()
    try:free=shutil.disk_usage(root).free
    except OSError:free=None
    steps=training.get("actual_steps") if isinstance(training.get("actual_steps"),int) else None
    total=training.get("requested_steps") if isinstance(training.get("requested_steps"),int) and training.get("requested_steps")>0 else None
    percent=round(100*steps/total,1) if steps is not None and total else None
    mem=sqlite_stats(root/"soul_gpu"/"soul.sqlite3")
    status={
        "schema":SCHEMA, "updated_utc":datetime.now(timezone.utc).isoformat(),
        "models":m,"disk_free_bytes":free,"battery":battery(),
        "gpu_temperature_c":temperature(),
        "gpu_temperature_source":"NVIDIA_SMI" if temperature() is not None else "UNAVAILABLE",
        "training":{"status":training.get("status","NO_ACTIVE_TRAINING_RECEIPT"),
                    "step":steps,"requested_steps":total,"progress_percent":percent,
                    "loss_metrics":training.get("loss_metrics"),"stage":training.get("stage"),
                    "gpu_temperature_c":training.get("gpu_temperature_c"),
                    "cooldown_seconds":training.get("cooldown_seconds"),
                    "source":"brain/telemetry/training.json"},
        "genesis":genesis,"cycle":cycle,
        "worms":{"planned":worms.get("planned",0),
                 "executed":cycle.get("worm_tasks_run",0),
                 "state":worms.get("status","NOT_INITIALIZED")},
        "memory":mem,"last_runner":receipt.get("status","NOT_RUN"),
        "native_exe_exists":(root/"release"/"NOX.HELION.exe").is_file(),
        "native_s03_verified":False,
        "native_exe_rebuilt":False,
        "stop":{"available":False,"reason":"Original OneHost STOP is not attached to this read-only dashboard"},
        "limits":{"intelligence_gb":70,"memory_gb":70,"skills_gb":70,
                  "free_disk_reserve_gb":60,"pause_at_c":65,"cooling_seconds":180},
        "note":"All counts from local files/services, never from animation or mock data."
    }
    return status

def server(root,port):
    html=(CODE/"forge_genesis_v8.html").read_bytes()
    class H(BaseHTTPRequestHandler):
        def respond(self,body,kind="application/json; charset=utf-8",code=200):
            self.send_response(code)
            self.send_header("Content-Type",kind)
            self.send_header("Content-Length",str(len(body)))
            self.send_header("Cache-Control","no-store")
            self.send_header("X-Content-Type-Options","nosniff")
            self.send_header("Content-Security-Policy","default-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:")
            self.end_headers()
            self.wfile.write(body)
        def do_GET(self):
            if self.path in ("/","/index.html"):
                return self.respond(html,"text/html; charset=utf-8")
            if self.path=="/api/health":
                return self.respond(json.dumps({"schema":SCHEMA,"status":"READY"}).encode())
            if self.path=="/api/status":
                return self.respond(json.dumps(get_state(root),ensure_ascii=False).encode())
            return self.respond(b'{"error":"not found"}',code=404)
        def do_POST(self):
            self.respond(b'{"error":"Read-only dashboard; native STOP unavailable"}',code=403)
        def log_message(self,*args):
            pass
    ThreadingHTTPServer(("127.0.0.1",port),H).serve_forever()

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,required=True)
    p.add_argument("--port",type=int,default=18872)
    a=p.parse_args()
    server(a.root.resolve(),a.port)
