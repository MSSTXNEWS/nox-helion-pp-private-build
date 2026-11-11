#!/usr/bin/env python3
"""Retire ONLY old CPU-only new-A40 controller and its known inference children.
No Pod restart; refuse cutover if GPU owns compute or process identity unknown.
"""
import os,pathlib,signal,subprocess,time
OLD="/workspace/nox/dispatcher/nox_a40new/bin/nox_a40new_teacher_controller.py"
OLD_BATCH="/workspace/nox/dispatcher/nox_a40new/bin/nox_teacher_server_batch.py"
OLD_CPU="/workspace/nox/tools/llama.cpp/build/bin/llama-server"
def procs():
 out=[]
 for entry in pathlib.Path("/proc").iterdir():
  if not entry.name.isdigit():continue
  try:
   args=[x.decode(errors="replace") for x in (entry/"cmdline").read_bytes().split(b"\0") if x]
   if not args:continue
   out.append((int(entry.name),args))
  except OSError:pass
 return out
def matches(args):
 return OLD in args or OLD_BATCH in args or (OLD_CPU in args and "--port" in args and
               args[args.index("--port")+1:][:1]==["18931"])
def main():
 p=subprocess.run(["nvidia-smi","--query-compute-apps=pid","--format=csv,noheader,nounits"],
     capture_output=True,text=True,timeout=10)
 if p.returncode!=0:raise SystemExit("HOLD_CUTOVER_GPU_QUERY_FAILED")
 owners={int(x) for x in p.stdout.splitlines() if x.strip().isdigit()}
 if owners:
  print("HOLD_ACTIVE_GPU_OWNERS",sorted(owners));return 2
 old=[(pid,args) for pid,args in procs() if matches(args)]
 if not old:
  print("CPU_ONLY_LEGACY_ABSENT");return 0
 # The in-flight CPU examples may not be complete; persist old JSONL before stopping.
 for pid,args in old:
  try:os.kill(pid,signal.SIGTERM)
  except ProcessLookupError:pass
 for _ in range(50):
  remain=[pid for pid,args in procs() if matches(args)]
  if not remain:
   print("CPU_ONLY_LEGACY_STOPPED_FOR_CUDA_UPGRADE",len(old));return 0
  time.sleep(.2)
 print("HOLD_CPU_ONLY_LEGACY_STILL_RUNNING",remain)
 return 2
if __name__=="__main__":raise SystemExit(main())
