#!/usr/bin/env python3
"""One workspace.js replacement using reviewed exchange/rollback primitives."""
import base64
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import time
import types

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

BASE_NAME = 'owner_chat_stream_asset_install_v2.py'
BASE_SHA = 'f3b1bddf2f53e57f671774e76d6bc7d64f59e6f0a0a9642a34714643323a89fa'
CANDIDATE = 'workspace-owner-capabilities.js'
OLD_SHA = '9b77c5011da892769c7332826c4b35bce581fb121960c13694638657735fc0ae'
NEW_SHA = '984b604dc18d9a0c5224518e24b90e58b0b5e3bae89b2aa2996fec3dff5bb4a8'
OLD_BYTES, NEW_BYTES = 6451, 7278
SCHEMA = 'NOX_OWNER_WORKSPACE_ASSET_INSTALL_V1'
ACCEPTED = 'WORKSPACE_CAPABILITIES_ASSET_SOURCE_AND_HTTP_VERIFIED_BROWSER_PENDING'
COALESCED_SHA = '02d6a0fe1d67dd6d19c020d9cb7540611b1c5ed1dbefa304e483277d140ebffc'
DEPENDENCIES = {
    BASE_NAME: BASE_SHA,
    'owner_media_acceptance_entry.py': '73107aed7d1eaa72d92fe15d4f91c8c5878e560e9efcffaf4dbf583f500fbf60',
    'owner_native_repair.py': 'b3d1887b92cb805076301f6631e56b6e42c48e7dae02d62f2a272c10669644e0',
    CANDIDATE: NEW_SHA,
}
PRESERVED = (
    'state/owner_training_admission.json', 'scripts/run_train_volta_t866u.sh',
    'config/owner_training_status.json', 'config/owner_qwen_training_guard.json',
    'config/owner_qwen_media_handoff.json', 'config/owner_media_runtime.json',
    'config/owner_qwen_execution_revision.json', 'config/owner_hermes_warm.json',
    'scripts/qwen_student_training_entry.py', 'scripts/qwen_student_training_entry_revision.py',
    'scripts/owner_qwen_execution_revision.py', 'scripts/owner_qwen_revision_install.py',
    'scripts/owner_training_status.py', 'scripts/owner_qwen_training_guard.py',
    'scripts/owner_qwen_media_handoff.py', 'scripts/owner_qwen_media_guard.py',
    'scripts/owner_qwen_handback_retry.py', 'scripts/nox_dispatcher_t855u.py',
    'scripts/owner_hermes_hydrate.py', 'scripts/nox_admin.py', 'scripts/owner_chat_stream.py',
    'state/TRAIN_HOLD.flag', 'state/TRAIN_PAUSE_REQUEST.flag', 'state/OWNER_MAINTENANCE.flag',
)


def require(ok, code):
    if not ok:
        raise RuntimeError('HOLD_WORKSPACE_ASSET_' + code)


def prepared_library():
    require(re.fullmatch('[a-f0-9]{64}', NEW_SHA) and 0 < NEW_BYTES <= 65536, 'CANDIDATE_NOT_FROZEN')
    decoded = {}
    for name, pin in DEPENDENCIES.items():
        text = BUNDLE.get(name)
        require(isinstance(text, str) and 0 < len(text) <= 500000, 'BUNDLE_BOUND')
        raw = base64.b64decode(text, validate=True)
        require(0 < len(raw) <= 262144 and hashlib.sha256(raw).hexdigest() == pin, 'BUNDLE_PIN')
        decoded[name] = raw
    base = types.ModuleType('_nox_workspace_asset_primitives')
    base.__file__ = '/root/nox/scripts/' + BASE_NAME
    base.__dict__['__NOX_' + 'BUNDLE_JSON__'] = dict(BUNDLE)
    exec(compile(decoded[BASE_NAME], base.__file__, 'exec'), base.__dict__)
    original_site = base.SITE
    base.SITE = original_site / 'pc'
    base.ASSET = 'workspace.js'; base.URL = '/nox-web-v29/pc/workspace.js'
    base.AREA = base.STATE / 'owner_workspace_asset_installs'
    base.CANDIDATE = CANDIDATE; base.OLD_SHA = OLD_SHA; base.NEW_SHA = NEW_SHA
    base.OLD_BYTES = OLD_BYTES; base.NEW_BYTES = NEW_BYTES
    base.SCHEMA = SCHEMA; base.ACCEPTED = ACCEPTED
    base.PINS = {name: pin for name, pin in DEPENDENCIES.items() if name != BASE_NAME}
    base.PROTECTED = {**base.PROTECTED,
                      original_site / 'nox-v135-resonance-owner-bridge.js': COALESCED_SHA}
    candidate, auth, helper = base.bundle_sources()
    require(candidate == decoded[CANDIDATE] and len(candidate) == NEW_BYTES, 'CANDIDATE_BYTES')
    return base, candidate, auth, helper


def training_snapshot(base, helper):
    guarded = {}
    for name in PRESERVED:
        path = base.ROOT / name
        guarded[name] = base.digest(base.read(path)) if os.path.lexists(path) else None
    require(all(guarded[name] is not None for name in (
        'state/owner_training_admission.json', 'scripts/run_train_volta_t866u.sh',
        'config/owner_training_status.json', 'scripts/nox_admin.py')), 'REQUIRED_PRESERVED_FILE')
    service = helper.service_state('nox-train-volta-t866u')
    require(service.get('state') in ('RUNNING', 'STOPPED', 'EXITED', 'FATAL'), 'TRAINER_UNSETTLED')
    rows = helper.process_table()
    relevant = [row for row in rows.values() if row.get('service') == 'nox-train-volta-t866u'
                and row.get('state') not in ('Z', 'X')]
    if service['state'] == 'RUNNING':
        require(service.get('pid') in rows and any(row['pid'] == service['pid'] for row in relevant), 'TRAINER_UNREADABLE')
    else:
        require(not relevant and service.get('pid') is None, 'TRAINER_UNEXPECTED')
    processes = sorted([{'pid': row['pid'], 'ppid': row['ppid'], 'pgrp': row['pgrp'],
        'starttime': row['starttime'], 'cuda': row.get('cuda'),
        'argv_sha256': base.digest(base.encode(row['argv']))} for row in relevant], key=lambda row: row['pid'])
    return {'file_hashes': guarded, 'state': service['state'], 'pid': service.get('pid'),
            'observed_service_processes': processes,
            'scope': 'READABLE_EXISTING_TRAINING_SERVICE_PROCESSES_NOT_GLOBAL_PROCESS_COVERAGE'}


def page_reference(page):
    return len(re.findall(br'<script\b[^>]*\bsrc=[\"\'](?:\./workspace\.js|/nox-web-v29/pc/workspace\.js)[\"\'][^>]*>',
                          page, re.I)) == 1


def seal_result(base, journal_fd, record, undo):
    try:
        return base.private_json(journal_fd, 'receipt.json', record)
    except BaseException as exc:
        record.update(state='HOLD_WORKSPACE_ASSET_RECEIPT', success=False, receipt_error=base.safe(exc))
        if undo is not None:
            record['rollback_requested'] = True
            try:
                record['rollback_verified'] = undo()
            except BaseException as error:
                record.update(rollback_verified=False, rollback_reason=base.safe(error),
                              displaced_file_retained=True, foreign_file_not_deleted=True)
        try:
            base.private_json(journal_fd, 'receipt_failure.json', record)
        except BaseException:
            record['failure_receipt_saved'] = False
        return None


def main():
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    require(re.fullmatch('[0-9]{1,24}', request) and re.fullmatch('[a-f0-9]{40}', source), 'OWNER_CONTEXT')
    require(os.geteuid() == 0, 'ROOT_REQUIRED')
    b, candidate, auth, helper = prepared_library()
    record = {'schema': SCHEMA, 'request': request, 'source_sha': source, 'started_at': time.time(),
        'state': 'PREPARING', 'success': False, 'target_asset': b.URL,
        'expected_before_sha256': OLD_SHA, 'expected_after_sha256': NEW_SHA,
        'source_pins': DEPENDENCIES, 'content_exported': False,
        'browser_acceptance_verified': False, 'workspace_capabilities_behavior_verified': False,
        'proxy_restarted': False, 'model_restarted': False, 'training_control_performed': False,
        'flags_or_configuration_modified': False, 'directory_permissions_modified': False,
        'maintenance_mode': 'SHARED', 'rollback_requested': False, 'rollback_verified': False,
        'rollback_verification_scope': 'EXACT_ASSET_SOURCE_PAIR', 'original_backup_retained': False}
    client = None; journal_fd = None; prepared = None; latch = {}; outcome = None
    previous = signal.getsignal(signal.SIGALRM); timer = signal.getitimer(signal.ITIMER_REAL); started = time.monotonic()
    signal.signal(signal.SIGALRM, b.timeout_signal)
    signal.setitimer(signal.ITIMER_REAL, min(100, timer[0]) if timer[0] else 100)
    with ExitStack() as stack:
        try:
            b.gate()
            stack.enter_context(b.lease(b.STATE / 'owner_workspace_asset.lock', create_file=True))
            stack.enter_context(b.lease(b.STATE / 'owner_maintenance.lock', shared=True))
            parent_fd = b.directory(b.SITE.parent); stack.callback(os.close, parent_fd)
            site_fd = b.directory(b.SITE); stack.callback(os.close, site_fd)
            old, old_info = b.read_at(site_fd, b.ASSET, expected=OLD_SHA)
            require(len(old) == OLD_BYTES, 'PREIMAGE_SIZE')
            record['before_asset'] = {'sha256': OLD_SHA, **old_info}
            guards = b.source_guards(); before = b.identities(helper)
            training_before = training_snapshot(b, helper)
            record.update(identities_before=before, training_before=training_before, health_before=b.health(helper))
            b.gate(); client = auth.OwnerClient.authenticate(); host = b.local_address()
            anonymous, _ = b.http_get(host, b.URL); require(anonymous == 401, 'ANONYMOUS_ASSET_ACCESS')
            page_status, page = b.http_get(host, b.PAGE, client.cookie)
            require(page_status == 200 and page_reference(page), 'PAGE_ASSET_REFERENCE')
            record.update(anonymous_http=anonymous, owner_page_http=page_status,
                          http_before=b.http_asset(host, client, OLD_SHA))
            b.gate(); b.plain(b.AREA); b.AREA.mkdir(mode=0o700, exist_ok=True)
            area_fd = b.directory(b.AREA); stack.callback(os.close, area_fd)
            require(stat.S_IMODE(os.fstat(area_fd).st_mode) == 0o700, 'JOURNAL_MODE')
            os.mkdir(request, mode=0o700, dir_fd=area_fd); os.fsync(area_fd)
            journal_path = b.AREA / request; journal_fd = b.directory(journal_path); stack.callback(os.close, journal_fd)
            require(os.fstat(site_fd).st_dev == os.fstat(journal_fd).st_dev, 'JOURNAL_FILESYSTEM')
            b.create(journal_fd, 'original.js', old)
            candidate_info = b.create(journal_fd, 'exchange.js', candidate, old_info['mode'])
            prepared = {'schema': 'NOX_OWNER_WORKSPACE_ASSET_PREPARED_V1', 'request': request, 'source_sha': source,
                'target_asset': b.URL, 'before': old_info, 'before_sha256': OLD_SHA,
                'candidate': candidate_info, 'candidate_sha256': NEW_SHA}
            record['prepared_receipt'] = b.private_json(journal_fd, 'prepared.json', prepared)
            record['original_backup_retained'] = True
            b.gate(); b.named_directory(b.SITE.parent, parent_fd); b.named_directory(b.SITE, site_fd)
            b.named_directory(journal_path, journal_fd)
            require(b.source_guards() == guards and b.same_chat(before, b.identities(helper))
                    and training_snapshot(b, helper) == training_before, 'PREINSTALL_CHANGED')
            b.private_json(journal_fd, 'exchange_intent.json', {'request': request, 'source_sha': source,
                'prepared_sha256': record['prepared_receipt']['sha256'], 'at': time.time()})
            b.gate(); b.publish(site_fd, journal_fd, prepared, latch)
            record['installed_asset'] = b.current_asset(site_fd)
            b.private_json(journal_fd, 'installed.json', record['installed_asset'])
            record['http_after'] = b.http_asset(host, client, NEW_SHA)
            record['health_after'] = b.health(helper); after = b.identities(helper)
            training_after = training_snapshot(b, helper)
            record.update(identities_after=after, training_after=training_after)
            require(b.same_chat(before, after) and b.source_guards() == guards
                    and training_after == training_before, 'POSTINSTALL_CHANGED')
            b.gate(); b.named_directory(b.SITE.parent, parent_fd); b.named_directory(b.SITE, site_fd)
            b.named_directory(journal_path, journal_fd); b.verify_pair(site_fd, journal_fd, prepared, installed=True)
            b.read_at(journal_fd, 'original.js', expected=OLD_SHA, private=True)
            record.update(state=ACCEPTED, success=True, source_guards_preserved=True,
                          model_identity_preserved=True, proxy_identity_preserved=True,
                          training_sources_flags_and_observed_processes_preserved=True)
        except BaseException as exc:
            signal.setitimer(signal.ITIMER_REAL, 0)
            record.update(state='HOLD_WORKSPACE_ASSET_INSTALL', reason=b.safe(exc), success=False)
            if latch.get('exchange_attempted'):
                record['rollback_requested'] = True
                try:
                    signal.setitimer(signal.ITIMER_REAL, 20)
                    b.named_directory(b.SITE, site_fd); b.named_directory(journal_path, journal_fd)
                    record['rollback_verified'] = b.restore_owned(site_fd, journal_fd, prepared)
                    record['asset_after_rollback'] = b.current_asset(site_fd)
                except BaseException as error:
                    record.update(rollback_verified=False, rollback_reason=b.safe(error),
                                  displaced_file_retained=True, foreign_file_not_deleted=True)
                finally:
                    signal.setitimer(signal.ITIMER_REAL, 0)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            if client is not None:
                try:
                    client.close(); record['owner_session_closed'] = True
                except Exception:
                    record['owner_session_closed'] = False
            record['finished_at'] = time.time()
            if journal_fd is not None:
                def undo():
                    b.named_directory(b.SITE, site_fd); b.named_directory(journal_path, journal_fd)
                    return b.restore_owned(site_fd, journal_fd, prepared)
                outcome = seal_result(b, journal_fd, record, undo if latch.get('exchange_attempted') else None)
            signal.signal(signal.SIGALRM, previous)
            signal.setitimer(signal.ITIMER_REAL,
                max(.001, timer[0] - (time.monotonic() - started)) if timer[0] else 0, timer[1])
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'workspace_asset_install', 'data': record},
        separators=(',', ':'), allow_nan=False), flush=True)
    if outcome is not None:
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'workspace_asset_context', 'data': {
            'request': request, 'source_sha': source, 'receipt_sha256': outcome['sha256'], 'receipt_bytes': outcome['bytes']}},
            separators=(',', ':')), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=' + str(record['success'] and outcome is not None).lower(), flush=True)
    return 0 if record['success'] and outcome is not None else 2


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'workspace_asset_install', 'data': {
            'schema': SCHEMA, 'state': 'HOLD_WORKSPACE_ASSET_PREFLIGHT', 'success': False}}, separators=(',', ':')), flush=True)
        print('NOX_MAINT_REPAIR_COMPLETE=false', flush=True)
        raise SystemExit(2)
