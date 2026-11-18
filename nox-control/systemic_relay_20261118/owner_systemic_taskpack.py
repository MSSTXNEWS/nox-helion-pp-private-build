"""Compile a grounded, reviewed next batch for the existing fenced NOX publisher.

Usage: owner_systemic_taskpack.py --previous-manifest FILE --previous-sha256 SHA
  --proposal FILE --source-census FILE --registry FILE --review FILE --output DIR

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
import stat
import sys

sys.path.insert(0,str(Path(__file__).parent / 'runtime'))
from owner_systemic_refill import (SCHEMA, RefillHold, canonical, digest, require,
                                   validate_manifest, _contract, _input, SHA)

PROPOSAL_SCHEMA = 'NOX_SYSTEMIC_GROUNDED_PROPOSALS_V1'
REVIEW_SCHEMA = 'NOX_SYSTEMIC_TASKPACK_REVIEW_V1'
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


def parent_registry(disposition):
    require(isinstance(disposition,dict) and disposition.get('total_original_ids') == 295,
            'REGISTRY_ORIGINAL_COUNT')
    tasks = disposition.get('tasks')
    require(isinstance(tasks,list) and len(tasks) == 295,'REGISTRY_ORIGINAL_ROWS')
    parents = {}
    for row in tasks:
        require(isinstance(row,dict) and row.get('task_id') not in parents,'REGISTRY_DUPLICATE')
        spec = row.get('spec')
        require(isinstance(spec,dict) and spec.get('id') == row.get('task_id')
                and hashlib.sha256(canonical(spec)).hexdigest() == row.get('spec_sha256'),
                'REGISTRY_SPEC_PIN')
        parents[row['task_id']] = {'spec_sha256':row['spec_sha256'],'queue_id':row['queue_id'],
            'required_evidence':spec['evidence'],'title':spec['title']}
    return {'total_original_ids':295,'source_registry_sha256':deepcopy(disposition['source_registry_sha256']),
            'parents':parents}


def bind_missions(proposals, roots, registry):
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
        missions.append(mission)
    return missions


def compile_taskpack(previous, previous_sha, proposal, proposal_sha, census, census_sha,
                     disposition, review):
    validate_manifest(previous)
    require(isinstance(proposal,dict) and proposal.get('schema') == PROPOSAL_SCHEMA
            and proposal.get('previous_manifest_sha256') == previous_sha,'PROPOSAL_PREDECESSOR')
    require(isinstance(census,dict) and census.get('schema') == 'NOX_SYSTEMIC_SOURCE_CENSUS_V1'
            and isinstance(census.get('roots'),dict),'SOURCE_CENSUS')
    require(isinstance(review,dict) and review.get('schema') == REVIEW_SCHEMA
            and review.get('review_origin') == 'OWNER_REVIEWED'
            and review.get('proposal_sha256') == proposal_sha
            and review.get('source_census_sha256') == census_sha
            and review.get('previous_manifest_sha256') == previous_sha
            and review.get('original_task_accepted') is False,'EXACT_REVIEW_RECEIPT')
    registry = parent_registry(disposition)
    require(registry['source_registry_sha256'] == previous['registry']['source_registry_sha256'],
            'REGISTRY_CHANGED_NEEDS_OWNER_REVIEW')
    missions = bind_missions(proposal.get('missions'),census['roots'],registry)
    old = {(row['mission_id'],row['revision']) for row in previous['missions']}
    require(not old.intersection((row['mission_id'],row['revision']) for row in missions),
            'MISSION_REVISION_ALREADY_PUBLISHED')
    # Replace the active small batch; pinned ancestry retains previous durable bindings.
    manifest = {'schema':SCHEMA,'revision':previous['revision']+1,
        'previous_manifest_sha256':previous_sha,'review_origin':'OWNER_REVIEWED',
        'acceptance_scope':'SOURCE_PATCH_TESTED','original_task_accepted':False,
        'registry':registry,'missions':missions,
        'research_topics':deepcopy(proposal.get('research_topics',previous.get('research_topics',[]))),
        'intent_sources':deepcopy(previous.get('intent_sources',[])),
        'producer_evidence':{'proposal_sha256':proposal_sha,'source_census_sha256':census_sha,
                             'review_sha256':digest(review),'refill_request_id':proposal.get('request_id')}}
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
    for option in ('previous-manifest','previous-sha256','proposal','source-census','registry','review','output'):
        parser.add_argument('--'+option,required=True)
    for option in ('publisher-checkpoint','publisher-template','transaction-helper'):
        parser.add_argument('--'+option)
    args = parser.parse_args()
    # Reject invalid publisher arguments before writing any local publish request.
    publisher_args = (args.publisher_checkpoint,args.publisher_template,args.transaction_helper)
    require(not any(publisher_args) or all(publisher_args),'PUBLISHER_ARGUMENTS')
    previous,previous_sha = read_document(args.previous_manifest)
    require(previous_sha == args.previous_sha256,'PREVIOUS_MANIFEST_PIN')
    proposal,proposal_sha = read_document(args.proposal)
    census,census_sha = read_document(args.source_census)
    disposition,_ = read_document(args.registry)
    review,_ = read_document(args.review)
    checkpoint = None
    if all(publisher_args):
        checkpoint,_ = read_document(args.publisher_checkpoint)
        require(checkpoint.get('expected_source_files_sha256') == census.get('observed_files_sha256'),
                'PUBLISH_CENSUS_PIN')
    manifest = compile_taskpack(previous,previous_sha,proposal,proposal_sha,census,census_sha,disposition,review)
    result = write_package(manifest,args.output,previous_sha=previous_sha)
    if checkpoint is not None:
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
