#!/usr/bin/env python3
"""Maintain NOX cgroup headroom by advising only verified unused cache files."""

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
import urllib.request

import owner_memory_cleanup_entry as cache
import owner_memory_governor as governor
import owner_storage_reclaim as storage


MIN_HEADROOM = 8 << 30
PASS_BUDGET = 512 << 20
CGROUP = Path('/sys/fs/cgroup')
CHAT_ACTIVITY = Path('/root/nox/state/chat_active')
EXPECTED_MODEL = 'http://127.0.0.1:8098/slots'


def current_scope():
    raw = Path('/proc/self/cgroup').read_text()
    mounts = []
    for line in Path('/proc/self/mountinfo').read_text().splitlines():
        before, _, after = line.partition(' - ')
        fields = before.split()
        if len(fields) > 4 and fields[4] == str(CGROUP):
            mounts.append((fields[0], fields[3], after.split()[0]))
    if raw.strip() != '0::/' or len(mounts) != 1 or mounts[0][1:] != ('/', 'cgroup2'):
        raise RuntimeError('HOLD_CACHE_SCOPE')
    member = CGROUP.stat()
    if str(os.getpid()) not in (CGROUP / 'cgroup.procs').read_text().splitlines():
        raise RuntimeError('HOLD_CACHE_SCOPE')
    return mounts[0][0], member.st_dev, member.st_ino


class RejectRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, url):
        raise RuntimeError('HOLD_CACHE_CHAT_BUSY_OR_UNKNOWN')


def assert_chat_idle():
    try:
        info = CHAT_ACTIVITY.lstat()
    except FileNotFoundError:
        pass
    else:
        age = time.time() - info.st_mtime
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022
                or age < 3):
            raise RuntimeError('HOLD_CACHE_CHAT_BUSY_OR_UNKNOWN')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), RejectRedirect())
    try:
        with opener.open(EXPECTED_MODEL, timeout=2) as response:
            raw = response.read(100_001)
            if response.status != 200 or len(raw) > 100_000:
                raise ValueError
            slots = json.loads(raw)
        if not isinstance(slots, list) or not 1 <= len(slots) <= 64:
            raise ValueError
        for row in slots:
            flags = [row[key] for key in ('is_processing', 'processing')
                     if isinstance(row, dict) and key in row]
            if not flags or any(flag is not False for flag in flags):
                raise ValueError
    except (OSError, ValueError) as error:
        raise RuntimeError('HOLD_CACHE_CHAT_BUSY_OR_UNKNOWN') from error


def run_once(source):
    cache.require_stop_clear()
    scope = current_scope()
    measured = cache.memory_counters(governor.sample())
    if measured['headroom_bytes'] >= MIN_HEADROOM:
        return {'state': 'HEADROOM_OK', 'before': measured, 'after': measured,
                'page_cache_residency_reduction_bytes': 0}

    def admission():
        cache.require_stop_clear()
        if current_scope() != scope:
            raise RuntimeError('HOLD_CACHE_SCOPE')
        assert_chat_idle()

    admission()
    candidates = storage.audit(str(time.time_ns() // 1000), source, cache_only=True)
    admission()
    result = cache.release_candidates(storage, governor, candidates, maximum_range_bytes=PASS_BUDGET,
                                      check_admission=admission)
    if current_scope() != scope:
        raise RuntimeError('HOLD_CACHE_SCOPE')
    return {key: value for key, value in result.items() if key != 'results'}


def main():
    source = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    while True:
        try:
            result = run_once(source)
        except (OSError, ValueError, RuntimeError) as error:
            state = str(error)
            result = {'state': state if re.fullmatch(r'HOLD_[A-Z0-9_]+', state) else 'HOLD_CACHE_UNVERIFIED'}
        print('NOX_CACHE_MAINTENANCE=' + json.dumps(result, separators=(',', ':')), flush=True)
        time.sleep(120 if result.get('page_cache_residency_reduction_bytes', 0) else 300)


if __name__ == '__main__':
    main()
