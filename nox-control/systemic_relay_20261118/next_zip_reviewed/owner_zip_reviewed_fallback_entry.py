#!/usr/bin/env python3
"""One-shot owner-reviewed ZIP fallback, ONLY after exact prior claim is settled.

No daemon, new worker/model, training or direct source mutation. The canonical
native owner publisher alone may append the pre-reviewed plan under its STOP,
lease, source CAS, immutable verifier, predecessor S03, and rollback checks.
"""
from __future__ import annotations
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import types

ROOT=Path('/root/nox')
CONFIG=ROOT/'config/owner_native_subagents.json'
QUEUE=ROOT/'state/dispatcher/state.json'
PACKAGE=ROOT/'state/dispatcher/project_executor/package'
PREDECESSOR_ID='0V14-14.relay.zip_extract_budget.5d39023513b45714'
PREDECESSOR_MANIFEST_SHA='b2cec01f43cb8434b5a050874082f7743f4ebe51a1d767fd899321d74e114c39'
PARENT='0V14-14'
PARENT_SPEC_SHA='3ace28409839c1e1259e5a24b7d40c11bf9dec3445b2b0073ef90ecc22b2216e'
TASK_ID='0V14-14.project.reviewed_zip_bounded_fallback.20261119'
SOURCE='merge_web_source.py'
BEFORE_SHA='a580a7d9f3efd570cf4e84396ceb3e6f980fe2dc846d0fda633b6e65b4c36b54'
TEST_SHA='97c433b8893514f5812b69fd53b0bb1e25d1fcd7b290f35c72407ad54b989667'
CONFIG_SHA='50b9914df62ffb13752aec28cc0028f87e676c7e68057c417363d108eaf25b87'
SOURCE_FILES_SHA='3229b2863e35b4179259ae651724051c0c2b6dbb9eab798386a95db1fa74e5e9'
CALLBACK_SHA='eac3ce9e2d8c862d1a7917ec447ea72e84454b7775a4260ad1e72e59de96fe11'
HELPER_SHA='8470a6720ca69864bbc4e6e630a1f853344839af424d3829dcdf1774442db609'
PATCH_GIT_BLOB_SHA='f77860aeeb96603447a994a5a16b19c141441e91'
IDENTITY={
 'expected_director':{'pid':359172,'start_ticks':184639742},
 'expected_workers':[
   {'pid':359266,'start_ticks':184640911},
   {'pid':359267,'start_ticks':184640911},
   {'pid':359268,'start_ticks':184640911}],
 'protected_processes':{
   'chat':{'pid':3266857,'start_ticks':172046662},
   'proxy':{'pid':356544,'start_ticks':184602380},
   'web':{'pid':356735,'start_ticks':184603716}}}
try:
    BUNDLE=__NOX_BUNDLE_JSON__
except NameError:
    BUNDLE={}

def hold(condition, code):
    if not condition:
        raise RuntimeError('HOLD_ZIP_REVIEWED_'+code)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def encoded(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,
                      separators=(',',':'),allow_nan=False).encode()

def module(name, raw):
    instance=types.ModuleType(name)
    instance.__file__='<verified-owner>/' + name+'.py'
    exec(compile(raw,instance.__file__,'exec'),instance.__dict__)
    return instance

def prepare():
    hold(re.fullmatch('[0-9]{1,24}',os.environ.get('NOX_OWNER_REQUEST_ID',''))
         and re.fullmatch('[0-9a-f]{40}',os.environ.get('NOX_OWNER_SOURCE_SHA','')),
         'OWNER_CONTEXT')
    expected={'owner_systemic_reviewed_publish.py','continuous_transaction_helpers.py',
              'merge_web_source.py'}
    hold(isinstance(BUNDLE,dict) and set(BUNDLE)==expected,'BUNDLE_SCOPE')
    assets={name:base64.b64decode(value,validate=True) for name,value in BUNDLE.items()}
    hold(all(0<len(value)<=1024*1024 for value in assets.values()),'BUNDLE_LIMIT')
    hold(sha(assets['continuous_transaction_helpers.py'])==HELPER_SHA,
         'HELPER_SOURCE_PIN')
    patch=assets['merge_web_source.py']
    git_blob=b'blob '+str(len(patch)).encode()+b'\0'+patch
    hold(hashlib.sha1(git_blob).hexdigest()==PATCH_GIT_BLOB_SHA,'REVIEWED_PATCH_PIN')
    compile(patch,'<sha-reviewed-zip-patch>','exec')
    helper=module('zip_reviewed_helpers',assets['continuous_transaction_helpers.py'])
    hold(helper.stop_clear(ROOT),'STOP')
    config_raw=helper.read_regular(CONFIG,2*1024*1024)
    hold(sha(config_raw)==CONFIG_SHA,'CONFIG_SHA')
    config=json.loads(config_raw)
    hold(config.get('owner_authorized') is True and
         config.get('instance_id')==60509551 and
         config.get('target')==config.get('global_worker_cap')==3 and
         config.get('execution_mode')=='NATIVE_PROJECT_V1' and
         config.get('mode')=='NORMAL','OWNER_SCOPE')
    current=config.get('systemic_relay')
    hold(isinstance(current,dict) and current.get('sha256')==PREDECESSOR_MANIFEST_SHA,
         'MANIFEST_POINTER')
    source=helper.source_snapshot(ROOT,config)
    hold(source['files_sha256']==SOURCE_FILES_SHA
         and source['files'][SOURCE]['sha256']==BEFORE_SHA
         and source['files']['test_nox_merge_overlay_paths.py']['sha256']==TEST_SHA,
         'SOURCE_CHANGED')
    # The initial live ZIP mission is allowed to finish naturally. A model
    # result, timeout, STOP or missing S03 is never licence to overwrite it.
    state,active=helper.queue_idle(ROOT)
    hold(not active,'PRIOR_CLAIM_ACTIVE')
    predecessor=state['tasks'].get(PREDECESSOR_ID)
    hold(isinstance(predecessor,dict) and predecessor.get('status')=='blocked'
         and predecessor.get('handler')=='owner_native_project_work'
         and predecessor.get('parent_task_id')==PARENT
         and (predecessor.get('native_worker_lease') or {}).get('phase')=='SETTLED',
         'PRIOR_NOT_SETTLED_BLOCKED')
    result=predecessor.get('result') or {}
    receipt=result.get('receipt') or {}
    event=receipt.get('worker_result') or {}
    evidence=event.get('project_evidence') or {}
    reason=evidence.get('reason')
    hold(result.get('verified') is True and result.get('scope')=='SOURCE_PATCH_TESTED'
         and isinstance(reason,str) and re.fullmatch('[A-Z][A-Z0-9_]{4,127}',reason)
         and evidence.get('state')=='BLOCKED_PLANNER'
         and evidence.get('project_source_changed') is False
         and receipt.get('phase')=='PROJECT_WORK_BLOCKED_ORIGINAL_NOT_ACCEPTED'
         and receipt.get('original_task_accepted') is False
         and receipt.get('project_source_changed') is False
         and receipt.get('plan_sha256') is None
         and receipt.get('claim')==predecessor.get('owner_claim'),
         'PRIOR_RECEIPT_SCOPE')
    prior_contract=predecessor.get('params',{}).get('contract_sha256')
    hold(isinstance(prior_contract,str) and re.fullmatch('[a-f0-9]{64}',prior_contract),
         'PRIOR_CONTRACT_SHA')
    contract_bytes=helper.read_regular(PACKAGE/'contracts'/(prior_contract+'.json'),
                                       2*1024*1024)
    hold(sha(contract_bytes)==prior_contract,'PRIOR_CONTRACT_CHANGED')
    contract=json.loads(contract_bytes)
    context=[{'path':SOURCE,'sha256':BEFORE_SHA},
             {'path':'test_nox_merge_overlay_paths.py','sha256':TEST_SHA}]
    verification={'kind':'python_unittest',
                  'modules':['test_nox_merge_overlay_paths'],
                  'min_tests':6,'timeout_sec':120}
    hold(contract.get('context')==context
         and contract.get('editable_paths')==[SOURCE]
         and contract.get('verification')==verification
         and contract.get('parent_task_id')==PARENT
         and contract.get('queue_id')=='Q4_INTEGRATION_ACCEPTANCE',
         'PRIOR_TEST_CONTRACT_CHANGED')
    after=sha(patch)
    hold(after!=BEFORE_SHA,'NO_PATCH_CHANGE')
    plan={
      'schema':'NOX_PROJECT_WORK_PLAN_V1',
      'task_id':TASK_ID,
      'parent_task_id':PARENT,
      'queue_id':'Q4_INTEGRATION_ACCEPTANCE',
      'root_id':'NOX_PROJECT_SOURCE',
      'operation':'apply_reviewed_files',
      'review_origin':'OWNER_REVIEWED',
      'spec_sha256':PARENT_SPEC_SHA,
      'context':context,
      'files':[{'path':SOURCE,'before_sha256':BEFORE_SHA,
                'after_sha256':after,'payload_sha256':after}],
      'verification':verification,
      'acceptance_scope':'SOURCE_PATCH_TESTED',
      'original_task_accepted':False
    }
    plan_bytes=encoded(plan)
    row={'id':TASK_ID,'handler':'owner_native_project_work',
         'queue_id':'Q4_INTEGRATION_ACCEPTANCE','resource':'CPU_LIGHT',
         'priority':'P1','deps':[],'estimated_cost':2,
         'source_sha256':CALLBACK_SHA,
         'params':{'parent_task_id':PARENT,'plan_sha256':sha(plan_bytes)},
         'title':'Apply independently reviewed bounded ZIP extraction to existing WEB merge'}
    predecessor_spec={
       'task_id':PREDECESSOR_ID,
       'parent_task_id':PARENT,
       'status':'blocked',
       'receipt_sha256':result['receipt_sha256'],
       'contract_sha256':prior_contract,
       'reason':reason
    }
    helper_asset='transaction_helpers.py'
    plan_asset='reviewed_zip_plan.json'
    payload_asset='reviewed_zip_payload.source'
    assets_to_publish={
        helper_asset:assets['continuous_transaction_helpers.py'],
        plan_asset:plan_bytes,
        payload_asset:patch}
    spec={
        'schema':'NOX_SYSTEMIC_REVIEWED_PUBLISH_SPEC_V1',
        'assets':{name:sha(raw) for name,raw in assets_to_publish.items()},
        'helper_asset':helper_asset,
        'batches':[{
            'title':row['title'],'plan_asset':plan_asset,
            'payload_assets':{after:payload_asset},
            'catalog_row':row}],
        'predecessors':[predecessor_spec],
        'expected_callback_sha256':CALLBACK_SHA,
        'expected_config_sha256':CONFIG_SHA,
        'expected_source_files_sha256':SOURCE_FILES_SHA,
        **IDENTITY}
    return spec,assets_to_publish,assets['owner_systemic_reviewed_publish.py']

def run():
    spec,assets,publisher_raw=prepare()
    print('NOX_MAINT_ZIP_FALLBACK_PREFLIGHT='+json.dumps({
       'schema':'NOX_ZIP_FALLBACK_CAS_PREFLIGHT_V1',
       'task_id':TASK_ID,'prior_terminal_verified':True,
       'new_plan_sha256':spec['batches'][0]['catalog_row']['params']['plan_sha256'],
       'new_source_sha256':spec['batches'][0]['payload_assets'].keys().__iter__().__next__(),
       'source_workspace_written':False,
       'prior_task_replayed':False,'original_task_accepted':False},
       separators=(',',':')),flush=True)
    publisher=module('zip_reviewed_publisher',publisher_raw)
    encoded_assets={name:base64.b64encode(value).decode('ascii')
                    for name,value in assets.items()}
    receipt=publisher.run(encoded_assets,spec)
    hold(receipt['state']=='CATALOG_APPENDED_NATIVE_EXECUTION_PENDING',
         'PUBLISH_NOT_ADMITTED')
    print('NOX_MAINT_ZIP_FALLBACK_PUBLISHED='+json.dumps({
       'schema':'NOX_ZIP_FALLBACK_CAS_PUBLISH_V1',
       'state':receipt['state'],'task_id':TASK_ID,
       'native_completion_proven':False,'s03_integration_proven':False,
       'original_task_accepted':False},separators=(',',':')),flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)

if __name__=='__main__':
    run()
