#!/usr/bin/env python3
"""Build three bounded model jobs from a verified current source census.

Local preparation only. The native installer owns source-test publication,
allowlist changes, module pins, writer leases and catalog append. This builder
never contacts NOX, alters a queue, or accepts an original requirement.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

BASE = Path(__file__).resolve().parent
REPO = BASE.parents[1]
RUNTIME = REPO / 'nox-control/complete_executor_retries_20261118/runtime'
sys.path.insert(0, str(RUNTIME))
import owner_project_planner as planner


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def exact(source, before, after):
    if source.count(before) != 1:
        raise ValueError('REVIEWED_REPLACEMENT_PREIMAGE_CHANGED')
    return source.replace(before, after, 1)


def reviewed_fallback(path, raw):
    source = raw.decode()
    if path == 'owner_dispatcher_mentor.py':
        before = "    elif retry_budget_exhausted(task):\n        result['state'] = 'BLOCKED_RETRY_BUDGET_EXHAUSTED'\n    else:\n"
        after = "    elif retry_budget_exhausted(task):\n        result['state'] = 'BLOCKED_RETRY_BUDGET_EXHAUSTED'\n    elif handler in ('wait_q4', 'verify_q4') and category in ('timeout', 'service_unavailable'):\n        # The native runner already increments retries before this callback.\n        # These exact probes are read-only; no advisor or service mutation is needed.\n        task['status'] = 'pending'\n        task['next_try'] = time.time() + min(120, 30 * 2 ** max(0, int(task.get('retries') or 0) - 1))\n        result['state'] = 'READ_ONLY_TRANSIENT_RETRY_SCHEDULED'\n    else:\n"
        source = exact(source, before, after)
    elif path.endswith('/durable_runtime.py'):
        before = '    def __call__(self,session:Session,prompt:str,limit:int)->list[dict]:\n'
        after = before + "        if type(limit) is not int or not 1 <= limit <= 20:\n            raise ValueError('S03_CACHE_LIMIT')\n"
        source = exact(source, before, after)
    elif path == 'forge_split_guard.py':
        before = '    coverage = {name: {"rows": 0, "languages": set(), "tasks": set(), "sha256": ""} for name in SPLITS}\n'
        source = exact(source, before, before + '    language_tasks = {name: set() for name in SPLITS}\n')
        before = '                    coverage[split]["tasks"].add(row["task"])\n'
        source = exact(source, before, before + '                    language_tasks[split].add((row["language"], row["task"]))\n')
        before = '            coverage[split]["sha256"] = digest.hexdigest()\n'
        after = '            if language_tasks[split] != {(language, task) for language in LANGS for task in TASKS}:\n                raise ValueError("LANGUAGE_TASK_COVERAGE_REQUIRED_PER_SPLIT")\n' + before
        source = exact(source, before, after)
    else:
        raise ValueError('UNKNOWN_REVIEWED_TASK')
    compile(source, path, 'exec')
    return source.encode()


JOBS = (
    {'parent': '6V14-12', 'suffix': 'readonly_transient_retry', 'queue': 'Q4_INTEGRATION_ACCEPTANCE',
     'source': 'owner_dispatcher_mentor.py', 'test': 'test_nox_readonly_retry_backoff.py',
     'title': 'Resume bounded read-only probes after transient failures without requiring a senior model',
     'instruction': "In the existing on_failure callback, after OWNER STOP and retry_budget_exhausted checks, schedule deterministic retries only for existing wait_q4 and verify_q4 handlers whose existing error_category is timeout or service_unavailable. Set pending and next_try to current time plus min(120,30*2**max(0,retries-1)) seconds, preserving retries (the native caller already increments it), all claim/source/STOP boundaries and both existing error/resolution journal writes. Use READ_ONLY_TRANSIENT_RETRY_SCHEDULED, verified_fix=False and accepted=False. Do not call a senior model or subprocess for this narrow case. All other handlers and failure categories retain their existing gated behavior. Do not restart services, modify training, accept the parent task, or change tests.",
     'context': ['test_3b05_skill_ancestor_swap.py', 'test_nox_skill_evidence_strict_json.py'],
     'modules': ['test_nox_readonly_retry_backoff', 'test_3b05_skill_ancestor_swap', 'test_nox_skill_evidence_strict_json'],
     'min_tests': 18,
     'focus': [('def retry_budget_exhausted(task):', 'def verify_success(task, evidence=None):')]},
    {'parent': '3A03', 'suffix': 'cache_limit_contract', 'queue': 'Q2_MEMORY_KNOWLEDGE',
     'source': 'nox_runpod/teacher_mesh/v38/durable_runtime.py',
     'test': 'test_nox_warm_cache_limit_contract.py',
     'title': 'Prevent malformed S03 cache limits from aliasing valid queries or reaching native recall',
     'instruction': "Validate limit at the entry of WarmS03Cache.__call__ before registering any active-read ticket, touching cache accounting, calling the revision callback or native recall. Require type(limit) is int and 1 <= limit <= 20 (the existing SynapticBrain memory_hits contract); reject bool, floats, strings, None, nonpositive and oversized values with ValueError('S03_CACHE_LIMIT'). Apply the same validation when revision is absent. Preserve valid requests, exact cache keys, deep-copy behavior, the final revision callback outside the invalidation lock, revocation fences and all immutable tests. No other behavior or source files need to change.",
     'context': ['nox_runpod/teacher_mesh/v38/synaptic_brain.py', 'source_tests/__init__.py',
                 'source_tests/test_cache_race.py', 'test_nox_existing_cache_race.py',
                 'test_nox_warm_cache_final_revision.py'],
     'modules': ['test_nox_warm_cache_limit_contract', 'test_nox_existing_cache_race',
                 'test_nox_warm_cache_final_revision'], 'min_tests': 16,
     'focus': [('    def __call__(self,session:Session,prompt:str,limit:int)',
                '    def _assert_read_active(')]},
    {'parent': '4A02', 'suffix': 'bilingual_task_matrix', 'queue': 'Q3_TRAINING_WEIGHTS',
     'source': 'forge_split_guard.py', 'test': 'test_nox_forge_language_task_coverage.py',
     'title': 'Require independent Russian and Spanish coverage for every training and evaluation task',
     'instruction': "Extend existing validate() source-only split checking to require all (language,task) pairs from LANGS x TASKS independently in each train, dev and holdout split. The current marginal language and task sets can miss Spanish code or Russian speech while still passing. Track pairs during the existing single pass; after the existing language and task coverage checks, reject an incomplete matrix with ValueError('LANGUAGE_TASK_COVERAGE_REQUIRED_PER_SPLIT'). Preserve all pin, URL, leakage, path and finite-JSON validation, the existing output schema and training_started=False. No corpus mutation, downloads, training launch, or test modification. Keep the additional storage bounded by the fixed language/task sets.",
     'context': ['test_forge_split_guard.py', 'test_nox_forge_split_coverage.py'],
     'modules': ['test_forge_split_guard', 'test_nox_forge_split_coverage',
                 'test_nox_forge_language_task_coverage'], 'min_tests': 39,
     'focus': [('    seen_ids, seen_origin, seen_source, seen_prompt, seen_url =',
                '    def check_cross('),
               ('                    coverage[split]["rows"] += 1',
                '    if set.union(')]},
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inspect-log', type=Path, required=True)
    parser.add_argument('--work-directory', type=Path, required=True)
    args = parser.parse_args()
    marker = 'NOX_MAINT_SCOPE_PROJECT_SOURCE_WORKSPACE_CENSUS='
    census = next(json.loads(line.split(marker, 1)[1])
        for line in args.inspect_log.read_text().splitlines() if marker in line)
    if (census.get('two_reads_match') is not True or census.get('read_errors')
            or census.get('unattributed_changed_paths')):
        raise ValueError('CURRENT_SOURCE_CENSUS_NOT_VERIFIED')
    pins = {name: row['sha256'] for name, row in census['files'].items()}
    wanted = set(pins.values())
    payloads = {}
    for folder in ('complete_executor_20261118', 'complete_executor_retries_20261118',
                   'complete_executor_followup_20261118'):
        for file in (BASE.parent / folder).rglob('*'):
            if file.is_file() and file.stat().st_size <= 2 * 1024 * 1024:
                raw = file.read_bytes()
                pin = sha(raw)
                if pin in wanted:
                    payloads[pin] = raw
    if not wanted <= payloads.keys():
        raise ValueError('CURRENT_SOURCE_BYTES_NOT_RECONSTRUCTABLE')
    current = args.work_directory / 'current'
    fixed = args.work_directory / 'reviewed_fallback'
    for destination in (current, fixed):
        destination.mkdir(parents=True, exist_ok=True)
        for path, pin in pins.items():
            target = destination / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payloads[pin])
        for test in (BASE / 'trusted_tests').glob('test_*.py'):
            shutil.copyfile(test, destination / test.name)
    for job in JOBS:
        source = job['source']
        (fixed / source).write_bytes(reviewed_fallback(source, (current / source).read_bytes()))
    records, catalog, assets = [], [], {}
    for job in JOBS:
        contexts = sorted({job['source'], job['test'], *job['context']})
        snapshot = {name: (current / name).read_bytes() for name in contexts}
        task_id = job['parent'] + '.project.' + job['suffix'] + '.20261118'
        contract = {'schema': planner.SCHEMA, 'task_id': task_id,
            'parent_task_id': job['parent'], 'queue_id': job['queue'], 'root_id': 'NOX_PROJECT_SOURCE',
            'instruction': job['instruction'],
            'context': [{'path': name, 'sha256': sha(raw)} for name, raw in snapshot.items()],
            'editable_paths': [job['source']], 'allowed_new_paths': [],
            'verification': {'kind': 'python_unittest', 'modules': job['modules'],
                             'min_tests': job['min_tests'], 'timeout_sec': 120},
            'acceptance_scope': 'SOURCE_PATCH_TESTED', 'original_task_accepted': False,
            'focus_regions': [{'path': job['source'], 'start_anchor': start,
                               'end_anchor': end} for start, end in job['focus']]}
        planner.validate_contract(contract, snapshot)
        raw = encoded(contract)
        contract_pin = sha(raw)
        relative = 'package/contracts/' + contract_pin + '.json'
        target = BASE / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        assets[relative] = contract_pin
        fallback = planner.candidate_plan(contract, snapshot,
            {**snapshot, job['source']: (fixed / job['source']).read_bytes()})[0]
        fallback['task_id'] = task_id + '.reviewed_rescue'
        fallback['review_origin'] = 'OWNER_REVIEWED'
        fallback.pop('contract_sha256', None)
        raw = encoded(fallback)
        relative_fallback = 'reserve/plans/' + sha(raw) + '.json'
        target = BASE / relative_fallback
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        for changed in fallback['files']:
            target = BASE / 'reserve/blobs' / changed['payload_sha256']
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((fixed / changed['path']).read_bytes())
        reports = {}
        for name, workspace in (('baseline', current), ('reviewed_solution', fixed)):
            result = subprocess.run([sys.executable, '-B', '-m', 'unittest', *job['modules']],
                cwd=workspace, capture_output=True, text=True, timeout=150)
            reports[name] = {'exit_code': result.returncode,
                'output_sha256': sha((result.stdout + result.stderr).encode()),
                'output': (result.stdout + result.stderr)[-14000:]}
        if reports['baseline']['exit_code'] == 0 or reports['reviewed_solution']['exit_code'] != 0:
            raise ValueError('BASELINE_FAIL_REVIEWED_SOLUTION_PASS_REQUIRED: ' + job['parent'] + '\n' +
                             reports['reviewed_solution']['output'])
        records.append({'task_id': task_id, 'parent_task_id': job['parent'],
            'source_path': job['source'], 'contract_path': relative, 'contract_sha256': contract_pin,
            'trusted_test_path': job['test'], 'trusted_test_sha256': sha(snapshot[job['test']]),
            'source_context': contract['context'], 'verification': contract['verification'],
            'reviewed_reserve_plan_path': relative_fallback,
            'reviewed_reserve_plan_sha256': sha(raw),
            'reviewed_reserve_source_sha256': sha((fixed / job['source']).read_bytes()),
            'tests': reports, 'original_task_accepted': False, 'live_deployment_verified': False})
        catalog.append({'id': task_id, 'handler': 'owner_native_project_work',
            'queue_id': job['queue'], 'deps': [], 'resource': 'CPU_LIGHT',
            'priority': 'P1', 'estimated_cost': 2, 'title': job['title'],
            'params': {'parent_task_id': job['parent'], 'contract_sha256': contract_pin}})
    manifest = {'schema': 'NOX_REVIEWED_CONTINUATION_BATCH_V1',
        'base_source_census_sha256': census['files_sha256'],
        'observed_native_config_sha256': census['config_sha256'],
        'source_context_pins': pins,
        'source_additions': {job['test']: {'repository_path': 'trusted_tests/' + job['test'],
                             'sha256': sha((BASE / 'trusted_tests' / job['test']).read_bytes())}
                             for job in JOBS},
        'package_assets': assets, 'catalog_append_without_callback_pin': catalog,
        'jobs': records, 'native_dispatch_cap': 3, 'original_acceptance_added': 0,
        'source_only': True, 'reserve_not_auto_admitted': True}
    (BASE / 'reviewed_batch.json').write_bytes(encoded(manifest) + b'\n')
    print(json.dumps({'jobs': len(records), 'source_tests': list(manifest['source_additions']),
                      'baseline_failed': True, 'reviewed_solutions_passed': True,
                      'catalog_requires_installed_callback_pin': True}))


if __name__ == '__main__':
    main()
