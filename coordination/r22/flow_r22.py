#!/usr/bin/env python3
"""NOX V16 R22: fail-closed renewal of the existing R20/R21 dispatch snapshot.

Local READ-ONLY planning, not a GitHub/GitLab API, CAS writer, lease authority,
or QA acceptance. Only explicit current HEAD and current register *bytes* passed
by an authorized operator may produce a refreshed preview.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path
# In Git the dependency is coordination/r21/flow_r21.py, not beside R22.
# Do not fetch modules from network or fall back to an unrelated package.
_sibling_r21 = Path(__file__).resolve().parents[1] / 'r21'
if (_sibling_r21 / 'flow_r21.py').is_file():
    sys.path.insert(0, str(_sibling_r21))
from flow_r21 import queue_preview, read_json, check, HEX40

SCHEMA = 'NOX_V16_R20_FIXED_DISPATCH_SNAPSHOT_V1'
STATUS = {
    'OPEN': 'OPEN',
    'FIX_APPLIED_UNVERIFIED': 'PATCHED',
    'VERIFIED_CLOSED': 'ACCEPTED',
}


def git_blob_id(raw: bytes) -> str:
    return hashlib.sha1(f'blob {len(raw)}\0'.encode() + raw).hexdigest()


def checked_registry(raw: bytes, expected_blob: str):
    check(type(expected_blob) is str and HEX40.fullmatch(expected_blob),
          'OBSERVED_REGISTER_BLOB_REQUIRED')
    check(len(raw) <= 4 * 1024 * 1024, 'REGISTER_TOO_LARGE')
    check(git_blob_id(raw) == expected_blob, 'REGISTER_BYTES_NOT_AT_OBSERVED_BLOB')
    # Parse exactly the verified bytes; no JSON duplicate keys, Infinity or NaN.
    def unique(pairs):
        result = {}
        for k, value in pairs:
            check(k not in result, 'DUPLICATE_REGISTER_KEY:' + k)
            result[k] = value
        return result
    register = json.loads(raw.decode('utf-8'), object_pairs_hook=unique,
                          parse_constant=lambda n: check(False, 'NONFINITE_REGISTER'))
    check(type(register) is dict and type(register.get('entries')) is list,
          'REGISTER_ENTRIES_REQUIRED')
    error_index = {}
    for row in register['entries']:
        check(type(row) is dict, 'INVALID_REGISTER_ENTRY')
        eid, status, owner = row.get('error_id'), row.get('status'), row.get('owner')
        check(type(eid) is str and 1 <= len(eid) <= 128 and eid not in error_index,
              'INVALID_OR_DUPLICATE_ERROR_ID')
        check(status in STATUS, 'UNKNOWN_ERROR_STATUS')
        check(type(owner) is str and bool(owner.strip()), 'REGISTER_OWNER_REQUIRED')
        error_index[eid] = row
    check(error_index, 'EMPTY_REGISTER')
    counts = {k:sum(x['status']==k for x in error_index.values()) for k in STATUS}
    if type(register.get('stats')) is dict:
        for key,val in counts.items():
            check(register['stats'].get(key) == val, 'REGISTER_STATS_INCONSISTENT')
        check(register['stats'].get('total')==len(error_index), 'REGISTER_TOTAL_INCONSISTENT')
    return register, error_index


def regenerate(snapshot: dict, register_bytes: bytes, observed_head: str,
               observed_registry_blob: str, now: str):
    """Produce a new *proposal*, never preserve unverified gate or lease successes."""
    check(type(snapshot) is dict and snapshot.get('schema') in
          ('NOX_V16_R20_FIXED_DISPATCH_SNAPSHOT_V1','NOX_V16_R20_DISPATCH_SNAPSHOT_V1'),
          'BASELINE_SCHEMA_REQUIRED')
    check(type(observed_head) is str and HEX40.fullmatch(observed_head),
          'OBSERVED_HEAD_SHA_REQUIRED')
    register, errors = checked_registry(register_bytes, observed_registry_blob)
    rows = snapshot.get('tasks')
    check(type(rows) is list and bool(rows), 'BASELINE_TASKS_REQUIRED')
    baseline = {}
    for row in rows:
        check(type(row) is dict and type(row.get('id')) is str and row['id'] not in baseline,
              'INVALID_OR_DUPLICATE_BASELINE_ID')
        baseline[row['id']] = row
    # Do not silently erase/forget historical errors that are missing from the live
    # register; a partial register may mean a lossy sync, not deletion permission.
    old_error_ids = {k for k,v in baseline.items() if v.get('source_error_status') is not None}
    missing = old_error_ids - errors.keys()
    check(not missing, 'ERROR_HISTORY_LOSS:' + ','.join(sorted(missing)[:5]))
    fresh=[]
    for key,row in baseline.items():
        new = deepcopy(row)
        new.pop('lease',None)  # expired/active leases cannot be auto-transferred
        new.pop('assignee',None)
        if key in errors:
            source = errors[key]
            new['source_error_status'] = source['status']
            new['state'] = STATUS[source['status']]
            new['owner'] = source['owner']
            new['source_error_register_blob'] = observed_registry_blob
        else:
            # Gate successes derived from a previously pinned HEAD cannot be
            # promoted to the new HEAD without independent owner/QA readback.
            new['state'] = 'OPEN'
        fresh.append(new)
    for key in sorted(errors.keys()-baseline.keys()):
        source=errors[key]
        fresh.append({'id':key,'package':'GATE','owner':source['owner'],
                      'state':STATUS[source['status']], 'priority':0,
                      'depends_on':[], 'source_error_status':source['status'],
                      'source_error_register_blob':observed_registry_blob})
    # T06 has no dependency on its own ERR-SRC-003/004: preserve other gate DAG.
    for row in fresh:
        if row['id']=='T06':
            row['depends_on']=[]
    new_snapshot = deepcopy(snapshot)
    new_snapshot['schema']=SCHEMA
    new_snapshot['head_at_snapshot']=observed_head
    new_snapshot['register_blob']=observed_registry_blob
    new_snapshot.pop('head_snapshot',None)
    new_snapshot.pop('error_register_blob',None)
    new_snapshot['tasks']=fresh
    new_snapshot['counts_at_snapshot']=register.get('stats',{})
    new_snapshot['canonical_product_progress']='N/D'
    new_snapshot['kind']='NON_CANONICAL_R22_READ_ONLY_REGENERATED'
    new_snapshot['warning']='Do NOT treat regenerated READY, PATCHED or old accepted gate statuses as QA signatures'
    new_snapshot['revalidated_owner_qa_receipts']=False
    new_snapshot['leases_require_reacquisition']=True
    preview=queue_preview(new_snapshot, observed_head, observed_registry_blob, now)
    check(preview['status']=='READ_ONLY_PLAN_NOT_AUTHORIZED', 'PREVIEW_NOT_READY')
    return {'status':'REFRESHED_READ_ONLY_NOT_AUTHORIZED',
            'snapshot':new_snapshot,'preview':preview,
            'historical_error_count':len(old_error_ids),
            'actual_error_count':len(errors),'rejected_old_leases':True,
            'source_qa_accepted':False, 'remote_mutations':0}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('saved_snapshot')
    ap.add_argument('current_register_json')
    ap.add_argument('--head',required=True)
    ap.add_argument('--registry-blob',required=True)
    ap.add_argument('--now',required=True)
    args=ap.parse_args()
    raw=Path(args.current_register_json).read_bytes()
    result=regenerate(read_json(args.saved_snapshot),raw,args.head,args.registry_blob,args.now)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':
    try: main()
    except (ValueError, TypeError, OSError, UnicodeError) as exc:
        print(json.dumps({'status':'BLOCKED','reason':str(exc)},ensure_ascii=False))
        raise SystemExit(2)