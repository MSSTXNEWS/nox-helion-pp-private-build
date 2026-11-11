#!/usr/bin/env python3
"""NOX Control API / read-only v1. Expose only behind Cloudflare Access.
No command execution from requests; no changes to trainers, STOP, weights or S03.
"""
import datetime as dt
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
import threading
import time

HOST = "127.0.0.1"
PORT = 18796
NODE = os.environ.get("NOX_CONTROL_NODE", "")
VALID_NODES = {"runpod-5f3j8hwyicc0bp", "vast-60254538"}
MAX_BODY = 8192
LOCK = threading.BoundedSemaphore(4)
MAX_PATH_SCAN = 2000

def read_gpu():
    try:
        proc = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total,power.draw",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
            env={"PATH": "/usr/local/cuda/bin:/usr/local/bin:/usr/bin:/bin", "LC_ALL": "C"},
        )
        if proc.returncode:
            return {"status": "HOLD_GPU", "exit": proc.returncode}
        rows = []
        for line in proc.stdout.strip().splitlines()[:4]:
            fields = [part.strip() for part in line.split(",")]
            if len(fields) != 6:
                return {"status": "HOLD_GPU_PARSE"}
            name, *values = fields
            if len(name)>80 or not all(x.replace(".", "", 1).isdigit() or x == "[Not Supported]" for x in values):
                return {"status": "HOLD_GPU_PARSE"}
            rows.append({"name": name, "temperature_c": values[0], "utilization_percent": values[1],
                         "vram_used_mib": values[2], "vram_total_mib": values[3], "power_w": values[4]})
        return {"status": "MEASURED" if rows else "HOLD_GPU_EMPTY", "gpus": rows}
    except (OSError, subprocess.TimeoutExpired):
        return {"status": "HOLD_GPU"}

def read_disk():
    out = {}
    for name in ("/", "/workspace", "/root/nox"):
        try:
            s = os.statvfs(name)
            out[name] = {"free_gib": round(s.f_bavail*s.f_frsize/1073741824,2),
                         "total_gib": round(s.f_blocks*s.f_frsize/1073741824,2)}
        except OSError:
            out[name] = {"status":"UNAVAILABLE"}
    return out

def read_processes():
    names = ("train_n36.py","learner.py","chat_proxy.py","watchdog_n36_v2.sh")
    result = {name:0 for name in names}
    for p in Path("/proc").iterdir():
        if not p.name.isdecimal(): continue
        try:
            args = (p/"cmdline").read_bytes().split(b"\0")
            tokens = [part.decode("utf-8","replace").rsplit("/",1)[-1] for part in args if part]
            for name in names:
                if name in tokens: result[name]+=1
        except (OSError, PermissionError):
            continue
    return result

def read_checkpoints():
    roots = (Path("/tmp/nox36/ckpt"), Path("/root/nox36/ckpt"), Path("/workspace/nox36/ckpt"))
    counts = {}
    for root in roots:
        count = 0
        if root.is_dir():
            try:
                for i,p in enumerate(root.rglob("*")):
                    if i >= MAX_PATH_SCAN: break
                    if p.is_file() and p.suffix in (".safetensors",".pt",".ckpt"): count += 1
            except OSError:
                pass
        counts[str(root)]={"files":count,"sha_verified":False}
    return counts

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass
    def do_GET(self):
        if self.client_address[0] not in ("127.0.0.1","::1"):
            self.send_error(403); return
        route = self.path.split("?",1)[0]
        routes = {
            "/v1/health":lambda: {"node":NODE,"state":"READ_ONLY","utc":dt.datetime.now(dt.timezone.utc).isoformat()},
            "/v1/gpu":read_gpu,
            "/v1/disk":read_disk,
            "/v1/processes":read_processes,
            "/v1/checkpoints":read_checkpoints
        }
        if route not in routes:
            self.send_error(404); return
        if not LOCK.acquire(blocking=False):
            self.send_error(429); return
        try:
            result = routes[route]()
            data = json.dumps(result,ensure_ascii=False).encode()
            if len(data)>MAX_BODY:
                self.send_error(413); return
            self.send_response(200)
            self.send_header("Content-Type","application/json; charset=utf-8")
            self.send_header("Cache-Control","no-store")
            self.send_header("X-Content-Type-Options","nosniff")
            self.send_header("Content-Length",str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        finally:
            LOCK.release()
    def do_POST(self): self.send_error(405)
    def do_PUT(self): self.send_error(405)
    def do_DELETE(self): self.send_error(405)

if __name__=="__main__":
    if NODE not in VALID_NODES: raise SystemExit("HOLD_NODE_ID")
    server=ThreadingHTTPServer((HOST,PORT),Handler)
    server.daemon_threads=True
    print("NOX_CONTROL_READONLY_LISTEN", HOST, PORT, NODE, flush=True)
    server.serve_forever()
