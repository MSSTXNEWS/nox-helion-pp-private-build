#!/usr/bin/env python3
"""Move the one redundant RAM builder to a verified canonical SSD alias.

No weight bytes, checkpoint, training source, admission or training flag is
changed. Only the exact canonical builder 0666 -> 0644 and its independently
observed parent 0777 -> 0755 are protected, with a durable reversible record
and all known legacy writers stopped. New receipt and consumers report cold
SSD explicitly; the old RAM receipt is untouched.
"""
from __future__ import annotations

import base64
from contextlib import ExitStack
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time
import types

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

ROOT = Path('/root/nox'); SCRIPTS = ROOT / 'scripts'; STATE = ROOT / 'state'
SCHEMA = 'NOX_BUILDER_COLD_STORAGE_TRANSITION_V1'
PINS = {
    'owner_builder_archive_reclaim.py': '804ea161e91c52df57964ca450c3da07a860a0ff428bb95993d5c94ecc4541f6',
    'owner_builder_proc_probe.py': '1743c8587dac72f412400be9059d1fe01ef73a1955af2056ff77a550e53af3ff',
    'owner_qwen_disk_rearm_entry.py': 'd7017fecab20dab1dc833b2509b14850d4a65151682031143c23e5596c9b8f38',
    'owner_download_status_entry.py': 'f17e8f5337f84ea5a3466053e08a8625c31d9b4b31e3963feecec874f145db36',
    'owner_native_repair.py': 'b3d1887b92cb805076301f6631e56b6e42c48e7dae02d62f2a272c10669644e0',
    'owner_training_status_binding.py': '91df0894f52e07ae36f6f05bcb17c846c1b06da88427f45bfe52faf8e50fc1fa',
}
NEW = {
    'owner_builder_cold_location.py': 'f573a7c5509786139b80768bc009fcbbae89c1a088e3d81361aa0d9eb7dbd965',
    'owner_drive_storage_bridge.py': 'b9e73d96e7ae48dedd7aa1a168d1caa09337d0f58fecca00af527d2347ba8d81',
    'owner_builder_cold_chat_binding.py': 'a9ff754639495d50e0cc67fa2bf49d592f7c16934f8efd63da1815fc9baa0689',
}
OLD = {
    'owner_download_status.py': '574bd91bb072a626b32fc557299e245b61a8798204fffd690099ffd78fc09eda',
    'owner_drive_ram_bridge.py': '57893b187155b12c08b3ca0612a62397d117218302d448994a346c84f556b786',
    'owner_chat_evidence.py': 'ea66e05f30472b066444058ac18d0c7af74def410bde760396d1e2431161e8b2',
}
OLD_JS = '62ad2c08382ee6ef6cec3c8eb0ba4598c4c09037f442ce83a04c0344d686525a'
PROXY_TAIL = ("\n# NOX_BUILDER_COLD_STORAGE_RUNTIME_V1\n"
              "from owner_builder_cold_chat_binding import bind as _nox_bind_builder_storage\n"
              "_nox_bind_builder_storage()\n")
MAIN_ANCHOR = 'if __name__ == "__main__":\n    main()'
CANONICAL_PARENT_PREIMAGE = {
    'st_dev': 39, 'st_ino': 106953430, 'st_uid': 0, 'st_gid': 0,
    'st_mode': stat.S_IFDIR | 0o777,
}
CANONICAL_PARENT_PROBE = {
    'request': '6910454892', 'source_sha': 'f5568e7725992ea58bc7e75ac5f61845c93e8073',
    'workflow_run': '43825634733', 'job': '133158708688',
}


def require(value, code):
    if not value:
        raise RuntimeError('HOLD_BUILDER_COLD_ENTRY_' + code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def bundle(name, expected):
    raw = base64.b64decode(BUNDLE.get(name, ''), validate=True)
    require(0 < len(raw) < 262144 and sha(raw) == expected, 'BUNDLE_PIN')
    return raw


def load(name, expected):
    raw = bundle(name, expected); m = types.ModuleType('_builder_cold_' + name.removesuffix('.py'))
    m.__file__ = str(SCRIPTS / name); m.__dict__['__NOX_' + 'BUNDLE_JSON__'] = BUNDLE
    exec(compile(raw, str(SCRIPTS / name), 'exec'), m.__dict__)
    return m


def dependencies():
    values = {name: load(name, pin) for name, pin in PINS.items()}
    values.update({name: load(name, pin) for name, pin in NEW.items()})
    core = values['owner_builder_archive_reclaim.py']; proc, proof = core.dependencies()
    return values, core, proc, proof


def patch_proxy(raw, training_binding):
    require(training_binding.patch_proxy(raw) == raw, 'CURRENT_TRAINING_HOOKS')
    text = raw.decode()
    require(text.count(MAIN_ANCHOR) == 1 and PROXY_TAIL not in text, 'PROXY_ANCHOR')
    result = text.replace(MAIN_ANCHOR, PROXY_TAIL + '\n' + MAIN_ANCHOR, 1).encode()
    compile(result, '<cold-storage-proxy-binding>', 'exec')
    return result


def patch_js(raw):
    require(sha(raw) == OLD_JS, 'JS_PREIMAGE')
    text = raw.decode()
    edits = (
        ("adapters.append(E('b','Адаптеры 3t724u · RAM'));", "adapters.append(E('b','Адаптеры 3t724u · RAM / SSD'));"),
        ("adapters.append(E('p',drive.verified_files+'/'+drive.selected_files+' проверены · '+size(drive.verified_bytes)));",
         "adapters.append(E('p',drive.verified_files+'/'+drive.selected_files+' проверены · '+size(drive.verified_bytes)));"
         "adapters.append(E('p','В RAM: '+(drive.storage_counts?.RAM??0)+' · на SSD: '+(drive.storage_counts?.SSD??0)));"
         "if(drive.assets.some(row=>row.location_state==='COLD_ON_SSD'))adapters.append(E('p','Builder — холодные веса на SSD; ссылка из RAM-каталога не означает загрузку в RAM.'));"),
    )
    for old, new in edits:
        require(text.count(old) == 1, 'JS_ANCHOR'); text = text.replace(old, new, 1)
    return text.encode()


def paused_proof(modules):
    rearm = modules['owner_qwen_disk_rearm_entry.py']
    guard = rearm.load(rearm.GUARD_NAME); status = rearm.load(rearm.STATUS_NAME)
    window = guard.module('owner_qwen_window_entry.py'); helper = guard.module('owner_qwen_install_entry.py')
    policy_sha = rearm.sources()
    cfg, cfgsha = guard.checked_config(rearm.CONTEXT, rearm.PINS[rearm.GUARD_NAME]); ctx = guard.context_evidence(cfg)
    rearm.stopped(ctx, window, helper)
    row, _ = guard.previous_state(guard.bindings(cfg, cfgsha, ctx))
    require(row and row['policy_state']['inhibit'] is True and row['policy_state']['reason'] == 'DISK_EARLY_MARGIN', 'DISK_PAUSE')
    fixed = rearm.flags(guard, row)
    proof, manifest, identities = rearm.full_checkpoint(guard, status, ctx, fixed)
    heavy = rearm.heavy_stopped(helper)

    def preserved():
        rearm.stop_gate(guard); rearm.stopped(ctx, window, helper)
        require(rearm.sources() == policy_sha and rearm.flags(guard, row) == fixed
                and rearm.checkpoint_identities(manifest) == identities, 'TRAINING_PRESERVATION')
        rearm.checkpoint_anchors(); rearm.heavy_stopped(helper)
    return proof, heavy, preserved


def current_sources(deploy):
    values = {}
    for name, pin in OLD.items():
        raw = deploy.read(SCRIPTS / name)
        require(sha(raw) == pin, 'FROZEN_CONSUMER_PIN'); values[name] = pin
    return values


def plan_sources(modules, deploy):
    rows = []
    for name, pin in NEW.items():
        raw = bundle(name, pin); path = SCRIPTS / name
        old = deploy.read(path) if path.exists() or path.is_symlink() else None
        require(old is None or old == raw, 'NEW_MODULE_FOREIGN_PREIMAGE')
        rows.append({'path': path, 'old': old, 'new': raw})
    proxy_path = SCRIPTS / 'chat_proxy.py'; old = deploy.read(proxy_path)
    rows.append({'path': proxy_path, 'old': old,
                 'new': patch_proxy(old, modules['owner_training_status_binding.py'])})
    js_path = deploy.SITE / 'owner-chat-ui.js'; old = deploy.read(js_path)
    rows.append({'path': js_path, 'old': old, 'new': patch_js(old)})
    return rows


def verify_parent(core, fd):
    info = os.fstat(fd)
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid() and not info.st_mode & 0o022, 'PARENT_DIRECTORY')


def named_parent(core, path, fd, expected=None):
    """Match the open directory to a second complete no-follow traversal."""
    before = core.identity(os.fstat(fd)); check = core.directory(path)
    try:
        named = core.identity(os.fstat(check)); after = core.identity(os.fstat(fd))
        require(stat.S_ISDIR(before['st_mode']) and before == named == after
                and (expected is None or after == expected), 'PARENT_PATH_CHANGED')
        return after
    finally:
        os.close(check)


def canonical_parent_preimage(core, fd):
    observed = named_parent(core, core.CANONICAL.parent, fd)
    require(observed['st_uid'] == os.geteuid()
            and all(observed[key] == value for key, value in CANONICAL_PARENT_PREIMAGE.items()),
            'CANONICAL_PARENT_PREIMAGE')
    return observed


def protect_parent(core, fd, before, mutation):
    named_parent(core, core.CANONICAL.parent, fd, before)
    mutation['attempted'] = True  # intent is already durable; latch before chmod/fsync
    os.fchmod(fd, 0o755)
    after = named_parent(core, core.CANONICAL.parent, fd)
    require(all(after[key] == before[key] for key in core.FIELDS if key not in ('st_mode', 'st_ctime_ns'))
            and stat.S_IMODE(after['st_mode']) == 0o755, 'PARENT_PERMISSION_SCOPE')
    mutation['after'] = after  # a following fsync failure still has an owned preimage
    os.fsync(fd)
    verify_parent(core, fd)
    return named_parent(core, core.CANONICAL.parent, fd, after)


def parent_rollback_target(core, fd, before, mutation):
    current = named_parent(core, core.CANONICAL.parent, fd)
    if mutation.get('after') is not None:
        require(current == mutation['after'], 'ROLLBACK_PARENT_FOREIGN')
    elif stat.S_IMODE(current['st_mode']) == 0o777:
        require(current == before, 'ROLLBACK_PARENT_FOREIGN')
    else:
        require(stat.S_IMODE(current['st_mode']) == 0o755
                and all(current[key] == before[key] for key in core.FIELDS
                        if key not in ('st_mode', 'st_ctime_ns')), 'ROLLBACK_PARENT_FOREIGN')
    return current


def restore_parent(core, fd, before, mutation):
    current = parent_rollback_target(core, fd, before, mutation)
    if stat.S_IMODE(current['st_mode']) != 0o777:
        os.fchmod(fd, 0o777); os.fsync(fd)
    restored = named_parent(core, core.CANONICAL.parent, fd)
    require(all(restored[key] == before[key] for key in core.FIELDS if key != 'st_ctime_ns'),
            'PARENT_PERMISSION_ROLLBACK')
    mutation['restored'] = True


def protect_canonical(core, parent, name, fd, before):
    core.named(parent, name, fd, before)
    mode = stat.S_IMODE(os.fstat(fd).st_mode)
    require(mode in (0o644, 0o666), 'CANONICAL_MODE')
    if mode == 0o666:
        os.fchmod(fd, 0o644); os.fsync(fd)
    after = core.named(parent, name, fd)
    require(all(after[k] == before[k] for k in core.FIELDS if k not in ('st_mode', 'st_ctime_ns'))
            and stat.S_IMODE(after['st_mode']) == 0o644, 'CANONICAL_PERMISSION_SCOPE')
    return after


def restore_mode(core, parent, name, fd, protected, original):
    core.named(parent, name, fd, protected)
    os.fchmod(fd, stat.S_IMODE(original['st_mode'])); os.fsync(fd)
    now = core.named(parent, name, fd)
    require(all(now[k] == original[k] for k in core.FIELDS if k != 'st_ctime_ns'), 'CANONICAL_MODE_ROLLBACK')


def storage_transition(core, location, proc, proof, request, source, backup, deadline, before_commit, after_alias, journal=None):
    """Retain old RAM inode until all consumers and HTTP verification pass."""
    journal = {} if journal is None else journal
    handles = []; moved = linked = published = removed = protected = False
    c = r = q = state = canonical_fd = ram_fd = None; canonical_before = canonical_after = None
    parent_before = parent_after = None; parent_mutation = {}
    alias_identity = None; storage_raw = None
    try:
        for index, path in enumerate((core.CANONICAL.parent, core.RAM.parent, location.RECEIPT.parent)):
            fd = core.directory(path); handles.append(fd)  # close even when the next guard fails
            if index == 0:
                parent_before = canonical_parent_preimage(core, fd)
            else:
                verify_parent(core, fd)
        c, r, state = handles
        canonical_fd = core.regular(c, core.CANONICAL.name, expected_size=core.SIZE); handles.append(canonical_fd)
        ram_fd = core.regular(r, core.RAM.name, expected_size=core.SIZE); handles.append(ram_fd)
        canonical_before = core.full_hash(canonical_fd, deadline)
        ram_before = core.full_hash(ram_fd, deadline)
        core.named(c, core.CANONICAL.name, canonical_fd, canonical_before); core.named(r, core.RAM.name, ram_fd, ram_before)
        require(canonical_before['st_dev'] != ram_before['st_dev'], 'RAM_AND_SSD_FILESYSTEMS')
        require(ram_before['st_dev'] == Path('/dev/shm').stat().st_dev, 'RAM_TMPFS_DEVICE')
        require(stat.S_IMODE(ram_before['st_mode']) == 0o600, 'ORIGINAL_RAM_MODE')
        old_ram = location.read(location.RAM_RECEIPT, private=True)
        historical = location.document(old_ram)
        require(historical.get('schema') == 'NOX_DRIVE_RAM_RECEIPT_V1'
                and historical.get('state') == 'RAM_FILES_SHA_VERIFIED_NOT_MERGED', 'ORIGINAL_RAM_RECEIPT')
        builder = [row for row in historical.get('assets', []) if row.get('role') == 'builder']
        require(len(builder) == 1 and builder[0].get('sha256') == core.SHA and builder[0].get('bytes') == core.SIZE
                and builder[0].get('verified') is True and builder[0].get('stat_inode') == ram_before['st_ino']
                and builder[0].get('stat_mtime_ns') == ram_before['st_mtime_ns'], 'ORIGINAL_RAM_IDENTITY')
        sidecars = core.sidecars(c)
        before_commit()
        usage = core.usage(proc, {(ram_before['st_dev'], ram_before['st_ino']): ['BUILDER_RAM'],
                                 (canonical_before['st_dev'], canonical_before['st_ino']): ['BUILDER_KEPT']},
                           {ram_fd, canonical_fd}, min(deadline, time.monotonic() + 10))
        require(usage['known_reference_count'] == 0, 'KNOWN_PROCESS_REFERENCE')
        qname = '.builder-cold-' + request
        q = core.prepare_private(r, qname); handles.append(q)
        restore_map = {'schema': 'NOX_BUILDER_COLD_RESTORE_MAP_V1', 'request': request, 'source_sha': source,
                       'canonical_path': str(core.CANONICAL), 'alias_path': str(core.RAM),
                       'quarantine_path': str(core.RAM.parent / qname / 'ram.safetensors'),
                       'canonical_before': canonical_before, 'ram_before': ram_before,
                       'sha256': core.SHA, 'bytes': core.SIZE, 'canonical_target_mode': 0o644,
                       'canonical_parent_path': str(core.CANONICAL.parent),
                       'canonical_parent_before': parent_before, 'canonical_parent_target_mode': 0o755,
                       'canonical_parent_observed_preimage': CANONICAL_PARENT_PREIMAGE,
                       'canonical_parent_probe': CANONICAL_PARENT_PROBE,
                       'external_drive_proof': proof, 'external_drive_proof_canonical_sha256': core.PROOF_SHA,
                       'previous_ram_receipt_sha256': sha(old_ram), 'sidecars': sidecars,
                       'restore_rule': 'NO_CLOBBER_RENAME_OWN_RAM_BEFORE_UNLINK_OTHERWISE_COPY_FULL_SHA_FROM_SSD',
                       'proc_visibility': usage}
        restore_proof = core.private_json(backup, 'restore-map.json', restore_map)
        core.absent(state, location.RECEIPT.name)
        before_commit(); core.tick(deadline)
        core.named(c, core.CANONICAL.name, canonical_fd, canonical_before)
        core.named(r, core.RAM.name, ram_fd, ram_before)
        require(core.sidecars(c) == sidecars, 'SIDECARS_CHANGED_BEFORE_PERMISSIONS')
        journal['canonical_parent_permission_intent'] = True
        parent_after = protect_parent(core, c, parent_before, parent_mutation)
        protected = True  # latch before fchmod; exceptions must recheck/restore
        canonical_after = protect_canonical(core, c, core.CANONICAL.name, canonical_fd, canonical_before)
        # Rehash after removing write permissions, before publishing any trust.
        core.full_hash(canonical_fd, deadline)
        core.named(r, core.RAM.name, ram_fd, ram_before)
        core.rename_noreplace(r, core.RAM.name, q, 'ram.safetensors'); moved = True
        core.fsync_dir(r); core.fsync_dir(q)
        os.symlink(str(core.CANONICAL), core.RAM.name, dir_fd=r); linked = True
        alias_identity = location.identity(os.stat(core.RAM.name, dir_fd=r, follow_symlinks=False))
        core.fsync_dir(r)
        require(stat.S_ISLNK(alias_identity['st_mode']) and os.readlink(core.RAM.name, dir_fd=r) == str(core.CANONICAL), 'ALIAS_READBACK')
        record = {'schema': location.SCHEMA, 'state': 'COLD_ON_SSD', 'request': request, 'source_sha': source,
                  'role': 'builder', 'filename': core.RAM.name, 'bytes': core.SIZE, 'sha256': core.SHA,
                  'canonical_path': str(core.CANONICAL), 'alias_path': str(core.RAM), 'alias_target': str(core.CANONICAL),
                  'canonical_identity': canonical_after, 'alias_identity': alias_identity,
                  'canonical_full_sha256_verified': True, 'previous_ram_full_sha256_verified': True,
                  'previous_ram_receipt_sha256': sha(old_ram), 'external_drive_proof_canonical_sha256': core.PROOF_SHA,
                  'ram_resident': False, 'automatic_ram_restage': False, 'weights_merged': False,
                  'active_model_changed': False, 'verified_at': time.time(), 'restore_map_sha256': restore_proof['sha256']}
        storage_raw = core.encoded(record)
        # Publication may succeed before a readback/fsync exception. Detect
        # that exact owned record in the rollback path without overwriting it.
        journal['storage_receipt_intent_sha256'] = sha(storage_raw)
        core.private_json(state, location.RECEIPT.name, record); published = True
        location.locate(rehash=True, deadline=deadline)
        after_alias()
        before_commit(); core.named(c, core.CANONICAL.name, canonical_fd, canonical_after)
        named_parent(core, core.CANONICAL.parent, c, parent_after); verify_parent(core, c)
        require(core.sidecars(c) == sidecars and location.read(location.RAM_RECEIPT, private=True) == old_ram, 'SIDECARS_OR_RAM_RECEIPT_CHANGED')
        require(location.read(location.RECEIPT, private=True) == storage_raw, 'STORAGE_RECEIPT_CHANGED')
        moved_now = core.named(q, 'ram.safetensors', ram_fd)
        require(all(moved_now[k] == ram_before[k] for k in core.FIELDS if k != 'st_ctime_ns'), 'QUARANTINE_CHANGED')
        os.unlink('ram.safetensors', dir_fd=q); removed = True; journal['ram_duplicate_unlinked'] = True
        core.fsync_dir(q)
        os.close(ram_fd); handles.remove(ram_fd); ram_fd = None
        location.locate()
        return {'state': 'BUILDER_COLD_ON_SSD_AND_CONSUMERS_VERIFIED', 'storage_receipt_sha256': sha(storage_raw),
                'ram_duplicate_unlinked_bytes': core.SIZE, 'canonical_permission_before': stat.S_IMODE(canonical_before['st_mode']),
                'canonical_permission_after': 0o644, 'canonical_full_sha256_verified': True,
                'canonical_parent_permission_before': 0o777, 'canonical_parent_permission_after': 0o755,
                'canonical_parent_identity_before': parent_before, 'canonical_parent_identity_after': parent_after,
                'canonical_parent_permission_verified': True, 'other_parent_permissions_changed': False,
                'previous_ram_full_sha256_verified': True, 'restore_map': restore_proof,
                'proc_visibility': usage, 'old_ram_receipt_unchanged': True,
                'unique_weight_content_removed': False, 'all_sidecars_preserved': True}
    except BaseException:
        if not removed:
            # Restore only this operation's namespace changes. Foreign paths
            # are preserved, and any uncertainty is a rollback HOLD.
            if parent_mutation.get('attempted'):
                parent_rollback_target(core, c, parent_before, parent_mutation)
            if storage_raw is not None and not published and location.RECEIPT.exists():
                require(location.read(location.RECEIPT, private=True) == storage_raw, 'ROLLBACK_PUBLICATION_FOREIGN')
                published = True
            if published:
                require(location.read(location.RECEIPT, private=True) == storage_raw, 'ROLLBACK_RECEIPT_CHANGED')
                os.unlink(location.RECEIPT.name, dir_fd=state); core.fsync_dir(state)
            if linked:
                require(location.identity(os.stat(core.RAM.name, dir_fd=r, follow_symlinks=False)) == alias_identity
                        and os.readlink(core.RAM.name, dir_fd=r) == str(core.CANONICAL), 'ROLLBACK_ALIAS_CHANGED')
                os.unlink(core.RAM.name, dir_fd=r); core.fsync_dir(r)
            if moved:
                core.rename_noreplace(q, 'ram.safetensors', r, core.RAM.name); core.fsync_dir(r); core.fsync_dir(q)
            if protected:
                if canonical_after is None:
                    canonical_after = core.named(c, core.CANONICAL.name, canonical_fd)
                    require(all(canonical_after[k] == canonical_before[k] for k in core.FIELDS
                                if k not in ('st_mode', 'st_ctime_ns'))
                            and stat.S_IMODE(canonical_after['st_mode']) in (0o644, stat.S_IMODE(canonical_before['st_mode'])),
                            'ROLLBACK_PERMISSION_IDENTITY')
                restore_mode(core, c, core.CANONICAL.name, canonical_fd, canonical_after, canonical_before)
            if parent_mutation.get('attempted'):
                restore_parent(core, c, parent_before, parent_mutation)
                journal['canonical_parent_permission_rollback_verified'] = True
            journal['storage_rollback_verified'] = True
        raise
    finally:
        for fd in reversed(handles):
            os.close(fd)


def live_probe(deploy, js_sha):
    old = "or value.get('drive_adapters',{}).get('verified_files')!=3"
    replacement = old + " or value['drive_adapters'].get('storage_counts')!={'RAM':2,'SSD':1}"
    require(deploy.API_PROBE.count(old) == 1, 'HTTP_PROBE_ANCHOR')
    script = deploy.API_PROBE.replace(old, replacement, 1)
    script = script.replace("'drive_verified_files':value['drive_adapters']['verified_files'],",
                            "'storage_counts':value['drive_adapters']['storage_counts'],'drive_verified_files':value['drive_adapters']['verified_files'],", 1)
    value = subprocess.run([deploy.PYTHON, '-B', '-c', script, js_sha], capture_output=True, timeout=45,
                           env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
    require(value.returncode == 0 and len(value.stdout) <= 16000, 'LIVE_HTTP_VERIFICATION')
    result = json.loads(value.stdout)
    require(result.get('anonymous_http') == 401 and result.get('owner_http') == 200
            and result.get('storage_counts') == {'RAM': 2, 'SSD': 1}, 'LIVE_STORAGE_COUNTS')
    return result


def rollback_sources(deploy, helper, rows, stop_attempted, original_proxy):
    """Classify all intents before service actions; never stop foreign code."""
    owned = []
    for row in rows:
        current = deploy.read(row['path']) if row['path'].exists() or row['path'].is_symlink() else None
        require(current in (row['old'], row['new']), 'ROLLBACK_FOREIGN_SOURCE')
        if current == row['new'] and row['old'] != row['new']:
            owned.append(row)
    state = helper.service_state('nox-proxy')['state']
    require(state in ('RUNNING', 'STOPPED', 'EXITED', 'FATAL'), 'ROLLBACK_UNSETTLED_PROXY')
    if state == 'RUNNING' and owned:
        deploy.stop_proxy(helper, deploy.proxy_identity(helper))
        state = helper.service_state('nox-proxy')['state']
        require(state in ('STOPPED', 'EXITED'), 'ROLLBACK_PROXY_STOP')
    elif state == 'RUNNING' and stop_attempted:
        require(deploy.proxy_identity(helper) == original_proxy, 'ROLLBACK_FOREIGN_PROXY_IDENTITY')
    for row in reversed(owned):
        require(deploy.read(row['path']) == row['new'], 'ROLLBACK_FOREIGN_SOURCE')
        if row['old'] is None:
            os.unlink(row['path'])
        else:
            helper.atomic(row['path'], row['old']); os.chmod(row['path'], 0o644)
        fd = os.open(row['path'].parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try: os.fsync(fd)
        finally: os.close(fd)
    if state in ('STOPPED', 'EXITED', 'FATAL') and stop_attempted:
        deploy.start_proxy(helper)
    return {'owned_writes_restored': len(owned), 'proxy_recovered_after_stop_attempt': stop_attempted}


def main():
    request = os.environ.get('NOX_OWNER_REQUEST_ID', ''); source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    require(re.fullmatch(r'[0-9]{1,24}', request) and re.fullmatch(r'[a-f0-9]{40}', source), 'OWNER_CONTEXT')
    modules, core, proc, proof = dependencies()
    rearm = modules['owner_qwen_disk_rearm_entry.py']; deploy = modules['owner_download_status_entry.py']
    helper = modules['owner_native_repair.py']; location = modules['owner_builder_cold_location.py']
    result = {'schema': SCHEMA, 'request': request, 'source_sha': source, 'started_at': time.time(),
              'state': 'PREFLIGHT', 'weights_merged': False, 'training_actions': 0, 'training_flags_modified': False,
              'private_urls_or_ids_exported': False, 'proxy_restarted': False, 'new_model_loaded': False,
              'global_free_delta_attributed_exclusively_to_operation': False}
    fds = []; rows = []; changed = []; stopped = False; stop_attempted = False; committed = False; journal = {}
    proxy = None
    state = core.directory(STATE); backup = None; receipt = 'owner_builder_cold_storage_' + request + '.json'
    try:
        core.absent(state, receipt)
        for path in (STATE/'media/controller.lock', STATE/'owner_maintenance.lock', STATE/'forge_training.lock',
                     STATE/'owner_drive_ram/transfer.lock'):
            fds.append(rearm.acquire(path))
        require(not (STATE/'OWNER_MAINTENANCE.flag').exists() and not (STATE/'OWNER_MAINTENANCE.flag').is_symlink(), 'MAINTENANCE_FLAG')
        current_sources(deploy)
        checkpoint, heavy, preserve = paused_proof(modules); result.update(checkpoint=checkpoint, legacy_writers=heavy)
        model = deploy.model_identity(helper); proxy = deploy.proxy_identity(helper)
        require(deploy.slots_idle(), 'OWNER_CHAT_BUSY')
        result['model_identity'] = model
        rows = plan_sources(modules, deploy)
        backup_parent = core.directory(ROOT/'backup'); fds.append(backup_parent)
        backup = core.prepare_private(backup_parent, 'builder-cold-storage-'+request); fds.append(backup)
        core.private_json(backup, 'sources-before.json', {'schema': 'NOX_BUILDER_COLD_SOURCE_RESTORE_V1',
            'request': request, 'source_sha': source, 'sources': [{'path': str(row['path']),
            'old_base64': base64.b64encode(row['old']).decode() if row['old'] is not None else None,
            'old_sha256': sha(row['old']) if row['old'] is not None else None, 'new_sha256': sha(row['new'])} for row in rows]})
        result['tmpfs_free_before'] = os.statvfs('/dev/shm').f_bavail * os.statvfs('/dev/shm').f_frsize

        def preserve_all():
            preserve(); current_sources(deploy)
            require(deploy.model_identity(helper) == model, 'MODEL_PID_CHANGED')

        def activate():
            nonlocal stopped, stop_attempted
            preserve_all(); require(deploy.slots_idle(), 'OWNER_CHAT_BUSY')
            stop_attempted = True
            deploy.stop_proxy(helper, proxy); stopped = True
            for row in rows:
                old_now = deploy.read(row['path']) if row['path'].exists() or row['path'].is_symlink() else None
                require(old_now == row['old'], 'SOURCE_PREIMAGE_CHANGED')
                if row['old'] == row['new']:
                    continue
                changed.append(row)  # intent precedes rename/fsync/chmod
                helper.atomic(row['path'], row['new']); os.chmod(row['path'], 0o644)
                require(deploy.read(row['path']) == row['new'], 'SOURCE_READBACK')
            preserve_all()
            deploy.start_proxy(helper); stopped = False; result['proxy_restarted'] = True
            result['acceptance'] = live_probe(deploy, sha(rows[-1]['new']))
            preserve_all()

        outcome = storage_transition(core, location, proc, proof, request, source, backup,
                                     time.monotonic()+180, preserve_all, activate, journal)
        committed = True; result.update(outcome)
        result['tmpfs_free_after'] = os.statvfs('/dev/shm').f_bavail * os.statvfs('/dev/shm').f_frsize
        result['observed_tmpfs_free_delta_bytes'] = result['tmpfs_free_after'] - result['tmpfs_free_before']
        result['source_deltas'] = [{'name': row['path'].name, 'before': sha(row['old']) if row['old'] else None,
                                    'after': sha(row['new'])} for row in rows]
        preserve_all()
    except Exception as exc:
        committed = committed or journal.get('ram_duplicate_unlinked') is True
        result.update(state='HOLD_BUILDER_COLD_STORAGE', reason=core.safe(exc), storage_commit_completed=committed)
        if not committed:
            try:
                if stop_attempted or changed:
                    result['source_rollback'] = rollback_sources(deploy, helper, changed, stop_attempted, proxy)
                    stopped = False
                result['rollback_verified'] = journal.get('storage_rollback_verified', not journal) is True
            except Exception as rollback_error:
                result['rollback_error'] = core.safe(rollback_error)
    finally:
        result['finished_at'] = time.time()
        saved = core.private_json(state, receipt, result)
        for fd in reversed(fds): os.close(fd)
        os.close(state)
    print('NOX_MAINT_REPAIR='+json.dumps({'kind':'builder_cold_storage','data':result},separators=(',',':')),flush=True)
    print('NOX_MAINT_REPAIR='+json.dumps({'kind':'builder_cold_storage_context','data':{'request':request,'source_sha':source,
          'receipt_sha256':saved['sha256'],'receipt_bytes':saved['bytes']}},separators=(',',':')),flush=True)
    ok = result['state'] == 'BUILDER_COLD_ON_SSD_AND_CONSUMERS_VERIFIED'
    print('NOX_MAINT_REPAIR_COMPLETE='+str(ok).lower(),flush=True)
    return 0 if ok else 2


if __name__ == '__main__':
    raise SystemExit(main())
