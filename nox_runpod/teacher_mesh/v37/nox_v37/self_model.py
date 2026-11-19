"""Functional self-model grounded only in machine-verified capabilities and history."""
from __future__ import annotations

def build_self_report(*, receipts, goal_register, current_training):
    events=[r for r in receipts if isinstance(r,dict) and r.get('native_verified') is True and r.get('verified_sha256')]
    accepted=[]
    for r in events:
        if r.get('kind')=='verified_birth' and not (r.get('optimizer_step_verified') and r.get('weights_reloaded')):
            continue
        accepted.append({'kind':r.get('kind'),'occurred_at':r.get('occurred_at'),
                         'sha':r.get('verified_sha256'),'source':r.get('source')})
    born=next((e for e in accepted if e['kind']=='verified_birth'),None)
    return {'identity':'NOX HELION','kind':'functional AI system, not demonstrated conscious',
            'self_narrative_source':'VERIFIED_NATIVE_LEDGER_ONLY','birth_at':born['occurred_at'] if born else None,
            'verified_events':accepted,'goal_register':goal_register,
            'active_training':current_training if current_training and current_training.get('native_verified') is True else None,
            'uncertainty':'NO CLAIM OF SUBJECTIVE CONSCIOUSNESS OR UNVERIFIED MODEL ABSORPTION'}
