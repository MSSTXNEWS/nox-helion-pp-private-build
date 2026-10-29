#!/usr/bin/env python3
"""G2-C R13: offline R21 queue/head/registry safety regression; no QA signing."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--flow', required=True)
p.add_argument('--snapshot', required=True)
p.add_argument('--head', required=True)
p.add_argument('--register-blob', required=True)
p.add_argument('--now', required=True)
a = p.parse_args()

def blob(path):
    data = Path(path).read_bytes()
    return hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest()

assert blob(a.flow) == '5f5503d9cdef177d43f715846d4c34efa91b41a8', 'FLOW_BLOB_DRIFT'
assert blob(a.snapshot) == '6cd258cf380a9b18b83fc1b4e8d6635c530e2a8a', 'SNAPSHOT_BLOB_DRIFT'
spec = importlib.util.spec_from_file_location('nox_flow_r21', a.flow)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
s = mod.read_json(a.snapshot)
now = a.now
old_head, old_register = s['head_at_snapshot'], s['register_blob']
def preview(v, h=old_head, r=old_register):
    return mod.queue_preview(v, h, r, now)
def rejects(v, reason):
    try: preview(v)
    except ValueError as e: assert reason in str(e), (reason, str(e))
    else: raise AssertionError(f'EXPECTED_REJECTION:{reason}')

matched = preview(s)
assert matched['status'] == 'READ_ONLY_PLAN_NOT_AUTHORIZED' and len(matched['ready']) == 11 and len(matched['deferred']) == 4
assert not matched['qa_accepted'] and matched['zero_mutations']
assert a.head != old_head and a.register_blob == old_register, 'ACTUAL_AUTHENTICATED_DRIFT_NOT_PRESENT'
stale = preview(s, a.head, a.register_blob)
assert stale['status'] == 'STALE_SNAPSHOT_REGENERATE' and stale['head_drift'] and not stale['register_drift'] and stale['ready'] == [] and not stale['qa_accepted']
reg_stale = preview(s, old_head, 'a' * 40)
assert reg_stale['status'] == 'STALE_SNAPSHOT_REGENERATE' and reg_stale['register_drift'] and reg_stale['ready'] == []
u = copy.deepcopy(s)
next(x for x in u['tasks'] if x.get('source_error_status') == 'FIX_APPLIED_UNVERIFIED')['state'] = 'ACCEPTED'
rejects(u, 'UNVERIFIED_ERROR_PROMOTED')
u = copy.deepcopy(s)
next(x for x in u['tasks'] if x['id'] == 'T06')['depends_on'] = ['ERR-SRC-003']
rejects(u, 'T06_SELF_DEADLOCK_REINTRODUCED')
u = copy.deepcopy(s); u['tasks'].append(copy.deepcopy(u['tasks'][0]))
rejects(u, 'DUPLICATE_OR_INVALID_TASK_ID')
u = copy.deepcopy(s)
preview(s, a.head, a.register_blob)
assert u == s, 'UNEXPECTED_MUTATION'
print(json.dumps({'status':'PASS','checks':'8/8','current_head':a.head,'register_blob':a.register_blob,'snapshot_status':stale['status'],'source_ready_used':False,'qa_accepted':False,'remote_mutations':0}, ensure_ascii=False))
