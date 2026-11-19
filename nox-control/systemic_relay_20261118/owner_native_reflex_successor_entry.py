#!/usr/bin/env python3
"""One-shot owner-pinned safe upgrade of the existing NOX native director.

Exactly two reviewed script replacements and the existing module-pin config.
No new daemon, queue, GPU/model, scheduler, training, source-workspace edits
or authorization created. Fails closed if live state diverged.
"""
from __future__ import annotations
import base64
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
import types

ROOT = Path('/root/nox')
CONFIG = 'config/owner_native_subagents.json'
REFILL = 'scripts/owner_systemic_refill.py'
DIRECTOR = 'scripts/owner_subagent_dispatcher.py'
HELPER_SHA = '8470a6720ca69864bbc4e6e630a1f853344839af424d3829dcdf1774442db609'
OLD = {
    CONFIG: '30effffe3c8a20c0df4dee936beb2f8183347fb2a5fd51d4543dfbde50efb919',
    REFILL: '4f0ea3f44ded11d40245de7573c5f48efc2e2f7424f979cec2da3e140a6d1197',
    DIRECTOR: '0193c511168489637b6df041bee2daf79bd42bd338c4ff5f9a6b129652dc4a13',
}
MANIFEST = 'd58ed9b020a78c3c8fcbfd476b3b0eecfd235e50f3a6ded29c8cec550e1a4212'
try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}


def require(value, reason):
    if not value:
        raise RuntimeError('HOLD_NATIVE_REFLEX_' + reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoding(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def decode():
    names = {'owner_systemic_refill.py', 'owner_subagent_dispatcher.py', 'continuous_transaction_helpers.py'}
    require(set(BUNDLE) == names, 'BUNDLE_FILES')
    assets = {}
    for name in names:
        raw = base64.b64decode(BUNDLE[name], validate=True)
        require(0 < len(raw) < 250000, 'BUNDLE_BOUND')
        compile(raw, '<owner-reviewed>/' + name, 'exec')
        assets[name] = raw
    require(sha(assets['continuous_transaction_helpers.py']) == HELPER_SHA, 'TRANSACTION_PIN')
    h = types.ModuleType('_nox_reflex_owner_helper')
    h.__file__ = '<verified helper>'
    exec(compile(assets['continuous_transaction_helpers.py'], h.__file__, 'exec'), h.__dict__)
    return h, {REFILL: assets['owner_systemic_refill.py'], DIRECTOR: assets['owner_subagent_dispatcher.py']}


def run():
    owner_request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    commit = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    require(re.fullmatch('[0-9]{1,24}', owner_request) and re.fullmatch('[a-f0-9]{40}', commit), 'OWNER_CONTEXT')
    h, scripts = decode()
    current = h.preimages(ROOT, OLD)
    old_config = json.loads(current[CONFIG])
    require(old_config.get('schema') == 'NOX_NATIVE_SUBAGENT_BINDING_V1'
        and old_config.get('instance_id') == 60509551
        and old_config.get('owner_authorized') is True
        and old_config.get('execution_mode') == 'NATIVE_PROJECT_V1'
        and old_config.get('global_worker_cap') == 3
        and old_config.get('target') == 3
        and (old_config.get('systemic_relay') or {}).get('sha256') == MANIFEST,
        'CURRENT_NATIVE_IDENTITY')
    pins = old_config['module_pins']
    require(pins.get('owner_systemic_refill.py') == OLD[REFILL]
        and pins.get('owner_subagent_dispatcher.py') == OLD[DIRECTOR],
        'CURRENT_SOURCE_PINS')
    require(h.stop_clear(ROOT), 'OWNER_STOP')
    new = copy.deepcopy(old_config)
    new['module_pins']['owner_systemic_refill.py'] = sha(scripts[REFILL])
    new['module_pins']['owner_subagent_dispatcher.py'] = sha(scripts[DIRECTOR])
    # Old terminal receipts have a pinned prior source and must remain verifiable.
    for history_name in ('historical_project_source_sha256', 'historical_leaf_source_sha256'):
        history = list(new.get(history_name, []))
        require(len(history) <= 31 and all(isinstance(x, str) and re.fullmatch('[a-f0-9]{64}', x) for x in history),
            'HISTORY_BOUND')
        previous = OLD[DIRECTOR]
        if previous not in history:
            history.append(previous)
        require(len(history) <= 32 and len(history) == len(set(history)), 'HISTORY_DUPLICATE')
        new[history_name] = history
    changes = {REFILL: scripts[REFILL], DIRECTOR: scripts[DIRECTOR], CONFIG: encoding(new)}

    # Immutable source and verified current queue guard; no owner/admin privilege is minted.
    lock = ROOT/'state/owner_maintenance.lock'
    require(lock.is_file() and not lock.is_symlink(), 'MAINTENANCE_LOCK_ID')
    fd = os.open(lock, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    applied = []
    stopped = False
    started = None
    old_director = None
    children = []
    backup = ROOT/'state/dispatcher/reflex_upgrade_backups'/owner_request
    receipt = {'schema':'NOX_NATIVE_REFLEX_UPGRADE_RECEIPT_V1',
        'source_sha': commit,'request':owner_request,'started':time.time(),
        'state':'PREFLIGHT','runtime_files_changed':0,
        'original_295_accepted':0,'weights_changed':False,
        'chat_or_web_restarted':False,'new_worker_pool':False}
    def emit():
        print('NOX_MAINT_REFLEX=' + encoding(receipt).decode(), flush=True)

    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('HOLD_NATIVE_REFLEX_MAINTENANCE_BUSY')
        info, named = os.fstat(fd), lock.stat()
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
            and info.st_nlink == 1 and not info.st_mode & 0o022
            and (info.st_dev, info.st_ino) == (named.st_dev, named.st_ino), 'MAINTENANCE_LOCK_CHANGED')
        identity = h.supervisor('status')
        require(identity['state'] == 'RUNNING' and identity.get('pid'), 'DIRECTOR_NOT_RUNNING')
        old_director = h.process_identity(identity['pid'])
        require(old_director is not None, 'DIRECTOR_PROCESS_ID')
        children = h.descendant_snapshot(old_director['pid'])
        require(len(children) >= 3, 'WORKER_CENSUS_INCOMPLETE')
        require(not backup.exists() and not backup.is_symlink(), 'ONE_SHOT_REUSE')
        # These protected services are not modified and must keep their original PID/starttime.
        protected_services = ('nox-ds41-8098', 'nox-proxy', 'nox-web29-18775')
        def service_guard():
            result = {}
            for name in protected_services:
                import subprocess
                proc = subprocess.run(['supervisorctl','status',name],capture_output=True,text=True,timeout=8)
                match = re.match(re.escape(name)+r'\s+RUNNING\s+pid\s+([0-9]+)', proc.stdout)
                require(proc.returncode == 0 and match, 'PROTECTED_SERVICE_'+name.replace('-','_'))
                ident = h.process_identity(int(match[1]))
                require(ident is not None, 'PROTECTED_PID_'+name.replace('-','_'))
                result[name] = ident
            return result
        protected = service_guard()
        queue_before, active = h.queue_idle(ROOT)
        require(not active, 'ACTIVE_QUEUE_CLAIM')
        for row in queue_before['tasks'].values():
            if not isinstance(row, dict): continue
            lease = row.get('native_worker_lease')
            if row.get('status') in ('running','retry','admitted') and isinstance(lease,dict) and lease:
                raise RuntimeError('HOLD_NATIVE_REFLEX_UNSETTLED_WORKER_LEASE')
        before_queue_sha = sha(h.read_regular(ROOT/'state/dispatcher/state.json', 32*1024*1024))
        # Before stopping, backups are fsynced under the owner lease.
        backup.mkdir(parents=True, mode=0o700)
        for rel, raw in current.items():
            h.atomic(backup / Path(rel).name, raw)
        h.atomic(backup/'queue_sha256.txt', (before_queue_sha+'\n').encode())
        require(h.stop_clear(ROOT) and service_guard() == protected, 'FENCE_CHANGED')
        h.preimages(ROOT, OLD)
        queue_again, active = h.queue_idle(ROOT)
        require(not active and sha(h.read_regular(ROOT/'state/dispatcher/state.json',32*1024*1024)) == before_queue_sha,
            'QUEUE_CHANGED_BEFORE_STOP')

        h.stop_checked()
        stopped = True
        h.wait_previous_descendants_stopped(children, timeout=10)
        require(h.stop_clear(ROOT) and service_guard() == protected, 'POST_STOP_SERVICE_CHANGED')
        require(sha(h.read_regular(ROOT/'state/dispatcher/state.json',32*1024*1024)) == before_queue_sha,
            'QUEUE_CHANGED_AFTER_STOP')
        for rel, raw in changes.items():
            # Config is deliberately written last; no mixed-pin execution.
            require(h.read_regular(ROOT/rel) == current[rel], 'WRITE_PREIMAGE_CHANGED')
            applied.append(rel)
            h.atomic(ROOT/rel, raw, 0o600 if rel == CONFIG else 0o644)
            require(h.read_regular(ROOT/rel) == raw, 'WRITE_POSTIMAGE')
        started = h.start_checked(ROOT, require_native_status=True)
        require(h.stop_clear(ROOT) and service_guard() == protected, 'PROTECTED_SERVICE_CHANGED')
        native_status = {}
        deadline = time.monotonic()+25
        while time.monotonic() < deadline:
            try:
                status = json.loads(h.read_regular(ROOT/'state/dispatcher/agents_status.json',2*1024*1024))
                native_status = status.get('native_subexecutors',{})
                reflex = (native_status.get('systemic_relay') or {}).get('self_monitor')
                if (isinstance(reflex,dict)
                    and reflex.get('schema') == 'NOX_NATIVE_REFLEX_MONITOR_V1'
                    and native_status.get('director',{}).get('pid') == started['pid']
                    and len(native_status.get('workers') or []) == 3):
                    break
            except (OSError, KeyError, ValueError, TypeError):
                pass
            time.sleep(1)
        else:
            raise RuntimeError('HOLD_NATIVE_REFLEX_POSTBOOT_TELEMETRY')
        final_config = h.read_regular(ROOT/CONFIG)
        require(final_config == changes[CONFIG]
            and sha(h.read_regular(ROOT/REFILL)) == sha(scripts[REFILL])
            and sha(h.read_regular(ROOT/DIRECTOR)) == sha(scripts[DIRECTOR]),
            'POSTBOOT_SOURCE_OR_CONFIG')
        receipt.update(state='NATIVE_REFLEX_TELEMETRY_VERIFIED',
            old_director=old_director,new_director=started,
            workers=len(native_status['workers']),new_config_sha256=sha(final_config),
            monitor_state=reflex.get('state'),
            observation_sha256=reflex.get('observation_sha256'),
            staged_research_count=reflex.get('staged_count'),
            new_native_jobs=reflex.get('new_native_jobs'),
            runtime_files_changed=2)
        emit()
        print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
        return True
    except BaseException as exc:
        receipt['state'] = str(exc) if str(exc).startswith('HOLD_') else 'HOLD_NATIVE_REFLEX_'+type(exc).__name__
        try:
            if applied:
                present = h.supervisor('status')
                live = h.process_identity(present.get('pid'))
                if live:
                    require(started is not None and live == started, 'FOREIGN_DIRECTOR_NO_ROLLBACK')
                    h.stop_checked()
                else:
                    require(present['state'] in ('STOPPED','FATAL','EXITED'), 'UNKNOWN_DIRECTOR_NO_ROLLBACK')
                for rel in reversed(applied):
                    post = h.read_regular(ROOT/rel)
                    require(post == changes[rel], 'ROLLBACK_FOREIGN_FILE_CHANGE')
                    h.atomic(ROOT/rel, current[rel], 0o600 if rel == CONFIG else 0o644)
                receipt['rollback_verified'] = all(h.read_regular(ROOT/rel) == raw for rel,raw in current.items())
            if stopped and h.supervisor('status')['state'] in ('STOPPED','FATAL','EXITED') and receipt.get('rollback_verified',True):
                receipt['restored_director'] = h.start_checked(ROOT, require_native_status=True)
        except BaseException as failure:
            receipt['recovery'] = str(failure) if str(failure).startswith('HOLD_') else 'HOLD_NATIVE_REFLEX_RECOVERY_'+type(failure).__name__
        emit()
        raise
    finally:
        os.close(fd)


if __name__ == '__main__':
    run()
