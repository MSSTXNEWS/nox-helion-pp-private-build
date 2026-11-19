#!/usr/bin/env python3
"""NOX Drive reconnection guard: bounded OAuth refresh/read-only health check.

No interactive login, secrets in logs, remote writes, syncs, mounts, or deletion.
Once rclone is authorized on the actual NOX host, rclone automatically refreshes
its OAuth access token as needed and updates its private writable config.
"""
from __future__ import annotations
import argparse
import configparser
import fcntl
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import time

APPROVED_FOLDER_ID = '1ewQ-R7z33fN0fKoMNNuFzv1_3rCEP96v'
REMOTE = 'noxdrive'
MAX_CONFIG_BYTES = 131072
MAX_RETRY = 1800
STOP_FLAGS = ('/root/nox/STOP', '/root/nox/STOP.flag', '/root/nox/state/STOP',
              '/root/nox/state/OWNER_MAINTENANCE.flag', '/workspace/NOX_STOP')
SCHEMA = 'NOX_DRIVE_AUTO_RECONNECT_V1'


class Hold(Exception):
    pass


def secure_path(path: Path, *, directory=False):
    """Only local-owner private regular files / private directories, no links."""
    path = Path(os.path.abspath(path))
    if path.is_symlink() or any(p.is_symlink() for p in path.parents):
        raise Hold('HOLD_SYMLINK_PATH')
    try:
        st = path.stat()
    except FileNotFoundError:
        raise Hold('HOLD_CONFIG_MISSING' if not directory else 'HOLD_STATE_DIR_MISSING')
    if st.st_uid != os.geteuid() or st.st_mode & 0o077:
        raise Hold('HOLD_OWNER_PERMISSIONS')
    if directory and not stat.S_ISDIR(st.st_mode):
        raise Hold('HOLD_STATE_DIRECTORY')
    if not directory and not stat.S_ISREG(st.st_mode):
        raise Hold('HOLD_CONFIG_REGULAR_FILE')
    return path, st


def authorized_config(path):
    path, st = secure_path(path)
    if not 0 < st.st_size <= MAX_CONFIG_BYTES:
        raise Hold('HOLD_CONFIG_SIZE')
    cfg = configparser.RawConfigParser(interpolation=None)
    try:
        cfg.read_string(path.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, configparser.Error):
        raise Hold('HOLD_CONFIG_UNREADABLE') from None
    if not cfg.has_section(REMOTE):
        raise Hold('HOLD_REMOTE_MISSING')
    get = lambda k: cfg.get(REMOTE, k, fallback='').strip()
    if get('type') != 'drive':
        raise Hold('HOLD_NOT_DRIVE')
    if get('root_folder_id') != APPROVED_FOLDER_ID:
        raise Hold('HOLD_PROJECT_ROOT_NOT_PINNED')
    if not (get('token') or get('service_account_file') or get('service_account_credentials')):
        raise Hold('HOLD_CREDENTIALS_MISSING')
    # A normal rclone OAuth refresh must be able to update this very config.
    if get('token') and not os.access(path, os.W_OK):
        raise Hold('HOLD_CONFIG_NOT_WRITABLE')
    return path


def read_previous(path):
    try:
        _, st = secure_path(path)
        if st.st_size > 16384:
            return {}
        data = json.loads(path.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) and data.get('schema') == SCHEMA else {}
    except (Hold, OSError, ValueError):
        return {}


def atomic_status(path, value):
    raw = (json.dumps(value, ensure_ascii=True, sort_keys=True) + '\n').encode('utf-8')
    temp = path.with_name('.' + path.name + '.pending')
    fd = os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb') as out:
            out.write(raw)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def next_delay(failures):
    return min(MAX_RETRY, 15 * 2 ** min(7, max(0, failures - 1)))


def classify_failure(stderr):
    # Inspect only known error fingerprints, never include provider response in output.
    value = stderr.lower()[:8192]
    if b'invalid_grant' in value or b'refresh token has expired' in value or b'token has been expired or revoked' in value:
        return 'OWNER_REAUTH_REQUIRED'
    if b'rate limit' in value or b'too many requests' in value or b'quota' in value:
        return 'RETRYABLE_RATE_LIMIT'
    return 'RETRYABLE_TRANSPORT_OR_AUTH'


def stopped(flags=STOP_FLAGS):
    return any(os.path.lexists(f) for f in flags)


def check_once(*, config_path, state_dir, run=subprocess.run, which=shutil.which,
               now=time.time, stop_flags=STOP_FLAGS, min_headroom_mib=128,
               cgroup_root='/sys/fs/cgroup'):
    """Status-only operation, no remote file names or OAuth material in receipts."""
    state_dir, _ = secure_path(Path(state_dir), directory=True)
    lock = state_dir / '.lock'
    fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        st = os.fstat(fd)
        if st.st_uid != os.geteuid() or st.st_mode & 0o077 or not stat.S_ISREG(st.st_mode):
            raise Hold('HOLD_LOCK_PERMISSIONS')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {'schema': SCHEMA, 'state': 'ALREADY_RUNNING', 'connected': False,
                    'verified_live_this_cycle': False}
        status_path = state_dir / 'status.json'
        previous = read_previous(status_path)
        t = int(now())
        result = {'schema': SCHEMA, 'observed_at_unix': t, 'remote': REMOTE,
                  'project_root_pinned': False, 'connected': False,
                  'write_access': 'NOT_TESTED', 'verified_live_this_cycle': False}
        failure = None
        if stopped(stop_flags):
            failure = 'HOLD_OWNER_STOP'
        else:
            try:
                authorized_config(config_path)
                result['project_root_pinned'] = True
            except Hold as exc:
                failure = str(exc)
            if failure is None:
                # If the host has very little cgroup RAM, don't launch a new rclone process.
                try:
                    max_text = (Path(cgroup_root) / 'memory.max').read_text().strip()
                    if max_text != 'max':
                        headroom = int(max_text) - int((Path(cgroup_root) / 'memory.current').read_text().strip())
                        if headroom < min_headroom_mib * 1048576:
                            failure = 'DEFERRED_CGROUP_RAM'
                except (OSError, ValueError):
                    failure = 'DEFERRED_CGROUP_UNVERIFIED'
            if failure is None:
                if previous.get('next_retry_unix', 0) > t and previous.get('state') != 'CONNECTED':
                    result.update(state='WAIT_BACKOFF', next_retry_unix=previous['next_retry_unix'],
                                  consecutive_failures=previous.get('consecutive_failures', 0))
                    atomic_status(status_path, result)
                    return result
                if not which('rclone'):
                    failure = 'HOLD_RCLONE_UNAVAILABLE'
                else:
                    # Read-only lsf will automatically refresh a valid OAuth token in rclone.conf.
                    cmd = ['rclone', '--config', str(config_path), 'lsf', REMOTE + ':',
                           '--max-depth', '1', '--retries', '1', '--low-level-retries', '1',
                           '--tpslimit', '2', '--contimeout', '5s', '--timeout', '10s',
                           '--log-level', 'ERROR']
                    try:
                        proc = run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=25, check=False)
                        failure = None if proc.returncode == 0 else classify_failure(proc.stderr or b'')
                    except subprocess.TimeoutExpired:
                        failure = 'RETRYABLE_TIMEOUT'
                    except (OSError, subprocess.SubprocessError):
                        failure = 'RETRYABLE_PROCESS_ERROR'
        if failure is None:
            result.update(state='CONNECTED', connected=True, verified_live_this_cycle=True,
                          consecutive_failures=0, next_retry_unix=t)
        else:
            fails = previous.get('consecutive_failures', 0)
            fails = max(0, min(100, fails if type(fails) is int else 0)) + 1
            result.update(state=failure, consecutive_failures=fails,
                          next_retry_unix=t + next_delay(fails))
        atomic_status(status_path, result)
        return result
    finally:
        os.close(fd)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--config', default='/root/.config/rclone/rclone.conf')
    ap.add_argument('--state-dir', default='/var/lib/nox-drive-reconnect')
    a = ap.parse_args(argv)
    try:
        value = check_once(config_path=a.config, state_dir=a.state_dir)
    except Hold as exc:
        value = {'schema': SCHEMA, 'state': str(exc), 'connected': False,
                 'verified_live_this_cycle': False}
    print(json.dumps(value, sort_keys=True))
    return 0 if value.get('connected') or value.get('state') in ('WAIT_BACKOFF', 'ALREADY_RUNNING', 'DEFERRED_CGROUP_RAM', 'DEFERRED_CGROUP_UNVERIFIED') else 2


if __name__ == '__main__':
    raise SystemExit(main())
