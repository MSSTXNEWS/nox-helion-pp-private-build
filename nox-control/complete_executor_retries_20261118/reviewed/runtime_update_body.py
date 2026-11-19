UPDATE_SCHEMA = 'NOX_PROJECT_RUNTIME_UPDATE_SPEC_V1'
SANDBOX_MODULES = frozenset({'owner_project_executor.py','owner_project_test_runner.py'})
MODEL_MODULES = frozenset({'owner_project_planner.py','owner_project_model_client.py','owner_project_model_bridge.py'})
UPDATE_MODULES = SANDBOX_MODULES | MODEL_MODULES
RETRY_PARENTS = frozenset({'1A03','3A02','3B05','6V14-04'})

def decode_update_assets(bundle, specification):
    require(specification.get('schema')==UPDATE_SCHEMA,'UPDATE_SPEC_SCHEMA')
    expected=specification.get('assets')
    require(isinstance(expected,dict) and 1<=len(expected)<=64 and set(bundle)==set(expected),'UPDATE_BUNDLE_FILESET')
    assets={};total=0
    for name,pin in expected.items():
        require(isinstance(name,str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,160}',name)
                and SHA.fullmatch(str(pin)),'UPDATE_ASSET_NAME_PIN')
        value=bundle[name];require(isinstance(value,str) and len(value)<=4*1024*1024,'UPDATE_ASSET_BOUND')
        raw=base64.b64decode(value,validate=True);total+=len(raw)
        require(len(raw)<=2*1024*1024 and total<=16*1024*1024 and digest(raw)==pin,'UPDATE_ASSET_DIGEST')
        assets[name]=raw
    paths=specification.get('runtime_paths')
    require(isinstance(paths,dict) and 2<=len(paths)<=5,'UPDATE_RUNTIME_SET')
    runtime={}
    for name,relative in paths.items():
        require(name in assets and relative=='scripts/'+Path(relative).name
                and Path(relative).name in UPDATE_MODULES and relative not in runtime,'UPDATE_RUNTIME_PATH')
        compile(assets[name],Path(relative).name,'exec');runtime[relative]=assets[name]
    require({'scripts/'+name for name in SANDBOX_MODULES}<=runtime.keys(),'UPDATE_SANDBOX_REQUIRED')
    return assets,runtime

def validate_append_row(row,known,callback):
    required={'id','handler','deps','resource','source_sha256','params','queue_id'}
    require(isinstance(row,dict) and required<=row.keys()
            and not row.keys()-(required|{'priority','title','estimated_cost'}),'UPDATE_ROW_FIELDS')
    tid=row['id'];params=row['params'];deps=row['deps'];cost=row.get('estimated_cost',1)
    require(isinstance(tid,str) and IDENT.fullmatch(tid) and tid not in known
            and row['handler']==PROJECT_HANDLER and row['source_sha256']==callback
            and row['queue_id'] in QUEUE_IDS and row['resource']=='CPU_LIGHT','UPDATE_ROW_SCOPE')
    require(isinstance(params,dict) and params.get('parent_task_id') in RETRY_PARENTS
            and tid.startswith(params['parent_task_id']+'.'),'UPDATE_ROW_PARENT')
    field='contract_sha256' if params['parent_task_id']=='1A03' else 'plan_sha256'
    require(set(params)=={'parent_task_id',field} and SHA.fullmatch(str(params[field])),'UPDATE_ROW_REFERENCE')
    require(isinstance(deps,list) and all(isinstance(x,str) and IDENT.fullmatch(x) for x in deps)
            and len(deps)==len(set(deps)) and tid not in deps,'UPDATE_ROW_DEPS')
    require(row.get('priority','P2') in ('P0','P1','P2','P3') and type(cost) in (int,float)
            and math.isfinite(cost) and 0<cost<=100000 and isinstance(row.get('title',tid),str)
            and 1<=len(row.get('title',tid))<=180,'UPDATE_ROW_PRESENTATION')

def compose_update(raw,runtime,specification,root):
    current=json.loads(raw)
    require(current.get('schema')=='NOX_NATIVE_SUBAGENT_BINDING_V1' and current.get('instance_id')==60509551
            and current.get('execution_mode')=='NATIVE_PROJECT_V1' and current.get('owner_authorized') is True
            and current.get('mode')=='NORMAL' and current.get('target')==3 and current.get('global_worker_cap')==3,
            'UPDATE_CURRENT_CONFIG')
    project=current.get('project_executor') or {}
    require(project.get('schema')=='NOX_PROJECT_EXECUTOR_CONFIG_V1' and project.get('enabled') is True
            and project.get('max_workers')==3 and project.get('package_root')==str(Path(root)/'state/dispatcher/project_executor/package')
            and project.get('state_root')==str(Path(root)/'state/dispatcher/project_executor/run')
            and project.get('roots',{}).get('NOX_PROJECT_SOURCE',{}).get('path')==str(Path(root)/'projects/owner_executor/source_workspace'),
            'UPDATE_PROJECT_CONFIG')
    catalog=current.get('catalog') or {};old=catalog.get('tasks')
    require(catalog.get('schema')=='NOX_AUTONOMY_PROCESS_POOL_V1' and isinstance(old,list)
            and digest(encoded(catalog))==current.get('catalog_sha256'),'UPDATE_CATALOG_HASH')
    known={row['id'] for row in old};require(len(known)==len(old),'UPDATE_OLD_DUPLICATE')
    callback=current.get('module_pins',{}).get('owner_subagent_dispatcher.py')
    require(callback==specification['expected_native'].get('scripts/owner_subagent_dispatcher.py')
            and SHA.fullmatch(str(callback)),'UPDATE_CALLBACK_PIN')
    new=specification.get('catalog_append');retry=specification.get('retry_of')
    require(isinstance(new,list) and len(new)==4 and isinstance(retry,dict),'UPDATE_RETRY_COUNT')
    parents=set();ids=set()
    for row in new:
        validate_append_row(row,known|ids,callback);parents.add(row['params']['parent_task_id']);ids.add(row['id'])
        reference=row['params'].get('plan_sha256') or row['params'].get('contract_sha256')
        directory='plans' if 'plan_sha256' in row['params'] else 'contracts'
        require(directory+'/'+reference+'.json' in specification['package_files'],'UPDATE_REFERENCE_ASSET')
    require(parents==RETRY_PARENTS and set(retry)==ids and len(set(retry.values()))==4
            and all(isinstance(old_id,str) and old_id in known for old_id in retry.values()),'UPDATE_RETRY_MAPPING')
    remaining={row['id']:set(row['deps']) for row in new}
    require(all(deps<=known|ids for deps in remaining.values()),'UPDATE_UNKNOWN_DEPENDENCY')
    remaining={tid:deps-known for tid,deps in remaining.items()}
    while remaining:
        ready={tid for tid,deps in remaining.items() if not deps};require(ready,'UPDATE_DEPENDENCY_CYCLE')
        remaining={tid:deps-ready for tid,deps in remaining.items() if tid not in ready}
    result=copy.deepcopy(current)
    for relative,source in runtime.items():
        name=Path(relative).name;pin=digest(source)
        require(name in UPDATE_MODULES and name in current['module_pins'],'UPDATE_RUNTIME_EXISTING_MODULE')
        result['module_pins'][name]=pin
        if name in SANDBOX_MODULES:result['project_executor']['source_pins'][name]=pin
        else:result['project_executor']['model']['source_pins'][name]=pin
    result['catalog']['tasks'].extend(copy.deepcopy(new));result['catalog_sha256']=digest(encoded(result['catalog']))
    # Reversing exactly the authorized edits must reconstruct the entire old config.
    check=copy.deepcopy(result)
    check['catalog']=current['catalog'];check['catalog_sha256']=current['catalog_sha256']
    for relative in runtime:
        name=Path(relative).name;check['module_pins'][name]=current['module_pins'][name]
        group=check['project_executor']['source_pins'] if name in SANDBOX_MODULES else check['project_executor']['model']['source_pins']
        previous=current['project_executor']['source_pins'] if name in SANDBOX_MODULES else current['project_executor']['model']['source_pins']
        group[name]=previous[name]
    require(check==current and result['catalog']['tasks'][:-4]==old,'UPDATE_UNRELATED_CONFIG_CHANGE')
    return current,result

def exact_s03(root,receipt):
    path=Path(root)/'kb/knowledge.sqlite'
    require(not any(p.is_symlink() for p in (path,*path.parents)) and stat.S_ISREG(path.stat().st_mode),'UPDATE_S03_PATH')
    pin=digest(encoded(receipt));text='NOX native job '+receipt['job_id']+' '+receipt['phase']+' receipt_sha256 '+pin
    with contextlib.closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=.2)) as connection:
        connection.execute('PRAGMA query_only=ON');deadline=time.monotonic()+2
        connection.set_progress_handler(lambda:int(time.monotonic()>deadline),1000)
        rows=connection.execute("SELECT id,meta,sha256 FROM s03_items WHERE segment='M2' AND text=? AND provenance=? LIMIT 2",
                                (text,'owner_native_subagents')).fetchall()
    require(len(rows)==1 and rows[0][2]==digest(('M2|'+text).encode())
            and json.loads(rows[0][1]).get('receipt')==receipt,'UPDATE_S03_EXACT')
    return {'verified':True,'receipt_sha256':pin,'s03_item_id':rows[0][0]}

def terminal_proofs(root,state,specification,config):
    expected=specification.get('terminal_receipts');retry=specification['retry_of']
    require(isinstance(expected,dict) and set(expected)==set(retry.values()),'UPDATE_TERMINAL_PINS')
    tasks=state['tasks'];proofs={};new_by_id={row['id']:row for row in specification['catalog_append']}
    for new_id,old_id in retry.items():
        row=tasks.get(old_id) or {};result=row.get('result') or {};receipt=result.get('receipt') or {}
        require(row.get('status')=='blocked' and row.get('handler')==PROJECT_HANDLER
                and row.get('parent_task_id')==new_by_id[new_id]['params']['parent_task_id']
                and new_id not in tasks,'UPDATE_RETRY_TERMINAL_REQUIRED')
        pin=digest(encoded(receipt));claim=row.get('owner_claim') or {}
        evidence=(receipt.get('worker_result') or {}).get('project_evidence') or {}
        require(SHA.fullmatch(str(expected[old_id])) and pin==expected[old_id] and result.get('receipt_sha256')==pin
                and result.get('verified') is True and receipt.get('claim')==claim
                and claim.get('pid')==specification['expected_director']['pid']
                and re.fullmatch(r'[a-f0-9]{24}',str(claim.get('nonce','')))
                and receipt.get('task_id')==old_id and receipt.get('source_sha256')==config['module_pins']['owner_subagent_dispatcher.py']
                and receipt.get('phase')=='PROJECT_WORK_BLOCKED_ORIGINAL_NOT_ACCEPTED'
                and receipt.get('original_task_accepted') is False and receipt.get('project_source_changed') is False
                and evidence.get('project_source_changed') is False,'UPDATE_TERMINAL_RECEIPT')
        proofs[old_id]=exact_s03(root,receipt)
    for row in specification['catalog_append']:
        require(all(dep in new_by_id or tasks.get(dep,{}).get('status')=='done' for dep in row['deps']),
                'UPDATE_UNSATISFIED_DEPENDENCY')
    return proofs

def source_snapshot(root,config):
    source=Path(root)/'projects/owner_executor/source_workspace'
    require(source.is_dir() and not any(p.is_symlink() for p in (source,*source.parents)),'UPDATE_SOURCE_ROOT')
    allowed=config['project_executor']['roots']['NOX_PROJECT_SOURCE']['allowed_paths']
    require(isinstance(allowed,list) and 1<=len(allowed)<=256 and len(set(allowed))==len(allowed),'UPDATE_SOURCE_ALLOWED')
    allowed=set(relpath(p) for p in allowed)
    marker=read_regular(source/'NOX_EXECUTOR_BOOTSTRAP.json',65536);owner=json.loads(marker)
    require(owner.get('schema')=='NOX_PROJECT_SOURCE_BOOTSTRAP_RECEIPT_V1'
            and owner.get('root')==str(source) and set(owner.get('file_pins',{}))==allowed,'UPDATE_SOURCE_OWNER')
    seen={};total=0;directories=0
    for directory,names,files in os.walk(source,followlinks=False):
        directories+=1;require(directories<=128,'UPDATE_SOURCE_DIRECTORY_BOUND')
        here=Path(directory)
        for name in list(names):
            child=here/name;require(not child.is_symlink(),'UPDATE_SOURCE_SYMLINK')
            if here==source and name=='.git':names.remove(name)
            else:relpath(str(child.relative_to(source)))
        for name in files:
            relative=str((here/name).relative_to(source))
            if relative=='NOX_EXECUTOR_BOOTSTRAP.json':continue
            require(relative in allowed,'UPDATE_UNKNOWN_SOURCE_FILE')
            raw=read_regular(here/name,2*1024*1024);info=(here/name).stat();total+=len(raw)
            require(total<=16*1024*1024,'UPDATE_SOURCE_BYTES')
            seen[relative]={'sha256':digest(raw),'mode':stat.S_IMODE(info.st_mode),'size':len(raw)}
    require(set(seen)==allowed,'UPDATE_SOURCE_FILESET')
    git=source/'.git';require(git.is_dir() and not git.is_symlink(),'UPDATE_GIT_ROOT')
    head=read_regular(git/'HEAD',4096);git_pins={'HEAD':digest(head)}
    if head.startswith(b'ref: '):
        reference=head[5:].decode('ascii').strip();require(reference.startswith('refs/heads/'),'UPDATE_GIT_HEAD')
        relpath(reference);git_pins[reference]=digest(read_regular(git/reference,4096))
    else:require(re.fullmatch(rb'[a-f0-9]{40}\n?',head),'UPDATE_GIT_HEAD')
    if (git/'index').exists():git_pins['index']=digest(read_regular(git/'index',2*1024*1024))
    return {'files':seen,'files_sha256':digest(encoded(seen)),'count':len(seen),'total_bytes':total,
            'bootstrap_sha256':digest(marker),'git_pins':git_pins,'root':str(source)}

def expected_processes(specification):
    expected=specification['expected_director'];director=process_identity(expected['pid'])
    require(director and director['start_ticks']==expected['start_ticks'],'UPDATE_DIRECTOR_CHANGED')
    workers=specification['expected_workers']
    require(isinstance(workers,list) and len(workers)==3 and len({x['pid'] for x in workers})==3,'UPDATE_WORKER_COUNT')
    result=[]
    for row in workers:
        actual=process_identity(row['pid'])
        require(actual and actual['start_ticks']==row['start_ticks'] and actual['ppid']==director['pid'],'UPDATE_WORKER_CHANGED')
        result.append(actual)
    return {'director':director,'workers':result}

def start_update_checked(root,owned):
    require(supervisor('status')['state'] in ('STOPPED','FATAL','EXITED'),'UPDATE_START_REQUIRES_STOPPED')
    try:supervisor('start')
    except (OSError,subprocess.SubprocessError,Hold):pass
    deadline=time.monotonic()+20;stable_since=None
    while time.monotonic()<deadline:
        observed=supervisor('status');identity=process_identity(observed.get('pid'))
        if observed['state']=='RUNNING' and identity:
            if not owned:owned.append(identity)
            require(identity==owned[0],'UPDATE_STARTED_DIRECTOR_REPLACED')
            try:
                doc=json.loads(read_regular(Path(root)/STATUS,2*1024*1024));native=doc.get('native_subexecutors') or {}
                director=native.get('director') or {};at=native.get('observed_at')
                loaded=(director.get('pid')==identity['pid'] and director.get('process_starttime')==identity['start_ticks']
                    and type(at) in (int,float) and 0<=time.time()-at<=15)
            except (OSError,ValueError,TypeError,Hold):loaded=False
            if loaded:
                if stable_since is None:stable_since=time.monotonic()
                elif time.monotonic()-stable_since>=2:return identity
        elif observed['state'] in ('FATAL','EXITED'):break
        time.sleep(.5)
    raise Hold('HOLD_COMPLETE_EXECUTOR_UPDATE_STARTUP_NOT_VERIFIED')

def unchanged_history(before,after):
    old=before['tasks'];new=after['tasks']
    missing=sorted(set(old)-set(new))
    protected={key:row for key,row in old.items() if row.get('owner_claim') or row.get('result') is not None}
    changed=[key for key,row in protected.items() if any(row.get(field)!=new.get(key,{}).get(field)
        for field in ('owner_claim','result','native_project_terminal'))]
    return {'old_count':len(old),'missing_old_ids':missing,'historical_entries':len(protected),
            'changed_claim_or_result_ids':changed,'verified':not missing and not changed}

def model_prompt_preflight(root,project,contract,snapshot,modules,runtime):
    name='owner_project_planner.py';raw=runtime.get('scripts/'+name)
    if raw is None:raw=read_regular(Path(root)/'scripts'/name)
    require(digest(raw)==project['model']['source_pins'][name],'UPDATE_PROMPT_PLANNER_PIN')
    atomic(modules/name,raw,0o644)
    loader=importlib.util.spec_from_file_location('_nox_approved_prompt_preflight_planner',modules/name)
    require(loader is not None and loader.loader is not None,'UPDATE_PROMPT_LOADER')
    planner=importlib.util.module_from_spec(loader);loader.loader.exec_module(planner)
    captured=[]
    class Captured(Exception):pass
    def capture(messages):captured.append(copy.deepcopy(messages));raise Captured()
    def no_verifier(*args):raise Hold('HOLD_COMPLETE_EXECUTOR_UPDATE_PROMPT_UNEXPECTED_VERIFIER')
    try:planner.plan_task(contract,snapshot,capture,no_verifier,lambda:not stop_clear(root))
    except Captured:pass
    require(len(captured)==1,'UPDATE_FIRST_PROMPT_CAPTURE')
    messages=captured[0]
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):raise Hold('HOLD_COMPLETE_EXECUTOR_UPDATE_PROMPT_REDIRECT')
    def request(path,payload=None):
        require(path in ('/v1/models','/props','/apply-template','/tokenize'),'UPDATE_PROMPT_ENDPOINT')
        data=None if payload is None else encoded(payload)
        require(data is None or len(data)<=256*1024,'UPDATE_PROMPT_REQUEST_BOUND')
        req=urllib.request.Request('http://127.0.0.1:8098'+path,data=data,
            method='GET' if payload is None else 'POST',headers={'Content-Type':'application/json'})
        with urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect()).open(req,timeout=15) as response:
            require(response.status==200,'UPDATE_PROMPT_HTTP_STATUS');reply=response.read(512*1024+1)
        require(len(reply)<=512*1024,'UPDATE_PROMPT_REPLY_BOUND');return json.loads(reply)
    models=request('/v1/models')
    require(isinstance(models,dict) and any(isinstance(row,dict) and row.get('id')==project['model']['expected_model_id']
        for row in models.get('data',[])),'UPDATE_PROMPT_MODEL_ID')
    props=request('/props');context=(props.get('default_generation_settings') or {}).get('n_ctx')
    require(type(context) is int and context==4096,'UPDATE_PROMPT_CONTEXT')
    rendered=request('/apply-template',{'messages':messages})
    require(isinstance(rendered,dict) and isinstance(rendered.get('prompt'),str),'UPDATE_PROMPT_TEMPLATE')
    tokenized=request('/tokenize',{'content':rendered['prompt'],'add_special':False,'parse_special':True,'with_pieces':False})
    tokens=tokenized.get('tokens') if isinstance(tokenized,dict) else None
    require(isinstance(tokens,list) and all(type(x) is int for x in tokens),'UPDATE_PROMPT_TOKENIZER')
    maximum=project['model']['max_tokens'];require(type(maximum) is int and 128<=maximum<=1200,'UPDATE_PROMPT_OUTPUT_BUDGET')
    summary={'schema':'NOX_PROJECT_MODEL_PROMPT_PREFLIGHT_V1','task_id':contract['task_id'],
        'prompt_messages_sha256':digest(encoded(messages)),'rendered_prompt_sha256':digest(rendered['prompt'].encode()),
        'input_tokens':len(tokens),'context_tokens':context,'max_output_tokens':maximum,'reserve_tokens':128,
        'first_prompt_unmodified':True,'model_inference_called':False,'source_tree_changed':False,
        'fits_context':len(tokens)+maximum+128<=context}
    atomic(modules.parent/'model_prompt_preflight.json',encoded(summary))
    print('NOX_MAINT_PROJECT_MODEL_PROMPT_PREFLIGHT='+encoded(summary).decode(),flush=True)
    require(summary['fits_context'],'UPDATE_FIRST_PROMPT_CONTEXT_EXCEEDED')
    return summary

def stage_and_validate_retries(root,project,package,preflight,specification,runtime):
    stage=Path(preflight['path']);modules=stage/'modules';review=stage/'reviewed-package';review.mkdir(mode=0o700)
    base=Path(root)/'state/dispatcher/project_executor/package'
    for relative,raw in package.items():
        target=Path(root)/relative;sub=target.relative_to(base);atomic(review/sub,raw)
    clone=copy.deepcopy(project);clone.update(package_root=str(review),state_root=str(stage/'reviewed-run'))
    loader=importlib.util.spec_from_file_location('_nox_approved_runtime_update_executor',modules/'owner_project_executor.py')
    require(loader is not None and loader.loader is not None,'UPDATE_EXECUTOR_LOADER')
    executor=importlib.util.module_from_spec(loader);loader.loader.exec_module(executor);executor.validate_config(clone)
    result=[]
    with executor.tree(project['roots']['NOX_PROJECT_SOURCE']['path']) as handle:
        for row in specification['catalog_append']:
            reference={key:value for key,value in row['params'].items() if key in ('plan_sha256','contract_sha256')}
            if 'plan_sha256' in reference:
                plan=executor.load_plan(reference,clone)
                require(plan.get('review_origin')=='OWNER_REVIEWED','UPDATE_REVIEWED_RETRY')
                for patch in plan['files']:
                    payload=read_regular(review/'blobs'/patch['payload_sha256'])
                    require(digest(payload)==patch['payload_sha256']==patch['after_sha256'],'UPDATE_RETRY_PAYLOAD')
                source_check=plan
            else:
                plan=executor.load_contract_metadata(reference,clone)
                source_check={'context':plan['context'],'files':[]}
            require(plan['task_id']==row['id'] and plan['parent_task_id']==row['params']['parent_task_id']
                    and plan['queue_id']==row['queue_id'] and plan['root_id']=='NOX_PROJECT_SOURCE','UPDATE_PLAN_IDENTITY')
            snapshot=executor._check_source(handle,source_check)
            item={'task_id':row['id'],'reference':reference,'source_preimages_verified':True}
            if 'plan_sha256' in reference:
                checked=executor.prepare(reference,clone,digest(('update-preflight:'+row['id']).encode())[:24],
                    stop_check=lambda:not stop_clear(root))
                evidence=checked.get('project_evidence') or {};tests=evidence.get('tests') or {};facts=tests.get('sandbox') or {}
                item['native_prepared']={'state':checked.get('state'),'tests':tests,'reason':evidence.get('reason'),
                    'evidence_sha256':checked.get('project_evidence_sha256'),'shared_source_integrated':False}
                print('NOX_MAINT_PROJECT_RETRY_PREFLIGHT='+encoded(item).decode(),flush=True)
                require(checked.get('state')=='PREPARED' and checked.get('passed') is True
                    and checked.get('sandbox_verified') is True and checked.get('trusted_tests_unchanged') is True
                    and tests.get('passed') is True and type(tests.get('tests_run')) is int
                    and tests['tests_run']>=plan['verification']['min_tests']
                    and all(tests.get(key)==0 for key in ('failures','errors','skipped'))
                    and facts.get('uid')==65534 and facts.get('gid')==65534
                    and all(facts.get(key) is True for key in ('network_denied','fork_denied','exec_denied',
                        'host_path_hidden','no_new_privs','seccomp_filter')),'UPDATE_RETRY_NATIVE_PREFLIGHT_FAILED')
                executor._check_source(handle,source_check)
            else:item['prompt_preflight']=model_prompt_preflight(root,project,plan,
                {path:value[0] for path,value in snapshot.items()},modules,runtime)
            result.append(item)
    return result

def update_receipt(root,request,receipt):
    raw=encoded(receipt);path=Path(root)/'state/dispatcher'/('project_runtime_update_'+request+'.json')
    atomic(path,raw);require(read_regular(path)==raw,'UPDATE_RECEIPT_READBACK')
    print('NOX_MAINT_PROJECT_RUNTIME_UPDATE='+raw.decode(),flush=True)

def update(bundle,specification,root=ROOT):
    request=os.environ.get('NOX_OWNER_REQUEST_ID','');source=os.environ.get('NOX_OWNER_SOURCE_SHA','')
    require(re.fullmatch(r'[0-9]{1,24}',request) and re.fullmatch(r'[0-9a-f]{40}',source),'UPDATE_OWNER_CONTEXT')
    root=Path(root);assets,runtime=decode_update_assets(bundle,specification)
    expected=specification['expected_native']
    require(isinstance(expected,dict) and CONFIG in expected and all(path==CONFIG or
            re.fullmatch(r'scripts/(?:owner_[a-z0-9_]+|nox_dispatcher_t855u)\.py',path) for path in expected),'UPDATE_EXPECTED_NATIVE_SCOPE')
    before=preimages(root,expected);old,proposed=compose_update(before[CONFIG],runtime,specification,root)
    require(all(expected.get('scripts/'+name)==pin for name,pin in old['module_pins'].items())
            and 'scripts/nox_dispatcher_t855u.py' in expected,'UPDATE_ALL_MODULE_PREIMAGES')
    package=package_changes(root,specification,assets)
    dependency=old['project_executor']['dependency_manifest'];dep_relative=str(Path(dependency['path']).relative_to(root))
    dep_raw=read_regular(root/dep_relative);require(digest(dep_raw)==dependency['sha256'],'UPDATE_DEPENDENCY_PIN')
    if dep_relative in package:require(package[dep_relative]==dep_raw,'UPDATE_DEPENDENCY_CHANGED')
    package[dep_relative]=dep_raw
    changes={relative:raw for relative,raw in runtime.items() if raw!=before.get(relative)}
    for relative,raw in package.items():
        try:current=read_regular(root/relative)
        except FileNotFoundError:current=None
        require(current is None or current==raw,'UPDATE_IMMUTABLE_PACKAGE_CONFLICT')
        if current is None:before[relative]=None;changes[relative]=raw
    changes[CONFIG]=encoded(proposed)
    protected=protected_snapshot(specification);expected_processes(specification)
    require(stop_clear(root),'UPDATE_OWNER_STOP')
    lockpath=root/'state/owner_maintenance.lock';require(not lockpath.is_symlink(),'UPDATE_LEASE_PATH')
    fd=os.open(lockpath,os.O_RDONLY|os.O_NOFOLLOW)
    receipt={'schema':'NOX_PROJECT_RUNTIME_UPDATE_RECEIPT_V1','request':request,'source_sha':source,
        'state':'PREFLIGHT','started_at':time.time(),'source_tree_writes':0,'queue_writes':0,'source_reseeded':False,
        'training_started':False,'model_restarted':False,'original_tasks_accepted':0,'runtime_changed':sorted(runtime)}
    applied=[];old_descendants=[];final_state=None;source_before=None;stop_attempted=False;new_director=None;new_owned=[]
    def lease_guard():
        info=os.fstat(fd);named=lockpath.stat()
        require(stat.S_ISREG(info.st_mode) and info.st_uid==os.geteuid() and info.st_nlink==1 and not info.st_mode&0o022
                and (info.st_dev,info.st_ino)==(named.st_dev,named.st_ino),'UPDATE_LEASE_CHANGED')
    def guard():
        lease_guard();require(stop_clear(root),'UPDATE_OWNER_STOP_CHANGED')
        require(protected_snapshot(specification)==protected,'UPDATE_PROTECTED_CHANGED')
    try:
        wait=specification.get('wait_for_idle_seconds',40);require(type(wait) is int and 0<=wait<=120,'UPDATE_WAIT_BOUND')
        deadline=time.monotonic()+wait
        while True:
            require(stop_clear(root),'UPDATE_OWNER_STOP_WHILE_WAITING');expected_processes(specification)
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);break
            except BlockingIOError:require(time.monotonic()<deadline,'UPDATE_ACTIVE_PROJECT_LEASE');time.sleep(.5)
        guard();expected_processes(specification);preimages(root,expected)
        deadline=time.monotonic()+40
        while True:
            state,active=queue_idle(root)
            if not active:break
            guard();require(time.monotonic()<deadline,'UPDATE_ACTIVE_CLAIMS');time.sleep(.5)
        receipt['terminal_receipts']=terminal_proofs(root,state,specification,old)
        source_before=source_snapshot(root,old);receipt['source_before']=source_before
        receipt['native_sandbox_preflight']=sandbox_preflight(root,runtime,package,proposed['project_executor'],request)
        receipt['reviewed_retries']=stage_and_validate_retries(root,proposed['project_executor'],package,
            receipt['native_sandbox_preflight'],specification,runtime)
        guard();expected_processes(specification);preimages(root,expected)
        require(source_snapshot(root,old)==source_before,'UPDATE_SOURCE_CHANGED_DURING_PREFLIGHT')
        baseline,active=queue_idle(root);require(not active,'UPDATE_ACTIVE_AFTER_PREFLIGHT')
        terminal_proofs(root,baseline,specification,old)
        require(unchanged_history(state,baseline)['verified'],'UPDATE_HISTORY_CHANGED_BEFORE_STOP')
        backup=root/'state/dispatcher/project_runtime_update_rollback'/request
        require(not backup.exists() and not backup.is_symlink(),'UPDATE_BACKUP_EXISTS');backup.mkdir(parents=True,mode=0o700)
        for relative in changes:
            if before.get(relative) is not None:atomic(backup/relative,before[relative])
        atomic(backup/'original_queue_snapshot.json',encoded(baseline));atomic(backup/'source_snapshot.json',encoded(source_before))
        receipt['backup_path']=str(backup);previous=expected_processes(specification)['director']
        require(supervisor('status').get('pid')==previous['pid'],'UPDATE_SUPERVISOR_IDENTITY')
        old_descendants=descendant_snapshot(previous['pid']);receipt['previous_descendants']=old_descendants
        receipt['previous_director']=previous;stop_attempted=True;stop_checked()
        require(process_identity(previous['pid']) is None,'UPDATE_OLD_DIRECTOR_ALIVE')
        receipt['previous_descendants_stopped']=wait_previous_descendants_stopped(old_descendants)
        guard();final_state,active=queue_idle(root);require(not active,'UPDATE_ACTIVE_AFTER_STOP')
        require(unchanged_history(baseline,final_state)['verified'],'UPDATE_HISTORY_CHANGED_ON_STOP')
        terminal_proofs(root,final_state,specification,old)
        require(source_snapshot(root,old)==source_before,'UPDATE_SOURCE_CHANGED_ON_STOP')
        atomic(backup/'final_stopped_queue_snapshot.json',encoded(final_state))
        receipt['final_stopped_queue_sha256']=digest(encoded(final_state))
        applied=apply_transaction(root,changes,before)
        guard();require(source_snapshot(root,old)==source_before,'UPDATE_SOURCE_CHANGED_AFTER_APPLY')
        new_director=start_update_checked(root,new_owned);receipt['new_director']=new_director
        guard();require(source_snapshot(root,old)==source_before,'UPDATE_SOURCE_CHANGED_BEFORE_RELEASE')
        receipt.update(state='UPDATED_RETRIES_PENDING',installed_files={path:digest(raw) for path,raw in changes.items()},
            source_preserved_before_admission=True,old_catalog_preserved=True,callback_unchanged=True,protected_processes=protected)
    except BaseException as exc:
        receipt['state']=str(exc) if isinstance(exc,Hold) else 'HOLD_COMPLETE_EXECUTOR_UPDATE_'+type(exc).__name__
        try:
            lease_guard()
            if applied:
                current=supervisor('status');pid=current.get('pid')
                if current['state']=='RUNNING':
                    identity=process_identity(pid)
                    require(new_owned and identity==new_owned[0],'UPDATE_FOREIGN_DIRECTOR_NO_ROLLBACK')
                    new_children=descendant_snapshot(pid);stop_checked();wait_previous_descendants_stopped(new_children)
                else:require(current['state'] in ('STOPPED','FATAL','EXITED'),'UPDATE_UNKNOWN_DIRECTOR_NO_ROLLBACK')
                receipt['rollback']=rollback_transaction(root,changes,before,applied)
            if stop_attempted and supervisor('status')['state'] in ('STOPPED','FATAL','EXITED') and stop_clear(root):
                require(not live_previous_descendants(old_descendants),'UPDATE_OLD_CHILDREN_ALIVE')
                require(all(before.get(path) is None or read_regular(root/path)==before[path] for path in changes),'UPDATE_ROLLBACK_UNVERIFIED')
                require(source_before is None or source_snapshot(root,old)==source_before,'UPDATE_SOURCE_CHANGED_NO_RESTART')
                require(protected_snapshot(specification)==protected,'UPDATE_PROTECTED_CHANGED_NO_RESTART')
                receipt['restored_director']=start_checked(root);receipt['restored_original_runtime']=True
        except Exception as recovery:
            receipt['recovery']=str(recovery) if isinstance(recovery,Hold) else 'HOLD_UPDATE_RECOVERY_'+type(recovery).__name__
        receipt['finished_at']=time.time();update_receipt(root,request,receipt);raise
    finally:os.close(fd)
    ids=[row['id'] for row in specification['catalog_append']];snapshots=[];last=None
    deadline=time.monotonic()+40
    try:
        while time.monotonic()<deadline:
            require(stop_clear(root),'UPDATE_OWNER_STOP_DURING_ADMISSION')
            require(protected_snapshot(specification)==protected,'UPDATE_PROTECTED_CHANGED_AFTER_RELEASE')
            try:
                last=acceptance_snapshot(root,ids)
                require(last.get('director')==new_director,'UPDATE_NEW_DIRECTOR_CHANGED')
                if len(last['workers'])==len({row['pid'] for row in last['workers']})==3:
                    snapshots.append(last)
                    if len(snapshots)>2:snapshots=[snapshots[0],snapshots[-1]]
                    if stable_three(snapshots) and any(row['claim_present'] for row in last['tasks']):break
            except (OSError,ValueError,TypeError,Hold):pass
            time.sleep(2)
        after,_=queue_idle(root);receipt['history_preservation']=unchanged_history(final_state,after)
        require(receipt['history_preservation']['verified'],'UPDATE_HISTORY_PRESERVATION_FAILED')
        live=bool(last and stable_three(snapshots) and last is snapshots[-1])
        running=bool(last and any(row['status']=='running' for row in last['tasks']))
        admitted=bool(last and any(row['claim_present'] for row in last['tasks']))
        receipt.update(state='UPDATED_RETRY_WORK_RUNNING' if live and running else
            'UPDATED_RETRY_WORK_ADMITTED' if live and admitted else 'UPDATED_RETRIES_PENDING',
            three_live_workers_verified=live,readback=last,process_snapshots=snapshots)
    except (OSError,ValueError,TypeError,Hold) as exc:
        receipt['state']=str(exc) if isinstance(exc,Hold) else 'HOLD_UPDATE_ADMISSION_READBACK'
        receipt['readback']=last;receipt['process_snapshots']=snapshots
    receipt['finished_at']=time.time();update_receipt(root,request,receipt);return receipt

def main():
    update(BUNDLE,SPEC)
    print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)

if __name__=='__main__':main()
