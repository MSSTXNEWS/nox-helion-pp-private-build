#!/usr/bin/env python3
"""Conditional storage-only Hermes SSD -> existing RAM path, with pinned hydration.

No model/trainer/service start, checkpoint or ledger edit, resource-policy
change, or memory.peak reset. The original SSD inode remains recoverable until
the RAM copy, both aliases, durable restore map and all protected state pass.
"""
from __future__ import annotations
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import time
import types

try:
    BUNDLE = __NOX_BUNDLE_JSON__
except NameError:
    BUNDLE = {}

ROOT = Path('/root/nox')
STATE = ROOT / 'state/owner_hermes_warm'
SCRIPTS = ROOT / 'scripts'
DOWNLOAD = SCRIPTS / 'download_t802u.sh'
DOWNLOAD_BEFORE = '8999a8e51c03a468ebffce2a116c92106a7aeedec1e0a4ce1ac2314e755d1ee9'
HYDRATE_NAME = 'owner_hermes_hydrate.py'
HYDRATE_SHA = 'd58ffd95fa5c3d572468d08f3ccbf14e6a2021c21c4468e1c69eab859ca0c327'
PINS = {
    'owner_hermes_ram_preflight.py': '6b1b0393101d485a12c2b0019095f2aa655c931385645ac655b88f916e154a10',
    'owner_builder_proc_probe.py': '1743c8587dac72f412400be9059d1fe01ef73a1955af2056ff77a550e53af3ff',
    'owner_qwen_disk_rearm_entry.py': 'd7017fecab20dab1dc833b2509b14850d4a65151682031143c23e5596c9b8f38',
}
SCHEMA = 'NOX_HERMES_STORAGE_WARM_MOVE_V1'
RATE = 64 * 1024 ** 2
SECONDS = 390
ANCHOR = b'  local out="$dest/$file"\n'
BRANCH = (b'  # NOX_PINNED_HERMES_RAM_HYDRATE_V1\n'
          b'  if [ "$file" = "Hermes-3-Llama-3.1-8B.Q4_K_M.gguf" ]; then\n'
          b'    /usr/bin/python3 -I -B /root/nox/scripts/owner_hermes_hydrate.py\n'
          b'    return $?\n'
          b'  fi\n')


class Hold(RuntimeError): pass


def require(ok, code):
    if not ok: raise Hold('HOLD_HERMES_WARM_MOVE_' + code)


def digest(raw): return hashlib.sha256(raw).hexdigest()
def encode(value): return json.dumps(value, sort_keys=True, allow_nan=False, separators=(',', ':')).encode()
def safe(exc):
    code = str(exc)
    return code if re.fullmatch('(HOLD|WAIT)_[A-Z0-9_]{1,120}', code) else 'HOLD_HERMES_WARM_MOVE_' + type(exc).__name__.upper()


def module(name, pin):
    raw = base64.b64decode(BUNDLE.get(name, ''), validate=True)
    require(isinstance(pin, str) and len(pin) == 64 and 0 < len(raw) <= 131072 and digest(raw) == pin, 'BUNDLE_PIN')
    value = types.ModuleType('_nox_hermes_move_' + name.removesuffix('.py'))
    value.__file__ = '<pinned-' + name + '>'; sys.modules[value.__name__] = value
    exec(compile(raw, value.__file__, 'exec'), value.__dict__)
    return value, raw


def dependencies():
    h, hraw = module(HYDRATE_NAME, HYDRATE_SHA)
    p, _ = module('owner_hermes_ram_preflight.py', PINS['owner_hermes_ram_preflight.py'])
    proc, _ = module('owner_builder_proc_probe.py', PINS['owner_builder_proc_probe.py'])
    r, _ = module('owner_qwen_disk_rearm_entry.py', PINS['owner_qwen_disk_rearm_entry.py'])
    require((h.SSD, h.WARM, h.SIZE, h.SHA, h.PROFILE_PINS) == (p.SSD, p.WARM, p.SIZE, p.SHA, p.PROFILE_PINS), 'DEPENDENCY_CONSTANTS')
    return h, hraw, p, proc, r


def patch_download(raw, expected=DOWNLOAD_BEFORE):
    require(digest(raw) == expected and raw.count(ANCHOR) == 1
            and b'NOX_PINNED_HERMES_RAM_HYDRATE_V1' not in raw
            and raw.count(b'download_one() {\n') == 1, 'DOWNLOADER_PREIMAGE')
    before, after = raw.split(ANCHOR)
    require(before.rfind(b'download_one() {\n') > before.rfind(b'\n}\n'), 'DOWNLOADER_ANCHOR_SCOPE')
    result = before + ANCHOR + BRANCH + after
    require(result.replace(BRANCH, b'', 1) == raw, 'DOWNLOADER_ONLY_ADDITION')
    checked = subprocess.run(['/bin/bash', '-n'], input=result, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, timeout=2, env={'PATH': '/usr/bin:/bin'})
    require(checked.returncode == 0, 'DOWNLOADER_BASH_SYNTAX')
    return result


def private_directory(h, path, *, create=False):
    if create: os.mkdir(path, 0o700)
    fd = h.directory(path); info = os.fstat(fd)
    try:
        require(info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o700, 'PRIVATE_DIRECTORY')
        require((info.st_dev, info.st_ino) == (path.stat(follow_symlinks=False).st_dev,
                                             path.stat(follow_symlinks=False).st_ino), 'DIRECTORY_CHANGED')
        return fd
    except BaseException: os.close(fd); raise


def create_bytes(h, path, raw, mode=0o600, on_created=None):
    require(0 < len(raw) <= 131072 and 0 <= mode <= 0o777 and mode & 0o400, 'SMALL_CREATE_SCOPE')
    parent = h.directory(path.parent)
    try:
        fd = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, mode, dir_fd=parent)
        try:
            if on_created is not None: on_created(h.identity(os.fstat(fd)))
            # Preserve the existing downloader mode on our new candidate only;
            # the process umask is not allowed to silently change that contract.
            os.fchmod(fd, mode)
            pending = memoryview(raw)
            while pending:
                count = os.write(fd, pending); require(count > 0, 'SMALL_WRITE_PROGRESS'); pending = pending[count:]
            os.fsync(fd); info = h.identity(os.fstat(fd))
        finally:
            try:
                if on_created is not None: on_created(h.identity(os.fstat(fd)))
            finally: os.close(fd)
        os.fsync(parent)
        require(info['st_uid'] == os.geteuid() and info['st_nlink'] == 1
                and stat.S_IMODE(info['st_mode']) == mode and info == h.identity(path.stat(follow_symlinks=False))
                and h.read(path, len(raw)) == raw, 'SMALL_CREATE_READBACK')
        return info
    finally: os.close(parent)


def moved_equal(h, before, after):
    return all(before[key] == after[key] for key in h.FIELDS if key != 'st_ctime_ns')


def checked_file(h, parent, name, size=None):
    fd = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC | getattr(os, 'O_NOATIME', 0), dir_fd=parent)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid() and info.st_nlink == 1
                and (size is None or info.st_size == size), 'FILE_SCOPE')
        require(h.identity(info) == h.identity(os.stat(name, dir_fd=parent, follow_symlinks=False)), 'FILE_NAME_CHANGED')
        return fd, h.identity(info)
    except BaseException: os.close(fd); raise


def paused_begin(h, r):
    r.sources(); guard = r.load(r.GUARD_NAME); status = r.load(r.STATUS_NAME)
    window = r.load('owner_qwen_window_entry.py'); helper = r.load('owner_qwen_install_entry.py')
    config, config_sha = guard.checked_config(r.CONTEXT, r.PINS[r.GUARD_NAME])
    ctx = guard.context_evidence(config); r.stopped(ctx, window, helper)
    previous, _ = guard.previous_state(guard.bindings(config, config_sha, ctx))
    require(previous['state'] == 'INHIBITED' and previous['policy_state']['inhibit'] is True
            and previous['policy_state']['reason'] == 'DISK_EARLY_MARGIN'
            and previous['policy_state']['last_successful_updates'] == 10, 'DISK_PAUSED_CHECKPOINT10')
    flags = r.flags(guard, previous)
    proof, manifest, identities = r.full_checkpoint(guard, status, ctx, flags)
    heavy = r.heavy_stopped(helper)
    return {'guard': guard, 'window': window, 'helper': helper, 'ctx': ctx, 'flags': flags,
            'manifest': manifest, 'identities': identities, 'proof': proof, 'heavy': heavy,
            'config': config, 'config_sha256': config_sha}


def paused_unchanged(r, state, *, services=False):
    r.stop_gate(state['guard']); r.checkpoint_anchors()
    require(r.flags(state['guard']) == state['flags']
            and r.checkpoint_identities(state['manifest']) == state['identities'], 'TRAINING_STATE_CHANGED')
    require(digest(r.read(r.STATE / 'owner_training_admission.json', 64000)) == r.ADMISSION_SHA
            and digest(r.read(r.SCRIPTS / 'run_train_volta_t866u.sh')) == r.WRAPPER_SHA, 'ADMISSION_CHANGED')
    if services:
        r.sources(); r.stopped(state['ctx'], state['window'], state['helper'])
        r.heavy_stopped(state['helper'])
    guard = state['guard']; row, _ = guard.previous_state(guard.bindings(state['config'], state['config_sha256'], state['ctx']))
    require(row['state'] == 'INHIBITED' and row['policy_state']['inhibit'] is True
            and row['policy_state']['reason'] == 'DISK_EARLY_MARGIN'
            and row['checkpoint']['pointer_sha256'] == r.TEN_POINTER
            and 0 <= time.time() - row['sampled_at'] <= 30, 'GUARD_PAUSE_CHANGED_OR_STALE')


def refs(p, proc, info, fd, deadline):
    row = p.process_refs(proc, info, fd, min(deadline, time.monotonic() + 5))
    require(row['known_reference_count'] == 0, 'KNOWN_HERMES_REFERENCE')
    # Unknown /proc visibility is reported, never converted into inactivity proof.
    return row


def raw_alias(h, parent):
    info = os.stat(h.WARM.name, dir_fd=parent, follow_symlinks=False)
    require(stat.S_ISLNK(info.st_mode) and info.st_uid == os.geteuid()
            and os.readlink(h.WARM.name, dir_fd=parent) == str(h.SSD), 'ORIGINAL_WARM_ALIAS')
    return h.identity(info)


def alias_proof(h, p, expected, original_links):
    require(h.reversed_alias(), 'REVERSE_ALIAS')
    rows = p.aliases(expected)
    require(all(row.get('state') == 'KNOWN_SCOPE_METADATA' and row.get('regular') is True
                and row.get('same_ssd_inode') is True for row in rows.values()), 'RAM_ALIAS_CHAIN')
    links = {row['source_path_sha256']: row for entry in rows.values() for row in entry.get('link_metadata', [])}
    require(all(links.get(key) == value for key, value in original_links.items()), 'OTHER_TEACHER_ALIAS_CHANGED')
    return {'warm_and_teacher_resolve_to_verified_ram': True, 'existing_teacher_links_preserved': True}


def copy_verified(h, source_fd, target_fd, source_info, deadline, pause_check):
    value = hashlib.sha256(); total = 0; started = time.monotonic(); last_check = 0
    while total < h.SIZE:
        h.tick(deadline); chunk = min(h.CHUNK, h.SIZE - total)
        h.allocation_gate(h.SIZE - total, chunk)
        raw = os.pread(source_fd, chunk, total); require(raw, 'COPY_EOF')
        h.allocation_gate(h.SIZE - total, len(raw))
        view = memoryview(raw)
        while view:
            count = os.write(target_fd, view); require(count > 0, 'COPY_WRITE'); view = view[count:]
        total += len(raw); value.update(raw); h.allocation_gate(h.SIZE - total)
        if time.monotonic() - last_check >= 1:
            pause_check(); last_check = time.monotonic()
        while time.monotonic() < started + total / RATE:
            h.tick(deadline); time.sleep(min(.02, max(0, started + total / RATE - time.monotonic())))
    os.fsync(target_fd)
    require(total == h.SIZE and value.hexdigest() == h.SHA
            and h.identity(os.fstat(source_fd)) == source_info, 'COPY_SHA_OR_SOURCE_CHANGED')
    return total


def full_hash(h, fd, deadline, path, pause_check):
    before = h.identity(os.fstat(fd)); value = hashlib.sha256(); total = 0; started = time.monotonic(); checked = 0
    require(stat.S_ISREG(before['st_mode']) and before['st_size'] == h.SIZE, 'HASH_SCOPE')
    while total < h.SIZE:
        h.tick(deadline); h.allocation_gate(0)
        raw = os.pread(fd, min(h.CHUNK, h.SIZE - total), total); require(raw, 'HASH_EOF')
        total += len(raw); value.update(raw)
        if time.monotonic() - checked >= 1:
            pause_check(); checked = time.monotonic()
        while time.monotonic() < started + total / RATE:
            h.tick(deadline); time.sleep(min(.02, max(0, started + total / RATE - time.monotonic())))
    require(value.hexdigest() == h.SHA and before == h.identity(os.fstat(fd))
            == h.identity(path.stat(follow_symlinks=False)), 'HASH_OR_NAME_CHANGED')
    return before


def convert_lease(fd, exclusive):
    fcntl.flock(fd, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)


def change_lease(fd, exclusive, journal):
    # flock conversion can drop the old lock before a nonblocking acquisition
    # fails. Never retain a stale EX/SH claim in the recovery path.
    journal['lease_mode'] = None
    convert_lease(fd, exclusive)
    journal['lease_mode'] = 'EX' if exclusive else 'SH'


def configured_manifest(h, context, download_sha):
    return {'schema': h.SCHEMA, 'context': context, 'public_repository': h.REPO,
            'public_revision': h.REVISION, 'public_filename': h.NAME, 'bytes': h.SIZE, 'sha256': h.SHA,
            'ram_path': str(h.WARM), 'ssd_path': str(h.SSD), 'hydrate_source_sha256': HYDRATE_SHA,
            'download_source_sha256': download_sha, 'profile_pins': h.PROFILE_PINS,
            'minimum_cgroup_headroom_bytes': h.MIN_HEADROOM, 'minimum_tmpfs_reserve_bytes': h.TMPFS_RESERVE,
            'durability': 'VOLATILE_RAM_PUBLIC_REVISION_RESTORABLE', 'new_daemon': False}


def switch_aliases(h, p, parents, td, temp, backup, journal, original_links):
    q, ram, ssd, _ = parents
    h.rename(td, 'payload.gguf', ram, h.WARM.name, 2); journal['phase']['warm_exchanged'] = True
    os.fsync(ram); os.fsync(td)
    require(moved_equal(h, journal['warm_original'], h.identity((temp / 'payload.gguf').lstat()))
            and moved_equal(h, journal['ram_verified'], h.identity(h.WARM.lstat())), 'WARM_EXCHANGE_READBACK')
    os.symlink(str(h.WARM), 'ssd.exchange', dir_fd=q)
    journal['ssd_alias_created'] = h.identity(os.stat('ssd.exchange', dir_fd=q, follow_symlinks=False))
    os.fsync(q)
    h.rename(q, 'ssd.exchange', ssd, h.SSD.name, 2); journal['phase']['ssd_exchanged'] = True
    journal['ssd_alias_after'] = h.reversed_alias()
    os.fsync(ssd); os.fsync(q)
    require(moved_equal(h, journal['ssd_original'], h.identity((backup / 'ssd.exchange').lstat())), 'SSD_EXCHANGE_READBACK')
    return alias_proof(h, p, h.identity(h.WARM.lstat()), original_links)


def remove_created(h, path, expected, q, label):
    """Capture by no-replace rename, then delete only our originally-created inode."""
    parent = h.directory(path.parent)
    qname = 'rollback_removed_' + label
    try:
        current = path.stat(follow_symlinks=False)
        require(stat.S_ISREG(current.st_mode) and current.st_uid == os.geteuid()
                and current.st_nlink == 1 and h.identity(current) == expected, 'ROLLBACK_CREATED_FOREIGN')
        h.rename(parent, path.name, q, qname, 1); os.fsync(parent); os.fsync(q)
        moved = os.stat(qname, dir_fd=q, follow_symlinks=False)
        if not moved_equal(h, expected, h.identity(moved)):
            # Preserve a foreign replacement, including when a newer public
            # name prevents no-clobber restoration of that captured inode.
            try: h.rename(q, qname, parent, path.name, 1)
            except OSError: pass
            require(False, 'ROLLBACK_CREATED_RACE_PRESERVED')
        os.unlink(qname, dir_fd=q); os.fsync(q)
    finally: os.close(parent)


def rollback(h, backup, temp, parents, state):
    """Exchange back only our still-identifiable publications; no blind replace."""
    q, ram, ssd, scripts = parents
    result = {}; phase = state['phase']
    if phase.get('ssd_exchanged'):
        current = h.identity(os.stat(h.SSD.name, dir_fd=ssd, follow_symlinks=False))
        require(moved_equal(h, state['ssd_alias_created'], current)
                and stat.S_ISLNK(current['st_mode']) and os.readlink(h.SSD.name, dir_fd=ssd) == str(h.WARM), 'ROLLBACK_SSD_FOREIGN')
        held = h.identity(os.stat('ssd.exchange', dir_fd=q, follow_symlinks=False))
        require(moved_equal(h, state['ssd_original'], held), 'ROLLBACK_SSD_ORIGINAL_CHANGED')
        h.rename(q, 'ssd.exchange', ssd, h.SSD.name, 2); phase['ssd_exchanged'] = False
        os.fsync(ssd); os.fsync(q); result['ssd_original_restored'] = True
    if phase.get('warm_exchanged'):
        require(moved_equal(h, state['ram_verified'], h.identity(os.stat(h.WARM.name, dir_fd=ram, follow_symlinks=False))), 'ROLLBACK_WARM_FOREIGN')
        held = h.identity((temp / 'payload.gguf').stat(follow_symlinks=False))
        require(moved_equal(h, state['warm_original'], held), 'ROLLBACK_WARM_ORIGINAL_CHANGED')
        td = h.directory(temp)
        try: h.rename(td, 'payload.gguf', ram, h.WARM.name, 2)
        finally: os.close(td)
        phase['warm_exchanged'] = False; os.fsync(ram); result['warm_original_alias_restored'] = True
    if phase.get('download_exchanged'):
        require(digest(h.read(DOWNLOAD)) == state['download_after_sha256'], 'ROLLBACK_DOWNLOAD_FOREIGN')
        require(digest(h.read(backup / 'download.exchange')) == DOWNLOAD_BEFORE, 'ROLLBACK_DOWNLOAD_ORIGINAL_CHANGED')
        h.rename(q, 'download.exchange', scripts, DOWNLOAD.name, 2); phase['download_exchanged'] = False
        os.fsync(scripts); os.fsync(q); result['original_downloader_restored'] = True
    for label, path in (('config_created', h.CONFIG), ('helper_created', SCRIPTS / HYDRATE_NAME)):
        if phase.get(label):
            remove_created(h, path, state[label], q, label)
            phase[label] = False; result[label + '_removed'] = True
    return result


def main():
    context = {'request': os.environ.get('NOX_OWNER_REQUEST_ID', ''), 'source_sha': os.environ.get('NOX_OWNER_SOURCE_SHA', '')}
    require(os.geteuid() == 0 and re.fullmatch('[0-9]{1,24}', context['request'])
            and re.fullmatch('[a-f0-9]{40}', context['source_sha']), 'OWNER_CONTEXT')
    h, hraw, p, proc, r = dependencies()
    require(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), 'EXISTING_TIMER')
    old_signal = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(Hold('HOLD_HERMES_WARM_MOVE_DEADLINE')))
    signal.setitimer(signal.ITIMER_REAL, SECONDS); deadline = time.monotonic() + SECONDS - 8
    result = {'schema': SCHEMA, **context, 'state': 'HELD', 'started_at': time.time(),
              'training_or_service_actions': 0, 'checkpoint_or_ledger_changes': 0,
              'memory_peak_reset': False, 'old_peak_credit_used': False, 'ssd_original_unlinked': False,
              'new_daemon': False, 'model_contents_exported': False}
    locks = []; handles = []; source_fd = target_fd = None; maintenance = None
    backup = STATE / context['request']; temp = h.WARM.parent / ('.nox_hermes_move_' + context['request'])
    journal = {'phase': {}, 'lease_mode': None}; parents = None; published = False; temp_owned = None
    backup_owned = False
    try:
        h.tick(deadline)
        if not STATE.exists(): os.mkdir(STATE, 0o700)
        area = private_directory(h, STATE); handles.append(area)
        if not h.LEASE.exists(): create_bytes(h, h.LEASE, b'NOX_HERMES_WARM_LEASE_V1\n')
        locks.append(h.lease(h.LEASE, fcntl.LOCK_EX))
        maintenance = h.lease(h.MAINTENANCE, fcntl.LOCK_SH); locks.append(maintenance); journal['lease_mode'] = 'SH'
        h.tmpfs_verified(); initial = h.allocation_gate(h.SIZE)
        require(initial['cgroup_headroom_bytes'] >= h.MIN_HEADROOM + h.SIZE, 'INITIAL_RAM_72GIB_PLUS_COPY')
        result.update(resources_before=initial, ssd_free_before=p.budget()['ssd_free_bytes'])
        state = paused_begin(h, r); result['checkpoint10_preserved_proof'] = state['proof']
        paused_unchanged(r, state, services=True)
        downloader = h.read(DOWNLOAD); patched = patch_download(downloader)
        result['download_before_sha256'] = DOWNLOAD_BEFORE; result['download_after_sha256'] = digest(patched)
        ssd = h.directory(h.SSD.parent); ram = h.directory(h.WARM.parent); scripts = h.directory(SCRIPTS)
        handles.extend((ssd, ram, scripts))
        source_fd, original = checked_file(h, ssd, h.SSD.name, h.SIZE)
        result['ssd_allocated_bytes_before'] = os.fstat(source_fd).st_blocks * 512
        warm_original = raw_alias(h, ram); aliases = p.aliases(original)
        require(all(row.get('same_ssd_inode') is True for row in aliases.values()), 'KNOWN_TEACHER_ALIASES_REQUIRED')
        original_links = {row['source_path_sha256']: row for item in aliases.values() for row in item.get('link_metadata', [])
                          if row['source_path_sha256'] != digest(str(h.WARM).encode())}
        result['references_before'] = refs(p, proc, original, source_fd, deadline)
        q = private_directory(h, backup, create=True); backup_owned = True; handles.append(q)
        td = private_directory(h, temp, create=True); handles.append(td)
        parents = (q, ram, ssd, scripts)
        # Restore metadata and exact original downloader bytes exist durably
        # before either alias or source namespace is touched.
        create_bytes(h, backup / 'original_download.sh', downloader)
        plan = {'schema': 'NOX_HERMES_STORAGE_RESTORE_MAP_V1', **context, 'ssd_original': original,
                'warm_original': warm_original, 'old_warm_target': str(h.SSD), 'public_repository': h.REPO,
                'public_revision': h.REVISION, 'sha256': h.SHA, 'bytes': h.SIZE,
                'aliases_before': aliases, 'original_download_sha256': DOWNLOAD_BEFORE,
                'hydrate_source_sha256': HYDRATE_SHA, 'checkpoint10_manifest_sha256': r.TEN_MANIFEST,
                'qwen_admission_sha256': r.ADMISSION_SHA, 'qwen_wrapper_sha256': r.WRAPPER_SHA,
                'partial_proc_visibility_not_inactivity_proof': True,
                'restore_after_final_unlink_requires_verified_ram_or_pinned_public_download': True}
        result['restore_map_sha256'] = h.private_record(backup / 'restore_map.json', plan)
        target_fd = os.open('payload.gguf', os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=td)
        temp_owned = h.identity(os.fstat(target_fd))
        journal.update(ssd_original=original, warm_original=warm_original, download_after_sha256=digest(patched))
        result['copied_bytes'] = copy_verified(h, source_fd, target_fd, original, deadline,
                                               lambda: paused_unchanged(r, state))
        os.close(target_fd); target_fd = None
        target_fd, _ = checked_file(h, td, 'payload.gguf', h.SIZE)
        ram_verified = full_hash(h, target_fd, deadline, temp / 'payload.gguf', lambda: paused_unchanged(r, state))
        journal['ram_verified'] = ram_verified
        require(h.identity(os.stat(h.SSD.name, dir_fd=ssd, follow_symlinks=False)) == original
                and raw_alias(h, ram) == warm_original, 'NAMESPACE_CHANGED_DURING_COPY')
        result['references_before_switch'] = refs(p, proc, original, source_fd, deadline)
        paused_unchanged(r, state, services=True)
        result['ram_full_sha_verified_before_publication'] = True
        h.private_record(backup / 'verified_copy.json', {'ram_identity': ram_verified, 'sha256': h.SHA, 'bytes': h.SIZE})
        change_lease(maintenance, True, journal); switch_started = time.monotonic()
        paused_unchanged(r, state, services=True); h.tick(deadline); h.allocation_gate(0)
        require(raw_alias(h, ram) == warm_original and digest(h.read(DOWNLOAD)) == DOWNLOAD_BEFORE, 'SWITCH_PREIMAGES')
        def created(label, info):
            journal[label] = info; journal['phase'][label] = True
        journal['helper_created'] = create_bytes(h, SCRIPTS / HYDRATE_NAME, hraw,
            on_created=lambda info: created('helper_created', info))
        manifest = configured_manifest(h, context, digest(patched))
        journal['config_created'] = create_bytes(h, h.CONFIG, encode(manifest),
            on_created=lambda info: created('config_created', info))
        create_bytes(h, backup / 'download.exchange', patched, stat.S_IMODE(DOWNLOAD.stat(follow_symlinks=False).st_mode))
        h.rename(q, 'download.exchange', scripts, DOWNLOAD.name, 2); journal['phase']['download_exchanged'] = True
        os.fsync(scripts); os.fsync(q)
        require(digest(h.read(backup / 'download.exchange')) == DOWNLOAD_BEFORE
                and digest(h.read(DOWNLOAD)) == digest(patched), 'DOWNLOADER_EXCHANGE_READBACK')
        result.update(switch_aliases(h, p, parents, td, temp, backup, journal, original_links))
        require(time.monotonic() - switch_started <= 12, 'SWITCH_LEASE_BUDGET')
        result['exclusive_switch_seconds'] = time.monotonic() - switch_started
        change_lease(maintenance, False, journal)
        # Large final verification is under SH so dispatcher guard samples live.
        quarantine_info = full_hash(h, source_fd, deadline, backup / 'ssd.exchange', lambda: paused_unchanged(r, state))
        result['references_before_unlink'] = refs(p, proc, quarantine_info, source_fd, deadline)
        paused_unchanged(r, state, services=True)
        require(moved_equal(h, ram_verified, h.identity(os.fstat(target_fd)))
                and h.identity(os.fstat(target_fd)) == h.identity(h.WARM.lstat()), 'PUBLISHED_RAM_CHANGED')
        result.update(alias_proof(h, p, h.identity(os.fstat(target_fd)), original_links))
        h.private_record(backup / 'unlink_intent.json', {
            'state': 'RAM_SHA_ALIASES_HYDRATE_AND_ORIGINAL_SSD_SHA_VERIFIED',
            'restore_map_sha256': result['restore_map_sha256'], 'sha256': h.SHA, 'bytes': h.SIZE,
            'ssd_quarantine_identity': quarantine_info, 'ram_identity': h.identity(os.fstat(target_fd)),
            'download_source_sha256': digest(patched), 'hydrate_source_sha256': HYDRATE_SHA,
            'manifest_sha256': digest(encode(manifest)), 'checkpoint10_preserved': True})
        change_lease(maintenance, True, journal)
        paused_unchanged(r, state, services=True); h.tick(deadline); h.allocation_gate(0)
        require(h.identity((backup / 'ssd.exchange').lstat()) == quarantine_info
                and h.identity(os.fstat(source_fd)) == quarantine_info
                and h.identity(os.fstat(target_fd)) == h.identity(h.WARM.lstat())
                and digest(h.read(DOWNLOAD)) == digest(patched)
                and h.read(h.CONFIG) == encode(manifest)
                and digest(h.read(SCRIPTS / HYDRATE_NAME)) == HYDRATE_SHA, 'FINAL_UNLINK_PROOF_CHANGED')
        result.update(alias_proof(h, p, h.identity(os.fstat(target_fd)), original_links))
        os.unlink('ssd.exchange', dir_fd=q); result['ssd_original_unlinked'] = True; published = True
        os.fsync(q)
        # Close the original inode before measuring; overlay lower layers or
        # invisible external FDs can still make actual reclaimed bytes zero.
        os.close(source_fd); source_fd = None
        result['own_ssd_payload_descriptors_closed'] = True
        change_lease(maintenance, False, journal)
        paused_unchanged(r, state, services=True)
        result.update(state='HERMES_RAM_SHA_ALIASES_AND_PINNED_HYDRATION_VERIFIED',
                      resources_after=h.allocation_gate(0), ssd_free_after=p.budget()['ssd_free_bytes'],
                      checkpoints_and_admission_unchanged=True, full_ram_sha_verified=True,
                      ram_is_durable_backup=False, hydrate_source_sha256=HYDRATE_SHA,
                      hydration_manifest_sha256=digest(encode(manifest)), download_source_sha256=digest(patched))
        result['observed_ssd_free_delta_bytes'] = result['ssd_free_after'] - result['ssd_free_before']
        result['ssd_free_delta_exclusively_attributed'] = False
        result['unlinked_logical_bytes'] = h.SIZE
        result['allocated_ssd_bytes_removed_upper_bound'] = result['ssd_allocated_bytes_before']
        result['qwen_disk_rearm_threshold_bytes'] = r.REARM_FREE
        result['qwen_disk_rearm_space_observed'] = result['ssd_free_after'] >= r.REARM_FREE
    except BaseException as exc:
        result.update(state='COMMITTED_STORAGE_WITH_POSTCHECK_HOLD' if published else 'HELD', reason=safe(exc))
        if not published and parents is not None and any(journal['phase'].values()):
            try:
                if journal['lease_mode'] != 'EX': change_lease(maintenance, True, journal)
                paused_unchanged(r, state, services=True)
                result['rollback'] = rollback(h, backup, temp, parents, journal)
            except BaseException as rollback_error:
                result['rollback_reason'] = safe(rollback_error)
        result['quarantine_retained_after_failure'] = not published and backup_owned
    finally:
        for fd in (source_fd, target_fd):
            if fd is not None: os.close(fd)
        # Only our unverified, unpublished partial can be discarded on failure.
        # A verified RAM copy or a failed rollback is kept for explicit recovery.
        if (temp_owned is not None and not published and not journal['phase'].get('warm_exchanged')
                and not result.get('ram_full_sha_verified_before_publication')):
            try:
                item = temp / 'payload.gguf'; current = item.stat(follow_symlinks=False)
                if (stat.S_ISREG(current.st_mode) and current.st_uid == os.geteuid()
                        and (current.st_dev, current.st_ino) == (temp_owned['st_dev'], temp_owned['st_ino'])):
                    os.unlink(item); result['own_unpublished_partial_removed'] = True
            except OSError:
                result['own_unpublished_partial_removed'] = False
        result['finished_at'] = time.time()
        try:
            if backup_owned: result['final_receipt_sha256'] = h.private_record(backup / 'result.json', result)
        except BaseException as receipt_error:
            result.update(state='COMMITTED_STORAGE_WITH_POSTCHECK_HOLD' if published else 'HELD', receipt_error=safe(receipt_error))
        for fd in reversed(handles): os.close(fd)
        for fd in reversed(locks): os.close(fd)
        signal.setitimer(signal.ITIMER_REAL, 0); signal.signal(signal.SIGALRM, old_signal)
    ok = result['state'] == 'HERMES_RAM_SHA_ALIASES_AND_PINNED_HYDRATION_VERIFIED'
    print('NOX_MAINT_REPAIR=' + encode({'kind': 'hermes_warm_move', 'data': result}).decode(), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=' + str(ok).lower(), flush=True)
    return 0 if ok else 2


if __name__ == '__main__':
    try: raise SystemExit(main())
    except Exception as exc:
        print('NOX_MAINT_REPAIR=' + encode({'kind': 'hermes_warm_move', 'data': {
            'schema': SCHEMA, 'state': 'HELD', 'reason': safe(exc), 'ssd_original_unlinked': False}}).decode(), flush=True)
        print('NOX_MAINT_REPAIR_COMPLETE=false', flush=True)
        raise SystemExit(2)
