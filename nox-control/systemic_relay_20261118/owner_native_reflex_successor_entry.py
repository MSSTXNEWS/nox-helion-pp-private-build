#!/usr/bin/env python3
"""One-shot owner-pinned safe upgrade of the existing NOX native director.

Exactly three reviewed script replacements and the existing module-pin config.
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
TASKPACK = 'scripts/owner_reflex_taskpack.py'
HELPER_SHA = '8470a6720ca69864bbc4e6e630a1f853344839af424d3829dcdf1774442db609'
OLD = {
    CONFIG: 'da355cfbd8bb07d543d388e6de19cfb05850c1ca7f5f28d75936507d540917b9',
    REFILL: '06bb8ec21607f09a5703e3f1b7d8694bbc120485e80c14058128902c6d9959ba',
    DIRECTOR: 'eac3ce9e2d8c862d1a7917ec447ea72e84454b7775a4260ad1e72e59de96fe11',
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


def pin_successor_modules(old_config, scripts):
    """Return a copy whose runtime pins cover all three installed modules."""
    new = copy.deepcopy(old_config)
    pins = new.get('module_pins')
    require(isinstance(pins, dict), 'MODULE_PIN_MAP')
    for relative in (REFILL, DIRECTOR, TASKPACK):
        require(relative in scripts, 'MODULE_ASSET_MISSING')
        pins[Path(relative).name] = sha(scripts[relative])
    return new


def _optional_regular(helper, path, maximum=250000):
    """Read an existing regular file, preserving absence as a distinct preimage."""
    path = Path(path)
    require(path.is_absolute() and not any(p.is_symlink() for p in (path, *path.parents)),
            'ROLLBACK_SYMLINK')
    if not path.exists():
        return None
    return helper.read_regular(path, maximum)


def apply_source_changes(helper, root, changes, before, applied):
    """Write each exact-preimage source in order; record before atomic replace."""
    for relative, raw in changes.items():
        path = Path(root) / relative
        maximum = 2 * 1024 * 1024 if relative == CONFIG else 250000
        require(_optional_regular(helper, path, maximum) == before[relative],
                'WRITE_PREIMAGE_CHANGED')
        # atomic() can raise either before or after os.replace. In both cases
        # rollback inspects the actual on-disk preimage before acting.
        applied.append(relative)
        helper.atomic(path, raw, 0o600 if relative == CONFIG else 0o644)
        require(_optional_regular(helper, path, maximum) == raw, 'WRITE_POSTIMAGE')


def rollback_source_changes(helper, root, changes, before, applied):
    """Restore only our postimages and verify every target, including absences."""
    try:
        for relative in reversed(applied):
            path = Path(root) / relative
            maximum = 2 * 1024 * 1024 if relative == CONFIG else 250000
            live = _optional_regular(helper, path, maximum)
            previous = before[relative]
            if live == previous:
                # A pre-replace atomic failure left this path untouched.
                continue
            if live != changes[relative]:
                return False  # Preserve foreign bytes; never overwrite them.
            if previous is None:
                require(relative == TASKPACK, 'ROLLBACK_UNEXPECTED_ABSENCE')
                os.unlink(path)
                directory = os.open(path.parent, os.O_DIRECTORY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            else:
                helper.atomic(path, previous,
                              0o600 if relative == CONFIG else 0o644)
        # Include files whose writes were not reached, and the additive-file absence.
        return all(_optional_regular(
            helper, Path(root) / relative,
            2 * 1024 * 1024 if relative == CONFIG else 250000) == raw
            for relative, raw in before.items())
    except BaseException:
        return False


def may_restart_after_rollback(stopped, supervisor_state, rollback_verified):
    """Restart the prior director only after a verified full preimage restore."""
    return (stopped is True
            and supervisor_state in ('STOPPED', 'FATAL', 'EXITED')
            and rollback_verified is True)


def decode():
    names = {'owner_systemic_refill.py', 'owner_subagent_dispatcher.py',
             'owner_reflex_taskpack.py', 'continuous_transaction_helpers.py'}
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
    return h, {REFILL: assets['owner_systemic_refill.py'],
               DIRECTOR: assets['owner_subagent_dispatcher.py'],
               TASKPACK: assets['owner_reflex_taskpack.py']}


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
    require('owner_reflex_taskpack.py' not in pins, 'TASKPACK_ALREADY_PINNED')
    taskpack_path = ROOT/TASKPACK
    require(not taskpack_path.is_symlink(), 'TASKPACK_SYMLINK')
    taskpack_before = (h.read_regular(taskpack_path, 250000)
                       if taskpack_path.exists() else None)
    require(taskpack_before is None or
            sha(taskpack_before) == sha(scripts[TASKPACK]), 'TASKPACK_PREIMAGE')
    require(h.stop_clear(ROOT), 'OWNER_STOP')
    new = pin_successor_modules(old_config, scripts)
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
    changes = {REFILL: scripts[REFILL], DIRECTOR: scripts[DIRECTOR],
               TASKPACK: scripts[TASKPACK], CONFIG: encoding(new)}
    before = dict(current)
    before[TASKPACK] = taskpack_before

    # Immutable source and verified current queue guard; no owner/admin privilege is minted.
    lock = ROOT/'state/owner_maintenance.lock'
    require(lock.is_file() and not lock.is_symlink(), 'MAINTENANCE_LOCK_ID')
    fd = os.open(lock, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    applied = []
    stopped = False
    started = None
    maintenance_released = False
    old_director = None
    children = []
    backup = ROOT/'state/dispatcher/reflex_upgrade_backups'/owner_request
    receipt = {'schema':'NOX_NATIVE_REFLEX_UPGRADE_RECEIPT_V1',
        'source_sha': commit,'request':owner_request,'started':time.time(),
        'state':'PREFLIGHT','runtime_files_changed':0,
        'rollback_verified':False,
        'original_295_accepted':0,'weights_changed':False,
        'chat_or_web_restarted':False,'new_worker_pool':False}
    def emit():
        print('NOX_MAINT_REFLEX_SUCCESSOR_HOLD=' + encoding(receipt).decode(), flush=True)

    try:
        # Existing native readers may hold SH briefly on the same owner lock.
        # Wait boundedly, never steal/clear the lock or retry a failed write.
        deadline = time.monotonic() + 12
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                require(time.monotonic() < deadline and h.stop_clear(ROOT),
                    'MAINTENANCE_BUSY')
                time.sleep(.2)
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
        require(not taskpack_path.is_symlink(), 'TASKPACK_SYMLINK')
        taskpack_now = (h.read_regular(taskpack_path, 250000)
                        if taskpack_path.exists() else None)
        require(taskpack_now == taskpack_before, 'TASKPACK_PREIMAGE_CHANGED')
        queue_again, active = h.queue_idle(ROOT)
        require(not active and sha(h.read_regular(ROOT/'state/dispatcher/state.json',32*1024*1024)) == before_queue_sha,
            'QUEUE_CHANGED_BEFORE_STOP')

        h.stop_checked()
        stopped = True
        h.wait_previous_descendants_stopped(children, timeout=10)
        require(h.stop_clear(ROOT) and service_guard() == protected, 'POST_STOP_SERVICE_CHANGED')
        require(sha(h.read_regular(ROOT/'state/dispatcher/state.json',32*1024*1024)) == before_queue_sha,
            'QUEUE_CHANGED_AFTER_STOP')
        # Config is deliberately written last; no mixed-pin execution.
        apply_source_changes(h, ROOT, changes, before, applied)
        started = h.start_checked(ROOT, require_native_status=True)
        require(h.stop_clear(ROOT) and service_guard() == protected, 'PROTECTED_SERVICE_CHANGED')
        # The director must acquire the maintenance lock in SH mode to refill.
        # Release our upgrade lock only after exact new source and director are live.
        fcntl.flock(fd, fcntl.LOCK_UN)
        maintenance_released = True
        native_status = {}
        deadline = time.monotonic()+25
        while time.monotonic() < deadline:
            try:
                status = json.loads(h.read_regular(ROOT/'status/agents_t856u.json',2*1024*1024))
                native_status = status.get('native_subexecutors',{})
                relay = native_status.get('systemic_relay') or {}
                reflex = relay.get('self_monitor')
                proposal = relay.get('successor_proposal')
                if (isinstance(reflex,dict)
                    and reflex.get('schema') == 'NOX_NATIVE_REFLEX_MONITOR_V1'
                    and isinstance(proposal,dict)
                    and proposal.get('schema') == 'NOX_NATIVE_REFLEX_DRAFT_TASKPACK_V1'
                    and proposal.get('authority') == 'PROPOSAL_ONLY'
                    and proposal.get('base_manifest_sha256') == MANIFEST
                    and re.fullmatch('[a-f0-9]{64}', str(proposal.get('monitor_observation_sha256','')))
                    and re.fullmatch('[a-f0-9]{64}', str(proposal.get('draft_manifest_sha256','')))
                    and proposal.get('native_jobs_created') == 0
                    and proposal.get('automatic_owner_approval') is False
                    and isinstance(proposal.get('draft_manifest'), dict)
                    and proposal['draft_manifest'].get('review_origin') == 'UNREVIEWED_REFLEX_DRAFT'
                    and proposal['draft_manifest'].get('acceptance_scope') == 'DRAFT_ONLY'
                    and proposal['draft_manifest'].get('original_task_accepted') is False
                    and len(proposal.get('draft_missions') or []) <= 3
                    and len(proposal.get('decisions') or []) <= 64
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
            and sha(h.read_regular(ROOT/DIRECTOR)) == sha(scripts[DIRECTOR])
            and sha(h.read_regular(taskpack_path, 250000)) == sha(scripts[TASKPACK])
            and json.loads(final_config)['module_pins'] == new['module_pins'],
            'POSTBOOT_SOURCE_OR_CONFIG')
        receipt.update(state='NATIVE_REFLEX_TELEMETRY_VERIFIED',
            old_director=old_director,new_director=started,
            workers=len(native_status['workers']),new_config_sha256=sha(final_config),
            monitor_state=reflex.get('state'),
            observation_sha256=reflex.get('observation_sha256'),
            staged_research_count=reflex.get('staged_count'),
            new_native_jobs=reflex.get('new_native_jobs'),
            successor_proposal_sha256=proposal.get('draft_manifest_sha256'),
            base_manifest_sha256=proposal.get('base_manifest_sha256'),
            monitor_observation_sha256=proposal.get('monitor_observation_sha256'),
            draft_manifest_sha256=proposal.get('draft_manifest_sha256'),
            successor_authority=proposal.get('authority'),
            successor_decisions=proposal.get('decisions'),
            successor_draft_missions=proposal.get('draft_missions'),
            successor_draft_manifest=proposal.get('draft_manifest'),
            successor_required_next_step=proposal.get('required_next_step'),
            runtime_files_changed=3)
        print('NOX_MAINT_REFLEX_SUCCESSOR=' + encoding(receipt).decode(), flush=True)
        print('NOX_MAINT_REFLEX_SUCCESSOR_COMPLETE=true', flush=True)
        return True
    except BaseException as exc:
        receipt['state'] = str(exc) if str(exc).startswith('HOLD_') else 'HOLD_NATIVE_REFLEX_'+type(exc).__name__
        try:
            if maintenance_released:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise RuntimeError('HOLD_NATIVE_REFLEX_ROLLBACK_LEASE_BUSY')
            if applied:
                present = h.supervisor('status')
                live = h.process_identity(present.get('pid'))
                if live:
                    require(started is not None and live == started, 'FOREIGN_DIRECTOR_NO_ROLLBACK')
                    h.stop_checked()
                else:
                    require(present['state'] in ('STOPPED','FATAL','EXITED'), 'UNKNOWN_DIRECTOR_NO_ROLLBACK')
            if stopped:
                receipt['rollback_verified'] = rollback_source_changes(
                    h, ROOT, changes, before, applied)
                if not receipt['rollback_verified']:
                    receipt['recovery'] = 'HOLD_NATIVE_REFLEX_ROLLBACK_INCOMPLETE'
            if may_restart_after_rollback(
                    stopped, h.supervisor('status')['state'], receipt['rollback_verified']):
                h.wait_previous_descendants_stopped(children, timeout=10)
                require(h.stop_clear(ROOT), 'RESTORE_OWNER_STOP')
                receipt['restored_director'] = h.start_checked(ROOT, require_native_status=True)
        except BaseException as failure:
            receipt['recovery'] = str(failure) if str(failure).startswith('HOLD_') else 'HOLD_NATIVE_REFLEX_RECOVERY_'+type(failure).__name__
        emit()
        raise
    finally:
        os.close(fd)


if __name__ == '__main__':
    run()
