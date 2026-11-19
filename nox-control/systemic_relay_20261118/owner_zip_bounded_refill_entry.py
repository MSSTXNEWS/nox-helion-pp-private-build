#!/usr/bin/env python3
"""Exactly one owner-reviewed mission admitted through EXISTING native relay.

One-shot, source-only task publication. It does not run a new daemon, create a
second queue, restart workers, alter model, train or claim integration. The
existing native publisher's exclusive owner lock and CAS stay authoritative.
"""
from __future__ import annotations

import base64
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import types

ROOT=Path('/root/nox')
PACKAGE=ROOT/'state/dispatcher/project_executor/package'
SOURCE=ROOT/'projects/owner_executor/source_workspace'
CONFIG=ROOT/'config/owner_native_subagents.json'
PREVIOUS='d58ed9b020a78c3c8fcbfd476b3b0eecfd235e50f3a6ded29c8cec550e1a4212'
PREVIOUS_CONFIG='7c05bfc72caf25fe3e0cd910039b6f4eac846d3f19d7a7a7ceb814bd879c01a5'
SOURCE_CENSUS='3229b2863e35b4179259ae651724051c0c2b6dbb9eab798386a95db1fa74e5e9'
CALLBACK='eac3ce9e2d8c862d1a7917ec447ea72e84454b7775a4260ad1e72e59de96fe11'
HELPER_SHA='8470a6720ca69864bbc4e6e630a1f853344839af424d3829dcdf1774442db609'
FILE_SHA='a580a7d9f3efd570cf4e84396ceb3e6f980fe2dc846d0fda633b6e65b4c36b54'
TEST_SHA='97c433b8893514f5812b69fd53b0bb1e25d1fcd7b290f35c72407ad54b989667'
PARENT_SHA='3ace28409839c1e1259e5a24b7d40c11bf9dec3445b2b0073ef90ecc22b2216e'
try:
    BUNDLE=__NOX_BUNDLE_JSON__
except NameError:
    BUNDLE={}

def require(ok,what):
    if not ok:
        raise RuntimeError('HOLD_ZIP_REFILL_'+what)

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),
                      ensure_ascii=False,allow_nan=False).encode('utf-8')

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def load(name,raw):
    obj=types.ModuleType(name)
    obj.__file__='<owner-reviewed>/' + name+'.py'
    exec(compile(raw,obj.__file__,'exec'),obj.__dict__)
    return obj

def mission():
    return {
      'mission_id':'zip_extract_budget',
      'revision':1,
      'parent_task_id':'0V14-14',
      'queue_id':'Q4_INTEGRATION_ACCEPTANCE',
      'priority':'P1',
      'repeat_policy':'ONCE_PER_REVIEWED_REVISION',
      'root_id':'NOX_PROJECT_SOURCE',
      'title':'Prevent unbounded expansion of pinned WEB ZIP archives',
      'instruction':(
        'Review merge_web_source.py only. The existing merge(v4,v11,overlay,out) '
        'calls ZipFile.extractall(out) after validating the archive SHA and '
        'path/member names. A hash-pinned archive can still contain excessive '
        'total uncompressed sizes, too many entries, high expansion ratios or '
        'unsafe special file types. Add a bounded preflight BEFORE any extraction '
        'that rejects oversized total uncompressed archives, excessive members, '
        'individual decompression bombs and special entries. Choose documented '
        'limits with enough headroom for the known V4/V11 WEB assets, and '
        'never silently truncate or skip valid members. Preserve exact file '
        'layout, hashing, overlay CAS and atomic source copying. Do not touch '
        'test files, S03, weights, process lifecycle or any other file. Run '
        'the pinned existing test_nox_merge_overlay_paths suite, then report '
        'what additional malicious ZIP fixture remains untested. A green '
        'existing suite is not proof of new bomb handling; verify the source '
        'diff and a bounded negative fixture before further acceptance.'
      ),
      'context':[
        {'path':'merge_web_source.py','sha256':FILE_SHA},
        {'path':'test_nox_merge_overlay_paths.py','sha256':TEST_SHA}
      ],
      'editable_paths':['merge_web_source.py'],
      'allowed_new_paths':[],
      'verification':{
        'kind':'python_unittest',
        'modules':['test_nox_merge_overlay_paths'],
        'min_tests':6,
        'timeout_sec':120
      },
      'budget':{'lane':'model','max_model_turns':24,'cpu_seconds':90,
                'max_searches':0,'max_output_bytes':49152},
      'defect':{
        'observed_source_sha256':FILE_SHA,
        'finding':'Current ZipFile.extractall follows only SHA/member-name validation, with no aggregate uncompressed byte budget or member-count limit.',
        'expected_delta':'Enforce bounded ZIP entry count, decompressed output budget and archive member type preflight before any extraction; preserve valid archive semantics.',
        'verification_limit':'Six immutable overlay regression tests; an independent malicious ZIP negative fixture and source diff review are still required.'
      },
      'experience':[],
      'focus_regions':[]
    }

def prepared():
    require(re.fullmatch('[0-9]{1,24}',os.getenv('NOX_OWNER_REQUEST_ID',''))
            and re.fullmatch('[a-f0-9]{40}',os.getenv('NOX_OWNER_SOURCE_SHA','')),
            'OWNER_CONTEXT')
    require(set(BUNDLE)=={'owner_systemic_relay_publish.py',
                          'continuous_transaction_helpers.py'},'BUNDLE_SCOPE')
    raw={name:base64.b64decode(body,validate=True)
         for name,body in BUNDLE.items()}
    require(all(0<len(value)<=65536 for value in raw.values()),'BUNDLE_BYTES')
    require(sha(raw['continuous_transaction_helpers.py'])==HELPER_SHA,'HELPER_PIN')
    helper=load('nox_zip_owner_helper',raw['continuous_transaction_helpers.py'])
    old_config_raw=helper.read_regular(CONFIG,2*1024*1024)
    require(sha(old_config_raw)==PREVIOUS_CONFIG,'CONFIG_CHANGED')
    config=json.loads(old_config_raw)
    require(config.get('instance_id')==60509551 and
            config.get('owner_authorized') is True and
            config.get('global_worker_cap')==3 and
            config.get('target')==3 and
            config.get('mode')=='NORMAL' and
            config.get('execution_mode')=='NATIVE_PROJECT_V1','OWNER_SCOPE')
    reference=config.get('systemic_relay')
    require(reference=={'path':str(PACKAGE/'relay'/(PREVIOUS+'.json')),
                        'sha256':PREVIOUS},'CURRENT_MANIFEST_POINTER')
    raw_previous=helper.read_regular(Path(reference['path']),2*1024*1024)
    require(sha(raw_previous)==PREVIOUS and
            canonical(json.loads(raw_previous))==raw_previous,'MANIFEST_PIN')
    previous=json.loads(raw_previous)
    require(previous.get('revision')==2 and
            previous.get('registry',{}).get('parents',{}).get('0V14-14',{}).get('spec_sha256')==PARENT_SHA,
            'PREVIOUS_REGISTRY')
    source=helper.source_snapshot(ROOT,config)
    require(source['files_sha256']==SOURCE_CENSUS and
            source['files']['merge_web_source.py']['sha256']==FILE_SHA and
            source['files']['test_nox_merge_overlay_paths.py']['sha256']==TEST_SHA,
            'CURRENT_SOURCE_PIN')
    require(helper.stop_clear(ROOT),'OWNER_STOP')
    runtime=helper.read_regular(ROOT/'scripts/owner_systemic_refill.py',1024*1024)
    require(sha(runtime)==config['module_pins']['owner_systemic_refill.py'],
            'REFILL_RUNTIME_PIN')
    refill=load('nox_zip_reviewed_refill',runtime)
    m=mission()
    new=deepcopy(previous)
    new.update(revision=previous['revision']+1,
               previous_manifest_sha256=PREVIOUS,
               missions=[m],
               producer_evidence={
                   'review_scope':'OWNER_REVIEWED_ONE_SHOT_SOURCE_MISSION',
                   'source_preimage_sha256':FILE_SHA,
                   'immutable_verifier_sha256':TEST_SHA,
                   'original_task_accepted':False,
                   'autonomous_approval_claimed':False
               })
    refill.validate_manifest(new)
    task_id=m['parent_task_id']+'.relay.'+m['mission_id']+'.'+refill._input(m)[:16]
    contract=refill._contract(m,task_id)
    cbytes=refill.canonical(contract)
    csha=sha(cbytes)
    mbytes=refill.canonical(new)
    msha=sha(mbytes)
    require(msha != PREVIOUS and csha==refill.digest(contract),'CONTRACT_BUILD')
    # Pure selector must identify exactly one new job. A stale/deferred source
    # is never rewritten or treated as permission to replay another task.
    existing=json.loads(helper.read_regular(ROOT/'state/dispatcher/state.json',
                                            16*1024*1024))['tasks']
    capacity={'slots_available':3,'now':0,'callback_sha256':CALLBACK,
              'manifest_sha256':msha,'reserved_sources':[]}
    selection=refill.select_next(new,existing,
      {'NOX_PROJECT_SOURCE':{'merge_web_source.py':FILE_SHA,
                             'test_nox_merge_overlay_paths.py':TEST_SHA}},
      capacity)
    require(len(selection.get('rows',[]))==1 and
            selection['rows'][0]['id']==task_id and
            selection['rows'][0]['params']['contract_sha256']==csha,
            'NO_UNIQUE_READY_MISSION')
    manifest_name='relay_manifest.json'
    contract_name='zip_extract_budget.json'
    transport={
      'transaction_helpers.py':raw['continuous_transaction_helpers.py'],
      manifest_name:mbytes,
      contract_name:cbytes
    }
    spec={
      'schema':'NOX_SYSTEMIC_RELAY_PUBLISH_SPEC_V1',
      'assets':{k:sha(v) for k,v in transport.items()},
      'helper_asset':'transaction_helpers.py',
      'package_paths':{
        manifest_name:'relay/'+msha+'.json',
        contract_name:'contracts/'+csha+'.json'
      },
      'manifest_sha256':msha,
      'expected_config_sha256':PREVIOUS_CONFIG,
      'previous_manifest_sha256':PREVIOUS,
      'expected_source_files_sha256':SOURCE_CENSUS,
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
    return raw,transport,spec,task_id

def run():
    raw,transport,spec,task_id=prepared()
    print('NOX_MAINT_ZIP_REFILL_PREPARED='+json.dumps({
      'schema':'NOX_ZIP_REVIEWED_TASKPACK_PREPARED_V1',
      'task_id':task_id,'manifest_sha256':spec['manifest_sha256'],
      'previous_manifest_sha256':PREVIOUS,
      'source_unchanged':True,'worker_cap':3,
      'native_job_created_before_publish':False,
      'original_task_accepted':False
    },separators=(',',':')),flush=True)
    publisher=load('nox_zip_owner_publisher',raw['owner_systemic_relay_publish.py'])
    bundle={name:base64.b64encode(value).decode('ascii')
            for name,value in transport.items()}
    receipt=publisher.run(bundle,spec)
    require(receipt.get('state')=='PUBLISHED_HOT_REFILL_PENDING',
            'PUBLISH_RECEIPT_NOT_ACCEPTED')
    print('NOX_MAINT_ZIP_REFILL_PUBLISH='+json.dumps({
      'schema':'NOX_ZIP_REFILL_PUBLISH_EVIDENCE_V1',
      'task_id':task_id,
      'manifest_sha256':spec['manifest_sha256'],
      'state':receipt['state'],
      'native_execution_proven':False,
      's03_result_proven':False,
      'source_files_modified':False,
      'existing_dispatcher_preserved':True,
      'original_task_accepted':False
    },separators=(',',':')),flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)

if __name__=='__main__':
    run()
