#!/usr/bin/env python3
"""NOX V16 R18 source-only execution controls. Stdlib; no network, merges or builds.

Read-only tools; every PREVIEW is explicitly non-authorizing. Original NOX
CANON §33 / V16 R29 and authorized owner review always prevail.
"""
import argparse
import datetime as dt
import hashlib
import json
import math
import pathlib
import re
import sys

STAGES = ('OPEN', 'PATCHED', 'VERIFIED', 'INTEGRATED', 'ACCEPTED', 'HOLD')
PRODUCT = {'P01': 0.20, 'P02': 0.25, 'P03': 0.20, 'P04': 0.25, 'P05': 0.10}
HEX40 = re.compile(r'[0-9a-f]{40}\Z')
HEX64 = re.compile(r'[0-9a-f]{64}\Z')
MAX_INPUT = 4 * 1024 * 1024


def require(test, reason):
    if not test:
        raise ValueError(reason)


def duplicate_guard(pairs):
    obj = {}
    for key, value in pairs:
        require(key not in obj, 'DUPLICATE_JSON_KEY:' + key)
        obj[key] = value
    return obj


def read_json(path):
    raw = pathlib.Path(path).read_bytes()
    require(len(raw) <= MAX_INPUT, 'INPUT_TOO_LARGE')
    return json.loads(raw.decode('utf-8'), object_pairs_hook=duplicate_guard,
                      parse_constant=lambda value: require(False, 'NONFINITE_JSON'))


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


def is_sha(value, pattern=HEX64):
    return type(value) is str and pattern.fullmatch(value) is not None


def iso_utc(text):
    require(type(text) is str and (text.endswith('Z') or re.search(r'[+-]\d\d:\d\d$', text)), 'TIMEZONE_REQUIRED')
    try:
        instant = dt.datetime.fromisoformat(text.replace('Z', '+00:00'))
    except ValueError as ex:
        raise ValueError('INVALID_TIMESTAMP') from ex
    require(instant.tzinfo is not None, 'TIMEZONE_REQUIRED')
    return instant.astimezone(dt.timezone.utc)


def checked_path(root, path, must_exist=True):
    require(type(path) is str and path and '\\' not in path and '\x00' not in path
            and not re.search(r'[:\x00-\x1f]', path), 'UNSAFE_PATH')
    parts = pathlib.PurePosixPath(path)
    require(not parts.is_absolute() and all(p not in ('.', '..') for p in path.split('/')),
            'UNSAFE_RELATIVE_PATH')
    base = pathlib.Path(root).resolve(strict=True)
    p = base.joinpath(*parts.parts)
    require(p.resolve(strict=False).is_relative_to(base), 'SYMLINK_ESCAPE')
    require(not p.is_symlink(), 'SYMLINK_FILE_FORBIDDEN')
    current = base
    for part in parts.parts:
        current = current / part
        require(not current.is_symlink(), 'SYMLINK_PARENT_FORBIDDEN')
    if must_exist:
        require(p.is_file(), 'FILE_MISSING:' + path)
    return p


def registry_ok(reg):
    require(type(reg) is dict and type(reg.get('tasks')) is list, 'TASK_ARRAY_REQUIRED')
    tasks = reg['tasks']
    require(tasks and len(tasks) <= 10000, 'INVALID_TASK_COUNT')
    ids = []
    for task in tasks:
        require(type(task) is dict, 'INVALID_TASK')
        task_id = task.get('id')
        require(type(task_id) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', task_id), 'INVALID_TASK_ID')
        ids.append(task_id)
        require(task.get('package') in (*PRODUCT, 'GATE'), 'UNKNOWN_PACKAGE')
        require(task.get('state') in STAGES, 'UNKNOWN_STATE')
        require(type(task.get('owner')) is str and task['owner'], 'OWNER_REQUIRED')
        require(type(task.get('priority', 2)) is int and 0 <= task.get('priority', 2) <= 3, 'INVALID_PRIORITY')
        deps = task.get('depends_on', [])
        require(type(deps) is list and all(type(d) is str for d in deps), 'INVALID_DEPENDENCIES')
        require(len(set(deps)) == len(deps), 'DUPLICATE_DEPENDENCY')
        if 'weight' in task:
            weight = task['weight']
            require(type(weight) in (int, float) and math.isfinite(weight) and 0 < weight <= 1000,
                    'INVALID_WEIGHT')
    require(len(ids) == len(set(ids)), 'DUPLICATE_TASK_ID')
    valid = set(ids)
    graph = {}
    for task in tasks:
        deps = task.get('depends_on', [])
        require(all(x in valid and x != task['id'] for x in deps), 'UNRESOLVED_DEPENDENCY')
        graph[task['id']] = deps
    marked = set()
    visiting = set()
    def walk(key):
        require(key not in visiting, 'DEPENDENCY_CYCLE')
        if key in marked:
            return
        visiting.add(key)
        for dep in graph[key]:
            walk(dep)
        visiting.remove(key)
        marked.add(key)
    for key in ids:
        walk(key)
    return tasks


def queue_preview(reg, now):
    tasks = registry_ok(reg)
    accepted = {t['id'] for t in tasks if t['state'] == 'ACCEPTED'}
    next_actions = []
    for task in tasks:
        if task['state'] in ('ACCEPTED', 'HOLD') or any(x not in accepted for x in task.get('depends_on', [])):
            continue
        lease = task.get('lease')
        if lease is not None:
            require(type(lease) is dict and type(lease.get('owner')) is str and type(lease.get('token')) is str,
                    'INVALID_LEASE')
            expires = iso_utc(lease.get('expires_at'))
            if expires > now:
                continue
            # Never automatically seize an expired lease, which may still be held by a live remote writer.
            next_actions.append({'id': task['id'], 'owner': task['owner'], 'state': 'STALE_LEASE_REQUIRES_OWNER_CAS',
                                 'priority': task.get('priority', 2)})
            continue
        next_actions.append({'id': task['id'], 'owner': task['owner'], 'state': task['state'],
                             'priority': task.get('priority', 2)})
    dependency_count = {t['id']: sum(t['id'] in v.get('depends_on', []) for v in tasks) for t in tasks}
    next_actions.sort(key=lambda t: (t['state'] == 'STALE_LEASE_REQUIRES_OWNER_CAS',
                                    t['priority'], -dependency_count[t['id']], t['id']))
    return {'status': 'QUEUE_PREVIEW_ONLY', 'ready': next_actions,
            'no_remote_reservation_or_owner_authorization': True}


def admit_preview(receipt, registry, owner_map, source_root, candidate_root, observed_head):
    tasks = registry_ok(registry)
    require(type(receipt) is dict and receipt.get('schema') == 'NOX_PATCH_V2', 'RECEIPT_V2_REQUIRED')
    require(is_sha(observed_head, HEX40) and receipt.get('expected_head') == observed_head, 'STALE_OR_INVALID_HEAD')
    task = next((t for t in tasks if t['id'] == receipt.get('task_id')), None)
    require(task is not None, 'UNKNOWN_TASK')
    require(task['state'] != 'ACCEPTED', 'TASK_ALREADY_ACCEPTED')
    require(receipt.get('owner') == task.get('owner'), 'TASK_OWNER_MISMATCH')
    require(type(owner_map) is dict and type(owner_map.get('path_owners')) is dict, 'TRUSTED_OWNER_MAP_REQUIRED')
    files = receipt.get('files')
    require(type(files) is list and 0 < len(files) <= 200, 'INVALID_PATCH_FILE_COUNT')
    observed = []
    paths = set()
    for f in files:
        require(type(f) is dict, 'INVALID_PATCH_ENTRY')
        path = f.get('path')
        require(type(path) is str and path not in paths, 'DUPLICATE_OR_INVALID_PATCH_PATH')
        paths.add(path)
        allowed = owner_map['path_owners'].get(path)
        require(allowed == receipt['owner'], 'PATH_OWNER_NOT_AUTHORIZED:' + path)
        expected_pre = f.get('pre_sha256')
        require(expected_pre == 'ABSENT' or is_sha(expected_pre), 'INVALID_PRE_SHA')
        require(is_sha(f.get('post_sha256')), 'INVALID_POST_SHA')
        candidate = checked_path(candidate_root, path)
        require(candidate.stat().st_size <= MAX_INPUT, 'PATCH_FILE_TOO_LARGE')
        real_post = digest(candidate.read_bytes())
        require(real_post == f['post_sha256'], 'CANDIDATE_BYTES_MISMATCH:' + path)
        original = checked_path(source_root, path, must_exist=False)
        if expected_pre == 'ABSENT':
            require(not original.exists(), 'EXPECTED_ABSENT_BUT_EXISTS:' + path)
        else:
            require(original.is_file(), 'SOURCE_FILE_MISSING:' + path)
            require(original.stat().st_size <= MAX_INPUT, 'SOURCE_FILE_TOO_LARGE')
            require(digest(original.read_bytes()) == expected_pre, 'PREIMAGE_MISMATCH:' + path)
        observed.append({'path': path, 'pre_sha256': expected_pre, 'post_sha256': real_post})
    return {'status': 'SOURCE_BYTES_MATCH_PREVIEW_NOT_AUTHORIZED', 'task_id': task['id'],
            'claimed_owner': receipt['owner'], 'expected_head': observed_head,
            'files': observed, 'git_remote_owner_authenticated': False,
            'merge_performed': False, 'qa_accepted': False}


def test_plan(matrix, changed):
    require(type(matrix) is dict and type(matrix.get('always')) is list
            and type(matrix.get('rules')) is list, 'INVALID_TEST_MATRIX')
    ensure = matrix['always']
    require(all(type(t) is str and t for t in ensure), 'INVALID_TEST_NAME')
    # Security and no-loss checks may never be disabled by a contributed matrix.
    tests = set(ensure) | {'stop_acl_consent_privacy', 'no_loss_source_lock'}
    unmatched = []
    for path in changed:
        require(type(path) is str and path, 'INVALID_CHANGED_PATH')
        matched = False
        for r in matrix['rules']:
            require(type(r) is dict and type(r.get('prefix')) is str and type(r.get('tests')) is list,
                    'INVALID_TEST_RULE')
            prefix = r['prefix'].rstrip('/')
            require(all(type(t) is str and t for t in r['tests']), 'INVALID_TEST_NAME')
            if path == prefix or path.startswith(prefix + '/'):
                tests.update(r['tests'])
                matched = True
        if not matched:
            unmatched.append(path)
    return {'status': 'MANUAL_TEST_MAPPING_REQUIRED' if unmatched else 'TEST_PLAN_ONLY',
            'tests': sorted(tests), 'unmapped_paths': sorted(set(unmatched)),
            'no_tests_were_executed': True}


def evidence_status(claims, qa_receipts_dir, current_head):
    """Checksum corroboration, NOT authentication of QA author or remote source."""
    require(is_sha(current_head, HEX40), 'INVALID_CURRENT_HEAD')
    require(type(claims) is list, 'CLAIMS_ARRAY_REQUIRED')
    corroborated = set()
    claimed = set()
    rejected = []
    for claim in claims:
        task_id = claim.get('task_id')
        if claim.get('stage') != 'ACCEPTED':
            continue
        claimed.add(task_id)
        try:
            require(type(task_id) is str and task_id, 'TASK_ID_MISSING')
            require(claim.get('head') == current_head, 'CLAIM_HEAD_DRIFT')
            path = claim.get('qa_receipt_path')
            require(is_sha(claim.get('qa_receipt_sha256')), 'QA_RECEIPT_SHA_MISSING')
            f = checked_path(qa_receipts_dir, path)
            require(digest(f.read_bytes()) == claim['qa_receipt_sha256'], 'QA_RECEIPT_HASH_MISMATCH')
            receipt = read_json(f)
            require(receipt.get('task_id') == task_id and receipt.get('head') == current_head
                    and receipt.get('reviewer_role') == '2' and receipt.get('decision') == 'PASS',
                    'QA_RECEIPT_CONTENT_MISMATCH')
            corroborated.add(task_id)
        except (ValueError, KeyError, TypeError, FileNotFoundError) as ex:
            rejected.append({'task_id': task_id, 'reason': str(ex)})
    return {'claimed_accepted': len(claimed), 'local_qa_receipts_checksum_matched': len(corroborated),
            'rejected_claims': rejected,
            'independent_remote_authorization_verified': False,
            'count_as_product_done_without_remote_owner_validation': False}


def productivity(runs, accepted_ids=None):
    """Do not mistake run-status completed for product acceptance or sum for wall time."""
    require(type(runs) is list, 'RUNS_ARRAY_REQUIRED')
    worker_seconds = 0.0
    intervals = []
    for run in runs:
        require(type(run) is dict and run.get('started_at') and run.get('completed_at'), 'COMPLETE_RUN_TIMES_REQUIRED')
        start = iso_utc(run['started_at'])
        finish = iso_utc(run['completed_at'])
        require(finish >= start, 'NEGATIVE_DURATION')
        seconds = (finish - start).total_seconds()
        worker_seconds += seconds
        intervals.append((start, finish))
    intervals.sort()
    merged = []
    for start, end in intervals:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    wall_seconds = sum((end - start).total_seconds() for start, end in merged)
    # Input IDs are self-reported, not independently authenticated QA evidence.
    # Never turn these into a trusted accepted rate or numerical ETA.
    require(accepted_ids is None or
            (type(accepted_ids) is list and
             all(type(x) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', x)
                 for x in accepted_ids)), 'INVALID_REPORTED_ACCEPTED_IDS')
    reported = len(set(accepted_ids)) if accepted_ids is not None else None
    return {'completed_runs': len(runs), 'worker_minutes': round(worker_seconds/60, 2),
            'wall_active_minutes': round(wall_seconds/60, 2),
            'unique_reported_accepted_unverified': reported,
            'unique_verified_accepted': None,
            'accepted_per_worker_hour': None,
            'forecast': 'N/D — independent QA receipts, complete denominator and critical path required',
            'source': 'system run timestamps; reported accepted IDs are not verified'}


def component_preview(components):
    """Validate pinned integration proposals, never claim license/remote provenance verification."""
    require(type(components) is list and 0 < len(components) <= 200, 'COMPONENTS_REQUIRED')
    rows = []
    names = set()
    for item in components:
        require(type(item) is dict, 'INVALID_COMPONENT')
        name = item.get('name')
        version = item.get('version')
        license_id = item.get('license_spdx')
        url = item.get('source_url')
        sha = item.get('sha256')
        require(type(name) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', name), 'INVALID_COMPONENT_NAME')
        require(name not in names, 'DUPLICATE_COMPONENT')
        names.add(name)
        require(type(version) is str and bool(re.fullmatch(r'[0-9]+(?:\.[0-9A-Za-z-]+)*', version))
                and not any(x in version.lower() for x in ('latest', 'nightly', 'snapshot')),
                'UNPINNED_VERSION')
        require(type(license_id) is str and bool(re.fullmatch(r'[A-Za-z0-9.+-]{2,64}', license_id)),
                'LICENSE_IDENTIFIER_REQUIRED')
        require(type(url) is str and url.startswith('https://') and len(url) <= 2048,
                'HTTPS_SOURCE_REQUIRED')
        require(is_sha(sha), 'COMPONENT_DIGEST_REQUIRED')
        rows.append({'name': name, 'version': version, 'license_spdx': license_id,
                     'declared_sha256': sha, 'status': 'EXTERNAL_PROVENANCE_AND_LICENSE_REVIEW_REQUIRED'})
    return {'status': 'PROPOSAL_ONLY', 'components': rows, 'network_fetched': False,
            'license_approved': False, 'can_import_to_product': False}


def progress_preview(lanes):
    require(type(lanes) is dict, 'LANES_REQUIRED')
    result = {}
    total = 0
    valid = True
    ids = set()
    for pkg, weight in PRODUCT.items():
        lane = lanes.get(pkg)
        if type(lane) is not dict or lane.get('frozen') is not True or not is_sha(lane.get('manifest_sha256')):
            result[pkg] = {'percent': None, 'reason': 'FROZEN_MANIFEST_AND_EVIDENCE_REQUIRED'}
            valid = False
            continue
        tasks = lane.get('tasks')
        if type(tasks) is not list or not tasks:
            result[pkg] = {'percent': None, 'reason': 'COMPLETE_TASK_INVENTORY_REQUIRED'}
            valid = False
            continue
        if any(type(t) is not dict or type(t.get('id')) is not str or t['id'] in ids for t in tasks):
            raise ValueError('DUPLICATE_OR_INVALID_PRODUCT_TASK')
        ids.update(t['id'] for t in tasks)
        if any(type(t.get('weight')) not in (int, float) or not math.isfinite(t['weight']) or t['weight'] <= 0 for t in tasks):
            raise ValueError('INVALID_PRODUCT_WEIGHTS')
        denominator = sum(t['weight'] for t in tasks)
        # Does not cryptographically verify claimed source acceptance, so provide only a conditional score.
        claimed = sum(t['weight'] for t in tasks if t.get('state') == 'ACCEPTED' and
                      is_sha(t.get('qa_receipt_sha256')) and is_sha(t.get('accepted_head'), HEX40))
        pct = round(100 * claimed/denominator, 2)
        result[pkg] = {'claimed_evidence_covered_percent': pct,
                       'percent': None, 'reason': 'INDEPENDENT_REMOTE_RECEIPT_VALIDATION_REQUIRED'}
        valid = False
    return {'blocks': result, 'product_percent': None, 'product_weights': PRODUCT,
            'release_acceptance': 'SEPARATE_GATE',
            'warning': 'Frozen manifest SHA alone is not authenticity; product score remains N/D until independently verified'}


def gitlab_compare(expected, observed):
    require(type(expected) is dict and type(observed) is dict, 'INPUT_OBJECTS_REQUIRED')
    ref = expected.get('source_commit')
    require(is_sha(ref, HEX40), 'INVALID_EXPECTED_COMMIT')
    actual = observed.get('head_commit')
    if actual is None or not observed.get('authenticated_readback'):
        return {'status': 'ACCESS_HOLD', 'gitlab_ready': False, 'reason': 'No authenticated live GitLab readback'}
    require(is_sha(actual, HEX40), 'INVALID_GITLAB_HEAD')
    same = actual == ref
    return {'status': 'SAME_COMMIT_REPORTED' if same else 'DIVERGENT_COMMIT',
            'gitlab_ready': False, 'same_commit': same,
            'note': 'Reported live heads are NOT a proof of ACL, provenance, file preservation, or approved build'}


def main():
    cli = argparse.ArgumentParser()
    sub = cli.add_subparsers(dest='command', required=True)
    q = sub.add_parser('queue');q.add_argument('registry');q.add_argument('--now', required=True)
    p = sub.add_parser('admit-preview');p.add_argument('receipt');p.add_argument('registry');p.add_argument('owner_map');p.add_argument('source_root');p.add_argument('candidate_root');p.add_argument('--head', required=True)
    t = sub.add_parser('select-tests');t.add_argument('matrix');t.add_argument('changed', nargs='+')
    v = sub.add_parser('verify-qa');v.add_argument('claims');v.add_argument('qa_receipts_dir');v.add_argument('--head', required=True)
    m = sub.add_parser('throughput');m.add_argument('runs')
    c = sub.add_parser('progress');c.add_argument('lanes')
    g = sub.add_parser('gitlab-compare');g.add_argument('expected');g.add_argument('observed')
    b = sub.add_parser('component-preview');b.add_argument('components')
    args = cli.parse_args()
    if args.command == 'queue': result = queue_preview(read_json(args.registry), iso_utc(args.now))
    elif args.command == 'admit-preview': result = admit_preview(read_json(args.receipt), read_json(args.registry), read_json(args.owner_map), args.source_root, args.candidate_root, args.head)
    elif args.command == 'select-tests': result = test_plan(read_json(args.matrix), args.changed)
    elif args.command == 'verify-qa': result = evidence_status(read_json(args.claims)['claims'], args.qa_receipts_dir, args.head)
    elif args.command == 'throughput': result = productivity(read_json(args.runs)['runs'])
    elif args.command == 'progress': result = progress_preview(read_json(args.lanes))
    elif args.command == 'gitlab-compare': result = gitlab_compare(read_json(args.expected), read_json(args.observed))
    else: result = component_preview(read_json(args.components)['components'])
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    try: main()
    except (ValueError, TypeError, KeyError, OSError, json.JSONDecodeError) as err:
        print(json.dumps({'status':'BLOCKED','reason':str(err)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(2)