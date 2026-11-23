#!/usr/bin/env python3
"""Bounded, STOP-aware supervisor watchdog for existing NOX services.

Observe-only by default. NEVER starts a second task dispatcher, never restarts a task
based on an LLM response, never clears owner STOP. Services need explicit allowlist.
Owner must verify actual paths, health schemas, native lease contract and privileges
on the real OneHost before enabling --apply. This is source-only tooling.
"""
from __future__ import annotations
import argparse, datetime, json, os, subprocess, time
from pathlib import Path

def now_utc():return datetime.datetime.now(datetime.timezone.utc)
def load_json(path):
    try:return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError,ValueError):return None

def gates(cfg,now=None):
    now=now or now_utc()
    stop=cfg.get('stop_paths',[])
    if not stop or not cfg.get('stop_contract_verified'):return False,'STOP_CONTRACT_UNVERIFIED'
    if any(Path(p).exists() for p in stop):return False,'OWNER_STOP_OR_MAINTENANCE_PRESENT'
    if not cfg.get('existing_dispatcher_owner_cas_verified'):return False,'OWNER_CAS_NOT_VERIFIED'
    lease=load_json(cfg.get('lease_evidence_file','')) or {}
    if lease.get('owner')!=cfg.get('expected_owner') or not lease.get('owner_authenticated'):
        return False,'LEASE_OWNER_NOT_AUTHENTICATED'
    try: expiry=datetime.datetime.fromisoformat(lease['expires_utc'].replace('Z','+00:00'))
    except (ValueError,KeyError,AttributeError):return False,'LEASE_EXPIRY_MISSING'
    if now>=expiry:return False,'LEASE_EXPIRED'
    res=load_json(cfg.get('resource_evidence_file','')) or {}
    if not res.get('verified_utc') or not res.get('safe_for_service_restart'):
        return False,'RESOURCE_GATE_UNKNOWN'
    try:t=datetime.datetime.fromisoformat(res['verified_utc'].replace('Z','+00:00'))
    except (ValueError,TypeError):return False,'RESOURCE_TIMESTAMP_INVALID'
    if (now-t).total_seconds()>cfg.get('resource_max_age_seconds',90):return False,'RESOURCE_SNAPSHOT_STALE'
    if res.get('oom_events',1)!=0:return False,'OOM_GATE'
    return True,'GATES_PASS'

def step(cfg,apply=False,state=None,now=None):
    state=state if state is not None else {}
    now=now or now_utc()
    ok,reason=gates(cfg,now)
    out=[]
    health=load_json(cfg.get('health_evidence_file','')) or {}
    workers=health.get('services',{})
    for svc in cfg.get('services',[]):
        name=svc.get('name','');info=workers.get(name,{})
        record={'service':name,'health':info.get('state','UNKNOWN'),'action':'NONE'}
        if not name or not svc.get('allowlisted',False):record['action']='SKIP_NOT_ALLOWLISTED';out.append(record);continue
        if not ok:record['action']='HOLD_'+reason;out.append(record);continue
        # One native writer/lease. No service restart on missing health source; NO restart if
        # there is no active work and the service is legitimately idle.
        if not info or not health.get('snapshot_utc'):
            record['action']='HOLD_HEALTH_UNKNOWN';out.append(record);continue
        try:ht=datetime.datetime.fromisoformat(health['snapshot_utc'].replace('Z','+00:00'))
        except Exception:record['action']='HOLD_HEALTH_TIME';out.append(record);continue
        if (now-ht).total_seconds()>cfg.get('health_max_age_seconds',90):
            record['action']='HOLD_HEALTH_STALE';out.append(record);continue
        if info.get('desired_state')!='RUNNING':
            record['action']='SKIP_INTENTIONALLY_STOPPED_OR_IDLE';out.append(record);continue
        if info.get('state') not in ('FAILED','EXITED','FATAL'):
            record['action']='HEALTHY_OR_TRANSIENT';out.append(record);continue
        ss=state.setdefault(name,{'attempts':[]})
        times=[t for t in ss['attempts'] if now.timestamp()-t<3600]
        ss['attempts']=times
        limit=cfg.get('max_attempts_per_hour',4)
        if len(times)>=limit:
            record['action']='BACKOFF_1H_NO_CRASH_LOOP';out.append(record);continue
        delay=min(cfg.get('max_backoff_seconds',1800), 20*(2**len(times)))
        last=max(times) if times else 0
        if times and now.timestamp()-last<delay:
            record['action']='BACKOFF_WAIT';out.append(record);continue
        command=svc.get('restart_argv',[])
        if not command or not isinstance(command,list) or command[:2]!=['supervisorctl','restart'] or len(command)!=3 or command[2]!=name:
            record['action']='HOLD_UNSAFE_RESTART_COMMAND';out.append(record);continue
        if not apply:
            record['action']='WOULD_RESTART_ONLY';out.append(record);continue
        # Final gate recheck immediately before side effect.
        if not gates(cfg,now_utc())[0]:record['action']='STOP_APPEARED';out.append(record);continue
        try:
            p=subprocess.run(command,check=False,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15,text=True)
            record['action']='RESTART_OK' if p.returncode==0 else 'RESTART_FAILED'
            record['returncode']=p.returncode
        except (OSError,subprocess.TimeoutExpired):record['action']='RESTART_TRANSPORT_FAILED'
        ss['attempts'].append(now.timestamp());out.append(record)
    return {'gates_passed':ok,'gate_reason':reason,'services':out,'source_only':not apply}

def main():
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--apply',action='store_true')
    p.add_argument('--loop',action='store_true');p.add_argument('--interval',type=int,default=60);p.add_argument('--state',default='watchdog_retry_state.json')
    a=p.parse_args();cfg=load_json(a.config)
    if not isinstance(cfg,dict):p.error('configuration cannot be read')
    # Even --apply requires an explicit owner-verified runtime gate file; config comes from trusted owner.
    if a.apply and not cfg.get('owner_explicitly_enabled',False):p.error('owner_explicitly_enabled missing')
    if a.interval<15:p.error('interval must be at least 15 seconds')
    while True:
        state=load_json(a.state) or {};result=step(cfg,apply=a.apply,state=state)
        print(json.dumps(result,ensure_ascii=False),flush=True)
        f=Path(a.state);tmp=f.with_suffix('.tmp');tmp.write_text(json.dumps(state),encoding='utf-8');os.replace(tmp,f)
        if not a.loop:break
        time.sleep(a.interval)
if __name__=='__main__':main()
