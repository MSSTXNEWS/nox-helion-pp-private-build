#!/usr/bin/env python3
"""NOX SAFE70 GPU watcher. Measures NVIDIA GPU temperature, not Windows AMD Hot Spot.

Three consecutive >=70 C => persistent STOP; unreadable sensor => HOLD.
Does not kill an in-flight trainer. The supervisor blocks new cycles and a
running trainer must implement a checkpoint-aware STOP at a safe point.
"""
import argparse,datetime,json,os,pathlib,subprocess,sys,time
R=pathlib.Path("/workspace/nox")
S=R/"dispatcher/nox_v3"
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def atomic(path,obj):
 path.parent.mkdir(parents=True,exist_ok=True)
 tmp=path.with_suffix(".tmp")
 with tmp.open("w") as f:
  json.dump(obj,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
 os.replace(tmp,path)
def measure():
 try:
  p=subprocess.run(["nvidia-smi","--query-gpu=temperature.gpu,utilization.gpu,memory.used,memory.free",
    "--format=csv,noheader,nounits"],capture_output=True,text=True,timeout=8)
  if p.returncode!=0:return None
  row=p.stdout.splitlines()[0].split(",")
  if len(row)<4:return None
  values=[float(t.strip()) for t in row[:4]]
  if values[0]<=0 or values[0]>120:return None
  return {"temperature_c":values[0],"utilization_pct":values[1],
          "vram_used_mib":values[2],"vram_free_mib":values[3]}
 except (ValueError,IndexError,OSError,subprocess.TimeoutExpired):return None
def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("--node",choices=("A40","A5000"),required=True)
 ap.add_argument("--once",action="store_true")
 args=ap.parse_args()
 S.mkdir(parents=True,exist_ok=True)
 consecutive=0
 while True:
  m=measure()
  if m is None:
   state="HOLD_SENSOR_MISSING"
   (S/("HOLD_"+args.node)).touch()
  else:
   consecutive=consecutive+1 if m["temperature_c"]>=70 else 0
   state="STOP_SAFE70" if consecutive>=3 else ("WARN_HEAT" if consecutive else "SAFE")
   if consecutive>=3:
    (S/("STOP_"+args.node)).touch()
    (S/("HOLD_"+args.node)).touch()
   # Deliberately do not auto-clear either STOP or HOLD: require reviewed resume.
  atomic(S/("safe70_"+args.node+".json"),{"utc":utc(),"node":args.node,
       "sensor":"NVIDIA_CORE_NOT_AMD_HOTSPOT","state":state,
       "consecutive_over_70":consecutive,"observed":m,"threshold_c":70})
  print("NOX_SAFE70",args.node,state,m,flush=True)
  if args.once:break
  time.sleep(20)
if __name__=="__main__":main()
