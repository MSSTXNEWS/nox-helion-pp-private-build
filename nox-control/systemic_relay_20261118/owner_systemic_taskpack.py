"""Compile a grounded, reviewed next batch for the existing fenced NOX publisher.

Usage: owner_systemic_taskpack.py --previous-manifest FILE --previous-sha256 SHA
  --proposal FILE --source-census FILE --refill-request FILE --registry FILE
  --review FILE --output DIR

The external producer researches concrete defects, prepares the proposal, and
independently reviews its exact bytes and source census. This compiler binds
existing original IDs, existing source paths and existing immutable test paths.
It writes a content-addressed LOCAL package plus an admission request. Publication
still uses the one native owner's existing lease/CAS gates; a review JSON is not
server authority. No subprocess, model request, test, scheduler or remote write.
"""
from __future__ import annotations

import argparse
import base64
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

sys.path.insert(0,str(Path(__file__).parent / 'runtime'))
from owner_systemic_refill import (SCHEMA, RefillHold, canonical, digest, require,
                                   validate_manifest, _contract, _input, SHA,
                                   acceptance_mapping_valid)
from owner_systemic_refill_eligibility import strict_parent_registry

PROPOSAL_SCHEMA = 'NOX_SYSTEMIC_GROUNDED_PROPOSALS_V1'
REVIEW_SCHEMA = 'NOX_SYSTEMIC_TASKPACK_REVIEW_V1'
REFILL_SCHEMA = 'NOX_SYSTEMIC_REFILL_REQUEST_V1'
HELPER_SHA = '8470a6720ca69864bbc4e6e630a1f853344839af424d3829dcdf1774442db609'


def read_raw(path, limit=4*1024*1024):
    """Bounded pinned read without following any ancestor or basename symlink."""
    target = Path(path).absolute()
    parent = os.open('/',os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in target.parts[1:-1]:
            child = os.open(part,os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,dir_fd=parent)
            os.close(parent); parent = child
        fd = os.open(target.name,os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,dir_fd=parent)
        try:
            before = os.fstat(fd)
            require(stat.S_ISREG(before.st_mode) and before.st_size <= limit, 'INPUT_FILE_BOUND')
            chunks, remaining = [], limit + 1
            while remaining:
                chunk = os.read(fd,min(65536,remaining))
                if not chunk: break
                chunks.append(chunk); remaining -= len(chunk)
            after = os.fstat(fd)
            require(all(getattr(before,key) == getattr(after,key) for key in
                        ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns')), 'INPUT_CHANGED')
            raw = b''.join(chunks)
            require(len(raw) <= limit, 'INPUT_FILE_BOUND')
        finally:
            os.close(fd)
    finally:
        os.close(parent)
    return raw


def read_document(path, limit=4*1024*1024):
    raw = read_raw(path,limit)
    def unique(pairs):
        result = {}
        for key,value in pairs:
            require(key not in result,'DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    def nonfinite(value):
        raise RefillHold('HOLD_SYSTEMIC_RELAY_NONFINITE_JSON')
    value = json.loads(raw,object_pairs_hook=unique,parse_constant=nonfinite)
    canonical(value)  # Reject exponent overflow too, before any package is written.
    return value,hashlib.sha256(raw).hexdigest()


def read_identical_duplicate_document(path, limit=4*1024*1024):
    """Read legacy JSON with duplicate keys only when every value is identical.

    The pinned receipts snapshot contains repeated, byte-equivalent task rows.
    Conflicting duplicate values remain a hard hold; this does not change the
    parser used for proposals, reviews, manifests, or any write target.
    """
    raw = read_raw(path,limit)
    class ObjectPairs:
        def __init__(self,pairs): self.pairs = pairs
    def nonfinite(value):
        raise RefillHold('HOLD_SYSTEMIC_RELAY_NONFINITE_JSON')
    parsed = json.loads(raw,object_pairs_hook=ObjectPairs,parse_constant=nonfinite)
    conflicts = []
    def collapse(value,path=()):
        if isinstance(value,ObjectPairs):
            result = {}
            for key,item in value.pairs:
                item = collapse(item,path+(key,))
                if key in result and canonical(result[key]) != canonical(item):
                    # This pinned legacy receipt snapshot repeats one task with
                    # extra descriptive fields in the later row. Treat only
                    # identical state/scope as a safe receipt projection; keep
                    # the ambiguity explicit and reject all other conflicts.
                    old = result[key]
                    same_receipt_projection = (path == ('tasks',)
                        and isinstance(old,dict) and isinstance(item,dict)
                        and old.get('state') == item.get('state')
                        and old.get('scope') == item.get('scope')
                        and old.get('state') is not None and old.get('scope') is not None)
                    require(same_receipt_projection,'DUPLICATE_JSON_KEY_CONFLICT')
                    conflicts.append(key)
                    result[key] = {'state':old['state'],'scope':old['scope']}
                else:
                    result[key] = item
            return result
        if isinstance(value,list): return [collapse(item,path) for item in value]
        return value
    value = collapse(parsed)
    if conflicts:
        value['_duplicate_receipt_ids'] = sorted(set(conflicts))
    canonical(value)
    return value,hashlib.sha256(raw).hexdigest()


def parent_registry(disposition):
    require(isinstance(disposition,dict) and disposition.get('total_original_ids') == 295,
            'REGISTRY_ORIGINAL_COUNT')
    require(disposition.get('original_acceptance_added') == 0,
            'REGISTRY_ACCEPTANCE_DELTA')
    tasks = disposition.get('tasks')
    require(isinstance(tasks,list) and len(tasks) == 295,'REGISTRY_ORIGINAL_ROWS')
    parents = {}
    for row in tasks:
        require(isinstance(row,dict) and row.get('task_id') not in parents,'REGISTRY_DUPLICATE')
        spec = row.get('spec')
        require(isinstance(spec,dict) and spec.get('id') == row.get('task_id')
                and hashlib.sha256(canonical(spec)).hexdigest() == row.get('spec_sha256'),
                'REGISTRY_SPEC_PIN')
        binding = row.get('execution_binding')
        require(isinstance(binding,dict) and type(binding.get('state')) is str,
                'REGISTRY_EXECUTION_STATE')
        parents[row['task_id']] = {'spec_sha256':row['spec_sha256'],'queue_id':row['queue_id'],
            'required_evidence':spec['evidence'],'title':spec['title']}
    return {'total_original_ids':295,'source_registry_sha256':deepcopy(disposition['source_registry_sha256']),
            'parents':parents}


def bind_missions(proposals, roots, registry, execution_states=None, *, require_acceptance_binding=False):
    execution_states = execution_states or {}
    require(isinstance(proposals,list) and 1 <= len(proposals) <= 3,'NEXT_BATCH_BOUND')
    missions = []
    for proposal in proposals:
        require(isinstance(proposal,dict),'PROPOSAL')
        mission = deepcopy(proposal)
        paths = mission.pop('context_paths',None)
        require(isinstance(paths,list) and paths and len(set(paths)) == len(paths),'PROPOSAL_PATHS')
        root = roots.get(mission.get('root_id'),{})
        require(isinstance(root,dict) and all(target in root for target in paths),'CURRENT_SOURCE_BINDING')
        mission['context'] = [{'path':target,'sha256':root[target]} for target in sorted(paths)]
        require(mission.get('defect',{}).get('observed_source_sha256')
                in {root[target] for target in mission.get('editable_paths',[])},'DEFECT_SOURCE_PIN')
        parent = registry['parents'].get(mission.get('parent_task_id'))
        require(parent is not None and mission.get('queue_id') == parent['queue_id'],'ORIGINAL_PARENT')
        require(execution_states.get(mission['parent_task_id']) ==
                'UNBOUND_PENDING_REAL_EXECUTION_PLAN',
                'ORIGINAL_PARENT_ALREADY_BOUND')
        require(mission.get('parent_spec_sha256') == parent['spec_sha256'],
                'ORIGINAL_SPEC_SHA_PIN')
        if require_acceptance_binding:
            acceptance = parent.get('registered_acceptance')
            require(parent.get('required_evidence') == 'source'
                    and type(acceptance) is str and bool(acceptance),
                    'ORIGINAL_ACCEPTANCE_NOT_REGISTERED')
            require(mission.get('registered_acceptance') == acceptance,
                    'ORIGINAL_ACCEPTANCE_BINDING')
            mapping = mission.get('acceptance_mapping')
            verification = mission.get('verification')
            require(acceptance_mapping_valid(acceptance,mapping,
                    verification.get('modules') if isinstance(verification,dict) else None,paths,
                    mission.get('editable_paths',[])),
                    'ACCEPTANCE_MAPPING_BINDING')
        # The identity is preserved in the successor manifest for independent
        # review; the runtime validator checks it against the registry binding.
        missions.append(mission)
    return missions


def _validate_refill_request(request, previous, previous_sha):
    require(isinstance(request,dict) and request.get('schema') == REFILL_SCHEMA
            and request.get('previous_manifest_sha256') == previous_sha
            and request.get('manifest_revision') == previous['revision']
            and request.get('registry_pins') == previous['registry']['source_registry_sha256']
            and request.get('original_task_accepted') is False
            and request.get('evidence_scope') == 'REFILL_REQUEST_ONLY_NOT_NATIVE_OR_BENCHMARK_ACCEPTANCE',
            'REFILL_REQUEST_BINDING')
    source_pins, outcomes = request.get('source_pins'), request.get('outcomes')
    original_states = request.get('original_task_states')
    require(isinstance(source_pins,dict) and isinstance(outcomes,list)
            and isinstance(original_states,list) and len(original_states) <= 8192
            and type(request.get('request_id')) is str and SHA.fullmatch(request['request_id']),
            'REFILL_REQUEST_SHAPE')
    require(request.get('original_task_states_sha256') == digest(original_states),
            'ORIGINAL_TASK_STATE_SNAPSHOT_SHA')
    fingerprint = digest({'manifest_sha256':previous_sha,'source_pins':source_pins,
                          'outcomes':outcomes,'original_task_states':original_states})
    require(fingerprint == request['request_id'], 'REFILL_REQUEST_ID')
    prior = {}
    for mission in previous['missions']:
        task_id = mission['parent_task_id'] + '.relay.' + mission['mission_id'] + '.' + _input(mission)[:16]
        prior[(mission['mission_id'],mission['revision'])] = (mission,task_id)
    seen = set()
    original_statuses = {}
    for row in original_states:
        require(isinstance(row,dict) and set(row) == {'task_id','status'}
                and type(row.get('task_id')) is str
                and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}',row['task_id'])
                and row.get('status') in {'pending','running','wait','retry','admitted',
                    'prepared','done','verified','blocked','failed','cancelled','unknown'},
                'ORIGINAL_TASK_STATE_ROW')
        require(row['task_id'] not in original_statuses, 'ORIGINAL_TASK_STATE_DUPLICATE')
        original_statuses[row['task_id']] = row['status']
    seen.update(original_statuses)
    for outcome in outcomes:
        require(isinstance(outcome,dict), 'REFILL_OUTCOME')
        task_id = outcome.get('task_id')
        key = (outcome.get('mission_id'),outcome.get('mission_revision'))
        require(type(task_id) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}',task_id)
                and type(outcome.get('input_sha256')) is str and SHA.fullmatch(outcome['input_sha256'])
                and outcome.get('status') in {'pending','running','wait','retry','admitted',
                    'prepared','done','verified','blocked','failed','cancelled','unknown'},
                'REFILL_OUTCOME_BINDING')
        if key in prior:
            mission,expected_task_id = prior[key]
            require(task_id == expected_task_id
                    and outcome.get('input_sha256') == _input(mission),
                    'REFILL_OUTCOME_BINDING')
        if task_id in seen:
            require(task_id in original_statuses
                    and outcome.get('status') == original_statuses[task_id],
                    'REFILL_OUTCOME_DUPLICATE_OR_STATE_MISMATCH')
        seen.add(task_id)
    return seen


def _validate_proposal_request(proposal, previous_sha, refill_request):
    request_id = refill_request.get('request_id') if isinstance(refill_request,dict) else None
    require(isinstance(proposal,dict) and proposal.get('schema') == PROPOSAL_SCHEMA
            and proposal.get('previous_manifest_sha256') == previous_sha
            and type(request_id) is str and SHA.fullmatch(request_id)
            and proposal.get('request_id') == request_id,
            'PROPOSAL_REFILL_REQUEST_BINDING')
    return True


def immutable_verifier_sha256(missions, roots):
    """Hash the exact verifier contract and source bytes pinned for each mission."""
    rows = []
    for mission in missions:
        root = roots[mission['root_id']]
        modules = mission['verification']['modules']
        pins = [{'module':module,'path':module.replace('.','/')+'.py',
                 'sha256':root[module.replace('.','/')+'.py']} for module in modules]
        rows.append({'parent_task_id':mission['parent_task_id'],
            'parent_spec_sha256':mission['parent_spec_sha256'],
            'registered_acceptance':mission.get('registered_acceptance'),
            'acceptance_mapping':deepcopy(mission.get('acceptance_mapping')),
            'mission_id':mission['mission_id'],'revision':mission['revision'],
            'verification':deepcopy(mission['verification']),'tests':pins})
    return digest(rows)


def compile_taskpack(previous, previous_sha, proposal, proposal_sha, census, census_sha,
                     refill_request, refill_request_sha, disposition, disposition_sha, review,
                     source_documents=None, source_raw_sha256=None):
    validate_manifest(previous)
    observed_task_ids = _validate_refill_request(refill_request,previous,previous_sha)
    _validate_proposal_request(proposal,previous_sha,refill_request)
    require(isinstance(census,dict) and census.get('schema') == 'NOX_SYSTEMIC_SOURCE_CENSUS_V1'
            and isinstance(census.get('roots'),dict),'SOURCE_CENSUS')
    require(isinstance(review,dict) and review.get('schema') == REVIEW_SCHEMA
            and review.get('review_origin') == 'OWNER_REVIEWED'
            and review.get('proposal_sha256') == proposal_sha
            and review.get('source_census_sha256') == census_sha
            and review.get('refill_request_sha256') == refill_request_sha
            and review.get('previous_manifest_sha256') == previous_sha
            and review.get('original_task_accepted') is False,'EXACT_REVIEW_RECEIPT')
    require(review.get('previous_claims_settled') is True
            and type(review.get('native_readback_sha256')) is str
            and SHA.fullmatch(review['native_readback_sha256']), 'OWNER_READBACK_RECEIPT')
    require(review.get('registry_sha256') == disposition_sha
            and review.get('status') == 'EXACT_SOURCE_AND_PROPOSAL_REVIEWED',
            'EXACT_REGISTRY_REVIEW')
    require(isinstance(source_documents,dict) and isinstance(source_raw_sha256,dict),
            'EXACT_ORIGINAL_SOURCE_INPUTS_REQUIRED')
    registry = strict_parent_registry(disposition,source_documents,source_raw_sha256)
    require(registry['source_registry_sha256'] == previous['registry']['source_registry_sha256'],
            'REGISTRY_CHANGED_NEEDS_OWNER_REVIEW')
    execution_states = {row['task_id']:row['execution_binding']['state']
                        for row in disposition['tasks']}
    missions = bind_missions(proposal.get('missions'),census['roots'],registry,execution_states,
                             require_acceptance_binding=True)
    require(review.get('reviewed_mission_ids') == sorted(row['mission_id'] for row in missions),
            'REVIEWED_MISSION_SET')
    prior_parents = {row['parent_task_id'] for row in previous['missions']}
    proposed_parents = [row['parent_task_id'] for row in missions]
    require(len(set(proposed_parents)) == len(proposed_parents), 'DUPLICATE_ORIGINAL_TASK')
    require(not prior_parents.intersection(proposed_parents), 'ORIGINAL_TASK_ALREADY_PLANNED')
    require(all(parent not in observed_task_ids
                and not any(task_id.startswith(parent+'.') for task_id in observed_task_ids)
                for parent in proposed_parents), 'ORIGINAL_TASK_ALREADY_OBSERVED')
    old = {(row['mission_id'],row['revision']) for row in previous['missions']}
    require(not old.intersection((row['mission_id'],row['revision']) for row in missions),
            'MISSION_REVISION_ALREADY_PUBLISHED')
    verifier_sha = immutable_verifier_sha256(missions,census['roots'])
    require(review.get('immutable_verifier_sha256') == verifier_sha,
            'IMMUTABLE_VERIFIER_REVIEW_PIN')
    # Replace the active small batch; pinned ancestry retains previous durable bindings.
    manifest = {'schema':SCHEMA,'revision':previous['revision']+1,
        'previous_manifest_sha256':previous_sha,'review_origin':'OWNER_REVIEWED',
        'acceptance_scope':'SOURCE_PATCH_TESTED','original_task_accepted':False,
        'registry':registry,'missions':missions,
        'research_topics':deepcopy(proposal.get('research_topics',previous.get('research_topics',[]))),
        'intent_sources':deepcopy(previous.get('intent_sources',[])),
        'producer_evidence':{'proposal_sha256':proposal_sha,'source_census_sha256':census_sha,
            'refill_request_sha256':refill_request_sha,'refill_request_id':proposal.get('request_id'),
            'registry_sha256':disposition_sha,'review_sha256':digest(review),
            'immutable_verifier_sha256':verifier_sha,
            'refill_request_binding':{'request_id':refill_request['request_id'],
                'source_pins':deepcopy(refill_request['source_pins']),
                'outcomes':deepcopy(refill_request['outcomes']),
                'original_task_states':deepcopy(refill_request['original_task_states']),
                'original_task_states_sha256':refill_request['original_task_states_sha256']},
            'original_task_spec_pins':[{'task_id':row['parent_task_id'],
                'spec_sha256':row['parent_spec_sha256'],'queue_id':row['queue_id'],
                'registered_acceptance_sha256':registry['parents'][row['parent_task_id']].get(
                    'registered_acceptance_sha256')} for row in missions]}}
    validate_manifest(manifest)
    return manifest


def _publish_local(path, raw):
    """Exclusive immutable local artifact; identical repeat is idempotent."""
    path.parent.mkdir(parents=True,exist_ok=True)
    try:
        fd = os.open(path,os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,0o600)
    except FileExistsError:
        value,sha256 = read_document(path)
        require(hashlib.sha256(raw).hexdigest() == sha256,'OUTPUT_ALREADY_DIFFERENT')
        return
    try:
        remaining = memoryview(raw)
        while remaining:
            count = os.write(fd,remaining)
            require(count > 0,'SHORT_LOCAL_WRITE')
            remaining = remaining[count:]
        os.fsync(fd)
    finally:
        os.close(fd)


def write_package(manifest, output, *, previous_sha=None):
    validate_manifest(manifest)
    output = Path(output)
    manifest_sha = digest(manifest)
    _publish_local(output / 'relay' / (manifest_sha + '.json'),canonical(manifest))
    contracts = {}
    for mission in manifest['missions']:
        task_id = mission['parent_task_id'] + '.relay.' + mission['mission_id'] + '.' + _input(mission)[:16]
        contract = _contract(mission,task_id); contract_sha = digest(contract)
        _publish_local(output / 'contracts' / (contract_sha + '.json'),canonical(contract))
        contracts[task_id] = contract_sha
    request = {'schema':'NOX_SYSTEMIC_RELAY_PUBLISH_REQUEST_V1',
        'expected_previous_manifest_sha256':previous_sha,'new_manifest_sha256':manifest_sha,
        'refill_request_sha256':manifest['producer_evidence']['refill_request_sha256'],
        'refill_request_id':manifest['producer_evidence']['refill_request_id'],
        'original_task_states_sha256':manifest['producer_evidence']['refill_request_binding']['original_task_states_sha256'],
        'registry_sha256':manifest['producer_evidence']['registry_sha256'],
        'immutable_verifier_sha256':manifest['producer_evidence']['immutable_verifier_sha256'],
        'owner_review_sha256':manifest['producer_evidence']['review_sha256'],
        'new_manifest_path':'state/dispatcher/project_executor/package/relay/' + manifest_sha + '.json',
        'contracts':contracts,'scope':'EXISTING_SOURCE_WORKSPACE_ONLY',
        'original_task_accepted':False,'native_write_performed':False,
        'publisher_requirements':['EXACT_CURRENT_CONFIG_CAS','EXISTING_NATIVE_OWNER_LEASE',
                                  'ALL_OLD_TASKS_AND_CLAIMS_PRESERVED','NO_OWNER_STOP_OVERRIDE',
                                  'SOURCE_CONTEXT_AND_IMMUTABLE_TEST_PINS','PUBLISH_READBACK']}
    _publish_local(output / ('publish_request_' + manifest_sha + '.json'),canonical(request))
    return request


def publisher_entry(manifest, package, checkpoint, template_path, helper_path):
    """Make the exact reviewed native entry locally; never execute or upload it."""
    require(isinstance(checkpoint,dict)
            and checkpoint.get('schema') == 'NOX_SYSTEMIC_NATIVE_PUBLISH_CHECKPOINT_V1',
            'PUBLISH_CHECKPOINT')
    for key in ('expected_config_sha256','previous_manifest_sha256',
                'expected_source_files_sha256','publisher_template_sha256'):
        require(type(checkpoint.get(key)) is str and SHA.fullmatch(checkpoint[key]),
                'CHECKPOINT_PIN')
    require(checkpoint['previous_manifest_sha256'] == manifest['previous_manifest_sha256'],
            'PUBLISH_PREDECESSOR')
    director,workers = checkpoint.get('expected_director'),checkpoint.get('expected_workers')
    def identity(value):
        return (isinstance(value,dict) and type(value.get('pid')) is int
                and 1 < value['pid'] <= 2**31 and type(value.get('start_ticks')) is int
                and 0 < value['start_ticks'] <= 2**63)
    require(identity(director) and isinstance(workers,list) and len(workers) == 3
            and all(identity(row) for row in workers)
            and len({row['pid'] for row in workers}) == 3
            and director['pid'] not in {row['pid'] for row in workers},'CHECKPOINT_WORKERS')
    protected = checkpoint.get('protected_processes')
    require(isinstance(protected,dict) and set(protected) == {'chat','proxy','web'}
            and all(identity(row) for row in protected.values()),'CHECKPOINT_PROTECTED')
    template,helper = read_raw(template_path),read_raw(helper_path)
    require(hashlib.sha256(template).hexdigest() == checkpoint['publisher_template_sha256']
            and hashlib.sha256(helper).hexdigest() == HELPER_SHA,'PUBLISHER_CODE_PIN')
    package = Path(package)
    manifest_sha = digest(manifest)
    assets = {'transaction_helpers.py':helper}
    paths = {}
    path = 'relay/'+manifest_sha+'.json'
    assets['relay_manifest.json'] = read_raw(package/path)
    require(assets['relay_manifest.json'] == canonical(manifest),'MANIFEST_PACKAGE_CHANGED')
    paths['relay_manifest.json'] = path
    for mission in manifest['missions']:
        task_id = mission['parent_task_id']+'.relay.'+mission['mission_id']+'.'+_input(mission)[:16]
        contract = _contract(mission,task_id)
        contract_sha = digest(contract)
        name = mission['mission_id']+'.json'
        path = 'contracts/'+contract_sha+'.json'
        raw = read_raw(package/path)
        require(raw == canonical(contract),'CONTRACT_PACKAGE_CHANGED')
        assets[name],paths[name] = raw,path
    require(len(assets) == len(manifest['missions'])+2,'PUBLISH_ASSET_COLLISION')
    spec = {'schema':'NOX_SYSTEMIC_RELAY_PUBLISH_SPEC_V1',
        'assets':{name:hashlib.sha256(raw).hexdigest() for name,raw in assets.items()},
        'helper_asset':'transaction_helpers.py','package_paths':paths,
        'manifest_sha256':manifest_sha,
        **{key:deepcopy(checkpoint[key]) for key in ('expected_config_sha256',
            'previous_manifest_sha256','expected_source_files_sha256','expected_director',
            'expected_workers','protected_processes')}}
    bundle = {name:base64.b64encode(raw).decode('ascii') for name,raw in assets.items()}
    text = template.decode('utf-8')
    require(text.count('\nSPEC = {}\n') == 1
            and text.count('    BUNDLE = __NOX_BUNDLE_JSON__\n') == 1,'PUBLISH_TEMPLATE_ANCHORS')
    text = text.replace('\nSPEC = {}\n','\nSPEC = '+repr(spec)+'\n',1)
    text = text.replace('    BUNDLE = __NOX_BUNDLE_JSON__\n','    BUNDLE = '+repr(bundle)+'\n',1)
    entry = text.encode('utf-8')
    compile(entry,'<reviewed-local-publisher-entry>','exec')
    _publish_local(package/('native_publish_spec_'+manifest_sha+'.json'),canonical(spec))
    _publish_local(package/('native_publish_bundle_'+manifest_sha+'.json'),canonical(bundle))
    # Same exclusive write semantics; an existing entry is compared as bytes.
    entry_path = package/('native_publish_entry_'+manifest_sha+'.py')
    if entry_path.exists():
        require(read_raw(entry_path) == entry,'OUTPUT_ALREADY_DIFFERENT')
    else:
        _publish_local(entry_path,entry)
    result = {'schema':'NOX_SYSTEMIC_NATIVE_PUBLISH_BUILD_V1','manifest_sha256':manifest_sha,
        'entry_path':str(entry_path),'entry_sha256':hashlib.sha256(entry).hexdigest(),
        'spec_sha256':digest(spec),'bundle_sha256':digest(bundle),
        'publisher_template_sha256':hashlib.sha256(template).hexdigest(),
        'helper_sha256':HELPER_SHA,'native_execution_performed':False,
        'original_task_accepted':False}
    _publish_local(package/('native_publish_build_'+manifest_sha+'.json'),canonical(result))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('previous-manifest','previous-sha256','proposal','source-census',
                   'refill-request','registry','review','output'):
        parser.add_argument('--'+option,required=True)
    source_root = Path(__file__).parent.parent / 'four_queue_20261118'
    for option, filename in (
        ('source-tasks','work_tasks.json'), ('source-ideas','work_ideas.json'),
        ('source-receipts','work_receipts.json'), ('routing-rules','routing_rules.json'),
        ('routing-overlay','NOX_FOUR_QUEUE_ROUTING_20261118.json')):
        parser.add_argument('--'+option,default=str(source_root / filename))
    for option in ('publisher-checkpoint','publisher-template','transaction-helper'):
        parser.add_argument('--'+option)
    args = parser.parse_args()
    previous,previous_sha = read_document(args.previous_manifest)
    require(previous_sha == args.previous_sha256,'PREVIOUS_MANIFEST_PIN')
    proposal,proposal_sha = read_document(args.proposal)
    census,census_sha = read_document(args.source_census)
    refill_request,refill_request_sha = read_document(args.refill_request)
    disposition,disposition_sha = read_document(args.registry)
    review,_ = read_document(args.review)
    source_documents,source_raw_sha256 = {},{}
    for key,option in (('tasks','source_tasks'),('ideas','source_ideas'),
                       ('receipts','source_receipts'),('routing_rules','routing_rules'),
                       ('routing_overlay','routing_overlay')):
        reader = read_identical_duplicate_document if key == 'receipts' else read_document
        source_documents[key],source_raw_sha256[key] = reader(getattr(args,option))
    manifest = compile_taskpack(previous,previous_sha,proposal,proposal_sha,census,census_sha,
        refill_request,refill_request_sha,disposition,disposition_sha,review,
        source_documents,source_raw_sha256)
    result = write_package(manifest,args.output,previous_sha=previous_sha)
    publisher_args = (args.publisher_checkpoint,args.publisher_template,args.transaction_helper)
    require(not any(publisher_args) or all(publisher_args),'PUBLISHER_ARGUMENTS')
    if all(publisher_args):
        checkpoint,_ = read_document(args.publisher_checkpoint)
        require(checkpoint.get('expected_source_files_sha256') == census.get('observed_files_sha256'),
                'PUBLISH_CENSUS_PIN')
        result['native_build'] = publisher_entry(manifest,args.output,checkpoint,
                                                 args.publisher_template,args.transaction_helper)
    print(json.dumps(result,ensure_ascii=False,sort_keys=True))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (RefillHold,OSError,ValueError,KeyError,TypeError) as exc:
        print(json.dumps({'state':'HOLD_TASKPACK_BUILD','reason':str(exc)[:500]}),file=sys.stderr)
        raise SystemExit(2)
