"""One NOX retention/backup gate before training, model swaps or UI promotion."""
from __future__ import annotations
import re

_SHA=re.compile(r'^[0-9a-f]{64}$')


def accept_checkpoint(state:dict)->dict:
    reasons=[]
    if not isinstance(state,dict):return {'state':'HOLD','reasons':['INVALID_INPUT']}
    for key in ('active_model_sha256','checkpoint_sha256','s03_snapshot_sha256','external_backup_manifest_sha256'):
        if not isinstance(state.get(key),str) or _SHA.fullmatch(state[key]) is None:reasons.append('INVALID_'+key.upper())
    if state.get('external_checkpoint_restore_tested') is not True:reasons.append('NO_CHECKPOINT_RESTORE_PROOF')
    if state.get('s03_external_restore_tested') is not True:reasons.append('NO_S03_RESTORE_PROOF')
    if state.get('reloaded_weights_match_checkpoint') is not True:reasons.append('NO_CHECKPOINT_RELOAD_PROOF')
    if state.get('optimizer_state_present') is not True:reasons.append('OPTIMIZER_MISSING')
    # 5m is the owner's claimed checkpoint interval, never assume it was met.
    age=state.get('checkpoint_age_seconds')
    if type(age) not in (float,int) or age<0 or age>600:reasons.append('CHECKPOINT_AGE_UNVERIFIED_OR_OVER_10MIN')
    if state.get('native_stop_active') is not False:reasons.append('STOP_OR_SENSOR_UNKNOWN')
    return {'state':'HOLD' if reasons else 'READY_FOR_NATIVE_OWNER_APPROVAL', 'reasons':reasons,
            'has_executed_restart':False, 'has_modified_weights':False,
            'configured_checkpoint_interval_s':300,'target_gpu_compute_pct':85}
