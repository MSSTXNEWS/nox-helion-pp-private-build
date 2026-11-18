"""Build an additive reviewed runtime update; never contacts the native host."""
from pathlib import Path
import ast
import hashlib
import json

BASE=Path(__file__).resolve().parent
OUT=BASE/'source_package'
PREFIX='nox-control/complete_executor_retries_20261118/'
ENTRY='nox-control/owner_project_runtime_update.py'

def sha(raw):return hashlib.sha256(raw).hexdigest()
def encoded(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def write(relative,raw):
    target=OUT/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)

def main():
    assets={};runtime_paths={};package_files={}
    def asset(raw,kind):
        name='ru_'+kind+'_'+sha(raw)[:20]+('.py' if kind=='runtime' else '.data')
        assert name not in assets or assets[name]==raw
        assets[name]=raw;write(PREFIX+'assets/'+name,raw)
        return name
    def package(directory,pin,raw):
        assert sha(raw)==pin
        suffix='' if directory=='blobs' else '.json'
        relative=directory+'/'+pin+suffix
        package_files[relative]=asset(raw,directory)
        write(PREFIX+'package/'+relative,raw)

    expected=json.loads((BASE/'native/expected_native_before_retries.json').read_text())
    old=json.loads((BASE/'native/current_config_6966579330.json').read_text())
    assert sha(encoded(old))==expected['config/owner_native_subagents.json']
    callback=old['module_pins']['owner_subagent_dispatcher.py']
    sandbox_manifest=json.loads((BASE/'runtime_sandbox_fix/manifest.json').read_text())
    for name in ('owner_project_executor.py','owner_project_test_runner.py'):
        raw=(BASE/'runtime_sandbox_fix'/name).read_bytes()
        assert sha(raw)==sandbox_manifest['files'][name]['sha256']
        assert sha(raw)!=expected['scripts/'+name]
        runtime_paths[asset(raw,'runtime')]='scripts/'+name
        write(PREFIX+'runtime/'+name,raw)
    planner=json.loads((BASE/'planner/manifest.json').read_text())
    for name,pin in planner['source_pins'].items():
        raw=(BASE/'planner'/name).read_bytes();assert sha(raw)==pin
        if pin!=expected['scripts/'+name]:runtime_paths[asset(raw,'runtime')]='scripts/'+name
        write(PREFIX+'runtime/'+name,raw)

    catalog=json.loads((BASE/'bindings/retries/catalog_append_template.json').read_text())
    index=json.loads((BASE/'bindings/retries/retry_plans_index.json').read_text())
    retry_of={r['task_id']:r['retry_of'] for r in index}
    for row in catalog:row['source_sha256']=callback
    for row in index:
        path=Path(row['plan_path']);raw=path.read_bytes();package('plans',row['plan_sha256'],raw)
        plan=json.loads(raw)
        for changed in plan['files']:
            pin=changed['payload_sha256'];package('blobs',pin,(path.parent.parent/'blobs'/pin).read_bytes())
    contract_raw=Path(planner['contract_path']).read_bytes();contract=json.loads(contract_raw)
    package('contracts',planner['contract_sha256'],contract_raw)
    catalog.append({'id':contract['task_id'],'handler':'owner_native_project_work',
        'queue_id':contract['queue_id'],'source_sha256':callback,'deps':[],
        'priority':'P1','resource':'CPU_LIGHT','estimated_cost':2,
        'title':'Implement request cursor admission using current focused source and protected tests',
        'params':{'parent_task_id':'1A03','contract_sha256':planner['contract_sha256']}})
    retry_of[contract['task_id']]=contract['retry_of']
    observed=json.loads((BASE/'observe_134519118144.json').read_text())
    terminal={r['data']['id']:r['data']['result']['receipt_sha256'] for r in observed
        if r['kind']=='PROJECT_EXECUTION' and r['data']['id'] in retry_of.values()}
    assert len(terminal)==4
    for row in observed:
        if row['kind']=='PROJECT_EXECUTION' and row['data']['id'] in terminal:
            value=row['data'];assert value['status']=='blocked'
            assert value['receipt_sha_matches'] and value['receipt_claim_matches'] and value['s03']['verified']
    installed=json.loads((BASE/'install_receipt_6966579330.json').read_text())['COMPLETE_EXECUTOR_INSTALL']
    protected=installed['protected_processes']
    spec={'schema':'NOX_PROJECT_RUNTIME_UPDATE_SPEC_V1',
        'assets':{name:sha(raw) for name,raw in assets.items()},
        'runtime_paths':runtime_paths,'package_files':package_files,'expected_native':expected,
        'expected_director':{'pid':3734446,'start_ticks':175943736},
        'expected_workers':[{'pid':pid,'start_ticks':175944600} for pid in (3734568,3734569,3734570)],
        'protected_processes':protected,'catalog_append':catalog,'retry_of':retry_of,
        'terminal_receipts':terminal,'wait_for_idle_seconds':40}
    entry=(BASE/'native/owner_project_runtime_update.py').read_text()
    assert entry.count('SPEC = {}')==1
    entry=entry.replace('SPEC = {}','SPEC = '+repr(spec));compile(entry,ENTRY,'exec')
    write(ENTRY,entry.encode());write(PREFIX+'update_spec.json',json.dumps(spec,indent=2).encode()+b'\n')
    operator_path=OUT/'nox-control/owner_native_operator.py'
    baseline=BASE/'operator_before_retry_update.py'
    if not baseline.exists():baseline.write_bytes(operator_path.read_bytes())
    original=baseline.read_text()
    old_route="'repair':'nox-control/owner_complete_executor_install.py'"
    assert original.count(old_route)==1
    operator=original.replace(old_route,"'repair':"+repr(ENTRY))
    operator=operator.replace('SCOPED_REPAIR_BUNDLES={\n',
        'SCOPED_REPAIR_BUNDLES={\n    '+repr(ENTRY)+':'+repr(tuple(assets))+',\n',1)
    operator=operator.replace('SCOPED_REPAIR_EXTRA_PATHS={\n',
        'SCOPED_REPAIR_EXTRA_PATHS={\n    '+repr(ENTRY)+':'+repr(tuple(PREFIX+'assets/'+n for n in assets))+',\n',1)
    before,after=ast.parse(original),ast.parse(operator)
    assert len(before.body)==len(after.body)
    changed=[]
    for a,b in zip(before.body,after.body):
        if ast.dump(a)!=ast.dump(b):
            assert isinstance(a,ast.Assign) and a.targets[0].id in {'FILES','SCOPED_REPAIR_BUNDLES','SCOPED_REPAIR_EXTRA_PATHS'}
            changed.append(a.targets[0].id)
    assert len(changed)==3
    write('nox-control/owner_native_operator.py',operator.encode())
    write(PREFIX+'build_retry_package.py',Path(__file__).read_bytes())
    for directory,filename in (
        ('native','owner_project_runtime_update.py'),('native','runtime_update_body.py'),
        ('native','build_runtime_update_entry.py'),('native','test_owner_project_runtime_update.py'),
        ('native','owner_project_catalog_append.py'),('native','test_owner_project_catalog_append.py'),
        ('planner','test_owner_project_planner.py'),('planner','test_owner_project_model_bridge.py')):
        write(PREFIX+'reviewed/'+filename,(BASE/directory/filename).read_bytes())
    for path in (
        BASE/'runtime_sandbox_fix/manifest.json',BASE/'runtime_sandbox_fix/READY.json',
        BASE/'runtime_sandbox_fix/layout_retry_final_validation.json',
        BASE/'runtime_sandbox_fix/fd_plan_validation.json',BASE/'runtime_sandbox_fix/model30_final_validation.json',
        BASE/'planner/focus_retry_review.json',BASE/'bindings/model_focus/independent_focus_retry_review.json',
        BASE/'bindings/retries/6V14-04/local_proof.json',BASE/'bindings/retries/6V14-04/fixture_revision.json',
        BASE/'bindings/retries/6V14-04/fixture_revision.patch',BASE/'bindings/retries/retry_plans_index.json'):
        write(PREFIX+'evidence/'+path.name,path.read_bytes())
    for path in (BASE/'native/runtime_update_local_qa.json',BASE/'bindings/runtime_update_review/review.json',
                 BASE/'retry_package_local_qa.json'):
        write(PREFIX+'evidence/'+path.name,path.read_bytes())
    write(PREFIX+'evidence/planner_manifest.json',(BASE/'planner/manifest.json').read_bytes())
    write(PREFIX+'evidence/native_update_predecessors.json',json.dumps(
        [r for r in observed if r['kind']=='PROJECT_EXECUTION'],indent=2).encode()+b'\n')
    rows=[]
    for path in sorted(OUT.rglob('*')):
        if not path.is_file():continue
        raw=path.read_bytes();rows.append({'path':str(path.relative_to(OUT)),'bytes':len(raw),'sha256':sha(raw),
            'git_blob':hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()})
    (BASE/'source_package_manifest.json').write_text(json.dumps(rows,indent=2)+'\n')
    print(json.dumps({'files':len(rows),'runtime_files':list(runtime_paths.values()),
        'assets':len(assets),'catalog_append':len(catalog),'operator_assignments':changed,'native_source_writes':0}))

if __name__=='__main__':main()
