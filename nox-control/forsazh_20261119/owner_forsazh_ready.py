"""Evaluate six independent reviewed plans against one immutable native snapshot."""

import hashlib
import json
import re


WIDTH = 6
HANDLER = 'owner_native_project_work'
SHA = re.compile(r'[0-9a-f]{64}')
TASK_ID = re.compile(r'[A-Za-z0-9_.-]{1,128}')
SOURCE_PATH = re.compile(r'[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*')
TERMINAL = {'done', 'completed'}
PRIORITIES = {'P0': 0, 'P1': 1, 'P2': 2, 'P3': 3}


def digest(data):
    raw = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def require(condition, reason):
    if not condition:
        raise ValueError('HOLD_FORSAZH_READY_' + reason)


def _identifier(value):
    return type(value) is str and TASK_ID.fullmatch(value) is not None


def _sha(value):
    return type(value) is str and SHA.fullmatch(value) is not None


def _paths(rows):
    require(isinstance(rows, list) and rows, 'SOURCE_ROWS')
    result = set()
    for row in rows:
        path = row.get('path') if isinstance(row, dict) else None
        require(type(path) is str and SOURCE_PATH.fullmatch(path)
                and not {'.', '..'}.intersection(path.split('/')) and path not in result, 'SOURCE_PATH')
        result.add(path)
    return result


def _verified_plan(row, plan, source_census, registry):
    task_id = row['id']
    params = row['params']
    parent = params['parent_task_id']
    source = plan.get('root_id')
    registry_row = registry.get(parent)
    require(isinstance(registry_row, dict) and _sha(registry_row.get('spec_sha256'))
            and plan.get('spec_sha256') == registry_row['spec_sha256']
            and registry_row.get('queue_id') == row.get('queue_id'), 'ORIGINAL_BINDING')
    require(plan.get('schema') == 'NOX_PROJECT_WORK_PLAN_V1'
            and plan.get('task_id') == task_id and plan.get('parent_task_id') == parent
            and plan.get('queue_id') == row.get('queue_id')
            and plan.get('review_origin') == 'OWNER_REVIEWED'
            and plan.get('original_task_accepted') is False, 'PLAN_SCOPE')
    context, edits = plan.get('context'), plan.get('files')
    reads, writes = _paths(context), _paths(edits)
    actual = source_census.get(source) if _identifier(source) else None
    require(isinstance(actual, dict), 'SOURCE_ROOT')
    require(all(_sha(entry.get('sha256')) and actual.get(entry['path']) == entry['sha256'] for entry in context)
            and all(_sha(entry.get('before_sha256')) and _sha(entry.get('after_sha256'))
                    and entry['after_sha256'] != entry['before_sha256']
                    and actual.get(entry['path']) == entry['before_sha256'] for entry in edits), 'SOURCE_PREIMAGE')
    verification = plan.get('verification')
    modules = verification.get('modules') if isinstance(verification, dict) else None
    require(isinstance(modules, list) and modules and all(_identifier(item) for item in modules),
            'IMMUTABLE_VERIFIER')
    verifiers = {item.replace('.', '/') + '.py' for item in modules}
    require(len(verifiers) == len(modules) and verifiers <= reads and not verifiers & writes, 'IMMUTABLE_VERIFIER')
    return ({(source, item) for item in reads | writes}, {(source, item) for item in writes})


def assess(catalog, state, registry, source_census, plans, *, catalog_sha256, dispatcher_sha256):
    """Use authenticated readbacks and materialized plans already verified by the caller."""
    require(isinstance(catalog, dict) and catalog.get('schema') == 'NOX_AUTONOMY_PROCESS_POOL_V1'
            and _sha(catalog_sha256) and digest(catalog) == catalog_sha256
            and isinstance(catalog.get('tasks'), list) and len(catalog['tasks']) <= 4096
            and _sha(dispatcher_sha256), 'CATALOG_PIN')
    require(isinstance(state, dict) and isinstance(state.get('tasks'), dict)
            and len(state['tasks']) <= 20000, 'QUEUE_STATE')
    records = state['tasks']
    require(all(isinstance(value, dict) for value in records.values())
            and isinstance(plans, dict) and isinstance(registry, dict)
            and isinstance(source_census, dict), 'STATE_SHAPE')
    tasks = catalog['tasks']
    ids = [row.get('id') if isinstance(row, dict) else None for row in tasks]
    require(all(_identifier(task_id) for task_id in ids) and len(ids) == len(set(ids)), 'CATALOG_DUPLICATE')
    prior_plans = {row['params']['plan_sha256'] for row in records.values()
                   if isinstance(row.get('params'), dict) and _sha(row['params'].get('plan_sha256'))}
    ordered = [row for row in tasks if row.get('handler') == HANDLER
               and type(row.get('priority')) is str and row['priority'] in PRIORITIES]
    ordered.sort(key=lambda row: (PRIORITIES[row['priority']], row['id']))
    ready, hold = [], {}
    parents, reads, writes = set(), set(), set()
    for row in ordered:
        task_id = row['id']
        params = row.get('params')
        deps = row.get('deps')
        try:
            require(task_id not in records and row.get('source_sha256') == dispatcher_sha256, 'ALREADY_ADMITTED_OR_HISTORICAL')
            require(row.get('resource') == 'CPU_LIGHT' and 'resource_demand' not in row
                    and row.get('promotion_candidate_sha256') is None, 'CPU_SCOPE')
            require(isinstance(deps, list) and all(_identifier(dep)
                    and records.get(dep, {}).get('status') in TERMINAL for dep in deps), 'DEPENDENCY')
            require(isinstance(params, dict) and set(params) == {'parent_task_id', 'plan_sha256'}
                    and _identifier(params['parent_task_id']) and _sha(params['plan_sha256']), 'MATERIALIZED_PLAN')
            pin, parent = params['plan_sha256'], params['parent_task_id']
            plan = plans.get(pin)
            require(pin not in prior_plans and isinstance(plan, dict) and digest(plan) == pin, 'PLAN_PIN_OR_REPLAY')
            candidate_reads, candidate_writes = _verified_plan(row, plan, source_census, registry)
            require(parent not in parents and not (writes & candidate_reads or reads & candidate_writes),
                    'CONFLICTING_PARENT_OR_SOURCE')
        except ValueError as failure:
            hold[task_id] = str(failure)
            continue
        ready.append({'task_id': task_id, 'parent_task_id': parent, 'plan_sha256': pin})
        parents.add(parent)
        reads.update(candidate_reads)
        writes.update(candidate_writes)
        if len(ready) == WIDTH:
            break
    return {'state': 'SIX_REVIEWED_CANDIDATES_BOUND' if len(ready) == WIDTH else 'HOLD_FEWER_THAN_SIX_REVIEWED_CANDIDATES',
            'catalog_sha256': catalog_sha256, 'dispatcher_sha256': dispatcher_sha256,
            'ready': ready, 'hold': hold, 'native_jobs_started': 0}
