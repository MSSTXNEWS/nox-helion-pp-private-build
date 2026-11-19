#!/usr/bin/env python3
"""Read exactly the three private journal records of the interrupted smoke.

No bundle, local module import, queue search, HTTP request, POST or filesystem
write. A sealed submission may be passed to the separate reviewed observer;
an intent without that submission never authorizes a second generation POST.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import stat
import time

AREA = Path('/root/nox/state/media/held_rollback_smoke/6913049268')
SCHEMA = 'NOX_QWEN_HELD_MEDIA_JOURNAL_RECOVERY_V1'
SMOKE_SCHEMA = 'NOX_QWEN_HELD_MEDIA_SMOKE_V1'
SUBMISSION_SCHEMA = 'NOX_QWEN_HELD_MEDIA_SUBMISSION_V1'
REQUEST = '6913200714'
SOURCE = '9ffb02f55af3b2d2467bbb60b25ecc56415f2112'
ROLLBACK = {'request': '6913049268', 'source_sha': 'a0fe9630a469713919a38c0542dc7116ae3e2d9f',
            'receipt_sha256': 'bad7e57d3934c433bc0709a12351ab6df3cfd83110b8cc031544395bc9ff5353'}
FIXTURE_SHA = '62005eaff88732087aeb7975212b18cefc21419c95229ea4188d40df0bac815a'
NAMES = ('intent.json', 'submission.json', 'result.json')
LIMIT = 131072
SHA = re.compile('[a-f0-9]{64}')
JOB = re.compile('[a-f0-9]{32}')


def require(ok, code):
    if not ok:
        raise RuntimeError('HOLD_HELD_MEDIA_RECOVERY_' + code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
            info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode), info.st_nlink)


def plain(path):
    require(path.is_absolute() and not any(p.is_symlink() for p in (*path.parents, path)), 'SYMLINK')
    return path


def file_identity(path):
    plain(path)
    try:
        return identity(path.stat(follow_symlinks=False))
    except FileNotFoundError:
        return None


def read_record(path):
    plain(path)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    except FileNotFoundError:
        return None, None
    with os.fdopen(fd, 'rb') as stream:
        first = os.fstat(stream.fileno())
        require(stat.S_ISREG(first.st_mode) and first.st_uid == os.geteuid()
                and stat.S_IMODE(first.st_mode) == 0o600 and first.st_nlink == 1, 'PRIVATE_FILE')
        require(0 <= first.st_size <= LIMIT, 'FILE_BOUND')
        raw = stream.read(LIMIT + 1)
        require(len(raw) == first.st_size and identity(first) == identity(os.fstat(stream.fileno()))
                == file_identity(path), 'FILE_CHANGED')
    return raw, identity(first)


def parse(raw):
    def unique(pairs):
        row = {}
        for key, value in pairs:
            require(key not in row, 'JSON_DUPLICATE'); row[key] = value
        return row
    try:
        row = json.loads(raw, object_pairs_hook=unique,
                         parse_constant=lambda _: require(False, 'JSON_NONFINITE'))
        require(isinstance(row, dict), 'JSON_OBJECT')
        json.dumps(row, allow_nan=False)
        return row
    except (ValueError, UnicodeError, RecursionError):
        require(False, 'PARTIAL_OR_INVALID_JSON')


def finite(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def check_intent(row):
    require(set(row) == {'schema', 'stage', 'rollback_reference', 'request', 'source_sha',
                        'fixture_sha256', 'created_at', 'before', 'generation_retry_authorized'}
            and row['schema'] == SUBMISSION_SCHEMA and row['stage'] == 'PREPARED_SINGLE_POST'
            and row['rollback_reference'] == ROLLBACK and row['request'] == REQUEST and row['source_sha'] == SOURCE
            and row['fixture_sha256'] == FIXTURE_SHA and finite(row['created_at'])
            and isinstance(row['before'], dict) and row['generation_retry_authorized'] is False, 'INTENT_BINDING')


def check_submission(row, intent, intent_sha):
    require(intent is not None and row.get('schema') == SUBMISSION_SCHEMA
            and row.get('stage') == 'SINGLE_JOB_SUBMITTED' and row.get('intent_sha256') == intent_sha
            and isinstance(row.get('job_id'), str) and JOB.fullmatch(row['job_id'])
            and finite(row.get('submitted_at')), 'SUBMISSION_BINDING')
    inverse = {k: v for k, v in row.items() if k not in ('intent_sha256', 'job_id', 'submitted_at')}
    inverse['stage'] = 'PREPARED_SINGLE_POST'
    require(inverse == intent, 'SUBMISSION_INTENT_MISMATCH')


def check_result(row, intent, submission, submission_sha):
    require(row.get('schema') == SMOKE_SCHEMA and row.get('request') == REQUEST
            and row.get('source_sha') == SOURCE and row.get('rollback_reference') == ROLLBACK
            and row.get('state') in {'HOLD', 'MEDIA_SUBMISSION_UNRESOLVED', 'MEDIA_GENERATION_PENDING',
                                    'HELD_TRAINER_IMAGE_AND_OWNER_DELIVERY_VERIFIED'}
            and type(row.get('generation_post_attempts')) is int and row['generation_post_attempts'] in (0, 1)
            and type(row.get('acceptance_verified')) is bool and type(row.get('artifact_verified')) is bool
            and type(row.get('trainer_start_calls')) is int and row['trainer_start_calls'] == 0
            and row.get('training_flags_written') is False and row.get('sources_modified') is False
            and type(row.get('direct_engine_control_calls')) is int and row['direct_engine_control_calls'] == 0
            and row.get('private_content_exported') is False, 'RESULT_BINDING')
    require(row['generation_post_attempts'] == 0 or intent is not None, 'RESULT_INTENT_MISSING')
    if submission is not None:
        expected = {'request': REQUEST, 'source_sha': SOURCE, 'receipt_sha256': submission_sha}
        require(row.get('submission_context') == expected and row.get('before') == intent['before'],
                'RESULT_SUBMISSION_MISMATCH')
        if 'job_id' in row:
            require(row['job_id'] == submission['job_id'], 'RESULT_JOB_MISMATCH')
    else:
        require('submission_context' not in row and 'job_id' not in row, 'UNSEALED_RESULT_JOB')
    if row['acceptance_verified']:
        require(submission is not None and row['state'] == 'HELD_TRAINER_IMAGE_AND_OWNER_DELIVERY_VERIFIED'
                and row['artifact_verified'] is True and row.get('native_generation_claim_verified') is True
                and row.get('training_still_held') is True and row.get('main_chat_identity_preserved') is True,
                'RESULT_ACCEPTANCE_FIELDS')


def inspect():
    result = {'schema': SCHEMA, 'state': 'READING_FIXED_JOURNAL', 'read_only': True,
              'smoke_request': REQUEST, 'smoke_source_sha': SOURCE, 'rollback_reference': ROLLBACK,
              'generation_posts_issued': 0, 'queue_searched': False, 'files_written': 0,
              'native_controls_invoked': 0, 'raw_content_exported': False,
              'generation_independently_verified_by_reader': False, 'automatic_repost_authorized': False,
              'files': {}, 'observed_at': time.time()}
    try:
        plain(AREA); directory_identity = file_identity(AREA)
        if directory_identity is None:
            require(file_identity(AREA) is None, 'DIRECTORY_APPEARED')
            result.update(state='JOURNAL_DIRECTORY_CONFIRMED_ABSENT', directory_present=False,
                          journal_observation_complete=True, prior_generation_occurrence='UNKNOWN')
            return result
        info = AREA.stat(follow_symlinks=False)
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid()
                and stat.S_IMODE(info.st_mode) == 0o700, 'PRIVATE_DIRECTORY')
        result['directory_present'] = True
        raws, identities, rows = {}, {}, {}
        for name in NAMES:
            raw, ident = read_record(AREA / name); raws[name] = raw; identities[name] = ident
            result['files'][name] = {'present': raw is not None}
            if raw is not None:
                result['files'][name].update(bytes=len(raw), sha256=digest(raw))
                rows[name] = parse(raw)
        intent, submission, outcome = (rows.get(name) for name in NAMES)
        if intent is not None:
            check_intent(intent)
        if submission is not None:
            check_submission(submission, intent, digest(raws['intent.json']) if intent is not None else None)
        if outcome is not None:
            check_result(outcome, intent, submission, digest(raws['submission.json']) if submission is not None else None)
        require(all(file_identity(AREA / name) == ident for name, ident in identities.items())
                and file_identity(AREA) == directory_identity, 'JOURNAL_CHANGED_DURING_READ')
        if submission is not None:
            result.update(state='SEALED_SUBMISSION_RESULT_PENDING', job_id=submission['job_id'],
                          submission_context={'request': REQUEST, 'source_sha': SOURCE,
                                              'receipt_sha256': digest(raws['submission.json'])},
                          explicit_observe_existing_available=True)
        elif intent is not None:
            result.update(state='INTENT_PRESENT_SUBMISSION_UNRESOLVED', prior_generation_occurrence='UNKNOWN',
                          explicit_observe_existing_available=False)
        else:
            result.update(state='JOURNAL_RECORDS_CONFIRMED_ABSENT', prior_generation_occurrence='UNKNOWN',
                          explicit_observe_existing_available=False)
        if outcome is not None:
            reason = outcome.get('reason')
            result.update(state='RESULT_RECORDED' if submission is not None else 'RESULT_RECORDED_WITHOUT_SEALED_SUBMISSION',
                          recorded_result_state=outcome['state'], recorded_acceptance_verified=outcome['acceptance_verified'],
                          recorded_artifact_verified=outcome['artifact_verified'],
                          recorded_generation_post_attempts=outcome['generation_post_attempts'],
                          recorded_reason=reason if isinstance(reason, str) and re.fullmatch('(HOLD|WAIT)_[A-Z0-9_]{1,140}', reason) else None,
                          result_context={'request': REQUEST, 'source_sha': SOURCE, 'receipt_sha256': digest(raws['result.json'])})
        result['journal_observation_complete'] = True
    except Exception as exc:
        reason = str(exc)
        result.update(state='JOURNAL_OBSERVATION_HELD', journal_observation_complete=False,
                      reason=reason if re.fullmatch('HOLD_HELD_MEDIA_RECOVERY_[A-Z0-9_]{1,100}', reason)
                      else 'HOLD_HELD_MEDIA_RECOVERY_' + type(exc).__name__.upper())
        # Never expose a job or adopt it after a partially validated snapshot.
        for key in ('job_id', 'submission_context', 'result_context'):
            result.pop(key, None)
        result['explicit_observe_existing_available'] = False
    return result


def main():
    started = time.monotonic(); previous = signal.getitimer(signal.ITIMER_REAL)
    handler = signal.getsignal(signal.SIGALRM)
    def expired(_signum, _frame):
        require(False, 'READ_DEADLINE')
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, min(30.0, previous[0]) if previous[0] > 0 else 30.0)
    try:
        result = inspect()
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0); signal.signal(signal.SIGALRM, handler)
        if previous[0] > 0:
            signal.setitimer(signal.ITIMER_REAL, max(.001, previous[0] - (time.monotonic() - started)), previous[1])
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'qwen_held_media_journal_recovery', 'data': result},
                                         sort_keys=True, separators=(',', ':'), allow_nan=False), flush=True)
    okay = result.get('journal_observation_complete') is True
    print('NOX_MAINT_REPAIR_COMPLETE=' + ('true' if okay else 'false'), flush=True)
    return 0 if okay else 2


if __name__ == '__main__':
    raise SystemExit(main())
