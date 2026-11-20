"""Fail-closed source registry and REFILL proposal eligibility checks.

This module only validates existing inputs. It does not create queue rows,
claims, statuses, acceptance receipts, or native authority.
"""
from __future__ import annotations

import hashlib
import re

from runtime.owner_systemic_refill import (RefillHold, canonical, require, SHA,
                                           acceptance_mapping_valid)


# The routing rules are a local derivation. The exact imported routing artifact
# itself is separately pinned by disposition['source_registry_sha256']['routing'].
ROUTING_RULES_SHA256 = '2d899a1880b09550a39be5d4fad1fc5324a5dd7a635a732d149c52aa2051d0eb'
ORIGINAL_COUNT = 295


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _rows(document, key, expected_schema, count):
    require(isinstance(document, dict) and document.get('schema') == expected_schema,
            'ORIGINAL_SOURCE_SCHEMA')
    rows = document.get(key)
    require(isinstance(rows, list) and len(rows) == count, 'ORIGINAL_SOURCE_ROW_COUNT')
    return rows


def strict_parent_registry(disposition, source_documents, source_raw_sha256):
    """Reconstruct all 295 parents from pinned originals, then compare overlay.

    `source_documents` contains parsed tasks, ideas, receipts, routing_rules and
    the exact installed routing overlay. `source_raw_sha256` contains each
    source's digest over the bytes actually read by the caller.
    """
    require(isinstance(disposition, dict)
            and disposition.get('total_original_ids') == ORIGINAL_COUNT
            and disposition.get('original_acceptance_added') == 0,
            'REGISTRY_ORIGINAL_COUNT_OR_ACCEPTANCE')
    pins = disposition.get('source_registry_sha256')
    require(isinstance(pins, dict) and set(pins) == {'tasks', 'ideas', 'receipts', 'routing'}
            and all(type(value) is str and SHA.fullmatch(value) for value in pins.values()),
            'REGISTRY_SOURCE_PINS')
    require(isinstance(source_documents, dict)
            and set(source_documents) == {'tasks', 'ideas', 'receipts', 'routing_rules', 'routing_overlay'}
            and isinstance(source_raw_sha256, dict), 'ORIGINAL_SOURCE_INPUTS')
    require(source_raw_sha256.get('tasks') == pins['tasks']
            and source_raw_sha256.get('ideas') == pins['ideas']
            and source_raw_sha256.get('receipts') == pins['receipts']
            and source_raw_sha256.get('routing_overlay') == pins['routing'],
            'ORIGINAL_SOURCE_SHA_PIN')
    require(source_raw_sha256.get('routing_rules') == ROUTING_RULES_SHA256,
            'ROUTING_RULES_SOURCE_SHA_PIN')

    tasks = _rows(source_documents['tasks'], 'tasks', 'nox-work-tasks-v1', 230)
    ideas = _rows(source_documents['ideas'], 'ideas', 'nox-work-ideas-v1', 65)
    receipts_doc = source_documents['receipts']
    require(isinstance(receipts_doc, dict) and receipts_doc.get('schema') == 'nox-work-receipts-v1'
            and isinstance(receipts_doc.get('tasks'), dict), 'ORIGINAL_RECEIPTS_SCHEMA')
    receipts = receipts_doc['tasks']
    receipt_conflicts = receipts_doc.get('_duplicate_receipt_ids', [])
    require(isinstance(receipt_conflicts,list) and len(receipt_conflicts) == len(set(receipt_conflicts))
            and all(type(task_id) is str for task_id in receipt_conflicts),
            'ORIGINAL_RECEIPT_DUPLICATE_AUDIT')
    rules = source_documents['routing_rules']
    require(isinstance(rules, dict) and isinstance(rules.get('group_defaults'), dict)
            and isinstance(rules.get('task_overrides'), dict), 'ROUTING_RULES_SCHEMA')
    overlay = source_documents['routing_overlay']
    require(isinstance(overlay, dict) and overlay.get('schema') == 'NOX_FOUR_QUEUE_ROUTING_OVERLAY_V1'
            and overlay.get('routing_only') is True, 'ROUTING_OVERLAY_SCHEMA')
    overlay_sources = overlay.get('sources')
    require(isinstance(overlay_sources, dict), 'ROUTING_OVERLAY_SOURCE_BINDING')
    for key, name in (('tasks', 'work_tasks.json'), ('ideas', 'work_ideas.json'),
                      ('receipts', 'work_receipts.json')):
        source = overlay_sources.get(name)
        require(isinstance(source, dict) and source.get('sha256') == pins[key],
                'ROUTING_OVERLAY_SOURCE_BINDING')

    raw_specs = tasks + ideas
    spec_by_id = {}
    for spec in raw_specs:
        require(isinstance(spec, dict) and type(spec.get('id')) is str
                and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', spec['id'])
                and spec['id'] not in spec_by_id, 'ORIGINAL_SPEC_ID')
        require(spec.get('evidence') in ('source', 'native'), 'ORIGINAL_EVIDENCE_SCOPE')
        if 'acceptance' in spec:
            require(type(spec['acceptance']) is str and 0 < len(spec['acceptance']) <= 1800,
                    'ORIGINAL_ACCEPTANCE_SHAPE')
        spec_by_id[spec['id']] = spec
    require(len(spec_by_id) == ORIGINAL_COUNT, 'ORIGINAL_SPEC_DENOMINATOR')
    require(set(receipts) <= set(spec_by_id), 'ORIGINAL_RECEIPT_UNKNOWN_ID')

    overlay_rows = overlay.get('tasks')
    require(isinstance(overlay_rows, list) and len(overlay_rows) == ORIGINAL_COUNT,
            'ROUTING_OVERLAY_ROWS')
    overlay_by_id = {}
    for row in overlay_rows:
        require(isinstance(row, dict) and type(row.get('task_id')) is str
                and row['task_id'] not in overlay_by_id, 'ROUTING_OVERLAY_DUPLICATE')
        overlay_by_id[row['task_id']] = row
    require(set(overlay_by_id) == set(spec_by_id), 'ROUTING_OVERLAY_ID_SET')

    disposition_rows = disposition.get('tasks')
    require(isinstance(disposition_rows, list) and len(disposition_rows) == ORIGINAL_COUNT,
            'REGISTRY_ORIGINAL_ROWS')
    disposition_by_id = {}
    for row in disposition_rows:
        require(isinstance(row, dict) and type(row.get('task_id')) is str
                and row['task_id'] not in disposition_by_id, 'REGISTRY_DUPLICATE')
        disposition_by_id[row['task_id']] = row
    require(set(disposition_by_id) == set(spec_by_id), 'REGISTRY_ID_SET')

    parents = {}
    for task_id, spec in spec_by_id.items():
        group = spec.get('group')
        require(type(group) is int and str(group) in rules['group_defaults'], 'ROUTING_GROUP')
        expected_queue = rules['task_overrides'].get(task_id, rules['group_defaults'][str(group)])
        row = disposition_by_id[task_id]
        overlay_row = overlay_by_id[task_id]
        spec_sha = _sha(canonical(spec))
        receipt = receipts.get(task_id)
        prior_state = receipt.get('state') if isinstance(receipt, dict) else None
        prior_scope = receipt.get('scope') if isinstance(receipt, dict) else None
        require(row.get('spec') == spec and row.get('spec_sha256') == spec_sha,
                'REGISTRY_SPEC_PIN')
        require(row.get('queue_id') == expected_queue == overlay_row.get('queue_id'),
                'REGISTRY_QUEUE_BINDING')
        require(overlay_row.get('required_evidence') == spec['evidence'],
                'ROUTING_EVIDENCE_BINDING')
        require(row.get('prior_receipt_state') == prior_state
                and row.get('prior_receipt_scope') == prior_scope,
                'REGISTRY_RECEIPT_BINDING')
        require(row.get('original_acceptance_added') is False, 'REGISTRY_ACCEPTANCE_DELTA')
        execution = row.get('execution_binding')
        require(isinstance(execution, dict) and type(execution.get('state')) is str,
                'REGISTRY_EXECUTION_STATE')
        parent = {'spec_sha256': spec_sha, 'queue_id': expected_queue,
                  'required_evidence': spec['evidence'], 'title': spec['title'],
                  'execution_state': execution['state'],
                  'prior_receipt_state': prior_state, 'prior_receipt_scope': prior_scope,
                  'prior_receipt_projection_ambiguous': task_id in receipt_conflicts}
        if 'acceptance' in spec:
            parent['registered_acceptance'] = spec['acceptance']
            parent['registered_acceptance_sha256'] = _sha(spec['acceptance'].encode('utf-8'))
        parents[task_id] = parent

    return {'total_original_ids': ORIGINAL_COUNT,
            'source_registry_sha256': dict(pins), 'parents': parents}


def eligibility_ledger(registry, previous=None, refill_request=None):
    """Describe structural eligibility; never label an ID executable by itself."""
    previous = previous if isinstance(previous, dict) else {}
    request = refill_request if isinstance(refill_request, dict) else {}
    prior_parents = {row.get('parent_task_id') for row in previous.get('missions', [])
                     if isinstance(row, dict)}
    outcomes = request.get('outcomes', [])
    observed_task_ids = {row.get('task_id') for row in outcomes if isinstance(row, dict)}
    original_task_states = request.get('original_task_states', [])
    observed_original_ids = {row.get('task_id') for row in original_task_states
                             if isinstance(row,dict)}
    observed_parent_ids = {task_id.split('.', 1)[0] for task_id in observed_task_ids
                           if isinstance(task_id, str) and '.' in task_id}
    observed_parent_ids.update(task_id.split('.',1)[0] for task_id in observed_original_ids
                               if isinstance(task_id,str) and '.' in task_id)
    result = []
    for task_id, parent in sorted(registry['parents'].items()):
        blockers, required_inputs = [], []
        if parent['required_evidence'] != 'source':
            blockers.append('ORIGINAL_SCOPE_IS_NOT_SOURCE')
        if not parent.get('registered_acceptance'):
            blockers.append('NO_REGISTERED_ACCEPTANCE_TEXT')
        if parent['execution_state'] != 'UNBOUND_PENDING_REAL_EXECUTION_PLAN':
            blockers.append('ORIGINAL_ALREADY_BOUND_OR_NOT_PENDING')
        if parent.get('prior_receipt_state') == 'verified':
            blockers.append('HISTORICAL_VERIFIED_RECEIPT_MUST_NOT_BE_REPLAYED')
        if parent.get('prior_receipt_projection_ambiguous'):
            blockers.append('DUPLICATE_RECEIPT_PROJECTION_REQUIRES_RECONCILIATION')
        if task_id in prior_parents:
            blockers.append('PARENT_ALREADY_IN_PREVIOUS_MANIFEST')
        if task_id in observed_parent_ids or task_id in observed_task_ids \
                or task_id in observed_original_ids:
            blockers.append('PARENT_ALREADY_OBSERVED_IN_REFILL_OUTCOMES')
        structural_candidate = not blockers
        if structural_candidate:
            required_inputs.extend(('GROUNDED_DEFECT_AND_CURRENT_SOURCE_PIN_REQUIRED',
                'EXISTING_IMMUTABLE_VERIFIER_PIN_REQUIRED',
                'EXACT_ACCEPTANCE_TO_VERIFIER_MAPPING_REQUIRED',
                'OWNER_REVIEW_AND_PUBLISHER_CAS_REQUIRED'))
        result.append({'task_id': task_id, 'spec_sha256': parent['spec_sha256'],
            'queue_id': parent['queue_id'], 'required_evidence': parent['required_evidence'],
            'registered_acceptance': parent.get('registered_acceptance'),
            'registered_acceptance_sha256': parent.get('registered_acceptance_sha256'),
            'structural_source_candidate': structural_candidate,
            'state': 'REQUIRES_GROUNDED_REVIEWED_PLAN' if structural_candidate else 'NOT_ELIGIBLE',
            'blockers': blockers,
            'required_inputs': required_inputs,
            'executable_task_emitted': False,
            'original_task_accepted': False})
    return result


def _predicate(name, expected, actual, passed, missing_field=None):
    row = {'predicate': name, 'expected': expected, 'actual': actual,
           'passed': passed is True}
    if missing_field:
        row['actionable_missing_field'] = missing_field
    return row


def proposal_predicate_diff(proposals, registry, roots, request, previous):
    """Return predicate diffs for proposed missions without repairing inputs."""
    rows = []
    if not isinstance(proposals, list):
        return [{'parent_task_id': None, 'predicates': [
            _predicate('missions_is_list', True, type(proposals).__name__, False,
                       'proposal.missions')]}]
    request_id = request.get('request_id') if isinstance(request, dict) else None
    previous_sha = request.get('previous_manifest_sha256') if isinstance(request, dict) else None
    previous_parents = {m.get('parent_task_id') for m in previous.get('missions', [])
                        if isinstance(m, dict)} if isinstance(previous, dict) else set()
    request_outcomes = request.get('outcomes', []) if isinstance(request, dict) else []
    observed_ids = {x.get('task_id') for x in request_outcomes if isinstance(x, dict)}
    observed_parents = {value.split('.', 1)[0] for value in observed_ids
                        if isinstance(value, str) and '.' in value}
    observed_parent_states = request.get('original_task_states', []) if isinstance(request,dict) else []
    observed_parents.update(row.get('task_id').split('.',1)[0]
        for row in observed_parent_states if isinstance(row,dict)
        and type(row.get('task_id')) is str and '.' in row['task_id'])
    for mission in proposals:
        if not isinstance(mission, dict):
            rows.append({'parent_task_id': None, 'predicates': [
                _predicate('mission_is_object', True, type(mission).__name__, False,
                           'proposal.missions[].parent_task_id')]})
            continue
        parent_id = mission.get('parent_task_id')
        parent = registry['parents'].get(parent_id) if type(parent_id) is str else None
        context_paths = mission.get('context_paths')
        editable = mission.get('editable_paths')
        verification = mission.get('verification')
        modules = verification.get('modules') if isinstance(verification, dict) else None
        root = roots.get(mission.get('root_id'), {}) if isinstance(roots, dict) else {}
        root_map = root if isinstance(root,dict) else {}
        context_strings = isinstance(context_paths,list) and all(type(x) is str for x in context_paths)
        editable_strings = isinstance(editable,list) and all(type(x) is str for x in editable)
        context_set = set(context_paths) if context_strings else set()
        editable_set = set(editable) if editable_strings else set()
        module_paths = [m.replace('.', '/') + '.py' for m in modules
                        if type(m) is str and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.]*', m)] \
                       if isinstance(modules, list) else []
        acceptance = parent.get('registered_acceptance') if parent else None
        acceptance_mapping = mission.get('acceptance_mapping')
        criteria_ok = acceptance_mapping_valid(acceptance,acceptance_mapping,
            modules if isinstance(modules,list) else None,
            context_paths if context_strings else None,
            editable if editable_strings else None)
        old_missions = {(m.get('mission_id'), m.get('revision'))
                        for m in previous.get('missions', []) if isinstance(m, dict)} \
                       if isinstance(previous, dict) else set()
        current_key = (mission.get('mission_id'), mission.get('revision'))
        current_key_safe = (type(current_key[0]) is str
                            and type(current_key[1]) is int)
        checks = [
            _predicate('original_task_id', 'one of original 295 IDs', parent_id,
                       parent is not None, 'proposal.missions[].parent_task_id'),
            _predicate('parent_spec_sha256', parent.get('spec_sha256') if parent else None,
                       mission.get('parent_spec_sha256'), parent is not None and
                       mission.get('parent_spec_sha256') == parent.get('spec_sha256'),
                       'proposal.missions[].parent_spec_sha256'),
            _predicate('queue_id', parent.get('queue_id') if parent else None,
                       mission.get('queue_id'), parent is not None and
                       mission.get('queue_id') == parent.get('queue_id'),
                       'proposal.missions[].queue_id'),
            _predicate('required_evidence', 'source', parent.get('required_evidence') if parent else None,
                       parent is not None and parent.get('required_evidence') == 'source',
                       'original source task with evidence=source'),
            _predicate('registered_acceptance', acceptance, mission.get('registered_acceptance'),
                       isinstance(acceptance, str) and
                       mission.get('registered_acceptance') == acceptance,
                       'proposal.missions[].registered_acceptance'),
            _predicate('acceptance_mapping_sha256', parent.get('registered_acceptance_sha256') if parent else None,
                       acceptance_mapping.get('registered_acceptance_sha256')
                       if isinstance(acceptance_mapping, dict) else None,
                       parent is not None and isinstance(acceptance_mapping, dict) and
                       acceptance_mapping.get('registered_acceptance_sha256') == parent.get('registered_acceptance_sha256') and
                       acceptance_mapping.get('registered_acceptance') == acceptance and criteria_ok,
                       'proposal.missions[].acceptance_mapping.criteria must cover the full exact acceptance text in order and bind each criterion to an immutable pinned verifier module'),
            _predicate('verifier_module_binding', 'every criterion module is pinned in context and excluded from edits',
                       [row.get('verifier_module') for row in acceptance_mapping.get('criteria',[])
                        if isinstance(row,dict)] if isinstance(acceptance_mapping,dict) else None,
                       criteria_ok and bool(module_paths) and set(module_paths) <= context_set
                       and not (set(module_paths) & editable_set),
                       'proposal.verification.modules must pin the mapped immutable verifier files'),
            _predicate('execution_state', 'UNBOUND_PENDING_REAL_EXECUTION_PLAN',
                       parent.get('execution_state') if parent else None,
                       parent is not None and parent.get('execution_state') ==
                       'UNBOUND_PENDING_REAL_EXECUTION_PLAN', 'original task needs an unbound real execution plan'),
            _predicate('not_previously_planned_or_observed', True,
                       parent_id in previous_parents or parent_id in observed_parents or parent_id in observed_ids,
                       parent_id not in previous_parents and parent_id not in observed_parents
                       and parent_id not in observed_ids, 'choose an unplanned original task ID'),
            _predicate('refill_request_id', request_id, mission.get('request_id', request_id),
                       isinstance(request_id, str) and SHA.fullmatch(request_id)
                       and mission.get('request_id', request_id) == request_id,
                       'proposal.request_id (64-hex exact REFILL_REQUIRED request ID)'),
            _predicate('proposal_predecessor_sha256', previous_sha,
                       mission.get('previous_manifest_sha256', previous_sha),
                       isinstance(previous_sha, str) and SHA.fullmatch(previous_sha)
                       and mission.get('previous_manifest_sha256', previous_sha) == previous_sha,
                       'proposal.previous_manifest_sha256'),
            _predicate('context_paths_pinned', 'nonempty paths all in current source census', context_paths,
                       context_strings and bool(context_paths)
                       and context_set <= set(root_map), 'proposal.missions[].context_paths'),
            _predicate('editable_paths_pinned', 'nonempty subset of pinned context', editable,
                       editable_strings and bool(editable) and
                       editable_set <= context_set and editable_set <= set(root_map),
                       'proposal.missions[].editable_paths'),
            _predicate('observed_defect_pin', 'observed SHA of an editable path',
                       (mission.get('defect') or {}).get('observed_source_sha256')
                       if isinstance(mission.get('defect'), dict) else None,
                       isinstance(mission.get('defect'), dict) and
                       (mission['defect'].get('observed_source_sha256') in
                        {root_map.get(path) for path in editable_set}),
                       'proposal.missions[].defect.observed_source_sha256'),
            _predicate('immutable_verifier_paths_pinned', 'existing noneditable modules in census', module_paths,
                       bool(module_paths) and set(module_paths) <= context_set and
                       set(module_paths) <= set(root_map) and not (set(module_paths) & editable_set),
                       'proposal.missions[].verification.modules'),
            _predicate('no_new_paths', [], mission.get('allowed_new_paths'),
                       mission.get('allowed_new_paths', []) == [],
                       'proposal.missions[].allowed_new_paths must remain []'),
            _predicate('original_receipt_not_historically_verified', 'not verified',
                       parent.get('prior_receipt_state') if parent else None,
                       parent is not None and parent.get('prior_receipt_state') != 'verified',
                       'reconcile historical receipt without replaying it'),
            _predicate('mission_revision_not_reused', True,
                       current_key in old_missions if current_key_safe else None,
                       current_key_safe and current_key not in old_missions,
                       'proposal.missions[].mission_id/revision'),
        ]
        rows.append({'parent_task_id': parent_id, 'predicates': checks,
                     'all_passed': all(row['passed'] for row in checks),
                     'native_publish_performed': False,
                     'original_task_accepted': False})
    return rows


def special_candidate_gaps(registry, source_census=None, source_census_sha256=None):
    """Evidence-based gaps for the three source ideas highlighted by the owner."""
    root = (source_census.get('roots',{}).get('NOX_PROJECT_SOURCE',{})
            if isinstance(source_census,dict) else {})
    root = root if isinstance(root,dict) else {}
    descriptions = {
        'I-39': {
            'observed_source_evidence': 'Existing Forge verifier has cross-split origin/prompt/provenance/source-URL checks; no current pinned verifier path establishes the exact MinHash-by-source criterion.',
            'source_evidence_refs': [
                {'path':'NOX_PROJECT_SOURCE/forge_split_guard.py','sha256':root.get('forge_split_guard.py')},
                {'path':'NOX_PROJECT_SOURCE/test_forge_split_guard.py','sha256':root.get('test_forge_split_guard.py')},
                {'path':'NOX_PROJECT_SOURCE/test_nox_forge_split_coverage.py','sha256':root.get('test_nox_forge_split_coverage.py')}],
            'actionable_missing_fields': ['editable_source_path_and_sha256_for_minhash_by_source',
                'existing_immutable_verifier_path_and_sha256_for_minhash',
                'acceptance_mapping_criterion_for_train_to_holdout_leakage'],
        },
        'I-48': {
            'observed_source_evidence': 'Existing queue evidence explicitly retains STOP_YIELD_RECONNECT_RESTORE_SEQUENCE_ACCEPTANCE_REQUIRED; current queue regression checks do not establish the complete property-generated sequence.',
            'source_evidence_refs': [
                {'path':'nox-control/four_queue_20261118/owner_subagent_dispatcher.py',
                 'sha256':'88af9c11d54e084ccb868c474d17c2a85511600a0ff6578bfe5490b437fe554e'},
                {'path':'nox-control/four_queue_20261118/test_owner_four_queue.py',
                 'sha256':'4334ec2e2047c34ed7ee5d1f24152a1a2468b07f4bdfc8ebf592d13a64648ac9'},
                {'path':'nox-control/four_queue_20261118/evidence/native_install_receipt_6964933277.json',
                 'sha256':'0f2348a25e78671bfe2e24d990290bd23d493fb84dfe79724646c764d0847ef9'}],
            'actionable_missing_fields': ['editable_source_path_and_sha256_for_sequence_harness',
                'existing_immutable_property_verifier_path_and_sha256',
                'acceptance_mapping_for_stop_yield_reconnect_restore_each_state'],
        },
        'I-50': {
            'observed_source_evidence': 'The pinned 33-file source census contains no RU/ES noisy-audio corpus or existing before/after WER verifier.',
            'source_evidence_refs': [{'path':'NOX_PROJECT_SOURCE source census',
                'sha256':source_census_sha256,
                'allowed_paths':sorted(root)}],
            'actionable_missing_fields': ['licensed_pinned_ru_es_audio_corpus_and_sha256',
                'existing_immutable_wer_verifier_path_and_sha256',
                'paired_before_after_voice_patch_source_sha256_and_metrics'],
        },
    }
    output = []
    for task_id, detail in descriptions.items():
        parent = registry['parents'].get(task_id)
        output.append({'task_id': task_id,
            'spec_sha256': parent.get('spec_sha256') if parent else None,
            'queue_id': parent.get('queue_id') if parent else None,
            'registered_acceptance': parent.get('registered_acceptance') if parent else None,
            'state': 'NOT_EXECUTABLE_NO_GROUNDED_SOURCE_AND_EXACT_VERIFIER',
            **detail, 'review_or_cas_weakened': False,
            'native_job_created': False, 'original_task_accepted': False})
    return output
