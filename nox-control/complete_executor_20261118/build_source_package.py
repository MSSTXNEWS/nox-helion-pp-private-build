#!/usr/bin/env python3
"""Build the pinned incremental package. Does not contact the native server."""
from pathlib import Path
import ast
import difflib
import hashlib
import json
import shutil

BASE = Path(__file__).resolve().parent
WORK = BASE.parent
OUT = BASE/'source_package'
ENTRY = 'nox-control/owner_complete_executor_install.py'
INSPECT = 'nox-control/owner_complete_executor_observe.py'
PREFIX = 'nox-control/complete_executor_20261118/'
NATIVE_ROOT = '/root/nox'
PACKAGE_ROOT = NATIVE_ROOT+'/state/dispatcher/project_executor/package'
SOURCE_ROOT = NATIVE_ROOT+'/projects/owner_executor/source_workspace'
LEGACY = '88af9c11d54e084ccb868c474d17c2a85511600a0ff6578bfe5490b437fe554e'


def sha(raw): return hashlib.sha256(raw).hexdigest()
def encoded(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def write(relative,raw):
    path=OUT/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)


def main():
    environment=json.loads((BASE/'native/native_executor_environment.json').read_text())
    planner=json.loads((BASE/'planner/manifest.json').read_text())
    runtime_manifest=json.loads((BASE/'runtime/manifest.json').read_text())
    seed=json.loads((BASE/'bindings/seed_manifest.json').read_text())
    plans=json.loads((BASE/'bindings/plans_index.json').read_text())
    raw_assets={};runtime_paths={};package_files={}

    def asset(raw,kind,suffix):
        pin=sha(raw);name='ce_'+kind+'_'+pin[:20]+suffix
        if name in raw_assets:assert raw_assets[name]==raw
        raw_assets[name]=raw;write(PREFIX+'assets/'+name,raw)
        return name

    names=('owner_autonomy_pool.py','owner_subagent_dispatcher.py','owner_subagent_processes.py',
           'owner_project_executor.py','owner_project_test_runner.py','owner_project_native.py')
    runtime={name:(BASE/'runtime'/name).read_bytes() for name in names}
    for name,raw in runtime.items():assert sha(raw)==runtime_manifest['files'][name]['sha256']
    policy=(BASE/'runtime/owner_resource_policy.py').read_bytes()
    if sha(policy)!=environment['expected_native']['scripts/owner_resource_policy.py']:
        runtime['owner_resource_policy.py']=policy
    for name,pin in planner['source_pins'].items():
        raw=(BASE/'planner'/name).read_bytes();assert sha(raw)==pin
        runtime[name]=raw
    callback=sha(runtime['owner_subagent_dispatcher.py'])
    wrapper=(WORK/'queue_work/native_leaf/owner_subagent_instruction_truth_four_queue.py').read_bytes()
    current_callback=environment['expected_native']['scripts/owner_subagent_dispatcher.py']
    assert wrapper.count(LEGACY.encode())==1
    wrapper=wrapper.replace(LEGACY.encode(),current_callback.encode())
    assert sha(wrapper)==environment['expected_native']['scripts/owner_subagent_instruction_truth.py']
    assert wrapper.count(current_callback.encode())==1
    runtime['owner_subagent_instruction_truth.py']=wrapper.replace(current_callback.encode(),callback.encode())
    assert sha(runtime['owner_subagent_instruction_truth.py'])==runtime_manifest['files']['owner_subagent_instruction_truth_project.py']['sha256']
    for name,raw in runtime.items():
        compile(raw,name,'exec');runtime_paths[asset(raw,'runtime','.py')]='scripts/'+name
        write(PREFIX+'runtime/'+name,raw)

    files={};baseline_pins={};source_refs=[]
    for row in seed['files']:
        raw=(BASE/'bindings/minimal_project_source'/row['path']).read_bytes()
        assert sha(raw)==row['sha256']
        files[row['path']]=asset(raw,'baseline','.source')
        baseline_pins[row['path']]=row['sha256']
        reference=row.get('source') or {}
        if reference.get('ref') and reference['ref'] not in source_refs:source_refs.append(reference['ref'])
        write(PREFIX+'source_baseline/'+row['path'],raw)
    source_refs=[{'repository':'https://gitlab.com/s-grouptwet/nox-helion-pp-private-build',
                  'commit':ref} for ref in sorted(source_refs)]
    baseline_manifest={'schema':'NOX_PROJECT_SOURCE_BASELINE_V1','files':baseline_pins,'source_refs':source_refs}
    seed_spec={'schema':'NOX_PROJECT_SOURCE_BOOTSTRAP_V1','root':SOURCE_ROOT,
               'files':files,'source_refs':source_refs,'manifest_sha256':sha(encoded(baseline_manifest))}

    def package(kind,pin,raw):
        assert sha(raw)==pin
        relative=kind+'/'+pin+('.json' if kind!='blobs' else '')
        package_files[relative]=asset(raw,kind,'.json' if kind!='blobs' else '.source')
        write(PREFIX+'package/'+relative,raw)

    for plan_row in plans:
        raw=Path(plan_row['plan_path']).read_bytes();package('plans',plan_row['plan_sha256'],raw)
        value=json.loads(raw)
        assert value['original_task_accepted'] is False
        for changed in value['files']:
            pin=changed['payload_sha256'];package('blobs',pin,(BASE/'bindings/blobs'/pin).read_bytes())
        for context in value['context']:
            assert baseline_pins[context['path']]==context['sha256']
    contract_raw=Path(planner['contract_path']).read_bytes()
    package('contracts',planner['contract_sha256'],contract_raw)
    contract=json.loads(contract_raw)
    for context in contract['context']:assert baseline_pins[context['path']]==context['sha256']
    dependencies=environment['dependency_manifest']
    dependency_raw=encoded(dependencies);dependency_pin=sha(dependency_raw)
    package('manifests',dependency_pin,dependency_raw)
    disposition=(BASE/'bindings/all295_execution_disposition.json').read_bytes()
    package('manifests',sha(disposition),disposition)

    project={'schema':'NOX_PROJECT_EXECUTOR_CONFIG_V1','enabled':True,'max_workers':3,
        'package_root':PACKAGE_ROOT,'state_root':NATIVE_ROOT+'/state/dispatcher/project_executor/run',
        'roots':{'NOX_PROJECT_SOURCE':{'path':SOURCE_ROOT,'integration_kind':'SOURCE_WORKSPACE',
                                    'allowed_paths':sorted(files),'deny_paths':[]}},
        'sandbox':environment['sandbox'],
        'source_pins':{name:sha(runtime[name]) for name in ('owner_project_executor.py','owner_project_test_runner.py')},
        'model':planner['model'],
        'dependency_manifest':{'path':PACKAGE_ROOT+'/manifests/'+dependency_pin+'.json','sha256':dependency_pin}}
    catalog=[]
    for row in plans:
        catalog.append({'id':row['task_id'],'handler':'owner_native_project_work',
            'queue_id':row['queue_id'],'source_sha256':callback,'deps':row.get('deps',[]),
            'priority':'P1','resource':'CPU_LIGHT','estimated_cost':1,
            'title':row['purpose'],
            'params':{'parent_task_id':row['parent_task_id'],'plan_sha256':row['plan_sha256']}})
    catalog.insert(0,{'id':contract['task_id'],'handler':'owner_native_project_work',
        'queue_id':contract['queue_id'],'source_sha256':callback,'deps':[],
        'priority':'P1','resource':'CPU_LIGHT','estimated_cost':2,
        'title':'Implement request cursor admission through existing local NOX model and protected source tests',
        'params':{'parent_task_id':contract['parent_task_id'],'contract_sha256':planner['contract_sha256']}})
    assert {row['queue_id'] for row in catalog}=={
        'Q1_RUNTIME_CHAT','Q2_MEMORY_KNOWLEDGE','Q3_TRAINING_WEIGHTS','Q4_INTEGRATION_ACCEPTANCE'}
    specification={'schema':'NOX_COMPLETE_EXECUTOR_INSTALL_SPEC_V1',
        'assets':{name:sha(raw) for name,raw in raw_assets.items()},
        'runtime_paths':runtime_paths,'package_files':package_files,
        'expected_native':environment['expected_native'],
        'protected_processes':environment['protected_processes'],
        'source_bootstrap':seed_spec,'catalog_append':catalog,'project_executor':project,
        'startup_observe_seconds':45}
    template=(BASE/'native/owner_complete_executor_install.py').read_text()
    assert template.count('SPEC = {}')==1
    template=template.replace('SPEC = {}','SPEC = '+repr(specification))
    compile(template,ENTRY,'exec');write(ENTRY,template.encode())
    write(INSPECT,(BASE/'owner_complete_executor_observe.py').read_bytes())
    write(PREFIX+'install_spec.json',json.dumps(specification,indent=2).encode()+b'\n')
    original=(BASE/'native/owner_native_operator_current.py').read_text()
    old="'repair':'nox-control/owner_post_reset_state_observe.py'"
    assert original.count(old)==1
    operator=original.replace(old,"'repair':"+repr(ENTRY))
    assert operator.count("'inspect':'nox-control/owner_native_inspect.py'")==1
    operator=operator.replace("'inspect':'nox-control/owner_native_inspect.py'","'inspect':"+repr(INSPECT))
    operator=operator.replace('SCOPED_REPAIR_BUNDLES={\n',
        'SCOPED_REPAIR_BUNDLES={\n    '+repr(ENTRY)+':'+repr(tuple(raw_assets))+',\n',1)
    operator=operator.replace('SCOPED_REPAIR_EXTRA_PATHS={\n',
        'SCOPED_REPAIR_EXTRA_PATHS={\n    '+repr(ENTRY)+':'+repr(tuple(PREFIX+'assets/'+n for n in raw_assets))+',\n',1)
    before,after=ast.parse(original),ast.parse(operator);assert len(before.body)==len(after.body)
    changed=[]
    for a,b in zip(before.body,after.body):
        if ast.dump(a)!=ast.dump(b):
            assert isinstance(a,ast.Assign) and a.targets[0].id in {
                'FILES','SCOPED_REPAIR_BUNDLES','SCOPED_REPAIR_EXTRA_PATHS'}
            changed.append(a.targets[0].id)
    assert len(changed)==3
    static_names={Path(node.value).name for node in ast.walk(before)
        if isinstance(node,ast.Constant) and isinstance(node.value,str)
        and node.value.startswith(('nox-control/','coordination/'))}
    assert not set(raw_assets)&static_names
    write('nox-control/owner_native_operator.py',operator.encode())
    (BASE/'operator_transport.diff').write_text(''.join(difflib.unified_diff(
        original.splitlines(True),operator.splitlines(True),fromfile='before',tofile='after')))
    extras=[BASE/'planner/manifest.json',BASE/'bindings/seed_manifest.json',
        BASE/'bindings/plans_index.json',BASE/'bindings/all295_execution_disposition.json',
        BASE/'bindings/local_fail_pass.json',BASE/'native/native_executor_environment.json']
    for path in extras:write(PREFIX+'evidence/'+path.name,path.read_bytes())
    write(PREFIX+'evidence/runtime_manifest.json',(BASE/'runtime/manifest.json').read_bytes())
    write(PREFIX+'evidence/installer_local_qa.json',(BASE/'native/installer_local_qa.json').read_bytes())
    write(PREFIX+'REVIEWED_SOURCE_FIXES.md',(BASE/'bindings/REPORT.md').read_bytes())
    write(PREFIX+'RUNTIME_CONTRACT.md',(BASE/'runtime/README.md').read_bytes())
    write(PREFIX+'build_source_package.py',Path(__file__).read_bytes())
    for directory in ('planner','runtime','native'):
        for path in (BASE/directory).glob('test_*.py'):write(PREFIX+'tests/'+path.name,path.read_bytes())
    record=[]
    for path in sorted(OUT.rglob('*')):
        if not path.is_file():continue
        raw=path.read_bytes()
        record.append({'path':str(path.relative_to(OUT)),'bytes':len(raw),'sha256':sha(raw),
            'git_blob':hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()})
    (BASE/'source_package_manifest.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps({'files':len(record),'assets':len(raw_assets),'source_bytes':sum(r['bytes'] for r in record),
        'catalog_appended':len(catalog),'queues':sorted({r['queue_id'] for r in catalog}),
        'callback_sha256':callback,'source_baseline':seed_spec['manifest_sha256'],
        'operator_changed_assignments':changed,'original_tasks_accepted':0}))


if __name__=='__main__':main()
