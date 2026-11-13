#!/usr/bin/env python3
"""NOX V37 read-only host/process inventory; never executes supplied commands.

Everything returned is observable telemetry, not proof that a specific model is
trained. No secrets, environment dumps, SSH credentials or private file contents.
"""
from __future__ import annotations
import argparse
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

GPU_QUERY=['index','uuid','name','memory.total','memory.used','utilization.gpu','temperature.gpu']
APP_QUERY=['gpu_uuid','pid','process_name','used_gpu_memory']

def command(args, timeout=10):
    r=subprocess.run(args,capture_output=True,text=True,timeout=timeout,check=False)
    if r.returncode!=0:raise RuntimeError('PROBE_FAILED_'+str(r.returncode))
    return r.stdout

def parse_gpu(text):
    out=[]
    for row in text.strip().splitlines():
        c=[x.strip() for x in row.split(',')]
        if len(c)!=7:raise ValueError('GPU_SHAPE_HOLD')
        try:
            i=int(c[0]);total=int(c[3]);used=int(c[4]);util=int(c[5]);temp=int(c[6])
        except ValueError:raise ValueError('GPU_SENSOR_UNKNOWN')
        if not (0<=i<8 and total>0 and 0<=used<=total and 0<=util<=100 and -10<temp<110):
            raise ValueError('GPU_BOUNDS_HOLD')
        out.append(dict(index=i,uuid=c[1],name=c[2],vram_total_mib=total,
            vram_used_mib=used,vram_free_mib=total-used,compute_util_pct=util,temp_core_c=temp))
    if sorted(x['index'] for x in out)!=[0,1]:raise ValueError('TWO_GPU_EXPECTED_HOLD')
    return sorted(out,key=lambda x:x['index'])

def parse_apps(text):
    out=[]
    for row in text.strip().splitlines():
        c=[x.strip() for x in row.split(',')]
        if len(c)!=4:continue
        try:pid=int(c[1]);mem=int(c[3].replace(' MiB',''))
        except ValueError:continue
        # Process metadata are untrusted, bounded strings, never arguments to a shell.
        if pid>0 and mem>=0:out.append(dict(gpu_uuid=c[0],pid=pid,name=c[2][:160],used_mib=mem))
    return out

def read_mem():
    d={}
    for s in Path('/proc/meminfo').read_text().splitlines():
        k,_,v=s.partition(':');m=re.match(r'\s*(\d+) kB',v)
        if m:d[k]=round(int(m.group(1))/1024,2)
    return {'total_mib':d.get('MemTotal'),'available_mib':d.get('MemAvailable'),
            'used_mib':round(d.get('MemTotal',0)-d.get('MemAvailable',0),2)}

def inventory(workspace):
    result={'schema':'NOX_V37_READ_ONLY_INVENTORY','at_utc':datetime.now(timezone.utc).isoformat(),
            'workspace':str(Path(workspace).resolve()),'claimed_live_training':False,
            'training_receipt':'NOT_READ_FROM_NATIVE_TRAINER'}
    try:result['gpus']=parse_gpu(command(['nvidia-smi','--query-gpu='+','.join(GPU_QUERY),'--format=csv,noheader,nounits']))
    except Exception as e:result['gpu_probe_error']=str(e)[:120];result['gpus']=[]
    try:result['processes']=parse_apps(command(['nvidia-smi','--query-compute-apps='+','.join(APP_QUERY),'--format=csv,noheader,nounits']))
    except Exception:result['processes']=[];result['process_probe_state']='UNAVAILABLE'
    try:result['ram']=read_mem()
    except Exception:result['ram']={'state':'UNKNOWN'}
    try:
        disk=shutil.disk_usage(workspace)
        result['disk']={'total_bytes':disk.total,'used_bytes':disk.used,'free_bytes':disk.free,
                        'free_gb':round(disk.free/1e9,2)}
    except Exception:result['disk']={'state':'UNKNOWN'}
    result['gpu_gap_state']='NO_PROCESS_MAPPING' if not result['processes'] else 'PROCESSES_PRESENT'
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--workspace',default='/workspace');p.add_argument('--out')
    a=p.parse_args();s=json.dumps(inventory(a.workspace),ensure_ascii=False,indent=2)
    if a.out:
        dest=Path(a.out).resolve();dest.parent.mkdir(parents=True,exist_ok=True)
        if dest.exists():raise SystemExit('HOLD_OUTPUT_EXISTS_NO_OVERWRITE')
        dest.write_text(s+'\n',encoding='utf-8')
    else:print(s)
