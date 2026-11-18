#!/usr/bin/env python3
"""Freeze one exact reviewed merge recovery against a verified current proxy.

This local assembler never runs the old three-task builder, edits the operator,
contacts the host, executes the payload, or runs tests. Chat completion is not a
dependency: a verified pre-mutation HOLD also preserves the observed lifetime.
Native admission retains the existing publisher and bounded queue settling.
"""
from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import json
from pathlib import Path
import re


HERE = Path(__file__).resolve().parent
BASE = HERE.parent
REPO = BASE.parents[1]
PLAN_SHA = 'bb6d20856fd56583e8440d85faac57ba8da9751440d487c5540b8e2896f9db96'
PAYLOAD_SHA = 'a580a7d9f3efd570cf4e84396ceb3e6f980fe2dc846d0fda633b6e65b4c36b54'
CONTRACT_SHA = '847f2aca0998b4029061c94ebc60bbf989c07a32b174720aa955239cae2d86fd'
MANIFEST_SHA = 'd58ed9b020a78c3c8fcbfd476b3b0eecfd235e50f3a6ded29c8cec550e1a4212'
HELPER_SHA = '8470a6720ca69864bbc4e6e630a1f853344839af424d3829dcdf1774442db609'
PUBLISHER_SHA = '93a0e25a2aea836b568bedc506c8445d2cd2ecbef3b7bd84d37c96162941d1c6'
CALLBACK_SHA = '0193c511168489637b6df041bee2daf79bd42bd338c4ff5f9a6b129652dc4a13'
CONFIG_SHA = '581ea94bf6b255afe3d8246529f120fc86edb962ee328ac24afdb377ed948e0c'
CENSUS_SHA = 'e2286de8bda894bdeeb5bfa94e112d5f3304ad49b281a89b1147eda867fde776'
PREDECESSOR_ID = '0V14-14.relay.merge_verified_descriptors.0b806763b859497e'
PREDECESSOR_RECEIPT = '43a0c7cbdd588a867c709609f8acdae6692d850edc32c45405747ae06acf5fca'
PREDECESSOR_CLAIM = 'feae0b1f48b1d440f869d1dd'
PREDECESSOR_REASON = 'HOLD_PROJECT_PLANNER_MODEL_INCOMPLETE_RESPONSE'
CHAT_HOLD_READBACK_SHA = '7bdc8f5c58aa57dba86238b08533f1a92ea9c267a57a4f2fb98932f8a373b135'
CHAT_HOLD_RECEIPT_SHA = '4f854c83232358d6f928558f7a41816a08213bbcecb04895e61c17a436207b7b'
NEW_TASK_ID = '0V14-14.project.systemic_reviewed_merge.20261118'
TITLE = 'Apply reviewed descriptor verification for archive and overlay source merge'


def require(ok, code):
    if not ok:
        raise ValueError('HOLD_REVIEWED_MERGE_BUILD_' + code)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pinned(path, expected):
    raw = path.read_bytes()
    require(sha(raw) == expected, 'LOCAL_PIN')
    return raw


def read_report(path):
    raw = path.read_bytes()
    require(0 < len(raw) <= 8 * 1024 * 1024, 'REPORT_BOUND')
    outer = json.loads(raw)
    require(isinstance(outer, dict), 'REPORT_SCHEMA')
    return outer.get('data', outer), sha(raw)


def one(report, key):
    rows = report.get(key)
    require(isinstance(rows, list) and len(rows) == 1, key)
    return rows[0]


def write_once(path, raw):
    require(not path.exists() or path.read_bytes() == raw, 'OUTPUT_EXISTS')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--chat-receipt', type=Path)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--output', type=Path, default=HERE / 'prepared_v3')
    args = parser.parse_args()
    require(args.prepare_only != bool(args.chat_receipt), 'CHOOSE_PREPARE_OR_FINAL')
    observed, snapshot_sha = read_report(args.snapshot)
    require(observed.get('NOX_MAINT_REMOTE_EXIT_CODE') == [0], 'SNAPSHOT_EXIT')
    census = one(observed, 'NOX_MAINT_SCOPE_PROJECT_SOURCE_WORKSPACE_CENSUS')
    require(census.get('two_reads_match') is True and census.get('complete_allowed_files_read') is True
            and census.get('config_unchanged_during_census') is True
            and census.get('bootstrap_unchanged_during_census') is True
            and census.get('unattributed_changed_paths') == [] and census.get('read_errors') == []
            and census.get('changed_between_reads') == [] and census.get('count') == 33
            and census.get('config_sha256') == CONFIG_SHA and census.get('files_sha256') == CENSUS_SHA
            and sha(encoded(census['files'])) == CENSUS_SHA, 'SOURCE_CENSUS')
    config = one(observed, 'NOX_MAINT_SCOPE_PROJECT_EXECUTOR_CONFIG')
    require(config['sha256'] == CONFIG_SHA and config['mode'] == 'NATIVE_PROJECT_V1'
            and config['worker_cap'] == 3, 'CONFIG_PIN')
    workers = observed.get('NOX_MAINT_SCOPE_POST_WORKERS')
    require(isinstance(workers, list) and len(workers) == 2, 'WORKER_SAMPLES')
    first, latest = workers
    require(first['observed_director'] == latest['observed_director']
            and len(first['workers']) == len(latest['workers']) == 3, 'DIRECTOR_STABLE')
    old_workers = {row['observed']['pid']: row for row in first['workers']}
    for row in latest['workers']:
        previous = old_workers.get(row['observed']['pid'])
        require(previous and previous['verified'] is True and row['verified'] is True
                and all(previous['observed'][key] == row['observed'][key]
                        for key in ('pid', 'ppid', 'pgrp', 'start_ticks'))
                and previous['claimed']['current_task'] is None and row['claimed']['current_task'] is None
                and row['claimed']['heartbeat_at'] > previous['claimed']['heartbeat_at'], 'WORKER_STABLE')
    require(latest['project']['received_unique_tasks'] == 295
            and all(latest['project']['project_status'][key] == 0 for key in ('pending', 'running', 'unknown'))
            and latest['systemic_relay']['manifest_sha256'] == MANIFEST_SHA, 'PROJECT_TERMINAL')
    executions = {row['id']: row for row in observed['NOX_MAINT_SCOPE_PROJECT_EXECUTION']}
    require(NEW_TASK_ID not in executions, 'ALREADY_ADMITTED')
    row = executions.get(PREDECESSOR_ID)
    require(row and row['status'] == 'blocked' and row['parent_task_id'] == '0V14-14'
            and row['receipt_sha_matches'] is True and row['receipt_claim_matches'] is True
            and row['project_evidence_sha_matches'] is True
            and row['result']['verified'] is True and row['result']['receipt_sha256'] == PREDECESSOR_RECEIPT
            and row['owner_claim']['nonce'] == PREDECESSOR_CLAIM
            and row['s03']['verified'] is True and row['s03']['receipt_sha256'] == PREDECESSOR_RECEIPT
            and row['s03']['s03_item_id'] == 'S03-cf1b762a31a449b4', 'PREDECESSOR_RECEIPT')
    require(row['project_evidence']['reason'] == PREDECESSOR_REASON
            and row['project_evidence']['state'] == 'BLOCKED_PLANNER'
            and row['project_evidence']['project_source_changed'] is False
            and row['receipt']['project_source_changed'] is False and row['receipt']['plan_sha256'] is None
            and row['receipt']['scope'] == 'SOURCE_PATCH_TESTED'
            and row['receipt']['original_task_accepted'] is False and row['receipt']['live_service_deployed'] is False
            and row['native_worker_lease']['phase'] == 'SETTLED'
            and row['native_worker_lease']['claim'] == PREDECESSOR_CLAIM
            and row['native_worker_lease']['receipt_sha256'] == PREDECESSOR_RECEIPT,
            'PREDECESSOR_FAILURE_SCOPE')
    require(row['receipt_source']['source_authorized'] is True
            and row['receipt_source']['matches_config_callback_pin'] is True
            and row['receipt_source']['current_callback_sha256'] == CALLBACK_SHA
            and row['receipt']['source_sha256'] == CALLBACK_SHA
            and row['systemic_relay']['reviewed_row']['params']['contract_sha256'] == CONTRACT_SHA,
            'CALLBACK_CONTRACT')
    pinned(BASE / 'runtime/owner_subagent_dispatcher.py', CALLBACK_SHA)
    plan_raw = pinned(BASE / 'next_reviewed_source/reviewed_merge_plan.json', PLAN_SHA)
    payload = pinned(BASE / 'next_reviewed_source/merge_web_source.py', PAYLOAD_SHA)
    contract = json.loads(pinned(BASE / 'next_pack_44368502183/package/contracts' / (CONTRACT_SHA + '.json'), CONTRACT_SHA))
    manifest = json.loads(pinned(BASE / 'next_pack_44368502183/package/relay' / (MANIFEST_SHA + '.json'), MANIFEST_SHA))
    require(manifest['registry']['total_original_ids'] == 295 and len(manifest['registry']['parents']) == 295,
            'ORIGINAL_DENOMINATOR')
    plan = json.loads(plan_raw)
    require(encoded(plan) == plan_raw and plan['task_id'] == NEW_TASK_ID
            and plan['parent_task_id'] == '0V14-14' and plan['queue_id'] == 'Q4_INTEGRATION_ACCEPTANCE'
            and plan['root_id'] == 'NOX_PROJECT_SOURCE' and plan['review_origin'] == 'OWNER_REVIEWED'
            and plan['operation'] == 'apply_reviewed_files' and plan['original_task_accepted'] is False
            and plan['acceptance_scope'] == 'SOURCE_PATCH_TESTED'
            and plan['spec_sha256'] == manifest['registry']['parents']['0V14-14']['spec_sha256'], 'PLAN_SCOPE')
    require(plan['verification'] == contract['verification']
            == {'kind': 'python_unittest', 'min_tests': 6, 'modules': ['test_nox_merge_overlay_paths'], 'timeout_sec': 120}
            and plan['context'] == contract['context']
            and set(contract['editable_paths']) == {'merge_web_source.py'}, 'TRUSTED_VERIFICATION')
    require(len(plan['files']) == 1 and plan['files'][0] == {
        'path': 'merge_web_source.py', 'before_sha256': census['files']['merge_web_source.py']['sha256'],
        'after_sha256': PAYLOAD_SHA, 'payload_sha256': PAYLOAD_SHA}
        and all(census['files'][part['path']]['sha256'] == part['sha256'] for part in plan['context']), 'PLAN_PREIMAGES')
    ast.parse(payload)
    helper = pinned(REPO / 'nox-control/continuous_executor_20261118/assets/continuous_transaction_helpers.py', HELPER_SHA)
    publisher = pinned(BASE / 'owner_systemic_reviewed_publish.py', PUBLISHER_SHA)
    assets = {'reviewed_systemic_transaction_helpers.py': helper,
              'reviewed_merge_plan.json': plan_raw, 'reviewed_merge_payload.source': payload}
    asset_sources = {}
    for name, raw in assets.items():
        target = args.output / 'assets' / name
        write_once(target, raw)
        asset_sources[name] = str(target.resolve().relative_to(REPO))
    catalog_row = {'id': NEW_TASK_ID, 'handler': 'owner_native_project_work', 'queue_id': plan['queue_id'],
                   'resource': 'CPU_LIGHT', 'priority': 'P1', 'deps': [], 'estimated_cost': 2,
                   'source_sha256': CALLBACK_SHA,
                   'params': {'parent_task_id': '0V14-14', 'plan_sha256': PLAN_SHA}, 'title': TITLE}
    catalog = one(observed, 'NOX_MAINT_SCOPE_PROJECT_CATALOG')
    require(all(part['id'] != NEW_TASK_ID for part in catalog['new_project_rows']), 'CATALOG_DUPLICATE')
    queue = one(observed, 'NOX_MAINT_SCOPE_PROJECT_QUEUE')
    services = one(observed, 'NOX_MAINT_SCOPE_SNAPSHOT_B')['services']
    def service(name):
        choices = [part['identity'] for part in services if part['service'] == name and part['state'] == 'RUNNING']
        require(len(choices) == 1, 'SERVICE')
        return {key: choices[0][key] for key in ('pid', 'ppid', 'pgrp', 'start_ticks')}
    protected = {'chat': service('nox-ds41-8098'), 'web': service('nox-web29-18775')}
    previous_proxy = service('nox-proxy')
    partial = {'schema': 'NOX_REVIEWED_MERGE_PREPARED_INPUTS_V1',
        'state': 'WAITING_FOR_VERIFIED_CURRENT_PROXY_RECEIPT',
        'native_publish_performed': False, 'tests_executed': False, 'operator_modified': False,
        'original_task_accepted': False, 'snapshot_sha256': snapshot_sha,
        'expected_config_sha256': CONFIG_SHA, 'expected_source_files_sha256': CENSUS_SHA,
        'expected_manifest_sha256': MANIFEST_SHA, 'source_files': census['files'],
        'predecessor': {'task_id': PREDECESSOR_ID, 'receipt_sha256': PREDECESSOR_RECEIPT,
                        'claim': PREDECESSOR_CLAIM, 's03_item_id': row['s03']['s03_item_id'],
                        'reason': PREDECESSOR_REASON, 'status': 'blocked', 'lease_phase': 'SETTLED'},
        'catalog_row': catalog_row, 'plan_sha256': PLAN_SHA, 'payload_sha256': PAYLOAD_SHA,
        'publisher_sha256': PUBLISHER_SHA, 'asset_sources': asset_sources,
        'observed_queue': {'rows': queue['rows'], 'counts': queue['counts'], 'sha256': queue['sha256']},
        'existing_global_running_is_not_waived': True, 'native_settle_deadline_seconds': 8,
        'legacy_pending_is_not_an_admission_blocker': True,
        'last_observed_proxy_not_final_publish_pin': previous_proxy,
        'native_queue_writes_by_publisher': 0, 'catalog_append_rows': 1,
        'full_receipt_claim_and_s03_rechecked_by_native_publisher': True}
    write_once(args.output / 'prepared_inputs.json', encoded(partial))
    write_once(args.output / 'asset_sources.json', encoded(asset_sources))
    write_once(args.output / 'catalog_row.json', encoded(catalog_row))
    if args.prepare_only:
        print(json.dumps({'state': partial['state'], 'output': str(args.output), 'assets': len(assets),
                          'task_id': NEW_TASK_ID, 'native_operation_performed': False}))
        return
    chat_report, chat_sha = read_report(args.chat_receipt)
    require(chat_report.get('NOX_MAINT_HOST_PIN') == ['VERIFIED']
            and chat_report.get('NOX_MAINT_AUTHENTICATED_INSTANCE') == [60509551], 'CHAT_NATIVE_PROVENANCE')
    chat_event = one(chat_report, 'NOX_MAINT_REPAIR')
    require(chat_event.get('kind') == 'chat_decomposition_install', 'CHAT_RECEIPT_KIND')
    chat = chat_event['data']
    require(chat.get('schema') == 'NOX_CHAT_DECOMPOSITION_INSTALL_V1'
            and str(one(chat_report, 'NOX_MAINT_AUTHORIZED_COMMENT_ID')) == chat.get('request')
            and chat.get('rollback_verified') is False and 'receipt_error' not in chat
            and chat.get('model_restarted') is False and chat.get('worker_restarts') == 0
            and chat.get('queue_or_claims_written') is False
            and chat.get('new_permissions_or_credentials') is False, 'CHAT_SCOPE')
    # Read the raw native JSON losslessly: inode nanoseconds are large integers.
    # Reject rounded inspection projections instead of calling them canonical.
    require(re.fullmatch('[a-f0-9]{64}', str(chat.get('receipt_sha256')))
            and sha(encoded({key: value for key, value in chat.items() if key != 'receipt_sha256'}))
                == chat['receipt_sha256'], 'CHAT_CANONICAL_RECEIPT_DIGEST')
    require(chat['proxy_before']['pid'] == previous_proxy['pid']
            and str(chat['proxy_before']['starttime']) == str(previous_proxy['start_ticks']), 'CHAT_PROXY_PREDECESSOR')
    def http_proof(key, expected, count):
        http = chat[key]
        require(http['port'] == 8080 and http['path'] == '/nox-web-v29/pc/v24/nox-v24-chat.js'
                and http['status'] == 200 and http['sha256'] == expected and http['bytes_read'] == count
                and http['content_encoding'] == 'identity' and http['body_within_limit'] is True
                and http['credentials_used'] is True and http['session_created'] is True
                and http['session_closed'] is True and http['raw_body_or_credentials_exported'] is False,
                'CHAT_ASSET_HTTP')
    http_proof('public_asset_before', '92b952b6c7ee31f22ed74912d9444a88989c014694424083336660dce21a8a5b', 31906)
    if chat.get('state') == 'SOURCE_AND_PROXY_HEALTH_VERIFIED':
        require(chat_report.get('NOX_MAINT_REMOTE_EXIT_CODE') == [0]
                and chat_report.get('NOX_MAINT_REPAIR_COMPLETE') in (True, [True])
                and all(chat.get(key) is True for key in ('source_install_verified', 'proxy_restart_verified',
                                                         'protected_processes_unchanged')),
                'CHAT_SUCCESS')
        after = chat['proxy_after']
        require(type(after.get('pid')) is int and after['pid'] > 1
                and re.fullmatch('[0-9]{1,20}', str(after.get('starttime')))
                and (after['pid'], str(after['starttime'])) != (previous_proxy['pid'], str(previous_proxy['start_ticks'])),
                'CHAT_REPLACEMENT')
        http_proof('public_asset_after', '646fe556bb446aa0a7b30abd44f1ed41865877553ceef2bb703c85f6b112d5a2', 33602)
        protected['proxy'] = {'pid': after['pid'], 'start_ticks': int(after['starttime'])}
        proxy_binding = 'VERIFIED_CHAT_REPLACEMENT'
    else:
        require(chat_report.get('NOX_MAINT_REMOTE_EXIT_CODE') == [2]
                and chat_sha == CHAT_HOLD_READBACK_SHA and chat['receipt_sha256'] == CHAT_HOLD_RECEIPT_SHA
                and chat_report.get('NOX_MAINT_REPAIR_COMPLETE') in (False, [False])
                and chat.get('state') == 'HOLD_CHAT_DECOMPOSITION_INSTALL'
                and chat.get('reason') == 'HOLD_CHAT_DECOMPOSITION_CHAT_REQUEST_ACTIVE'
                and chat.get('changed') == [] and chat.get('proxy_stop_attempted') is False
                and chat.get('proxy_after') is None and chat.get('source_install_verified') is False
                and chat.get('proxy_restart_verified') is False, 'CHAT_PREMUTATION_HOLD')
        protected['proxy'] = {'pid': previous_proxy['pid'], 'start_ticks': previous_proxy['start_ticks']}
        proxy_binding = 'VERIFIED_UNCHANGED_PROXY_AFTER_CHAT_PREMUTATION_HOLD'
    spec = {'schema': 'NOX_SYSTEMIC_REVIEWED_PUBLISH_SPEC_V1',
        'assets': {name: sha(raw) for name, raw in assets.items()},
        'helper_asset': 'reviewed_systemic_transaction_helpers.py',
        'batches': [{'title': TITLE, 'plan_asset': 'reviewed_merge_plan.json',
                    'payload_assets': {PAYLOAD_SHA: 'reviewed_merge_payload.source'}, 'catalog_row': catalog_row}],
        'predecessors': [{'task_id': PREDECESSOR_ID, 'parent_task_id': '0V14-14', 'status': 'blocked',
                          'receipt_sha256': PREDECESSOR_RECEIPT, 'contract_sha256': CONTRACT_SHA,
                          'reason': PREDECESSOR_REASON}],
        'expected_callback_sha256': CALLBACK_SHA, 'expected_config_sha256': CONFIG_SHA,
        'expected_source_files_sha256': CENSUS_SHA,
        'expected_director': {key: latest['observed_director'][key] for key in ('pid', 'start_ticks')},
        'expected_workers': [{key: part['observed'][key] for key in ('pid', 'start_ticks')} for part in latest['workers']],
        'protected_processes': protected}
    require(publisher.count(b'SPEC = {}') == 1, 'PUBLISHER_TEMPLATE')
    entry = publisher.replace(b'SPEC = {}', ('SPEC = ' + repr(spec)).encode(), 1)
    bundle = {name: base64.b64encode(raw).decode() for name, raw in assets.items()}
    ast.parse(entry)
    ast.parse(entry.replace(b'__NOX_BUNDLE_JSON__', repr(bundle).encode(), 1))
    outputs = {'publish_spec.json': encoded(spec), 'publish_bundle.json': encoded(bundle),
               'owner_systemic_reviewed_merge_entry.py': entry}
    for name, raw in outputs.items():
        write_once(args.output / name, raw)
    final = {'schema': 'NOX_REVIEWED_MERGE_FINAL_BUILD_V1', 'state': 'READY_FOR_NATIVE_REVIEWED_PUBLISH',
             'outputs': {name: sha(raw) for name, raw in outputs.items()},
             'chat_proxy_proof_readback_sha256': chat_sha, 'chat_request': chat['request'],
             'chat_receipt_sha256': chat['receipt_sha256'], 'proxy_binding': proxy_binding,
             'chat_receipt_digest_recomputed_from_lossless_native_json': True,
             'chat_completion_is_merge_dependency': False,
             'protected_proxy': protected['proxy'], 'snapshot_sha256': snapshot_sha,
             'task_id': NEW_TASK_ID, 'native_operation_performed': False, 'tests_executed': False,
             'operator_modified': False, 'original_task_accepted': False}
    write_once(args.output / 'final_build.json', encoded(final))
    print(json.dumps(final, sort_keys=True))


if __name__ == '__main__':
    main()
