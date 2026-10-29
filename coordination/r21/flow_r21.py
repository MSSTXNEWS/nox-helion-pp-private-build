#!/usr/bin/env python3
"""R21 read-only adapter for the actual Git-persisted R20 dispatch snapshot.

Never acquires leases, writes product files, creates authorizations or claims QA.
A live authenticated observation of both PR162 HEAD and the error-registry blob
must be supplied by the caller. All results are non-authorizing previews.
"""
import argparse
import json
from flow_r20 import flow_plan
from nox_flow import HEX40, is_sha, registry_ok, iso_utc, read_json, require

SCHEMAS = frozenset({
    'NOX_V16_R20_FIXED_DISPATCH_SNAPSHOT_V1',
    'NOX_V16_R20_DISPATCH_SNAPSHOT_V1',
})

def reconcile(snapshot, observed_head, observed_registry_blob):
    """Reject drift rather than using a stale coordination snapshot."""
    require(type(snapshot) is dict, 'DISPATCH_OBJECT_REQUIRED')
    require(snapshot.get('schema') in SCHEMAS, 'UNSUPPORTED_DISPATCH_SCHEMA')
    require(is_sha(observed_head, HEX40), 'OBSERVED_HEAD_SHA_REQUIRED')
    require(is_sha(observed_registry_blob, HEX40), 'OBSERVED_REGISTER_BLOB_REQUIRED')
    pinned_head = snapshot.get('head_snapshot', snapshot.get('head_at_snapshot'))
    pinned_register = snapshot.get('error_register_blob', snapshot.get('register_blob'))
    require(is_sha(pinned_head, HEX40) and is_sha(pinned_register, HEX40), 'SNAPSHOT_PROVENANCE_MISSING')
    if pinned_head != observed_head or pinned_register != observed_registry_blob:
        return {'status':'STALE_SNAPSHOT_REGENERATE',
                'head_drift':pinned_head != observed_head,
                'register_drift':pinned_register != observed_registry_blob,
                'ready':[], 'zero_mutations':True,
                'next_action':'REFETCH_CURRENT_HEAD_AND_REGISTER_REGENERATE_DISPATCH'}
    tasks = snapshot.get('tasks')
    require(type(tasks) is list and bool(tasks), 'TASKS_REQUIRED')
    records = []
    for x in tasks:
        require(type(x) is dict, 'INVALID_TASK')
        r = dict(x)
        # Never promote an unverified patch to VERIFIED merely because a source
        # file or a coordination receipt exists.
        if r.get('source_error_status') == 'FIX_APPLIED_UNVERIFIED':
            require(r.get('state') in ('PATCHED', 'OPEN', 'HOLD'), 'UNVERIFIED_ERROR_PROMOTED')
        if r.get('id') == 'T06':
            require(not r.get('depends_on'), 'T06_SELF_DEADLOCK_REINTRODUCED')
        records.append(r)
    clean={'schema':'NOX_V16_R20_DISPATCH_SNAPSHOT_V1',
           'head_snapshot':observed_head,
           'error_register_blob':observed_registry_blob,
           'tasks':records,
           'product_percent':None}
    registry_ok(clean)
    return {'status':'CURRENT_SNAPSHOT_METADATA_VALIDATED_NOT_AUTHORIZED',
            'dispatch':clean,
            'zero_mutations':True,
            'remote_owner_authenticated':False,
            'qa_accepted':False}

def preview(snapshot, observed_head, observed_registry_blob, now):
    result=reconcile(snapshot,observed_head,observed_registry_blob)
    if result['status'] != 'CURRENT_SNAPSHOT_METADATA_VALIDATED_NOT_AUTHORIZED':
        return result
    p=flow_plan(result['dispatch'],iso_utc(now),observed_head)
    # An earlier checksum-only handoff is not an authenticated Git author or
    # valid signature: never label ready tasks as authorized for merge.
    p['remote_owner_authenticated']=False
    p['qa_accepted']=False
    p['register_blob_observed']=observed_registry_blob
    p['zero_mutations']=True
    return p

def main():
    p=argparse.ArgumentParser()
    p.add_argument('snapshot')
    p.add_argument('--head',required=True)
    p.add_argument('--registry-blob',required=True)
    p.add_argument('--now',required=True)
    args=p.parse_args()
    out=preview(read_json(args.snapshot),args.head,args.registry_blob,args.now)
    print(json.dumps(out,indent=2,ensure_ascii=False))
if __name__ == '__main__':
    try:main()
    except (ValueError,KeyError,TypeError,OSError) as exc:
        print(json.dumps({'status':'BLOCKED','reason':str(exc)},ensure_ascii=False))
        raise SystemExit(2)