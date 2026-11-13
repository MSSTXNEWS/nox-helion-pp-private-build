#!/usr/bin/env python3
"""V37 continual NOX control monitor: bounded telemetry and safe job proposals.

This is NOT a competing training scheduler: it never spawns a GPU worker,
changes active checkpoints or stops a process. Existing OneHost/FORGE must own
any actual job. `--loop` runs until SIGINT/SIGTERM or the host-owned STOP flag.
"""
from __future__ import annotations
import argparse,json,os,signal,time
from pathlib import Path
from .live_inventory import inventory
from .admission import admission

TASK_ORDER=('PROTECT_EXISTING_RUNNING_TRAINER','EXTERNAL_CHECKPOINT_BACKUP',
            'GGUF_VERIFY_SHA','GPU0_TEACHER_EVAL_IF_APPROVED','NOX_S03_MEMORY_EVAL',
            'SELF_BUILDER_PR_SANDBOX','REAL_UI_SERVER_PANEL',
            'MULTIMODAL_IMAGE_BENCH','VIDEO_SINGLE_MODEL_BENCH')

def propose(probe, *, live_receipts=None):
    rec=live_receipts or {}
    if not rec.get('optimizer_jobs_live_verified'):
        active='UNKNOWN_DO_NOT_RESTART'
    else:active='PRESERVE_EXISTING_TRAINER_NO_INTERRUPTION'
    gpus=probe.get('gpus') or []
    by_index={g.get('index'):g for g in gpus}
    resource=[]
    for i in (0,1):
        g=by_index.get(i)
        if not g:resource.append({'gpu':i,'state':'HOLD_MISSING_TELEMETRY'});continue
        compute=g.get('compute_util_pct')
        r={'gpu':i,'compute_util_pct':compute,'vram_free_mib':g.get('vram_free_mib'),
           'state':'RUNNING_OR_RESERVED' if compute is not None and compute>=80 else 'CANDIDATE_FOR_NEXT_APPROVED_JOB'}
        if g.get('vram_free_mib',0)<4096:r['state']='HOLD_TOO_LITTLE_FREE_VRAM'
        resource.append(r)
    return {'schema':'NOX_V37_NATIVE_JOB_PROPOSAL','existing_training':active,
        'priority':TASK_ORDER,'per_gpu':resource,
        'real_optimizer_steps':'UNKNOWN_UNTIL_NATIVE_CHECKPOINT_RECEIPTS',
        'actual_gpu_job_launched':False,
        'next':'USE_EXISTING_ONEHOST_CALLBACKS_TO_APPROVE_AND_RUN; DO_NOT_DUPLICATE_TRAINERS'}

class LogWriter:
    def __init__(self,path,max_bytes=10_000_000):
        self.path=Path(path);self.max_bytes=max_bytes
    def write(self,row):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        if self.path.exists() and self.path.stat().st_size>self.max_bytes:
            raise RuntimeError('TELEMETRY_LOG_CAP_HOLD_NO_DELETION')
        with self.path.open('a',encoding='utf8') as f:
            f.write(json.dumps(row,ensure_ascii=False,separators=(',',':'))+'\n')
            f.flush()

def main():
    p=argparse.ArgumentParser();p.add_argument('--workspace',default='/workspace')
    p.add_argument('--loop',action='store_true');p.add_argument('--interval',type=int,default=30)
    p.add_argument('--log');p.add_argument('--stop-flag')
    a=p.parse_args()
    if not 10<=a.interval<=600:raise SystemExit('INTERVAL_BOUNDS_10_600')
    stopped=False
    def handle(*_):
        nonlocal stopped;stopped=True
    signal.signal(signal.SIGINT,handle);signal.signal(signal.SIGTERM,handle)
    writer=LogWriter(a.log) if a.log else None
    while not stopped:
        if a.stop_flag and Path(a.stop_flag).exists():break
        try:
            row={'inventory':inventory(a.workspace)}
            row['proposal']=propose(row['inventory'])
        except Exception as e:
            row={'state':'HOLD_TELEMETRY','error':type(e).__name__}
        if writer:writer.write(row)
        else:print(json.dumps(row,ensure_ascii=False,indent=2),flush=True)
        if not a.loop:break
        time.sleep(a.interval)

if __name__=='__main__':main()
