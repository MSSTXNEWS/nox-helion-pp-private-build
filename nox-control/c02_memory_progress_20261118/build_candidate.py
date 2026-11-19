#!/usr/bin/env python3
"""Prepare a source-only C02 capacity task; never publish or enqueue it."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

BASE = Path(__file__).resolve().parent
REPO = BASE.parents[1]
sys.path.insert(0, str(REPO / 'nox-control/complete_executor_retries_20261118/runtime'))
import owner_project_planner as planner

SOURCE = 'nox_runpod/teacher_mesh/v38/synaptic_brain.py'
SOURCE_SHA = '8657ad367e6dd25b48ca8d6d7c4a947c0e1b0d4b979d63fbdaaf2a8e9ba5e74c'
TEST = 'test_nox_c02_optional_starvation.py'
LEGACY_TEST = 'test_nox_c02_existing_cognition.py'
TASK = '3A01.project.c02_memory_capacity.20261118'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(doc):
    return json.dumps(doc, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def reviewed_solution(raw):
    source = raw.decode()
    before = '        self.inflight = threading.BoundedSemaphore(config.max_inflight)\n'
    after = before + ('        # Optional callbacks can outlive a pulse; retain capacity for the next C02.\n'
                      '        self.optional_inflight = threading.BoundedSemaphore(config.max_workers - 1)\n')
    if source.count(before) != 1:
        raise ValueError('SOURCE_INIT_PREIMAGE')
    source = source.replace(before, after, 1)
    before = '''        # C02 is a hard dependency: reserve the first worker/queue slot for
        # indexed S03 recall instead of letting optional sensors starve memory.
        for name in ('C02', *(k for k in CORE_NAMES if k != 'C02')):
            if not self.inflight.acquire(blocking=False):
                submitted[name] = None
                continue
            try:
                task = self.pool.submit(self._core, name, session, prompt, utc)
                task.add_done_callback(lambda _task: self.inflight.release())
                submitted[name] = task
            except RuntimeError:
                self.inflight.release()
                submitted[name] = None
'''
    after = '''        # Reserve one existing worker and queue credit across requests for C02.
        # A timed-out optional callback may still be running in this same pool.
        for name in ('C02', *(k for k in CORE_NAMES if k != 'C02')):
            optional = name != 'C02'
            if optional and not self.optional_inflight.acquire(blocking=False):
                submitted[name] = None
                continue
            if not self.inflight.acquire(blocking=False):
                if optional:
                    self.optional_inflight.release()
                submitted[name] = None
                continue
            try:
                task = self.pool.submit(self._core, name, session, prompt, utc)
                def release_credit(_task, optional=optional):
                    self.inflight.release()
                    if optional:
                        self.optional_inflight.release()
                task.add_done_callback(release_credit)
                submitted[name] = task
            except RuntimeError:
                self.inflight.release()
                if optional:
                    self.optional_inflight.release()
                submitted[name] = None
'''
    if source.count(before) != 1:
        raise ValueError('SOURCE_SUBMISSION_PREIMAGE')
    source = source.replace(before, after, 1)
    compile(source, SOURCE, 'exec')
    return source.encode()


def verify_legacy_tests():
    provenance = json.loads((BASE / 'legacy_provenance.json').read_bytes())
    copied = ast.parse((BASE / 'trusted_tests' / LEGACY_TEST).read_bytes())
    classes = {node.name: node for node in copied.body if isinstance(node, ast.ClassDef)}
    originals = {}
    for entry in provenance['sources']:
        raw = (REPO / entry['repository_path']).read_bytes()
        if sha(raw) != entry['sha256']:
            raise ValueError('LEGACY_TEST_SOURCE_PIN')
        source = ast.parse(raw)
        originals[entry['repository_path']] = source
        original = next(node for node in source.body
                        if isinstance(node, ast.ClassDef) and node.name == entry['original_class'])
        methods = {node.name: node for node in original.body if isinstance(node, ast.FunctionDef)}
        selected = {node.name: node for node in classes[entry['copied_class']].body
                    if isinstance(node, ast.FunctionDef)}
        if set(selected) != set(entry['methods']):
            raise ValueError('LEGACY_TEST_METHOD_SET')
        for name, node in selected.items():
            if ast.dump(node, include_attributes=False) != ast.dump(methods[name], include_attributes=False):
                raise ValueError('LEGACY_TEST_METHOD_CHANGED:' + name)
    helper_source = originals[provenance['module_helpers_from']['repository_path']]
    def helpers(tree):
        return {name: node for node in tree.body
                for name in ([node.name] if isinstance(node, ast.FunctionDef) else
                             [target.id for target in node.targets if isinstance(target, ast.Name)]
                             if isinstance(node, ast.Assign) else [])}
    before, after = helpers(helper_source), helpers(copied)
    for name in provenance['module_helpers_from']['names']:
        if ast.dump(before[name], include_attributes=False) != ast.dump(after[name], include_attributes=False):
            raise ValueError('LEGACY_TEST_HELPER_CHANGED:' + name)
    return provenance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inspect-json', type=Path, required=True)
    parser.add_argument('--source-file', type=Path, required=True)
    parser.add_argument('--work-directory', type=Path, required=True)
    args = parser.parse_args()
    observation = json.loads(args.inspect_json.read_bytes())
    census = observation['NOX_MAINT_SCOPE_PROJECT_SOURCE_WORKSPACE_CENSUS'][-1]
    raw = args.source_file.read_bytes()
    if (census.get('two_reads_match') is not True or census.get('read_errors')
            or census['files'][SOURCE]['sha256'] != SOURCE_SHA or sha(raw) != SOURCE_SHA):
        raise ValueError('CURRENT_SOURCE_PIN_NOT_VERIFIED')
    provenance = verify_legacy_tests()
    trusted_tests = {name: (BASE / 'trusted_tests' / name).read_bytes()
                     for name in (TEST, LEGACY_TEST)}
    snapshot = {SOURCE: raw, **trusted_tests}
    contract = {'schema': planner.SCHEMA, 'task_id': TASK, 'parent_task_id': '3A01',
        'queue_id': 'Q2_MEMORY_KNOWLEDGE', 'root_id': 'NOX_PROJECT_SOURCE',
        'instruction': 'Fix cross-request C02 starvation in the existing SynapticBrain pool. '
            'Timed-out optional core callbacks may still be running when the next pulse starts; '
            'submitting C02 first inside a pulse does not reserve capacity across pulses. '
            'Keep exactly the existing ThreadPoolExecutor and unchanged max_workers/max_inflight limits. '
            'Bound the total outstanding optional (non-C02) jobs across requests to max_workers - 1, '
            'using nonblocking admission, so at least one existing worker and inflight credit remain '
            'available for indexed S03 memory. Every completion/cancellation/submission-error path '
            'must release exactly its acquired credits; bind each callback to its own optional flag. '
            'With max_workers=1, optional groups get the existing explicit HOLD_QUEUE_SATURATED state '
            'and the single worker remains available for C02. Preserve C02-first scheduling, memory '
            'deadlines, required-memory holds, all eight output group entries, STOP/authorization, '
            'persona/scope filtering and the existing close behavior. Do not create another pool, '
            'process, service or model, increase budgets, remove S03 dependence, accept the parent, '
            'or modify tests.',
        'context': [{'path': path, 'sha256': sha(data)} for path, data in snapshot.items()],
        'editable_paths': [SOURCE], 'allowed_new_paths': [],
        'verification': {'kind': 'python_unittest',
                         'modules': [name.removesuffix('.py') for name in trusted_tests],
                         'min_tests': 22, 'timeout_sec': 120},
        'acceptance_scope': 'SOURCE_PATCH_TESTED', 'original_task_accepted': False,
        'focus_regions': [
            {'path': SOURCE, 'start_anchor': '        self.pool = ThreadPoolExecutor(',
             'end_anchor': '    def close(self) -> None:'},
            {'path': SOURCE, 'start_anchor': '        submitted = {}',
             'end_anchor': '        futures = [f for f in submitted.values() if f is not None]'},
        ]}
    planner.validate_contract(contract, snapshot)
    fixed = reviewed_solution(raw)
    tests = {}
    for label, data in (('baseline', raw), ('reviewed_solution', fixed)):
        root = args.work_directory / label
        target = root / SOURCE
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        for name in trusted_tests:
            shutil.copyfile(BASE / 'trusted_tests' / name, root / name)
        result = subprocess.run([sys.executable, '-B', '-m', 'unittest',
                                 *contract['verification']['modules'], '-v'],
                                cwd=root, capture_output=True, text=True, timeout=15)
        output = (result.stdout + result.stderr).encode()
        tests[label] = {'exit_code': result.returncode, 'output_sha256': sha(output),
                        'output': output.decode()}
    if tests['baseline']['exit_code'] == 0 or tests['reviewed_solution']['exit_code'] != 0:
        raise ValueError('BASELINE_FAIL_REVIEWED_SOLUTION_PASS_REQUIRED')
    contract_raw = encoded(contract)
    contract_pin = sha(contract_raw)
    contract_path = BASE / 'package/contracts' / (contract_pin + '.json')
    contract_path.parent.mkdir(parents=True, exist_ok=True)
    contract_path.write_bytes(contract_raw)
    plan = planner.candidate_plan(contract, snapshot, {**snapshot, SOURCE: fixed})[0]
    plan['task_id'] = TASK + '.reviewed_reserve'
    plan['review_origin'] = 'OWNER_REVIEWED'
    plan.pop('contract_sha256', None)
    plan_raw = encoded(plan)
    plan_path = BASE / 'reserve/plans' / (sha(plan_raw) + '.json')
    blob_path = BASE / 'reserve/blobs' / sha(fixed)
    for path, data in ((plan_path, plan_raw), (blob_path, fixed)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    catalog_row = {'id': TASK, 'handler': 'owner_native_project_work',
        'queue_id': 'Q2_MEMORY_KNOWLEDGE', 'deps': [], 'resource': 'CPU_LIGHT',
        'priority': 'P1', 'estimated_cost': 2,
        'title': 'Keep an existing CPU worker available for S03 across successive chat requests',
        'params': {'parent_task_id': '3A01', 'contract_sha256': contract_pin}}
    source_test_paths = {'c02_' + name: name for name in trusted_tests}
    contract_asset = 'c02_contract_' + contract_pin[:20] + '.json'
    manifest = {'schema': 'NOX_REVIEWED_C02_CAPACITY_CANDIDATE_V1',
        'source_test_paths': source_test_paths,
        'package_paths': {contract_asset: 'state/dispatcher/project_executor/package/contracts/' + contract_pin + '.json'},
        'asset_sources': {**{asset: str((BASE / 'trusted_tests' / name).relative_to(REPO))
                            for asset, name in source_test_paths.items()},
                          contract_asset: str(contract_path.relative_to(REPO))},
        'asset_sha256': {**{asset: sha(trusted_tests[name]) for asset, name in source_test_paths.items()},
                         contract_asset: contract_pin},
        'catalog_append_without_callback_pin': [catalog_row],
        'source_context_pins': {SOURCE: SOURCE_SHA},
        'observed_full_source_census_sha256': census['files_sha256'],
        'current_full_source_census_required_before_install': True,
        'current_callback_pin_required_before_install': True,
        'original_parent_registry': 'nox-control/complete_executor_20261118/evidence/all295_execution_disposition.json',
        'original_parent_spec_sha256': '1965af50c0377dd9e81f0e944fe046322ba704218fa045b40542ecd8ec822e3d',
        'verification': contract['verification'], 'tests': tests,
        'legacy_test_provenance': provenance,
        'optional_capacity_tradeoff': 'At max_workers=1, optional cores retain explicit HOLD_QUEUE_SATURATED; the sole worker is reserved for S03. At larger budgets, outstanding optional work is bounded to max_workers-1 in the same existing executor.',
        'reviewed_reserve_plan': str(plan_path.relative_to(REPO)),
        'reviewed_reserve_postimage_sha256': sha(fixed),
        'reserve_auto_admitted': False, 'catalog_admitted': False,
        'source_only': True, 'live_service_deployed': False,
        'original_task_accepted': False, 'original_acceptance_added': 0}
    (BASE / 'candidate.json').write_bytes(encoded(manifest) + b'\n')
    print(json.dumps({'task_id': TASK, 'contract_sha256': contract_pin,
        'baseline_exit': tests['baseline']['exit_code'],
        'reviewed_solution_exit': tests['reviewed_solution']['exit_code'],
        'source_only': True, 'admitted': False}))


if __name__ == '__main__':
    main()
