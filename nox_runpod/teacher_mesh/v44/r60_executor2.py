"""Executor #2's 30 R60 tasks for the EXISTING OneHost master queue.

No duplicate scheduler, no invented native task_id/job_id, no GPU spawning.
Source IDs remain distinct from the runtime OneHost job receipts.
"""
from __future__ import annotations
from collections.abc import Mapping, Callable
import re

SPECS = {
  21:'Diagnose train_error at optimizer step 0',
  22:'Verify real optimizer, trainable parameters and state',
  23:'Verify teacher manifest, SHA, tokenizer and licenses',
  24:'Prepare source-disjoint train/dev/holdout',
  25:'Deduplicate approved distillation corpus',
  26:'Sequence-level distillation: DeepSeek teacher',
  27:'Sequence-level distillation: Qwen teacher',
  28:'Sequence-level distillation: Coder teacher',
  29:'Prove changed student weight SHA after actual steps',
  30:'Checkpoint optimizer, reload, independent exam',
  31:'Planning independent benchmark and error mining',
  32:'Reasoning quality benchmark',
  33:'Math independent benchmark',
  34:'Russian and Spanish independent benchmark',
  35:'Research grounded source QA',
  36:'Real code development tests',
  37:'Native tool execution and explicit owner grants',
  38:'Verified error correction and regression',
  39:'Skill Memory read/write/readback in S03',
  40:'Reflection and DREAM on verified facts only',
  51:'Native STOP and revoke test',
  52:'Independent per-GPU SAFE telemetry',
  53:'Telemetry PID VRAM utilization and latency',
  54:'Offsite checkpoint and S03 backup',
  55:'Full checkpoint and S03 restore drill',
  56:'Fixed-source benchmark before and after',
  57:'Regression holdout and retention check',
  58:'GitHub CI source and targeted tests',
  59:'Verified model rollback without chat interruption',
  60:'Publish only native verified progress receipts',
}


def prepared_tasks():
    out=[]
    for i,label in SPECS.items():
        resource=('GPU1_FORGE' if 21<=i<=30 else 'CPU_OR_ADMITTED_GPU' if 31<=i<=40
                  else 'NATIVE_QA')
        out.append({'task_id':f'R60-{i:03d}', 'title':label,
                    'owner':'EXECUTOR_02','scheduler':'EXISTING_NOX_ONEHOST',
                    'resource':resource,'status':'PREPARED_NOT_ENQUEUED',
                    'job_id':None,'native_receipt_sha256':None,
                    'production_verified':False})
    return out


def merge_without_overwrite(existing: Mapping, *, get_native_task: Callable[[str],Mapping]|None=None):
    """Merge a supplied live master snapshot without overwriting Executor #1 or receipts.
    Does not claim it saved into OneHost. Caller must use native CAS and readback.
    """
    if not isinstance(existing,Mapping) or not isinstance(existing.get('tasks'),list):
        return {'state':'HOLD_MASTER_MISSING','write_performed':False}
    indexed={}
    for r in existing['tasks']:
        if not isinstance(r,Mapping) or not re.fullmatch(r'R60-0[0-6][0-9]',str(r.get('task_id',''))):
            return {'state':'HOLD_BAD_EXISTING_MASTER','write_performed':False}
        if r['task_id'] in indexed:
            return {'state':'HOLD_DUPLICATE_MASTER_IDS','write_performed':False}
        indexed[r['task_id']]=dict(r)
    missing=[]
    for task in prepared_tasks():
        if task['task_id'] not in indexed:
            indexed[task['task_id']]=task
            missing.append(task['task_id'])
    return {'state':'CANDIDATE_MASTER_NOT_WRITTEN','tasks':list(indexed.values()),
            'task_count':len(indexed),'missing_executor2_ids':missing,
            'all_60_present':len(indexed)==60 and all(f'R60-{n:03d}' in indexed for n in range(1,61)),
            'write_performed':False,'native_job_ids':[]}
