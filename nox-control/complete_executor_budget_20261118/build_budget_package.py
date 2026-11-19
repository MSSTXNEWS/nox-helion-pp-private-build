"""Assemble the pinned bounded CPU policy correction; no native writes."""
from pathlib import Path
import ast
import base64
import hashlib
import importlib.util
import json

BASE=Path(__file__).resolve().parent
OUT=BASE/'source_package'
PREFIX='nox-control/complete_executor_budget_20261118/'
ENTRY='nox-control/owner_bounded_cpu_install.py'

def sha(raw):return hashlib.sha256(raw).hexdigest()
def encoded(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def write(relative,raw):
    path=OUT/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)

def main():
    manifest_path=BASE/'runtime_budget_fix/manifest.json'
    assert sha(manifest_path.read_bytes())=='426eea7632fc35112abfa4ee6ebae35babb012c435bcbf4d129aa1ff5983e719'
    manifest=json.loads(manifest_path.read_text())
    before_raw=(BASE/'native/current_config_6966949947.json').read_bytes()
    expected=json.loads((BASE/'native/expected_native_before_budget.json').read_text())
    assert sha(before_raw)==expected['config/owner_native_subagents.json']
    current=json.loads(before_raw);assets={};runtime_paths={}
    for filename,row in manifest['files'].items():
        raw=(BASE/'runtime_budget_fix'/filename).read_bytes();assert sha(raw)==row['sha256']
        relative=str(Path(row['native_path']).relative_to('/root/nox'))
        assert expected[relative]==row['before_sha256']
        name='bc_runtime_'+row['sha256'][:20]+'.py';assets[name]=raw;runtime_paths[name]=relative
        write(PREFIX+'assets/'+name,raw);write(PREFIX+'runtime/'+Path(relative).name,raw)
    for name,pin in manifest['unchanged_current_runtime'].items():
        assert expected['scripts/'+name]==pin
    installed=json.loads((BASE/'install_receipt_6966579330.json').read_text())['COMPLETE_EXECUTOR_INSTALL']
    spec={'schema':'NOX_BOUNDED_CPU_POLICY_INSTALL_SPEC_V1',
        'assets':{name:sha(raw) for name,raw in assets.items()},'runtime_paths':runtime_paths,
        'expected_native':expected,'expected_director':{'pid':3748557,'start_ticks':176081802},
        'expected_no_children':True,'protected_processes':installed['protected_processes'],
        'rebind_task_ids':[row['id'] for row in current['catalog']['tasks'][15:]]}
    entry_path=BASE/'native/owner_bounded_cpu_install.py';template=entry_path.read_text()
    assert sha(template.encode())=='89581d0fb8b571c99db3305c2a6b97e2758a431b273281ef8c6072d7f18a12b9'
    assert template.count('SPEC = {}')==1
    source=template.replace('SPEC = {}','SPEC = '+repr(spec));compile(source,ENTRY,'exec');write(ENTRY,source.encode())
    write(PREFIX+'budget_spec.json',json.dumps(spec,indent=2).encode()+b'\n')
    loader=importlib.util.spec_from_file_location('approved_budget_builder',entry_path)
    module=importlib.util.module_from_spec(loader);loader.loader.exec_module(module)
    bundle={name:base64.b64encode(raw).decode() for name,raw in assets.items()}
    runtime=module.budget_assets(bundle,spec);old,new=module.compose_budget_config(before_raw,runtime,spec)
    assert old['catalog']['tasks'][:15]==new['catalog']['tasks'][:15]
    assert old['project_executor']==new['project_executor']
    proposed=encoded(new);(BASE/'native/proposed_config_budget.json').write_bytes(proposed)
    qa={'schema':'NOX_BUDGET_PACKAGE_LOCAL_QA_V1','assets':4,'old_config_sha256':sha(before_raw),
        'proposed_config_sha256':sha(proposed),'old_catalog_rows_preserved':15,
        'unadmitted_rows_rebound':4,'source_workspace_writes':0,'model_executor_config_unchanged':True,
        'native_admission_not_yet_verified':True}
    (BASE/'budget_package_local_qa.json').write_text(json.dumps(qa,indent=2)+'\n')
    write(PREFIX+'evidence/budget_package_local_qa.json',json.dumps(qa,indent=2).encode()+b'\n')
    operator_path=OUT/'nox-control/owner_native_operator.py';baseline=BASE/'operator_before_budget_update.py'
    if not baseline.exists():baseline.write_bytes(operator_path.read_bytes())
    original=baseline.read_text()
    old_route="'repair':'nox-control/owner_project_runtime_update.py'"
    old_inspect="'inspect':'nox-control/owner_project_update_history_observe.py'"
    assert original.count(old_route)==original.count(old_inspect)==1
    operator=original.replace(old_route,"'repair':"+repr(ENTRY)).replace(
        old_inspect,"'inspect':'nox-control/owner_complete_executor_observe.py'")
    operator=operator.replace('SCOPED_REPAIR_BUNDLES={\n',
        'SCOPED_REPAIR_BUNDLES={\n    '+repr(ENTRY)+':'+repr(tuple(assets))+',\n',1)
    operator=operator.replace('SCOPED_REPAIR_EXTRA_PATHS={\n',
        'SCOPED_REPAIR_EXTRA_PATHS={\n    '+repr(ENTRY)+':'+repr(tuple(PREFIX+'assets/'+n for n in assets))+',\n',1)
    a,b=ast.parse(original),ast.parse(operator);assert len(a.body)==len(b.body);changed=[]
    for left,right in zip(a.body,b.body):
        if ast.dump(left)!=ast.dump(right):
            assert isinstance(left,ast.Assign) and left.targets[0].id in {'FILES','SCOPED_REPAIR_BUNDLES','SCOPED_REPAIR_EXTRA_PATHS'}
            changed.append(left.targets[0].id)
    assert len(changed)==3;write('nox-control/owner_native_operator.py',operator.encode())
    for path in (manifest_path,BASE/'runtime_budget_fix/qa.json',BASE/'runtime_budget_fix/recorded_budget_replay.json',
        BASE/'runtime_budget_fix/bounded_cpu_budget.patch',BASE/'bindings/resource_admission_review/budget_source_review.json',
        BASE/'bindings/resource_admission_review/history_scope_review.json'):
        write(PREFIX+'evidence/'+path.name,path.read_bytes())
    for path in (entry_path,BASE/'native/budget_policy_update_body.py',BASE/'native/build_bounded_cpu_entry.py',
        BASE/'native/test_owner_bounded_cpu_install.py',BASE/'native/runtime_update_history_inspect.py',
        BASE/'runtime_budget_fix/test_owner_bounded_cpu_budget.py'):
        write(PREFIX+'reviewed/'+path.name,path.read_bytes())
    write(PREFIX+'build_budget_package.py',Path(__file__).read_bytes())
    # This observation contains only bounded sanitized queue/receipt metadata.
    write(PREFIX+'evidence/history_observe_134528655335.json',(BASE/'history_observe_134528655335.json').read_bytes())
    records=[]
    for path in sorted(OUT.rglob('*')):
        if path.is_file():
            raw=path.read_bytes();records.append({'path':str(path.relative_to(OUT)),'bytes':len(raw),'sha256':sha(raw),
                'git_blob':hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()})
    (BASE/'source_package_manifest.json').write_text(json.dumps(records,indent=2)+'\n')
    print(json.dumps({'files':len(records),'assets':4,'runtime':list(runtime),'proposed_config_sha256':sha(proposed),
        'operator_assignments':changed,'native_mutations':0}))

if __name__=='__main__':main()
