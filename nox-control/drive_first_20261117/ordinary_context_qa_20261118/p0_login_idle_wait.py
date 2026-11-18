"""Observe one official login, then wait for the unchanged arbiter idle guard.

Read-only evidence never overrides native.owner_idle(). Fixed log/heartbeat
observations only add reasons to HOLD; raw log lines never leave this helper.
No app imports, activity writes, counter reset, service action or model request.
"""
from __future__ import annotations
from datetime import datetime
import math
import os
from pathlib import Path
import re
import stat
import time

from p0_witness_protocol import Hold, require, digest

ARBITER_SHA = '4c9df9bbdaa2d788766090b466e3aff226d3c214ce936ac1559e7856a9190be0'
MAX_WAIT = 240.0
MAX_LOG_APPEND = 65536


def evidence_read(path, limit, *, optional=False):
    """Stable root-owned evidence, including its mode; not an admission grant.

    Existing arbiter/log artifacts may be group-writable. They remain unchanged;
    no assertion of strict write protection is made. The authoritative fresh
    priority/STOP/slot checks still use the existing strict native reader.
    """
    path = Path(path)
    try:
        info = path.lstat()
    except FileNotFoundError:
        if optional:
            return None, {'present': False}
        raise
    require(path.resolve() == path and stat.S_ISREG(info.st_mode)
            and info.st_uid == os.geteuid() and not info.st_mode & 0o002
            and info.st_size <= limit, 'HOLD_ACTIVITY_EVIDENCE_PATH')
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        first = os.fstat(fd)
        raw = os.pread(fd, limit + 1, 0)
        after, named = os.fstat(fd), path.lstat()
        keys = ('st_dev', 'st_ino', 'st_uid', 'st_gid', 'st_mode', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
        require(len(raw) == first.st_size and all(getattr(info, k) == getattr(first, k)
                == getattr(after, k) == getattr(named, k) for k in keys), 'HOLD_ACTIVITY_EVIDENCE_DRIFT')
        return raw, {'present': True, 'sha256': digest(raw), 'bytes': len(raw),
                     'dev': first.st_dev, 'ino': first.st_ino, 'mode': oct(stat.S_IMODE(first.st_mode)),
                     'group_writable': bool(first.st_mode & 0o020), 'mtime_ns': first.st_mtime_ns}
    finally:
        os.close(fd)


def priority_snapshot(native, document, now):
    result = {'flags': {}, 'ages_seconds': {}}
    for name in ('CHAT_ACTIVE', 'MODE'):
        raw, info = native.stable_read(native.STATE / 'priority' / name, 64)
        value = raw.strip().decode('ascii')
        require(value in (('0', '1') if name == 'CHAT_ACTIVE' else ('ACTIVE', 'IDLE')),
                'HOLD_PRIORITY_VALUE_UNKNOWN')
        age = now - info['mtime_ns'] / 1e9
        result['flags'][name] = value
        result['ages_seconds'][name] = round(age, 3)
    raw, info = native.stable_read(native.STATE / 'priority/status.json', 32768)
    value = document(raw)
    require(isinstance(value, dict) and value.get('mode') in ('ACTIVE', 'IDLE')
            and type(value.get('train_pause')) is bool, 'HOLD_PRIORITY_SCHEMA_UNKNOWN')
    threshold = value.get('idle_threshold_min')
    require(type(threshold) in (int, float) and math.isfinite(threshold) and 0.5 <= threshold <= 3.5,
            'HOLD_IDLE_THRESHOLD_EXCEEDS_CONTINUATION_BUDGET')
    last_owner = value.get('last_owner_chat')
    if last_owner is not None:
        require(isinstance(last_owner, str) and re.fullmatch(
            r'\d{4}-\d\d-\d\d \d\d:\d\d:\d\d UTC\+01:00', last_owner),
            'HOLD_PRIORITY_LAST_OWNER_FORMAT')
        try:
            datetime.strptime(last_owner, '%Y-%m-%d %H:%M:%S UTC+01:00')
        except ValueError:
            raise Hold('HOLD_PRIORITY_LAST_OWNER_FORMAT') from None
    result.update(status_mode=value['mode'], train_pause=value['train_pause'],
                  idle_threshold_min=threshold, status_sha256=digest(raw),
                  last_owner_chat=last_owner)
    result['ages_seconds']['status'] = round(now - info['mtime_ns'] / 1e9, 3)
    result['fresh'] = all(-2 <= age <= 5 for age in result['ages_seconds'].values())
    result['consistent_idle'] = (result['flags'] == {'CHAT_ACTIVE': '0', 'MODE': 'IDLE'}
                                 and result['status_mode'] == 'IDLE' and result['train_pause'] is False)
    return result


class LoginIdleWait:
    def __init__(self, native, document, counter_reader, baseline, before, lock,
                 report, *, clock=time.time, monotonic=time.monotonic, sleep=time.sleep):
        self.native, self.document = native, document
        self.counter_reader, self.baseline = counter_reader, baseline
        self.before, self.lock, self.report = before, lock, report
        self.clock, self.monotonic, self.sleep = clock, monotonic, sleep
        self.path = native.ROOT / 'logs/proxy.log'
        self.heartbeat = native.STATE / 'priority/LAST_OWNER_CHAT'
        self.fd = None
        self.login_epoch = None
        self.login_at = None
        self.appended = 0
        self.login_seen = False

    def capture(self):
        source, source_info = evidence_read(self.native.SCRIPTS / 'nox_priority_arbiter.py', 32768)
        require(digest(source) == ARBITER_SHA, 'HOLD_ARBITER_SOURCE_DRIFT')
        self.heartbeat_before = evidence_read(self.heartbeat, 4096, optional=True)
        self.initial_priority = priority_snapshot(self.native, self.document, self.clock())
        self.report.update(schema='NOX_OFFICIAL_LOGIN_IDLE_WAIT_V1', status='CAPTURED_BEFORE_LOGIN',
                           maximum_wait_seconds=MAX_WAIT, arbiter_source=source_info,
                           priority_before_login=self.initial_priority,
                           raw_log_exported=False, authority='EXISTING_STRICT_OWNER_IDLE_ONLY',
                           atomic_owner_admission_lease=False, login_markers=0, poll_count=0)
        require(self.initial_priority['fresh'] and self.initial_priority['consistent_idle'],
                'HOLD_PRIORITY_NOT_FRESH_IDLE_BEFORE_LOGIN')
        info = self.path.lstat()
        require(self.path.resolve() == self.path and stat.S_ISREG(info.st_mode)
                and info.st_uid == os.geteuid() and not info.st_mode & 0o002,
                'HOLD_PROXY_LOG_PATH')
        self.fd = os.open(self.path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC)
        bound = os.fstat(self.fd)
        self.log_identity = (info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode)
        require(self.log_identity == (bound.st_dev, bound.st_ino, bound.st_uid, bound.st_gid, bound.st_mode),
                'HOLD_PROXY_LOG_IDENTITY')
        require(all(getattr(info, key) == getattr(bound, key)
                    for key in ('st_size', 'st_mtime_ns', 'st_ctime_ns')), 'HOLD_PROXY_LOG_CAPTURE_RACE')
        self.offset = bound.st_size
        require(self.offset == 0 or os.pread(self.fd, 1, self.offset - 1) == b'\n', 'HOLD_LOG_PARTIAL_BASELINE')
        self.report['log_binding'] = {'dev': bound.st_dev, 'ino': bound.st_ino,
                                     'offset_before_login': self.offset,
                                     'mode': oct(stat.S_IMODE(bound.st_mode))}
        self.login_at = self.clock()
        self.start_mono = self.monotonic()
        return self

    def _log_check(self, *, require_login=False):
        bound, named = os.fstat(self.fd), self.path.lstat()
        for row in (bound, named):
            require((row.st_dev, row.st_ino, row.st_uid, row.st_gid, row.st_mode) == self.log_identity
                    and row.st_size >= self.offset, 'HOLD_PROXY_LOG_ROTATED_OR_TRUNCATED')
        size = bound.st_size - self.offset
        require(0 <= size <= MAX_LOG_APPEND, 'HOLD_PROXY_LOG_APPEND_BUDGET')
        raw = os.pread(self.fd, size, self.offset)
        after, named = os.fstat(self.fd), self.path.lstat()
        for row in (after, named):
            require((row.st_dev, row.st_ino, row.st_uid, row.st_gid, row.st_mode) == self.log_identity,
                    'HOLD_PROXY_LOG_CHANGED_DURING_READ')
        require(all(getattr(bound, key) == getattr(after, key) == getattr(named, key)
                    for key in ('st_mtime_ns', 'st_ctime_ns')), 'HOLD_PROXY_LOG_CHANGED_DURING_READ')
        require(after.st_size == bound.st_size == named.st_size and raw.endswith(b'\n')
                and len(raw) == size, 'HOLD_LOG_CHANGED_OR_PARTIAL_AFTER_LOGIN')
        # Every appended line must be our one loopback login. Even a second
        # login, an unclassified line, or any completion marker fails closed.
        lines = raw.splitlines()
        require(len(lines) == 1, 'HOLD_NEW_OR_UNKNOWN_OWNER_ACTIVITY')
        match = re.fullmatch(
            rb'(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d [+-]\d{4}) chat_login_ok ip=(127\.0\.0\.1|::1)', lines[0])
        require(match is not None, 'HOLD_NEW_OR_UNKNOWN_OWNER_ACTIVITY')
        stamp = datetime.strptime(match[1].decode('ascii'), '%Y-%m-%d %H:%M:%S %z').timestamp()
        require(self.login_at - 1 <= stamp <= self.clock() + 1, 'HOLD_LOGIN_MARKER_TIME_BINDING')
        if self.login_epoch is not None:
            require(stamp == self.login_epoch and digest(raw) == self.login_log_sha,
                    'HOLD_LOGIN_MARKER_CHANGED')
        self.login_epoch, self.login_log_sha = stamp, digest(raw)
        self.appended = size
        self.login_seen = True
        self.report.update(login_markers=1, append_bytes=size, appended_log_sha256=self.login_log_sha)
        return stamp

    def _unchanged(self):
        self.native.global_stop_guard()
        info = (self.native.STATE / 'owner_maintenance.lock').lstat()
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid() and not info.st_mode & 0o022
                and {'dev': info.st_dev, 'ino': info.st_ino} == self.lock, 'HOLD_MAINTENANCE_LOCK_DRIFT')
        observed = self.native.process(self.before['process']['pid'], details=False)
        require(observed is not None and observed['start_ticks'] == self.before['process']['start_ticks'],
                'HOLD_PROXY_LIFETIME_DURING_IDLE_WAIT')
        require(observed.get('state') not in ('Z', 'X'), 'HOLD_PROXY_DEAD_DURING_IDLE_WAIT')
        require(self.counter_reader()[0] == self.baseline, 'HOLD_NEW_COUNTER_ACTIVITY_DURING_IDLE_WAIT')
        require(evidence_read(self.heartbeat, 4096, optional=True) == self.heartbeat_before,
                'HOLD_NEW_HEARTBEAT_DURING_IDLE_WAIT')
        self._log_check(require_login=True)

    def wait(self):
        threshold = self.initial_priority['idle_threshold_min']
        expected_last = None
        while self.monotonic() - self.start_mono <= MAX_WAIT:
            self._unchanged()
            if expected_last is None:
                # Actual arbiter iso() uses the fixed winter Madrid timezone.
                from datetime import timezone, timedelta
                expected_last = datetime.fromtimestamp(self.login_epoch, timezone(timedelta(hours=1))).strftime('%Y-%m-%d %H:%M:%S %Z')
            snapshot = priority_snapshot(self.native, self.document, self.clock())
            elapsed = self.monotonic() - self.start_mono
            self.report.update(latest_priority=snapshot, elapsed_seconds=round(elapsed, 3),
                               poll_count=self.report['poll_count'] + 1)
            require(snapshot['fresh'], 'HOLD_PRIORITY_STALE_DURING_LOGIN_WAIT')
            require(snapshot['idle_threshold_min'] == threshold, 'HOLD_IDLE_THRESHOLD_CHANGED')
            allowed_last = {expected_last}
            if elapsed <= 5:
                allowed_last.add(self.initial_priority['last_owner_chat'])
            require(snapshot['last_owner_chat'] in allowed_last, 'HOLD_NEW_OR_UNKNOWN_ARBITER_ACTIVITY')
            if elapsed >= threshold * 60 + 2 and snapshot['consistent_idle']:
                self._unchanged()
                admission = self.native.owner_idle()  # Never bypass or weaken.
                self._unchanged()
                self.report.update(status='EXISTING_IDLE_REACHED_AFTER_OWN_LOGIN',
                                   idle_threshold_seconds=threshold * 60,
                                   heartbeat_unchanged=True, baseline_counter_unchanged=True)
                return admission
            self.sleep(1.0)
        raise Hold('HOLD_EXISTING_IDLE_NOT_REACHED_WITHIN_BOUND')

    def final_check(self):
        self._unchanged()
        return self.native.owner_idle()

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
