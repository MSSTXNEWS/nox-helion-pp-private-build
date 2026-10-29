#!/usr/bin/env python3
"""R21 standalone, read-only adapter for the real Git-saved R20 queue.

No remote calls, no merge, no locks, no QA signing, no release actions.
Live authenticated PR162 HEAD and register blob are required as input.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import re
from pathlib import Path

HEX40 = re.compile(r'[0-9a-f]{40}\Z')
TASK_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z')
SCHEMAS = {'NOX_V16_R20_FIXED_DISPATCH_SNAPSHOT_V1',
           'NOX_V16_R20_DISPATCH_SNAPSHOT_V1'}
STATES = {'OPEN','PATCHED','VERIFIED','INTEGRATED','ACCEPTED','HOLD'}

def check(condition, msg):
    if not condition: raise ValueError(msg)

def read_json(path):
    raw=Path(path).read_bytes()
    check(len(raw)<=4*1024*1024,'INPUT_TOO_LARGE')
    def unique(pairs):
        d={}
        for k,v in pairs:
            check(k not in d,'DUPLICATE_JSON_KEY')
            d[k]=v
        return d
    return json.loads(raw.decode('utf-8'),object_pairs_hook=unique,
                      parse_constant=lambda x:check(False,'NONFINITE_JSON'))

def queue_preview(snapshot, observed_head, observed_registry_blob, now):
    check(type(snapshot) is dict,'DISPATCH_OBJECT_REQUIRED')
    check(snapshot.get('schema') in SCHEMAS,'UNSUPPORTED_DISPATCH_SCHEMA')
    check(type(observed_head) is str and HEX40.fullmatch(observed_head),'OBSERVED_HEAD_SHA_REQUIRED')
    check(type(observed_registry_blob) is str and HEX40.fullmatch(observed_registry_blob),'OBSERVED_REGISTER_BLOB_REQUIRED')
    saved_head=snapshot.get('head_snapshot',snapshot.get('head_at_snapshot'))
    saved_reg=snapshot.get('error_register_blob',snapshot.get('register_blob'))
    check(type(saved_head) is str and HEX40.fullmatch(saved_head) and
          type(saved_reg) is str and HEX40.fullmatch(saved_reg),'SNAPSHOT_PROVENANCE_MISSING')
    try:
        stamp=dt.datetime.fromisoformat(now.replace('Z','+00:00'))
        check(stamp.tzinfo is not None,'TIMEZONE_REQUIRED')
    except (AttributeError,ValueError) as ex:
        raise ValueError('INVALID_TIME') from ex
    if saved_head!=observed_head or saved_reg!=observed_registry_blob:
        return {'status':'STALE_SNAPSHOT_REGENERATE','head_drift':saved_head!=observed_head,
                'register_drift':saved_reg!=observed_registry_blob,'ready':[],
                'zero_mutations':True,'qa_accepted':False}
    rows=snapshot.get('tasks')
    check(type(rows) is list and len(rows)>0,'TASKS_REQUIRED')
    index={}
    for row in rows:
        check(type(row) is dict,'INVALID_TASK')
        task_id=row.get('id')
        check(type(task_id) is str and TASK_ID.fullmatch(task_id) and task_id not in index,
              'DUPLICATE_OR_INVALID_TASK_ID')
        check(type(row.get('owner')) is str and row['owner'],'OWNER_REQUIRED')
        check(row.get('state') in STATES,'INVALID_STATE')
        deps=row.get('depends_on',[])
        check(type(deps) is list and all(type(x) is str for x in deps) and len(set(deps))==len(deps),
              'INVALID_DEPENDENCIES')
        if row.get('source_error_status')=='FIX_APPLIED_UNVERIFIED':
            check(row['state'] in ('OPEN','PATCHED','HOLD'),'UNVERIFIED_ERROR_PROMOTED')
        if task_id=='T06':check(deps==[],'T06_SELF_DEADLOCK_REINTRODUCED')
        index[task_id]=row
    visiting=set();done=set()
    def visit(task_id):
        check(task_id not in visiting,'DEPENDENCY_CYCLE')
        if task_id in done:return
        visiting.add(task_id)
        for dep in index[task_id].get('depends_on',[]):
            check(dep in index and dep!=task_id,'UNKNOWN_DEPENDENCY')
            visit(dep)
        visiting.remove(task_id);done.add(task_id)
    for task_id in index:visit(task_id)
    accepted={k for k,v in index.items() if v['state']=='ACCEPTED'}
    ready=[];deferred=[]
    for task_id,v in index.items():
        if v['state']=='ACCEPTED':continue
        missing=[dep for dep in v.get('depends_on',[]) if dep not in accepted]
        if missing:
            deferred.append({'id':task_id,'missing_accepted_dependencies':missing})
            continue
        if v['state']=='HOLD':continue
        if v.get('lease') is not None:
            ready.append({'id':task_id,'state':'LEASE_REQUIRES_OWNER_CAS','owner':v['owner']})
            continue
        ready.append({'id':task_id,'state':v['state'],'owner':v['owner']})
    ready.sort(key=lambda v:(v['state']=='LEASE_REQUIRES_OWNER_CAS',v['id']))
    return {'status':'READ_ONLY_PLAN_NOT_AUTHORIZED','ready':ready,'deferred':deferred,
            'source_head':observed_head,'error_blob':observed_registry_blob,
            'remote_owner_authenticated':False,'qa_accepted':False,
            'zero_mutations':True}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('snapshot');ap.add_argument('--head',required=True)
    ap.add_argument('--registry-blob',required=True);ap.add_argument('--now',required=True)
    a=ap.parse_args()
    print(json.dumps(queue_preview(read_json(a.snapshot),a.head,a.registry_blob,a.now),
                     ensure_ascii=False,indent=2))
if __name__=='__main__':
    try:main()
    except (ValueError,TypeError,OSError) as ex:
        print(json.dumps({'status':'BLOCKED','reason':str(ex)},ensure_ascii=False))
        raise SystemExit(2)