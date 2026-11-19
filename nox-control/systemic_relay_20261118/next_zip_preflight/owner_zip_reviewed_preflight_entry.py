#!/usr/bin/env python3
"""Owner-pinned one-shot ZIP source repair via EXISTING native project executor.

The model attempted the ZIP task and produced a verifiable BLOCKED receipt, not
a source edit. This entry accepts a separately tested exact reviewed source
candidate and the *existing* immutable six-test contract. It only appends the
new reviewed plan; existing workers apply, verify, integrate and persist S03.
No new worker, queue, model, scheduler, service restart, or original acceptance.
"""
from __future__ import annotations
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import types

ROOT = Path('/root/nox')
CONFIG = ROOT / 'config/owner_native_subagents.json'
PACKAGE = ROOT / 'state/dispatcher/project_executor/package'
TASK_ID = '0V14-14.project.reviewed_zip_preflight_20261119'
PARENT_ID = '0V14-14'
PREDECESSOR_ID = '0V14-14.project.reviewed_zip_budget_20261119'
PREDECESSOR_RECEIPT_SHA = '4c347d8001d6c67e6f5479cb2af868fdc03e84a7a88203102244d6d359149c3b'
PREDECESSOR_CONTRACT_SHA = '7712f29693ec68d98be656baded2c1b543410a3026a386cd02645c99bf43597e'
PREDECESSOR_REASON = 'MODEL_REPORTED_BLOCKER_NOT_VERIFIED'
SOURCE_SHA = '7e9ffd7e6a3c69d8d7529d804ebd8d29d3a9199b1c39a2177eb1bc2a230d55b3'
REVIEWED_SHA = '9f091b4e608194e6142e0491e9a22896fec8cc32803870214647efee7884e413'
TEST_SHA = '97c433b8893514f5812b69fd53b0bb1e25d1fcd7b290f35c72407ad54b989667'
REGISTRY_PARENT_SHA = '3ace28409839c1e1259e5a24b7d40c11bf9dec3445b2b0073ef90ecc22b2216e'
CURRENT_CONFIG_SHA = '6ba8de14b7498740d5a3ffb7a0216c5387c2ce904c19cf7a16772c1046cdfeb3'
CURRENT_SOURCE_SCOPE_SHA = 'b93ae5fe2423acf8b5391d56482c567038744decc629c194ee676a7671530779'
CURRENT_CALLBACK_SHA = 'eac3ce9e2d8c862d1a7917ec447ea72e84454b7775a4260ad1e72e59de96fe11'
CURRENT_MANIFEST_SHA = 'b2cec01f43cb8434b5a050874082f7743f4ebe51a1d767fd899321d74e114c39'
HELPER_SHA = '8470a6720ca69864bbc4e6e630a1f853344839af424d3829dcdf1774442db609'
ASSET_NAMES = frozenset(('owner_systemic_reviewed_publish.py',
                         'continuous_transaction_helpers.py','merge_web_source.py'))
try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}


def require(value, code):
    if not value:
        raise RuntimeError('HOLD_ZIP_REVIEWED_' + code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def load(name, raw):
    module = types.ModuleType(name)
    module.__file__ = '<reviewed-zip>/' + name + '.py'
    exec(compile(raw, module.__file__, 'exec'), module.__dict__)
    return module


def preflight():
    request = os.getenv('NOX_OWNER_REQUEST_ID', '')
    commit = os.getenv('NOX_OWNER_SOURCE_SHA', '')
    require(bool(re.fullmatch(r'[0-9]{1,24}', request)) and
            bool(re.fullmatch(r'[a-f0-9]{40}', commit)), 'OWNER_CONTEXT')
    require(isinstance(BUNDLE, dict) and set(BUNDLE) == ASSET_NAMES, 'EXACT_BUNDLE')
    assets = {}
    for name in sorted(ASSET_NAMES):
        value = BUNDLE[name]
        require(isinstance(value, str) and len(value) < 300000, 'ASSET_ENCODING')
        raw = base64.b64decode(value, validate=True)
        require(0 < len(raw) <= 125000, 'ASSET_BYTES')
        assets[name] = raw
    require(digest(assets['continuous_transaction_helpers.py']) == HELPER_SHA
            and digest(assets['merge_web_source.py']) == REVIEWED_SHA,
            'SOURCE_ASSET_PIN')
    helper = load('_nox_zip_reviewed_helper',
                  assets['continuous_transaction_helpers.py'])
    require(helper.stop_clear(ROOT), 'OWNER_STOP')
    old_bytes = helper.read_regular(CONFIG, 2*1024*1024)
    require(digest(old_bytes) == CURRENT_CONFIG_SHA, 'CONFIG_PREDECESSOR')
    old = json.loads(old_bytes)
    require(old.get('owner_authorized') is True and old.get('instance_id') == 60509551
            and old.get('mode') == 'NORMAL'
            and old.get('target') == old.get('global_worker_cap') == 3
            and old.get('execution_mode') == 'NATIVE_PROJECT_V1'
            and old.get('systemic_relay',{}).get('sha256') == CURRENT_MANIFEST_SHA
            and old['module_pins']['owner_subagent_dispatcher.py'] == CURRENT_CALLBACK_SHA,
            'OWNER_CONFIG_SCOPE')
    snapshot = helper.source_snapshot(ROOT, old)
    require(snapshot['files_sha256'] == CURRENT_SOURCE_SCOPE_SHA
            and snapshot['files']['merge_web_source.py']['sha256'] == SOURCE_SHA
            and snapshot['files']['test_nox_merge_overlay_paths.py']['sha256'] == TEST_SHA,
            'EXACT_CURRENT_SOURCE')
    state, active = helper.queue_idle(ROOT)
    require(not active, 'ACTIVE_NATIVE_CLAIM')
    prior = state['tasks'].get(PREDECESSOR_ID)
    result = prior.get('result') or {} if isinstance(prior, dict) else {}
    receipt = result.get('receipt') or {}
    evidence = (receipt.get('worker_result') or {}).get('project_evidence') or {}
    require(isinstance(prior, dict) and prior.get('status') == 'blocked'
            and result.get('receipt_sha256') == PREDECESSOR_RECEIPT_SHA
            and prior.get('native_worker_lease',{}).get('phase') == 'SETTLED'
            and evidence.get('state') == 'INTEGRATED'
            and evidence.get('integration_verified') is True
            and evidence.get('postimages') == {'merge_web_source.py': SOURCE_SHA}
            and evidence.get('trusted_tests_unchanged') is True,
            'DONE_PREDECESSOR_READBACK')
    require(TASK_ID not in state['tasks']
            and all(row.get('id') != TASK_ID for row in old['catalog']['tasks']),
            'ONE_SHOT_NO_REPLAY')
    manifest = json.loads(helper.read_regular(
        PACKAGE/'relay'/(CURRENT_MANIFEST_SHA+'.json'),2*1024*1024))
    require(manifest.get('registry',{}).get('parents',{}).get(PARENT_ID,{}).get('spec_sha256')
            == REGISTRY_PARENT_SHA,'PARENT_REGISTRY_PIN')
    return assets


def reviewed_plan():
    """One changed source; immutable trusted verifier and original spec pins."""
    return {
      'schema':'NOX_PROJECT_WORK_PLAN_V1',
      'task_id':TASK_ID,'parent_task_id':PARENT_ID,
      'queue_id':'Q4_INTEGRATION_ACCEPTANCE','root_id':'NOX_PROJECT_SOURCE',
      'operation':'apply_reviewed_files','review_origin':'OWNER_REVIEWED',
      'spec_sha256':REGISTRY_PARENT_SHA,
      'context':[
        {'path':'merge_web_source.py','sha256':SOURCE_SHA},
        {'path':'test_nox_merge_overlay_paths.py','sha256':TEST_SHA}
      ],
      'files':[{
        'path':'merge_web_source.py',
        'before_sha256':SOURCE_SHA,
        'after_sha256':REVIEWED_SHA,
        'payload_sha256':REVIEWED_SHA
      }],
      'verification':{'kind':'python_unittest','min_tests':6,
                      'modules':['test_nox_merge_overlay_paths'],
                      'timeout_sec':120},
      'acceptance_scope':'SOURCE_PATCH_TESTED',
      'original_task_accepted':False
    }


def run():
    assets = preflight()
    plan_bytes = encoded(reviewed_plan())
    plan_sha = digest(plan_bytes)
    title = 'Preflight both pinned WEB archives before extracting first archive'
    reviewer = {
      'reviewed_systemic_transaction_helpers.py':assets['continuous_transaction_helpers.py'],
      'reviewed_zip_plan.json':plan_bytes,
      'reviewed_zip_payload.source':assets['merge_web_source.py']
    }
    row = {'id':TASK_ID,'handler':'owner_native_project_work',
           'queue_id':'Q4_INTEGRATION_ACCEPTANCE','resource':'CPU_LIGHT',
           'priority':'P1','deps':[],'estimated_cost':2,
           'source_sha256':CURRENT_CALLBACK_SHA,
           'params':{'parent_task_id':PARENT_ID,'plan_sha256':plan_sha},
           'title':title}
    spec = {
      'schema':'NOX_SYSTEMIC_REVIEWED_PUBLISH_SPEC_V1',
      'assets':{name:digest(value) for name,value in reviewer.items()},
      'helper_asset':'reviewed_systemic_transaction_helpers.py',
      'batches':[{
        'title':title,'plan_asset':'reviewed_zip_plan.json',
        'payload_assets':{REVIEWED_SHA:'reviewed_zip_payload.source'},
        'catalog_row':row
      }],
      'predecessors':[{
        'task_id':PREDECESSOR_ID,'parent_task_id':PARENT_ID,
        'status':'done','receipt_sha256':PREDECESSOR_RECEIPT_SHA,
        'contract_sha256':PREDECESSOR_CONTRACT_SHA,
        'postimages':{'merge_web_source.py':SOURCE_SHA}
      }],
      'expected_callback_sha256':CURRENT_CALLBACK_SHA,
      'expected_config_sha256':CURRENT_CONFIG_SHA,
      'expected_source_files_sha256':CURRENT_SOURCE_SCOPE_SHA,
      'expected_director':{'pid':359172,'start_ticks':184639742},
      'expected_workers':[
         {'pid':359266,'start_ticks':184640911},
         {'pid':359267,'start_ticks':184640911},
         {'pid':359268,'start_ticks':184640911}
      ],
      'protected_processes':{
         'chat':{'pid':3266857,'start_ticks':172046662},
         'proxy':{'pid':356544,'start_ticks':184602380},
         'web':{'pid':356735,'start_ticks':184603716}
      }
    }
    print('NOX_MAINT_ZIP_REVIEWED_PREFLIGHT=' + encoded({
        'schema':'NOX_OWNER_ZIP_REVIEWED_PREFLIGHT_V1',
        'new_task_id':TASK_ID,'previous_done_task_id':PREDECESSOR_ID,
        'source_before_sha256':SOURCE_SHA,'source_after_sha256':REVIEWED_SHA,
        'plan_sha256':plan_sha,'exact_test_preimage_sha256':TEST_SHA,
        'reviewed_origin':'OWNER_REVIEWED','native_task_admitted':False,
        'original_295_accepted':False
    }).decode(),flush=True)
    reviewed_publisher = load('_nox_zip_existing_reviewed_publisher',
                              assets['owner_systemic_reviewed_publish.py'])
    bundle = {name:base64.b64encode(value).decode('ascii')
              for name,value in reviewer.items()}
    receipt = reviewed_publisher.run(bundle, spec)
    require(receipt.get('state') == 'CATALOG_APPENDED_NATIVE_EXECUTION_PENDING',
            'PUBLISH_RECEIPT')
    print('NOX_MAINT_ZIP_REVIEWED_NEXT=' + encoded({
      'state':receipt['state'],'task_id':TASK_ID,
      'catalog_appended':True,'new_worker_created':False,
      'source_edited_by_publisher':False,
      's03_result_pending':True,'original_295_accepted':False
    }).decode(),flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)


if __name__=='__main__':
    run()
