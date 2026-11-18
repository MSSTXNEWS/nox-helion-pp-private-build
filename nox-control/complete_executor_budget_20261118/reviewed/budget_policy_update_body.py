BUDGET_UPDATE_SCHEMA='NOX_BOUNDED_CPU_POLICY_INSTALL_SPEC_V1'
BUDGET_MODULES=frozenset({'owner_subagent_dispatcher.py','owner_autonomy_pool.py',
    'owner_project_native.py','owner_subagent_instruction_truth.py'})
MIB=1024*1024
GIB=1024*MIB

def budget_assets(bundle,specification):
    require(specification.get('schema')==BUDGET_UPDATE_SCHEMA,'BUDGET_SPEC_SCHEMA')
    pins=specification.get('assets');paths=specification.get('runtime_paths')
    require(isinstance(pins,dict) and isinstance(paths,dict) and set(pins)==set(bundle)==set(paths)
            and len(pins)==4 and set(paths.values())=={'scripts/'+name for name in BUDGET_MODULES},'BUDGET_MODULE_SET')
    result={}
    for name,pin in pins.items():
        require(isinstance(name,str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,160}',name)
                and SHA.fullmatch(str(pin)) and isinstance(bundle[name],str) and len(bundle[name])<=512*1024,'BUDGET_ASSET_PIN')
        raw=base64.b64decode(bundle[name],validate=True)
        require(len(raw)<=256*1024 and digest(raw)==pin,'BUDGET_ASSET_HASH')
        compile(raw,paths[name],'exec');result[paths[name]]=raw
    return result

def compose_budget_config(raw,runtime,specification):
    config=json.loads(raw);catalog=config.get('catalog') or {};old=catalog.get('tasks')
    require(config.get('schema')=='NOX_NATIVE_SUBAGENT_BINDING_V1' and config.get('instance_id')==60509551
            and config.get('owner_authorized') is True and config.get('mode')=='NORMAL' and config.get('target')==3
            and config.get('global_worker_cap')==3 and config.get('execution_mode')=='NATIVE_PROJECT_V1','BUDGET_CONFIG_SCOPE')
    require(catalog.get('schema')=='NOX_AUTONOMY_PROCESS_POOL_V1' and isinstance(old,list) and len(old)==19
            and digest(encoded(catalog))==config.get('catalog_sha256'),'BUDGET_CATALOG_PREIMAGE')
    previous=config.get('module_pins',{}).get('owner_subagent_dispatcher.py')
    require(SHA.fullmatch(str(previous)) and previous==specification['expected_native'].get('scripts/owner_subagent_dispatcher.py'),
            'BUDGET_PREVIOUS_CALLBACK')
    ids=specification.get('rebind_task_ids');require(isinstance(ids,list) and len(ids)==len(set(ids))==4,'BUDGET_REBIND_COUNT')
    require(set(ids)=={row['id'] for row in old[15:]},'BUDGET_REBIND_EXACT_LAST_FOUR')
    require({row.get('params',{}).get('parent_task_id') for row in old[15:]}=={'1A03','3A02','3B05','6V14-04'},'BUDGET_REBIND_PARENTS')
    for row in old[15:]:
        require(row.get('handler')==PROJECT_HANDLER and row.get('source_sha256')==previous
                and row.get('resource')=='CPU_LIGHT' and row.get('queue_id') in QUEUE_IDS,'BUDGET_REBIND_SCOPE')
    result=copy.deepcopy(config);callback=digest(runtime['scripts/owner_subagent_dispatcher.py'])
    require(callback!=previous,'BUDGET_CALLBACK_UNCHANGED')
    for name in BUDGET_MODULES:
        require(name in config['module_pins'],'BUDGET_EXISTING_MODULE')
        result['module_pins'][name]=digest(runtime['scripts/'+name])
    for row in result['catalog']['tasks'][15:]:row['source_sha256']=callback
    result['catalog_sha256']=digest(encoded(result['catalog']))
    for key in ('historical_project_source_sha256','historical_leaf_source_sha256'):
        values=config.get(key,[])
        require(isinstance(values,list) and len(values)<=16 and all(SHA.fullmatch(str(v)) for v in values),'BUDGET_HISTORICAL_PINS')
        result[key]=sorted(set(values)|{previous})
    check=copy.deepcopy(result);check['catalog']=config['catalog'];check['catalog_sha256']=config['catalog_sha256']
    for name in BUDGET_MODULES:check['module_pins'][name]=config['module_pins'][name]
    for key in ('historical_project_source_sha256','historical_leaf_source_sha256'):
        if key in config:check[key]=config[key]
        else:check.pop(key,None)
    require(check==config and result['catalog']['tasks'][:15]==old[:15],'BUDGET_UNRELATED_CONFIG_CHANGE')
    return config,result

def absent_retry_rows(state,ids):
    require(all(tid not in state['tasks'] for tid in ids),'BUDGET_RETRY_ALREADY_ADMITTED')

def project_history_proofs(root,state,config):
    rows={tid:row for tid,row in state['tasks'].items() if row.get('handler')==PROJECT_HANDLER}
    require(len(rows)==7,'BUDGET_EXISTING_PROJECT_COUNT')
    allowed={config['module_pins']['owner_subagent_dispatcher.py'],*config.get('historical_project_source_sha256',[])}
    proofs={}
    for tid,row in rows.items():
        result=row.get('result') or {};receipt=result.get('receipt') or {}
        phase='PROJECT_WORK_INTEGRATED_ORIGINAL_NOT_ACCEPTED' if row.get('status')=='done' else 'PROJECT_WORK_BLOCKED_ORIGINAL_NOT_ACCEPTED'
        require(row.get('status') in ('done','blocked') and result.get('verified') is True
                and receipt.get('task_id')==tid and receipt.get('claim')==row.get('owner_claim')
                and receipt.get('original_task_accepted') is False and receipt.get('source_sha256') in allowed
                and receipt.get('phase')==phase and result.get('receipt_sha256')==digest(encoded(receipt)),
                'BUDGET_EXISTING_PROJECT_RECEIPT')
        proofs[tid]=exact_s03(root,receipt)
    return proofs

def preserve_terminal_history(before,after):
    old=before['tasks'];new=after['tasks'];missing=sorted(set(old)-set(new))
    terminal={tid:row for tid,row in old.items() if row.get('status') in ('done','completed','failed','blocked','cancelled','canceled')
        or row.get('native_project_terminal')}
    changed=[];resumed=[]
    for tid,row in old.items():
        different=any(row.get(field)!=new.get(tid,{}).get(field) for field in ('owner_claim','result','native_project_terminal'))
        if different:
            if tid in terminal:changed.append(tid)
            else:resumed.append({'id':tid,'old_status':row.get('status'),'new_status':new.get(tid,{}).get('status'),
                'old_claim_sha256':digest(encoded(row.get('owner_claim'))),
                'new_claim_sha256':digest(encoded(new.get(tid,{}).get('owner_claim'))),
                'same_result':row.get('result')==new.get(tid,{}).get('result')})
    return {'old_count':len(old),'missing_old_ids':missing,'terminal_rows_checked':len(terminal),
        'changed_terminal_claim_result_ids':changed,'nonterminal_claim_changes':resumed[:100],
        'nonterminal_claim_changes_count':len(resumed),'verified':not missing and not changed}

def zero_children_guard(specification):
    require(specification.get('expected_no_children') is True,'BUDGET_ZERO_CHILDREN_CONTRACT')
    expected=specification['expected_director'];identity=process_identity(expected['pid'])
    require(identity and identity['start_ticks']==expected['start_ticks'],'BUDGET_DIRECTOR_CHANGED')
    status=supervisor('status');require(status['state']=='RUNNING' and status.get('pid')==identity['pid'],'BUDGET_SUPERVISOR_IDENTITY')
    children=descendant_snapshot(identity['pid']);require(not children,'BUDGET_UNEXPECTED_DIRECTOR_CHILDREN')
    return {'director':identity,'children':children,'observed_at':time.time()}

def wait_idle_zero_children(root,specification,timeout=40):
    deadline=time.monotonic()+timeout
    while True:
        require(stop_clear(root),'BUDGET_OWNER_STOP_DURING_DRAIN')
        state,active=queue_idle(root);absent_retry_rows(state,specification['rebind_task_ids'])
        try:observed=zero_children_guard(specification)
        except Hold as exc:
            if str(exc)!='HOLD_COMPLETE_EXECUTOR_BUDGET_UNEXPECTED_DIRECTOR_CHILDREN':raise
            observed=None
        if not active and observed:return state,observed
        require(time.monotonic()<deadline,'BUDGET_ACTIVE_CLAIMS_OR_CHILDREN_NOT_DRAINED')
        time.sleep(.5)

def read_budget_snapshot(config,cgroup=Path('/sys/fs/cgroup')):
    def raw(name):return read_regular(Path(cgroup)/name,65536).decode('ascii')
    def integer(name):
        text=raw(name).strip();require(re.fullmatch(r'[0-9]{1,20}',text),'BUDGET_CGROUP_INTEGER');return int(text)
    stats={}
    for line in raw('memory.stat').splitlines():
        key,value=line.split();require(key not in stats and re.fullmatch(r'[0-9]{1,20}',value),'BUDGET_MEMORY_STAT');stats[key]=int(value)
    def psi(text,kind):
        for line in text.splitlines():
            if line.startswith(kind+' '):
                fields=dict(part.split('=',1) for part in line.split()[1:]);value=float(fields['avg10'])
                require(math.isfinite(value) and value>=0,'BUDGET_PSI');return value
        raise Hold('HOLD_COMPLETE_EXECUTOR_BUDGET_PSI_MISSING')
    pressure=raw('memory.pressure');cpu=psi(raw('cpu.pressure'),'some')
    sandbox=config['project_executor']['sandbox'].get('memory_mb')
    require(type(sandbox) is int and 96<=sandbox<=512,'BUDGET_SANDBOX_LIMIT')
    return {'schema':'NOX_BOUNDED_CPU_BUDGET_V1','source':'cgroup_v2','instance_id':60509551,'observed_at':time.time(),
        'worker_slots':3,'current_bytes':integer('memory.current'),'max_bytes':integer('memory.max'),
        'inactive_file_bytes':stats['inactive_file'],'file_bytes':stats['file'],'shmem_bytes':stats['shmem'],
        'sandbox_limit_bytes':sandbox*MIB,'planner_reserve_bytes':128*MIB,'minimum_headroom_bytes':2*GIB,
        'memory_psi_some_avg10':psi(pressure,'some'),'memory_psi_full_avg10':psi(pressure,'full'),'cpu_pressure':cpu}

def load_budget_module(root,runtime,expected,request):
    stage=Path(root)/'state/dispatcher/bounded_cpu_preflight'/request
    require(not stage.exists() and not stage.is_symlink(),'BUDGET_PREFLIGHT_ALREADY_EXISTS')
    stage.mkdir(parents=True,mode=0o700)
    policy=read_regular(Path(root)/'scripts/owner_resource_policy.py')
    require(digest(policy)==expected.get('scripts/owner_resource_policy.py'),'BUDGET_RESOURCE_POLICY_PIN')
    sources={'owner_resource_policy':policy,'owner_autonomy_pool':runtime['scripts/owner_autonomy_pool.py']}
    previous={name:sys.modules.get(name) for name in sources};loaded={}
    try:
        for name,source in sources.items():
            path=stage/(name+'.py');atomic(path,source,0o644)
            loader=importlib.util.spec_from_file_location(name,path);require(loader and loader.loader,'BUDGET_MODULE_LOADER')
            module=importlib.util.module_from_spec(loader);sys.modules[name]=module;loader.loader.exec_module(module);loaded[name]=module
        module=loaded['owner_autonomy_pool'];require(callable(getattr(module,'bounded_cpu_decision',None)),'BUDGET_VALIDATOR_REQUIRED')
        return module,stage
    finally:
        for name,value in previous.items():
            if value is None:sys.modules.pop(name,None)
            else:sys.modules[name]=value

def budget_preflight(config,module,stage,phase,cgroup=Path('/sys/fs/cgroup')):
    snapshot=read_budget_snapshot(config,cgroup)
    reclaim=min(snapshot['inactive_file_bytes'],snapshot['file_bytes']-snapshot['shmem_bytes'],snapshot['current_bytes'])
    reserve=3*(max(256*MIB,snapshot['sandbox_limit_bytes'])+128*MIB)
    projected=snapshot['current_bytes']-reclaim+reserve
    decision=module.bounded_cpu_decision(snapshot,memory_ratio=projected/snapshot['max_bytes'],
        cpu_pressure=snapshot['cpu_pressure'],now=time.time())
    require(decision.get('reclaimable_bytes')==reclaim and decision.get('reserved_bytes')==reserve
            and decision.get('projected_bytes')==projected and decision.get('headroom_bytes')==snapshot['max_bytes']-projected,
            'BUDGET_INDEPENDENT_ARITHMETIC')
    result={'schema':'NOX_BOUNDED_CPU_NATIVE_PREFLIGHT_V1','phase':phase,'snapshot':snapshot,'decision':decision,
        'model_inference_called':False,'workers_started':0,'source_tree_writes':0}
    atomic(Path(stage)/(phase+'.json'),encoded(result));print('NOX_MAINT_BOUNDED_CPU_PREFLIGHT='+encoded(result).decode(),flush=True)
    require(decision.get('eligible') is True and decision['headroom_bytes']>=2*GIB,'BUDGET_NATIVE_ADMISSION_HOLD')
    return result

def budget_receipt(root,request,receipt):
    path=Path(root)/'state/dispatcher'/('bounded_cpu_install_'+request+'.json');raw=encoded(receipt)
    atomic(path,raw);require(read_regular(path)==raw,'BUDGET_RECEIPT_READBACK')
    print('NOX_MAINT_BOUNDED_CPU_INSTALL='+raw.decode(),flush=True)

def install_budget(bundle,specification,root=ROOT):
    request=os.environ.get('NOX_OWNER_REQUEST_ID','');source=os.environ.get('NOX_OWNER_SOURCE_SHA','')
    require(re.fullmatch(r'[0-9]{1,24}',request) and re.fullmatch(r'[0-9a-f]{40}',source),'BUDGET_OWNER_CONTEXT')
    root=Path(root);runtime=budget_assets(bundle,specification);expected=specification['expected_native']
    require(isinstance(expected,dict) and CONFIG in expected and all(path==CONFIG or
        re.fullmatch(r'scripts/(?:owner_[a-z0-9_]+|nox_dispatcher_t855u)\.py',path) for path in expected),'BUDGET_EXPECTED_SCOPE')
    before=preimages(root,expected);old,new=compose_budget_config(before[CONFIG],runtime,specification)
    require(all(expected.get('scripts/'+name)==pin for name,pin in old['module_pins'].items())
        and 'scripts/nox_dispatcher_t855u.py' in expected,'BUDGET_ALL_MODULE_PREIMAGES')
    changes={**runtime,CONFIG:encoded(new)};ids=specification['rebind_task_ids'];protected=protected_snapshot(specification)
    require(stop_clear(root),'BUDGET_OWNER_STOP')
    lockpath=root/'state/owner_maintenance.lock';require(not lockpath.is_symlink(),'BUDGET_LEASE_PATH');fd=os.open(lockpath,os.O_RDONLY|os.O_NOFOLLOW)
    receipt={'schema':'NOX_BOUNDED_CPU_POLICY_INSTALL_RECEIPT_V1','request':request,'source_sha':source,'state':'PREFLIGHT',
        'started_at':time.time(),'queue_writes':0,'source_tree_writes':0,'source_reseeded':False,
        'model_restarted':False,'training_started':False,'original_tasks_accepted':0}
    applied=[];stop_attempted=False;new_owned=[];source_before=None;final_state=None;original_projects=None
    def lease_guard():
        info=os.fstat(fd);named=lockpath.stat()
        require(stat.S_ISREG(info.st_mode) and info.st_uid==os.geteuid() and info.st_nlink==1 and not info.st_mode&0o022
            and (info.st_dev,info.st_ino)==(named.st_dev,named.st_ino),'BUDGET_LEASE_CHANGED')
    def guard():
        lease_guard();require(stop_clear(root),'BUDGET_OWNER_STOP_CHANGED')
        require(protected_snapshot(specification)==protected,'BUDGET_PROTECTED_CHANGED')
    try:
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as exc:raise Hold('HOLD_COMPLETE_EXECUTOR_BUDGET_MAINTENANCE_BUSY') from exc
        guard();preimages(root,expected);baseline,first=wait_idle_zero_children(root,specification)
        absent_retry_rows(baseline,ids);original_projects=project_history_proofs(root,baseline,old)
        receipt['existing_project_receipts']=original_projects
        source_before=source_snapshot(root,old);receipt['source_before']=source_before
        module,stage=load_budget_module(root,runtime,expected,request)
        receipt['budget_before_stop']=budget_preflight(new,module,stage,'before_stop')
        state,second=wait_idle_zero_children(root,specification)
        require(second['director']==first['director'],'BUDGET_DIRECTOR_CHANGED_BEFORE_STOP')
        receipt['zero_children_snapshots']=[first,second]
        guard();preimages(root,expected);require(source_snapshot(root,old)==source_before,'BUDGET_SOURCE_CHANGED_PREFLIGHT')
        state,active=queue_idle(root);require(not active,'BUDGET_ACTIVE_BEFORE_STOP');absent_retry_rows(state,ids)
        require(preserve_terminal_history(baseline,state)['verified'],'BUDGET_HISTORY_CHANGED_BEFORE_STOP')
        require(project_history_proofs(root,state,old)==original_projects,'BUDGET_PROJECT_RECEIPTS_CHANGED_BEFORE_STOP')
        backup=root/'state/dispatcher/bounded_cpu_rollback'/request
        require(not backup.exists() and not backup.is_symlink(),'BUDGET_BACKUP_EXISTS');backup.mkdir(parents=True,mode=0o700)
        for relative in changes:atomic(backup/relative,before[relative])
        atomic(backup/'original_queue_snapshot.json',encoded(state));atomic(backup/'source_snapshot.json',encoded(source_before))
        receipt.update(backup_path=str(backup),previous_director=first['director'])
        guard();zero_children_guard(specification);stop_attempted=True;stop_checked()
        require(process_identity(first['director']['pid']) is None,'BUDGET_OLD_DIRECTOR_ALIVE')
        final_state,active=queue_idle(root);require(not active,'BUDGET_ACTIVE_AFTER_STOP');absent_retry_rows(final_state,ids)
        require(preserve_terminal_history(state,final_state)['verified'],'BUDGET_TERMINAL_HISTORY_CHANGED_ON_STOP')
        require(project_history_proofs(root,final_state,old)==original_projects,'BUDGET_PROJECT_RECEIPTS_CHANGED_ON_STOP')
        require(source_snapshot(root,old)==source_before,'BUDGET_SOURCE_CHANGED_ON_STOP')
        atomic(backup/'final_stopped_queue_snapshot.json',encoded(final_state));receipt['final_stopped_queue_sha256']=digest(encoded(final_state))
        guard();receipt['budget_after_stop']=budget_preflight(new,module,stage,'after_stop')
        applied=apply_transaction(root,changes,before)
        guard();require(source_snapshot(root,old)==source_before,'BUDGET_SOURCE_CHANGED_AFTER_APPLY')
        receipt['new_director']=start_update_checked(root,new_owned)
        guard();require(source_snapshot(root,old)==source_before,'BUDGET_SOURCE_CHANGED_BEFORE_ADMISSION')
        receipt.update(state='BOUNDED_CPU_INSTALLED_ADMISSION_PENDING',source_preserved_before_admission=True,
            first_fifteen_catalog_rows_preserved=True,old_module_pins=old['module_pins'],
            installed_files={path:digest(raw) for path,raw in changes.items()},protected_processes=protected)
    except BaseException as exc:
        receipt['state']=str(exc) if isinstance(exc,Hold) else 'HOLD_BOUNDED_CPU_'+type(exc).__name__
        try:
            lease_guard()
            if applied:
                observed=supervisor('status')
                if observed['state']=='RUNNING':
                    actual=process_identity(observed.get('pid'))
                    require(new_owned and actual==new_owned[0],'BUDGET_FOREIGN_DIRECTOR_NO_ROLLBACK')
                    children=descendant_snapshot(actual['pid']);stop_checked();wait_previous_descendants_stopped(children)
                else:require(observed['state'] in ('STOPPED','FATAL','EXITED'),'BUDGET_UNKNOWN_PROCESS_NO_ROLLBACK')
                receipt['rollback']=rollback_transaction(root,changes,before,applied)
            if stop_attempted and supervisor('status')['state'] in ('STOPPED','FATAL','EXITED') and stop_clear(root):
                require(all(read_regular(root/path)==before[path] for path in changes),'BUDGET_ROLLBACK_UNVERIFIED')
                require(source_snapshot(root,old)==source_before,'BUDGET_SOURCE_CHANGED_NO_RESTART')
                require(protected_snapshot(specification)==protected,'BUDGET_PROTECTED_CHANGED_NO_RESTART')
                receipt['restored_director']=start_checked(root);receipt['restored_original_runtime']=True
        except Exception as recovery:
            receipt['recovery']=str(recovery) if isinstance(recovery,Hold) else 'HOLD_BUDGET_RECOVERY_'+type(recovery).__name__
        receipt['finished_at']=time.time();budget_receipt(root,request,receipt);raise
    finally:os.close(fd)
    last=None;snapshots=[];deadline=time.monotonic()+45
    try:
        while time.monotonic()<deadline:
            require(stop_clear(root),'BUDGET_OWNER_STOP_AFTER_ADMISSION')
            require(protected_snapshot(specification)==protected,'BUDGET_PROTECTED_CHANGED_AFTER_ADMISSION')
            try:
                last=acceptance_snapshot(root,ids)
                require(last['director']==receipt['new_director'],'BUDGET_NEW_DIRECTOR_CHANGED')
                if len(last['workers'])==len({row['pid'] for row in last['workers']})==3:
                    snapshots.append(last)
                    if len(snapshots)>2:snapshots=[snapshots[0],snapshots[-1]]
                    if stable_three(snapshots) and any(row['claim_present'] for row in last['tasks']):break
            except (OSError,ValueError,TypeError,Hold):pass
            time.sleep(2)
        after,_=queue_idle(root);receipt['history_preservation']=preserve_terminal_history(final_state,after)
        require(receipt['history_preservation']['verified'],'BUDGET_TERMINAL_HISTORY_PRESERVATION_FAILED')
        # New retry rows are valid new work; verify the seven old rows independently.
        old_only={'tasks':{tid:after['tasks'][tid] for tid,row in final_state['tasks'].items() if row.get('handler')==PROJECT_HANDLER}}
        receipt['existing_project_receipts_after_admission']=project_history_proofs(root,old_only,old)
        require(receipt['existing_project_receipts_after_admission']==original_projects,'BUDGET_OLD_PROJECT_RECEIPT_DRIFT')
        receipt.update(readback=last,process_snapshots=snapshots)
        require(last and len(snapshots)==2 and last is snapshots[-1] and stable_three(snapshots),'BUDGET_THREE_NATIVE_WORKERS_NOT_VERIFIED')
        require(any(row['claim_present'] for row in last['tasks']),'BUDGET_NO_RETRY_ADMISSION')
        receipt.update(three_live_workers_verified=True,state='BOUNDED_CPU_THREE_WORKERS_RETRY_RUNNING'
            if any(row['status']=='running' for row in last['tasks']) else 'BOUNDED_CPU_THREE_WORKERS_RETRY_ADMITTED')
    except (OSError,ValueError,TypeError,Hold) as exc:
        receipt['state']=str(exc) if isinstance(exc,Hold) else 'HOLD_BUDGET_ADMISSION_READBACK'
        receipt['readback']=last;receipt['process_snapshots']=snapshots
    receipt['finished_at']=time.time();budget_receipt(root,request,receipt);return receipt

def main():
    result=install_budget(BUNDLE,SPEC)
    if result.get('three_live_workers_verified') is True:
        print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
    else:raise Hold('HOLD_COMPLETE_EXECUTOR_BUDGET_ADMISSION_NOT_VERIFIED')

if __name__=='__main__':main()
