#!/usr/bin/env python3
"""Bounded read-only metadata for the existing media jobs directory.

Only valid job JSON names may have their small schema/state fields projected.
No filenames, prompts, error text, arbitrary JSON, writes or HTTP operations.
"""
import collections
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import time

DIRECTORY = Path('/root/nox/state/media/jobs')
RUNTIME = Path('/root/nox/scripts/owner_media_runtime.py')
RUNTIME_SHA = 'ca8ce2466d0ee4321e17bbf2dc26a6f6396bafb93f3df361a1b35a7e8e3347e5'
SCHEMA = 'NOX_MEDIA_JOB_INVENTORY_OBSERVATION_V1'
MAX_ENTRIES = 450
MAX_JSON = 65536
MAX_TOTAL_JSON = 2 * 1024 ** 2
STATES = {'QUEUED', 'WAITING_RESOURCES', 'YIELDING_TRAINING', 'SUBMITTING', 'RUNNING',
          'CANCEL_REQUESTED', 'COMPLETED', 'BLOCKED', 'FAILED', 'CANCELLED'}


class Deadline(RuntimeError):
    pass


def require(ok, code):
    if not ok:
        raise RuntimeError('HOLD_MEDIA_JOB_INVENTORY_' + code)


def plain(path):
    require(path.is_absolute() and not any(p.is_symlink() for p in (*path.parents, path)), 'SYMLINK')
    return path


def identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
            info.st_uid, stat.S_IMODE(info.st_mode), info.st_nlink)


def read_regular(path, limit):
    fd = os.open(plain(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(fd, 'rb') as stream:
        first = os.fstat(stream.fileno())
        require(stat.S_ISREG(first.st_mode) and first.st_uid == os.geteuid()
                and not stat.S_IMODE(first.st_mode) & 0o022 and 0 <= first.st_size <= limit, 'READ_SCOPE')
        raw = stream.read(limit + 1)
        require(len(raw) == first.st_size and identity(first) == identity(os.fstat(stream.fileno()))
                == identity(path.stat(follow_symlinks=False)), 'READ_CHANGED')
    return raw


def category(name):
    if re.fullmatch(r'[a-f0-9]{32}\.json', name):
        return 'JOB_JSON'
    if re.fullmatch(r'[a-f0-9]{32}\.lock', name):
        return 'JOB_LOCK'
    if re.fullmatch(r'\.media-[A-Za-z0-9_-]{6,64}', name):
        return 'RUNTIME_ATOMIC_TEMP'
    return 'OTHER_JSON' if name.endswith('.json') else 'OTHER_ENTRY'


def schema_state(raw, stem):
    def unique(pairs):
        row = {}
        for key, value in pairs:
            require(key not in row, 'JSON_DUPLICATE'); row[key] = value
        return row
    try:
        value = json.loads(raw, object_pairs_hook=unique,
                           parse_constant=lambda _: require(False, 'JSON_NONFINITE'))
        require(isinstance(value, dict), 'JSON_OBJECT')
        json.dumps(value, allow_nan=False)
        state = value.get('state')
        return {'read_state': 'PARSED', 'schema_matches': value.get('schema') == 'NOX_OWNER_MEDIA_JOB_V1',
                'id_matches_filename': value.get('id') == stem,
                'state': state if isinstance(state, str) and state in STATES else 'OTHER_STATE'}
    except Deadline:
        raise
    except Exception:
        return {'read_state': 'INVALID_OR_PARTIAL_JSON'}


def inspect():
    result = {'schema': SCHEMA, 'state': 'READING', 'read_only': True, 'observed_at': time.time(),
              'generation_posts_issued': 0, 'files_written': 0, 'raw_content_exported': False,
              'filenames_exported': False, 'generation_admission_authorized': False,
              'runtime_source_sha256': RUNTIME_SHA, 'entries': [], 'json_bytes_read': 0}
    try:
        source = read_regular(RUNTIME, 131072)
        require(hashlib.sha256(source).hexdigest() == RUNTIME_SHA, 'RUNTIME_PIN')
        plain(DIRECTORY)
        info = DIRECTORY.stat(follow_symlinks=False)
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid(), 'DIRECTORY_SCOPE')
        directory_before = identity(info)
        rows = []
        with os.scandir(DIRECTORY) as entries:
            for index, entry in enumerate(entries, 1):
                require(index <= MAX_ENTRIES, 'ENTRY_BOUND')
                rows.append((entry.name, entry.stat(follow_symlinks=False)))
        names = {name for name, _ in rows}
        categories = collections.Counter(); states = collections.Counter(); failures = 0; unread = 0
        for name, info in rows:
            kind = category(name); categories[kind] += 1
            regular = stat.S_ISREG(info.st_mode)
            typename = ('REGULAR' if regular else 'SYMLINK' if stat.S_ISLNK(info.st_mode)
                        else 'DIRECTORY' if stat.S_ISDIR(info.st_mode) else 'OTHER')
            strict_ok = regular and kind == 'JOB_JSON'
            failures += int(not strict_ok)
            row = {'entry_hash_id': hashlib.sha256(os.fsencode(name)).hexdigest()[:24], 'category': kind,
                   'type': typename, 'bytes': info.st_size, 'uid': info.st_uid, 'mode': oct(stat.S_IMODE(info.st_mode)),
                   'link_count': info.st_nlink, 'smoke51_name_type_predicate_pass': strict_ok}
            if kind == 'JOB_LOCK':
                row.update(companion_json_name_present=name[:-5] + '.json' in names,
                           regular_owner600_empty_single_link=regular and info.st_uid == os.geteuid()
                               and stat.S_IMODE(info.st_mode) == 0o600 and info.st_size == 0 and info.st_nlink == 1)
            elif kind == 'JOB_JSON':
                if (regular and info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o600
                        and info.st_nlink == 1 and info.st_size <= MAX_JSON
                        and result['json_bytes_read'] + info.st_size <= MAX_TOTAL_JSON):
                    try:
                        raw = read_regular(DIRECTORY / name, min(MAX_JSON, MAX_TOTAL_JSON - result['json_bytes_read']))
                        result['json_bytes_read'] += len(raw)
                        row.update(schema_state(raw, name[:-5]))
                    except Deadline:
                        raise
                    except Exception:
                        row['read_state'] = 'UNAVAILABLE_OR_CHANGED'
                else:
                    row['read_state'] = 'SKIPPED_SCOPE_OR_BUDGET'
                if row.get('read_state') == 'PARSED':
                    states[row['state']] += 1
                else:
                    unread += 1
            if len(result['entries']) < 128:
                result['entries'].append(row)
        after = DIRECTORY.stat(follow_symlinks=False)
        result.update(state='MEDIA_JOB_INVENTORY_OBSERVED', observation_complete=True,
                      entry_count=len(rows), category_counts=dict(categories), parsed_state_counts=dict(states),
                      strict_smoke51_predicate_failures=failures, json_records_not_parsed=unread,
                      details_truncated=len(rows) > 128,
                      directory_metadata_stable=directory_before == identity(after))
    except Exception as exc:
        reason = str(exc)
        result.update(state='MEDIA_JOB_INVENTORY_OBSERVATION_HELD', observation_complete=False,
                      reason=reason if re.fullmatch('HOLD_MEDIA_JOB_INVENTORY_[A-Z0-9_]{1,100}', reason)
                      else 'HOLD_MEDIA_JOB_INVENTORY_' + type(exc).__name__.upper())
    return result


def main():
    started = time.monotonic(); previous = signal.getitimer(signal.ITIMER_REAL)
    handler = signal.getsignal(signal.SIGALRM)
    def expired(_signum, _frame):
        raise Deadline('HOLD_MEDIA_JOB_INVENTORY_DEADLINE')
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, min(30., previous[0]) if previous[0] else 30.)
    try:
        result = inspect()
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0); signal.signal(signal.SIGALRM, handler)
        if previous[0]:
            signal.setitimer(signal.ITIMER_REAL, max(.001, previous[0] - (time.monotonic() - started)), previous[1])
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'media_job_inventory', 'data': result},
                                         sort_keys=True, separators=(',', ':'), allow_nan=False), flush=True)
    okay = result.get('observation_complete') is True
    print('NOX_MAINT_REPAIR_COMPLETE=' + ('true' if okay else 'false'), flush=True)
    return 0 if okay else 2


if __name__ == '__main__':
    raise SystemExit(main())
