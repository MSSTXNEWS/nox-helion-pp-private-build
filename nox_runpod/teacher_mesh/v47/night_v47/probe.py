#!/usr/bin/env python3
"""Read-only Vast/GPU trainer inventory. Safe on a real host or offline desktop.
No install, restart, key reading, or model load. Unknown values are UNKNOWN.
"""
import datetime as dt
import importlib.metadata as im
import json, os, shutil, subprocess, sys
from pathlib import Path

def run(argv, timeout=8):
    try:
        r=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
                        timeout=timeout,check=False)
        return {'returncode':r.returncode,'stdout':r.stdout[:12000], 'stderr':r.stderr[:1200]}
    except (OSError,subprocess.TimeoutExpired) as exc:
        return {'error':type(exc).__name__}

def versions():
    packages=['torch','transformers','accelerate','deepspeed','safetensors',
              'numpy','trl','peft','bitsandbytes','psutil','huggingface-hub']
    d={}
    for n in packages:
        try:d[n]=im.version(n)
        except im.PackageNotFoundError:d[n]='NOT_INSTALLED'
    return d

def collect():
    out={'schema':'NOX_V47_READONLY_PROBE','observed_at':dt.datetime.now(dt.timezone.utc).isoformat(),
         'host_mutated':False,'source':'UNAUTHENTICATED_LOCAL_READONLY_PROBE',
         'python':sys.version.split()[0],'packages':versions(),
         'nvidia_smi':run(['nvidia-smi','--query-gpu=index,name,compute_cap,memory.total,memory.used,memory.free,utilization.gpu,driver_version', '--format=csv,noheader,nounits']),
         'nvidia_processes':run(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,used_gpu_memory','--format=csv,noheader,nounits']),
         'nvcc':run(['nvcc','--version'])}
    for p in ('/workspace','/opt','/tmp'):
        try:
            s=shutil.disk_usage(p)
            out['disk_'+p]={'free_bytes':s.free,'total_bytes':s.total}
        except OSError:out['disk_'+p]='UNAVAILABLE'
    try:
        meminfo=Path('/proc/meminfo').read_text()
        out['memavailable_kib']=int(next(ln.split()[1] for ln in meminfo.splitlines() if ln.startswith('MemAvailable:')))
    except (OSError,ValueError,StopIteration):out['memavailable_kib']='UNAVAILABLE'
    return out
if __name__=='__main__':
    print(json.dumps(collect(),ensure_ascii=False,indent=2))
