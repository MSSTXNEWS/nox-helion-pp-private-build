#!/usr/bin/env python3
"""Non-mutating native training restart decision for Volta SM70, never kill a job.
Only an existing signed OneHost FORGE callback may run the returned proposal.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path

HEX = re.compile(r'^[a-f0-9]{64}$')

def build_plan(state:dict) -> dict:
    reasons=[]
    if not isinstance(state,dict):return {'state':'HOLD','reason':['BAD_INPUT'], 'performed':False}
    if state.get('instance_id') != '60509551':reasons.append('INSTANCE_ID_NOT_VERIFIED')
    gpus=state.get('gpus') or []
    if not isinstance(gpus,list) or len(gpus)!=2 or sorted(g.get('index') for g in gpus if isinstance(g,dict))!=[0,1]:
        reasons.append('TWO_V100_SENSORS_REQUIRED')
    else:
        for g in gpus:
            if 'V100' not in str(g.get('name','')):reasons.append('NOT_V100')
            if not isinstance(g.get('vram_free_mib'),int) or g['vram_free_mib'] < 4096:
                reasons.append('GPU_'+str(g['index'])+'_LOW_VRAM_HEADROOM')
            if g.get('compute_util_pct') is None: reasons.append('GPU_UTIL_UNKNOWN')
    if state.get('driver_cuda_toolkit_major')!=12 or state.get('sm')!=70 or state.get('bf16') is not False:
        reasons.append('VOLTA_CUDA12_FP16_ABI_UNVERIFIED')
    if not isinstance(state.get('free_disk_bytes'),int) or state['free_disk_bytes'] < 20_000_000_000:
        reasons.append('DISK_LT_20GB')
    if not isinstance(state.get('ram_available_mib'),int) or state['ram_available_mib']<12288:
        reasons.append('RAM_RESERVE_LOW')
    if state.get('external_checkpoint_restore_verified') is not True or not isinstance(state.get('checkpoint_sha256'),str) or not HEX.fullmatch(state['checkpoint_sha256']):
        reasons.append('OFFSITE_RESTORABLE_CHECKPOINT_NOT_VERIFIED')
    if state.get('s03_offsite_restore_verified') is not True:reasons.append('S03_OFFSITE_RESTORE_NOT_VERIFIED')
    if state.get('student_weights_active_sha256') is None or not HEX.fullmatch(str(state.get('student_weights_active_sha256',''))):
        reasons.append('STUDENT_ACTIVE_WEIGHTS_SHA_UNVERIFIED')
    if state.get('training_error_diagnosed') is not True:reasons.append('TRAIN_ERROR_ROOT_CAUSE_UNKNOWN')
    if state.get('no_live_optimizer_process') is not True:reasons.append('MAY_INTERRUPT_ACTIVE_OPTIMIZER')
    if state.get('native_stop_active') is not False:reasons.append('STOP_OR_STOP_SENSOR_NOT_VERIFIED')
    return {'schema':'NOX_V40_RESUME_ADMISSION','state':'HOLD' if reasons else 'READY_FOR_EXISTING_NATIVE_APPROVAL',
            'reasons':reasons,'performed':False,'target_compute_util_pct':85,
            'recommended_action':'training.resume_existing_only','per_gpu_vram_reserve_mib':3072,
            'never_launch_new_35b_without_verified_memory_budget':True,
            'no_force_restart':True,'next':'Use existing OneHost native_admin.dispatch and signed approval; do not run from assistant text'}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--inventory',required=True);a=ap.parse_args()
    p=Path(a.inventory)
    if p.stat().st_size>1024*1024:raise SystemExit('HOLD_OVERSIZE')
    print(json.dumps(build_plan(json.loads(p.read_text('utf8'))),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
