"""Pure reviewed-mission producer for the existing NOX task/claim queue.

This module performs no I/O, model call, native action or original-task acceptance.
The caller pins the manifest bytes, reads source through the existing executor,
persists returned contracts by SHA, then uses the existing admission transaction.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
from pathlib import PurePosixPath
import re

SCHEMA = 'NOX_SYSTEMIC_RELAY_MANIFEST_V1'
CONTRACT_SCHEMA = 'NOX_PROJECT_PLANNER_CONTRACT_V1'
SHA = re.compile(r'[0-9a-f]{64}\Z')
ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z')
MISSION = re.compile(r'[a-z][a-z0-9_]{0,39}\Z')
QUEUES = {'Q1_RUNTIME_CHAT','Q2_MEMORY_KNOWLEDGE','Q3_TRAINING_WEIGHTS','Q4_INTEGRATION_ACCEPTANCE'}
ACTIVE = {'pending','running','wait','retry','admitted','prepared'}
TERMINAL = {'done','verified','blocked','failed','cancelled'}
PUBLIC_REASONS = {'MODEL_SLOT_BUSY','PLANNER_REPEATED_ACTION_NO_PROGRESS',
    'PLANNER_NO_CHANGES','PLANNER_BUDGET_EXHAUSTED','HOLD_PROJECT_SOURCE_DRIFT',
    'HOLD_RESOURCE_PRESSURE','HOLD_OWNER_STOP','INTEGRATED','PREPARED',
    'FAILED_TESTS','BLOCKED_PLANNER','BLOCKED_SANDBOX'}


class RefillHold(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise RefillHold('HOLD_SYSTEMIC_RELAY_' + code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf-8')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def path(value):
    require(type(value) is str and 0 < len(value) <= 240, 'PATH')
    parsed = PurePosixPath(value)
    require(not parsed.is_absolute() and parsed.as_posix() == value
            and all(part not in ('', '.', '..') for part in parsed.parts)
            and '\\' not in value and '\x00' not in value, 'PATH')
    return value


def validate_manifest(manifest):
    require(isinstance(manifest, dict) and manifest.get('schema') == SCHEMA, 'SCHEMA')
    require(len(canonical(manifest)) <= 1024 * 1024, 'MANIFEST_SIZE')
    require(type(manifest.get('revision')) is int and 1 <= manifest['revision'] <= 10**9,
            'REVISION')
    require(manifest.get('review_origin') == 'OWNER_REVIEWED'
            and manifest.get('acceptance_scope') == 'SOURCE_PATCH_TESTED'
            and manifest.get('original_task_accepted') is False, 'AUTHORITY_SCOPE')
    previous = manifest.get('previous_manifest_sha256')
    require(previous is None or type(previous) is str and SHA.fullmatch(previous), 'PREDECESSOR')
    registry = manifest.get('registry')
    require(isinstance(registry, dict) and registry.get('total_original_ids') == 295,
            'ORIGINAL_DENOMINATOR')
    pins = registry.get('source_registry_sha256')
    require(isinstance(pins, dict) and set(pins) == {'tasks','ideas','receipts','routing'}
            and all(type(value) is str and SHA.fullmatch(value) for value in pins.values()),
            'REGISTRY_PINS')
    parents = registry.get('parents')
    require(isinstance(parents, dict) and 1 <= len(parents) <= 295, 'PARENTS')
    for task_id, parent in parents.items():
        require(type(task_id) is str and ID.fullmatch(task_id) and isinstance(parent, dict)
                and type(parent.get('spec_sha256')) is str and SHA.fullmatch(parent['spec_sha256'])
                and parent.get('queue_id') in QUEUES
                and parent.get('required_evidence') in ('source','native'), 'PARENT')
    missions = manifest.get('missions')
    require(isinstance(missions, list) and len(missions) <= 128, 'MISSIONS')
    seen = set()
    for mission in missions:
        require(isinstance(mission, dict), 'MISSION')
        name, revision = mission.get('mission_id'), mission.get('revision')
        require(type(name) is str and MISSION.fullmatch(name)
                and type(revision) is int and 1 <= revision <= 10**9
                and (name,revision) not in seen, 'MISSION_ID')
        seen.add((name,revision))
        parent = parents.get(mission.get('parent_task_id'))
        require(parent is not None and mission.get('queue_id') == parent['queue_id'], 'PARENT_BINDING')
        require(mission.get('priority') in ('P0','P1','P2','P3')
                and mission.get('repeat_policy') == 'ONCE_PER_REVIEWED_REVISION', 'MISSION_POLICY')
        require(type(mission.get('root_id')) is str and ID.fullmatch(mission['root_id']), 'ROOT')
        require(type(mission.get('title')) is str and 0 < len(mission['title']) <= 180,
                'TITLE')
        require(len(mission['parent_task_id'] + '.relay.' + name + '.' + '0'*16) <= 128,
                'GENERATED_TASK_ID')
        for key, bound in (('instruction',8192),):
            require(type(mission.get(key)) is str and 0 < len(mission[key].encode()) <= bound, key.upper())
        context = mission.get('context')
        require(isinstance(context,list) and 1 <= len(context) <= 128, 'CONTEXT')
        context_pins = {}
        for row in context:
            require(isinstance(row,dict) and set(row) == {'path','sha256'}, 'CONTEXT_ROW')
            target = path(row['path'])
            require(target not in context_pins and type(row['sha256']) is str
                    and SHA.fullmatch(row['sha256']), 'CONTEXT_PIN')
            context_pins[target] = row['sha256']
        editable = mission.get('editable_paths')
        require(isinstance(editable,list) and 1 <= len(editable) <= 8
                and len(set(editable)) == len(editable)
                and set(editable) <= set(context_pins), 'EDITABLE_SCOPE')
        for target in editable:
            path(target)
            require(not PurePosixPath(target).name.startswith('test_')
                    and not any(part in ('tests','source_tests','trusted_tests')
                                for part in PurePosixPath(target).parts), 'IMMUTABLE_TESTS')
        require(mission.get('allowed_new_paths',[]) == [], 'EXISTING_SOURCE_ONLY')
        verification = mission.get('verification')
        require(isinstance(verification,dict) and verification.get('kind') == 'python_unittest',
                'EXISTING_VERIFICATION')
        modules = verification.get('modules')
        require(isinstance(modules,list) and 1 <= len(modules) <= 16
                and len(set(modules)) == len(modules), 'TEST_MODULES')
        for module in modules:
            require(type(module) is str and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.]*',module),
                    'TEST_MODULE')
            target = module.replace('.','/') + '.py'
            require(target in context_pins and target not in editable, 'TEST_PIN')
        require(type(verification.get('min_tests')) is int and 1 <= verification['min_tests'] <= 10000
                and type(verification.get('timeout_sec')) is int
                and 1 <= verification['timeout_sec'] <= 120, 'VERIFICATION_BUDGET')
        dependencies = mission.get('dependencies',[])
        require(isinstance(dependencies,list) and len(dependencies) <= 16
                and all(type(item) is str and ID.fullmatch(item) for item in dependencies), 'DEPENDENCIES')
        focus = mission.get('focus_regions',[])
        require(isinstance(focus,list) and len(focus) <= 6, 'FOCUS')
        for region in focus:
            require(isinstance(region,dict) and set(region) == {'path','start_anchor','end_anchor'}
                    and region.get('path') in editable
                    and all(type(region.get(key)) is str and 0 < len(region[key]) <= 200
                            for key in ('start_anchor','end_anchor')), 'FOCUS_REGION')
        experience = mission.get('experience',[])
        require(isinstance(experience,list) and len(experience) <= 6
                and len(canonical(experience)) <= 2400, 'EXPERIENCE_BUDGET')
        for lesson in experience:
            require(isinstance(lesson,dict) and set(lesson) == {'id','lesson','evidence_sha256'}
                    and type(lesson['id']) is str and ID.fullmatch(lesson['id'])
                    and type(lesson['lesson']) is str and 0 < len(lesson['lesson']) <= 360
                    and type(lesson['evidence_sha256']) is str and SHA.fullmatch(lesson['evidence_sha256']),
                    'EXPERIENCE')
        budget = mission.get('budget')
        require(isinstance(budget,dict) and budget.get('lane') == 'model'
                and budget.get('max_model_turns') == 24
                and type(budget.get('cpu_seconds')) is int and 1 <= budget['cpu_seconds'] <= 120
                and budget.get('max_searches') == 0
                and type(budget.get('max_output_bytes')) is int
                and 1 <= budget['max_output_bytes'] <= 96*1024, 'BUDGET')
        defect = mission.get('defect')
        require(isinstance(defect,dict) and type(defect.get('observed_source_sha256')) is str
                and defect['observed_source_sha256'] in context_pins.values()
                and all(type(defect.get(key)) is str and 0 < len(defect[key]) <= 1800
                        for key in ('finding','expected_delta','verification_limit')), 'GROUNDED_DEFECT')
    topics = manifest.get('research_topics',[])
    require(isinstance(topics,list) and len(topics) <= 32, 'RESEARCH_TOPICS')
    for topic in topics:
        require(isinstance(topic,dict) and topic.get('parent_task_id') in parents
                and type(topic.get('objective')) is str and 0 < len(topic['objective']) <= 1800,
                'RESEARCH_TOPIC')
    return manifest


def source_requests(manifest):
    validate_manifest(manifest)
    roots = {}
    for mission in manifest['missions']:
        roots.setdefault(mission['root_id'],set()).update(row['path'] for row in mission['context'])
    return {root:sorted(paths) for root,paths in roots.items()}


def _binding(task):
    relay = task.get('systemic_relay',{}) if isinstance(task,dict) else {}
    return relay.get('binding',relay) if isinstance(relay,dict) else {}


def _outcomes(tasks):
    output = []
    for task_id,task in sorted(tasks.items()):
        if not isinstance(task,dict) or not isinstance(task_id,str) or not ID.fullmatch(task_id):
            continue
        binding = _binding(task)
        if not isinstance(binding,dict) or not binding.get('mission_id'):
            continue
        row = {'task_id':task_id,'mission_id':binding['mission_id'],
               'mission_revision':binding.get('mission_revision'),
               'input_sha256':binding.get('input_sha256'),
               'status':task.get('status') if task.get('status') in ACTIVE|TERMINAL else 'unknown',
               'evidence_scope':'QUEUE_STATE_REQUIRES_RECEIPT_AND_POSTIMAGE_READBACK',
               'original_task_accepted':False}
        # Preserve only recognized scalar evidence. A result body can contain private text.
        sources = [task,task.get('result',{}),task.get('owner_result',{}),
                   task.get('native_project_terminal',{})]
        for terminal in list(sources[1:]):
            if not isinstance(terminal,dict):
                continue
            receipt = terminal.get('receipt')
            if not isinstance(receipt,dict):
                continue
            worker = receipt.get('worker_result',{})
            if not isinstance(worker,dict):
                continue
            project,planner = worker.get('project_evidence',{}),worker.get('planner_receipt',{})
            sources.extend((project,planner))
            if isinstance(project,dict):
                tests = project.get('tests',{})
                if isinstance(tests,dict) and type(tests.get('tests_run')) is int \
                        and 0 <= tests['tests_run'] <= 100000:
                    row['reported_test_count'] = tests['tests_run']
                    row['reported_tests_passed'] = tests.get('passed') is True
                posts = project.get('postimages',{})
                if isinstance(posts,dict) and len(posts) <= 8:
                    observed = {}
                    for target,pin in posts.items():
                        if target in binding.get('editable_paths',[]) and type(pin) is str and SHA.fullmatch(pin):
                            observed[target] = pin
                    if observed:
                        row['reported_postimages'] = observed
                row['reported_integration_verified'] = project.get('integration_verified') is True
        for source in sources:
            if not isinstance(source,dict):
                continue
            for key in ('receipt_sha256','planner_receipt_sha256','artifact_sha256'):
                value = source.get(key)
                if type(value) is str and SHA.fullmatch(value):
                    row[key] = value
            for key in ('model_turns','test_count'):
                value = source.get(key)
                if type(value) is int and 0 <= value <= 100000:
                    row[key] = value
            for key in ('reason','reason_code','phase','result_state'):
                value = source.get(key)
                if type(value) is str and value in PUBLIC_REASONS:
                    row['reason_code'] = value
        output.append(row)
    return output[-128:]


def _input(mission):
    return digest({'mission_id':mission['mission_id'],'revision':mission['revision'],
                   'root_id':mission['root_id'],'context':mission['context'],
                   'instruction_sha256':hashlib.sha256(mission['instruction'].encode()).hexdigest(),
                   'verification':mission['verification']})


def _contract(mission, task_id):
    contract = {'schema':CONTRACT_SCHEMA,'task_id':task_id,
        'parent_task_id':mission['parent_task_id'],'queue_id':mission['queue_id'],
        'root_id':mission['root_id'],'instruction':mission['instruction'],
        'context':deepcopy(mission['context']),'editable_paths':list(mission['editable_paths']),
        'allowed_new_paths':[],'verification':deepcopy(mission['verification']),
        'acceptance_scope':'SOURCE_PATCH_TESTED','original_task_accepted':False}
    for key in ('focus_regions','experience'):
        if mission.get(key): contract[key] = deepcopy(mission[key])
    return contract


def validate_binding(manifest, binding, row, contract):
    """Validate a durable admission against its own pinned ancestral manifest.

    The caller verifies raw manifest SHA and ancestry before calling. This does
    not compare mutable source preimages: an integrated task must survive restart.
    """
    validate_manifest(manifest)
    require(isinstance(binding,dict) and isinstance(row,dict) and isinstance(contract,dict),
            'BINDING_SCHEMA')
    choices = [mission for mission in manifest['missions']
               if (mission['mission_id'],mission['revision']) ==
                  (binding.get('mission_id'),binding.get('mission_revision'))]
    require(len(choices) == 1, 'BINDING_MISSION')
    mission = choices[0]
    input_sha = _input(mission)
    task_id = mission['parent_task_id'] + '.relay.' + mission['mission_id'] + '.' + input_sha[:16]
    require(binding.get('input_sha256') == input_sha and binding.get('root_id') == mission['root_id']
            and binding.get('editable_paths') == mission['editable_paths']
            and binding.get('spec_sha256') == manifest['registry']['parents'][mission['parent_task_id']]['spec_sha256']
            and type(binding.get('manifest_sha256')) is str and SHA.fullmatch(binding['manifest_sha256']),
            'BINDING_IDENTITY')
    expected = _contract(mission, task_id)
    require(canonical(expected) == canonical(contract), 'CONTRACT_CHANGED')
    callback = row.get('source_sha256')
    require(type(callback) is str and SHA.fullmatch(callback), 'CALLBACK_PIN')
    expected_row = {'id':task_id,'queue_id':mission['queue_id'],'priority':mission['priority'],
        'title':mission['title'],'handler':'owner_native_project_work','resource':'CPU_LIGHT',
        'estimated_cost':2,'deps':list(mission.get('dependencies',[])),'source_sha256':callback,
        'params':{'parent_task_id':mission['parent_task_id'],'contract_sha256':digest(expected)}}
    require(row == expected_row, 'REVIEWED_ROW_CHANGED')
    return True



def memory_governor_projection(capacity):
    """Cheap observation already captured by the existing native resource gate.

    This never reloads model memory or reclaims the page cache. The resource
    gate, STOP and lease retain exclusive permission to admit new jobs.
    """
    if not isinstance(capacity, dict):
        return {'schema': 'NOX_NATIVE_MEMORY_GOVERNOR_PROJECTION_V1',
                'state': 'RESOURCE_SNAPSHOT_UNKNOWN',
                'auto_reclaim': False}
    budget = capacity.get('bounded_cpu_budget')
    decision = capacity.get('bounded_cpu_decision')
    if not isinstance(budget, dict) or not isinstance(decision, dict):
        return {'schema': 'NOX_NATIVE_MEMORY_GOVERNOR_PROJECTION_V1',
                'state': 'BOUNDED_CPU_ACCOUNTING_NOT_AVAILABLE',
                'auto_reclaim': False}
    fields = (budget.get('current_bytes'), budget.get('max_bytes'),
              budget.get('file_bytes'), budget.get('inactive_file_bytes'),
              budget.get('shmem_bytes'), decision.get('projected_memory_ratio'),
              budget.get('memory_psi_some_avg10'),
              budget.get('memory_psi_full_avg10'))
    # cgroup memory.stat and memory.current/max are byte counters, never
    # floating-point measurements. Fractional/coerced counters are not a
    # trustworthy basis for a green background-work recommendation.
    if (any(type(v) is not int for v in fields[:5])
            or any(type(v) not in (int, float) or v < 0
            or v > (1 << 63) - 1 or not math.isfinite(v)
            for v in fields)
            or not 0 < budget['max_bytes']
            or budget['current_bytes'] > budget['max_bytes']
            or budget['file_bytes'] > budget['current_bytes']
            or budget['inactive_file_bytes'] > budget['file_bytes']
            or budget['shmem_bytes'] > budget['file_bytes']):
        return {'schema': 'NOX_NATIVE_MEMORY_GOVERNOR_PROJECTION_V1',
                'state': 'RESOURCE_METADATA_HOLD',
                'auto_reclaim': False}
    raw_ratio = budget['current_bytes'] / budget['max_bytes']
    raw_headroom = budget['max_bytes'] - budget['current_bytes']
    # Reclaim-aware estimates can look healthy with almost no raw cgroup RAM.
    # Preserve the 512 MiB chat buffer, but do not recommend background work
    # below the owner-required 2 GiB raw resource fence. Observation only.
    chat_buffer_available = raw_headroom >= 512 * 1024 ** 2
    owner_raw_admission_available = raw_headroom >= 2 * 1024 ** 3
    psi_some = budget['memory_psi_some_avg10']
    psi_full = budget['memory_psi_full_avg10']
    if not chat_buffer_available:
        condition = 'RAW_CGROUP_CHAT_BUFFER_HOLD'
    elif not owner_raw_admission_available:
        condition = 'RAW_CGROUP_ADMISSION_HEADROOM_HOLD'
    elif psi_full >= 2 or psi_some >= 10 or decision['projected_memory_ratio'] >= .94:
        condition = 'PRESSURE_CRITICAL'
    elif psi_full >= .2 or psi_some >= 2 or decision['projected_memory_ratio'] >= .85:
        condition = 'PRESSURE_ELEVATED'
    else:
        condition = 'CACHE_HEALTHY'
    # This is read-only advice, not a new owner admission. Never recommend
    # background work when measured PSI or projected RAM is already critical,
    # even if an inconsistent upstream decision claims eligible=True.
    observed_eligible = (decision.get('eligible') is True
                         and chat_buffer_available and owner_raw_admission_available
                         and condition != 'PRESSURE_CRITICAL')
    return {'schema': 'NOX_NATIVE_MEMORY_GOVERNOR_PROJECTION_V1',
            'state': condition,
            'raw_cgroup_memory_ratio': raw_ratio,
            'projected_memory_ratio': decision['projected_memory_ratio'],
            'memory_psi_some_avg10': psi_some, 'memory_psi_full_avg10': psi_full,
            'inactive_file_bytes': budget['inactive_file_bytes'],
            'shmem_protected_bytes': budget['shmem_bytes'],
            'native_bounded_cpu_eligible': observed_eligible,
            'next_action': ('REUSE_EXISTING_OWNER_ADMISSION'
                            if observed_eligible else 'RESPECT_EXISTING_RESOURCE_HOLD'),
            'safe_disk_cleanup': 'OWNER_SHA_PINNED_AUDIT_AND_EXACT_EPHEMERAL_RECLAIM',
            'auto_reclaim': False, 'global_cache_eviction': False,
            'model_or_s03_mutation': False}


def _reflex_cycle(manifest, tasks, source_pins, capacity, deferred, admitted_rows):
    """Continuous *read-only* NOX self-observation and task discovery.

    Can never mint OWNER_REVIEWED, a native job or an executable contract.
    Every suggestion is anchored to the existing original registry, a real
    pinned path and an observed queue fact. Recomputing the same snapshot is
    deterministic; changing a receipt/source SHA creates a new observation.
    """
    outcomes = _outcomes(tasks)
    outcome_by_mission = {}
    for outcome in outcomes:
        key = outcome.get('mission_id')
        if isinstance(key, str):
            outcome_by_mission.setdefault(key, []).append(outcome)
    blocked = {item['mission_id']:item['reason'] for item in deferred}
    parents = manifest['registry']['parents']
    states = {'not_seen':0, 'ready':len(admitted_rows), 'pending':0,
              'running':0, 'terminal':0, 'blocked':0, 'unknown':0}
    # The outer NOX dispatcher also tracks many legacy catalog/track entries.
    # Only these three native execution handlers count as native workload.
    native_handlers = {'owner_native_subagent_review',
                       'owner_native_typed_leaf', 'owner_native_project_work'}
    native_observed = 0
    for row in tasks.values():
        if not isinstance(row, dict) or row.get('handler') not in native_handlers:
            continue
        native_observed += 1
        status = row.get('status')
        if status in ('pending','admitted','prepared','retry','wait'):
            states['pending'] += 1
        elif status == 'running':
            states['running'] += 1
        elif status in TERMINAL:
            states['terminal'] += 1
            if status in ('failed','blocked','cancelled'):
                states['blocked'] += 1
        else:
            states['unknown'] += 1

    suggestions = []
    seen = set()
    for mission in sorted(manifest['missions'], key=lambda m:
                          (m['priority'],m['parent_task_id'],m['mission_id'])):
        source = source_pins.get(mission['root_id'], {})
        evidence = outcome_by_mission.get(mission['mission_id'], [])
        last = evidence[-1] if evidence else {}
        reason = blocked.get(mission['mission_id'])
        if last.get('status') in ('failed','blocked','cancelled'):
            hypothesis = 'ANALYZE_FAILED_TERMINAL_RECEIPT'
        elif reason == 'SOURCE_PIN_DRIFT_REVIEW_REQUIRED':
            hypothesis = 'REBASE_AGAINST_OBSERVED_SOURCE_DRIFT'
        elif reason == 'ALREADY_ADMITTED_NO_REPLAY':
            continue
        elif reason == 'DEPENDENCY_NOT_VERIFIED':
            hypothesis = 'INSPECT_BLOCKING_DEPENDENCY'
        elif reason in ('SOURCE_ALREADY_RESERVED','CAPACITY_WAIT'):
            continue
        else:
            continue
        pinned = [{'path':row['path'], 'observed_sha256':source.get(row['path'])}
                  for row in mission['context'] if source.get(row['path'])]
        if not pinned:
            continue
        identity = {'parent_task_id':mission['parent_task_id'],
                    'mission_id':mission['mission_id'],
                    'hypothesis':hypothesis, 'source':pinned,
                    'receipt_sha256':last.get('receipt_sha256'),
                    'planner_receipt_sha256':last.get('planner_receipt_sha256')}
        signature = digest(identity)
        if signature in seen:
            continue
        seen.add(signature)
        suggestions.append({'schema':'NOX_NATIVE_REFLEX_CANDIDATE_V1',
            'fingerprint':signature,'queue_id':mission['queue_id'],
            'parent_task_id':mission['parent_task_id'],
            'root_id':mission['root_id'], 'mission_id':mission['mission_id'],
            'hypothesis':hypothesis,'observed_sources':pinned[:8],
            'receipt_sha256':last.get('receipt_sha256'),
            'required_next_step':'SOURCE_INSPECTION_THEN_INDEPENDENT_REVIEW',
            'authority':'RESEARCH_PROPOSAL_ONLY',
            'new_native_job_created':False})
        if len(suggestions) == 3:
            break

    if len(suggestions) < 3:
        represented = {m['parent_task_id'] for m in manifest['missions']}
        for topic in manifest.get('research_topics', []):
            parent = topic['parent_task_id']
            if parent in represented:
                continue
            identity = {'parent_task_id':parent,
                        'objective':topic['objective'],
                        'manifest_sha256':capacity['manifest_sha256']}
            signature = digest(identity)
            if signature in seen:
                continue
            seen.add(signature)
            suggestions.append({'schema':'NOX_NATIVE_REFLEX_CANDIDATE_V1',
                'fingerprint':signature,
                'queue_id':parents[parent]['queue_id'],
                'parent_task_id':parent,'hypothesis':'RESEARCH_UNBOUND_REQUIREMENT',
                'objective':topic['objective'],
                'required_next_step':'OBSERVE_ACTUAL_ALLOWED_SOURCE_AND_PIN_VERIFIER',
                'authority':'RESEARCH_PROPOSAL_ONLY',
                'new_native_job_created':False})
            if len(suggestions) == 3:
                break

    exhausted = (states['pending'] + states['running'] + states['ready'] == 0)
    context = {'manifest_sha256':capacity['manifest_sha256'],
               'source_pins':source_pins,
               'task_outcomes':outcomes[-32:], 'deferred':deferred}
    return {'schema':'NOX_NATIVE_REFLEX_MONITOR_V1',
        'observation_sha256':digest(context),
        'state':('REFILL_REQUIRED' if exhausted else 'EXECUTION_OR_ADMISSION_IN_PROGRESS'),
        'worker_cap':3,'available_slots':capacity['slots_available'],
        'observed_task_counts':states,
        'native_records_observed':native_observed,
        'legacy_or_non_native_records_ignored':len(tasks)-native_observed,
        'registry_original_total':manifest['registry']['total_original_ids'],
        'registry_parents_indexed':len(parents),
        'unindexed_original_count':manifest['registry']['total_original_ids']-len(parents),
        'staged_research_candidates':suggestions,
        'staged_count':len(suggestions),
        'repeated_snapshot_idempotent':True,
        'automatic_owner_approval':False,
        'new_native_jobs':len(admitted_rows),
        'next_action':('RUN_ADMITTED_VERIFIED_MISSIONS' if admitted_rows else
            'VERIFY_AND_PUBLISH_NEW_GROUNDED_TASKPACK'),
        'performance_or_training_success_claimed':False,
        'memory_governor':memory_governor_projection(capacity)}

def select_next(manifest, state_snapshot, source_pins, capacity):
    """Produce a bounded deterministic batch; never reset/reclaim an existing task."""
    validate_manifest(manifest)
    require(isinstance(state_snapshot,dict) and len(state_snapshot) <= 100000, 'TASK_SNAPSHOT')
    require(isinstance(source_pins,dict) and isinstance(capacity,dict), 'CALLER_INPUTS')
    require(len(source_pins) <= 32, 'SOURCE_ROOT_BOUND')
    for root_id,pins in source_pins.items():
        require(type(root_id) is str and ID.fullmatch(root_id) and isinstance(pins,dict)
                and len(pins) <= 512, 'SOURCE_PINS')
        for target,sha256 in pins.items():
            path(target)
            require(type(sha256) is str and SHA.fullmatch(sha256), 'SOURCE_PIN')
    slots = capacity.get('slots_available')
    callback = capacity.get('callback_sha256')
    require(type(slots) is int and 0 <= slots <= 3 and type(callback) is str
            and SHA.fullmatch(callback), 'CAPACITY')
    now = capacity.get('now')
    require(type(now) in (int,float) and 0 <= now <= 10**12 and math.isfinite(now), 'CLOCK')
    manifest_sha = capacity.get('manifest_sha256',digest(manifest))
    require(type(manifest_sha) is str and SHA.fullmatch(manifest_sha), 'MANIFEST_PIN')
    rows, contracts, bindings, rejected = [], {}, {}, []
    reserved = set()
    external_reservations = capacity.get('reserved_sources',[])
    require(isinstance(external_reservations,list) and len(external_reservations) <= 512,
            'RESERVATIONS')
    for reservation in external_reservations:
        require(isinstance(reservation,dict) and set(reservation) == {'root_id','path'}
                and type(reservation['root_id']) is str and ID.fullmatch(reservation['root_id']),
                'RESERVATION')
        reserved.add((reservation['root_id'],path(reservation['path'])))
    admitted_missions = set()
    for task in state_snapshot.values():
        if not isinstance(task,dict):
            continue
        binding = _binding(task)
        if not isinstance(binding,dict):
            continue
        admitted_missions.add((binding.get('mission_id'),binding.get('mission_revision')))
        if task.get('status') not in TERMINAL:
            for target in binding.get('editable_paths',[]):
                if type(target) is str:
                    reserved.add((binding.get('root_id'),target))
    for mission in sorted(manifest['missions'],key=lambda row:(row['priority'],row['mission_id'],row['revision'])):
        name = mission['mission_id']; input_sha = _input(mission)
        task_id = mission['parent_task_id'] + '.relay.' + name + '.' + input_sha[:16]
        reason = None
        if task_id in state_snapshot or (name,mission['revision']) in admitted_missions:
            reason = 'ALREADY_ADMITTED_NO_REPLAY'
        elif any(state_snapshot.get(task_id,{}).get('status') not in ('done','verified')
                 for task_id in mission.get('dependencies',[])):
            reason = 'DEPENDENCY_NOT_VERIFIED'
        elif any(source_pins.get(mission['root_id'],{}).get(row['path']) != row['sha256']
                 for row in mission['context']):
            reason = 'SOURCE_PIN_DRIFT_REVIEW_REQUIRED'
        elif any((mission['root_id'],target) in reserved for target in mission['editable_paths']):
            reason = 'SOURCE_ALREADY_RESERVED'
        elif len(rows) >= slots:
            reason = 'CAPACITY_WAIT'
        if reason:
            rejected.append({'mission_id':name,'mission_revision':mission['revision'],
                             'input_sha256':input_sha,'reason':reason})
            continue
        contract = _contract(mission, task_id)
        contract_sha = digest(contract)
        contracts[contract_sha] = contract
        rows.append({'id':task_id,'queue_id':mission['queue_id'],'priority':mission['priority'],
            'title':mission['title'],'handler':'owner_native_project_work','resource':'CPU_LIGHT',
            'estimated_cost':2,'deps':list(mission.get('dependencies',[])),
            'source_sha256':callback,
            'params':{'parent_task_id':mission['parent_task_id'],'contract_sha256':contract_sha}})
        bindings[task_id] = {'mission_id':name,'mission_revision':mission['revision'],
            'input_sha256':input_sha,'manifest_sha256':manifest_sha,'root_id':mission['root_id'],
            'editable_paths':list(mission['editable_paths']),
            'spec_sha256':manifest['registry']['parents'][mission['parent_task_id']]['spec_sha256']}
        reserved.update((mission['root_id'],target) for target in mission['editable_paths'])
    outcomes = _outcomes(state_snapshot)
    fingerprint = digest({'manifest_sha256':manifest_sha,'source_pins':source_pins,'outcomes':outcomes})
    waits = {'CAPACITY_WAIT','SOURCE_ALREADY_RESERVED','DEPENDENCY_NOT_VERIFIED'}
    waiting = any(row['reason'] in waits for row in rejected)
    state = 'REVIEWED_BATCH_READY' if rows else 'WAIT_EXISTING_WORK' if waiting else 'REFILL_REQUIRED'
    request = None
    if state == 'REFILL_REQUIRED':
        request = {'schema':'NOX_SYSTEMIC_REFILL_REQUEST_V1','request_id':fingerprint,
            'previous_manifest_sha256':manifest_sha,'manifest_revision':manifest['revision'],
            'registry_pins':deepcopy(manifest['registry']['source_registry_sha256']),
            'source_pins':deepcopy(source_pins),'outcomes':outcomes,'blocked_missions':rejected,
            'research_topics':deepcopy(manifest.get('research_topics',[])),
            'required_next_step':'GROUNDED_PROPOSAL_TO_PINNED_TASKPACK_TO_EXISTING_FENCED_MANIFEST_CAS',
            'max_next_missions':3,'original_task_accepted':False,
            'evidence_scope':'REFILL_REQUEST_ONLY_NOT_NATIVE_OR_BENCHMARK_ACCEPTANCE'}
    reflex = _reflex_cycle(manifest, state_snapshot, source_pins, capacity, rejected, rows)
    return {'rows':rows,'contracts':contracts,'bindings':bindings,'state':state,
            'fingerprint':fingerprint,'refill_request':request,'outcomes':outcomes,
            'deferred':rejected,'original_acceptance_added':0,
            'self_monitor':reflex}
