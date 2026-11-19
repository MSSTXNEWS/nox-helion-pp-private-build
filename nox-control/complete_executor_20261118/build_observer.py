"""Build the read-only native readback, reusing previously reviewed IO helpers."""
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
old = (BASE/'runtime_diag/postinstall_readonly_inspect.py').read_text()
helper = old[:old.index('\ndef main():')]
extra = r'''

def project_execution_readback():
    import base64
    config, config_raw, _ = obj(ROOT/'config/owner_native_subagents.json')
    emit('PROJECT_EXECUTOR_CONFIG', {'sha256':hashlib.sha256(config_raw).hexdigest(),
        'mode':config.get('execution_mode'),'worker_cap':config.get('global_worker_cap'),
        'source_pins':config.get('project_executor',{}).get('source_pins'),
        'model_pins':config.get('project_executor',{}).get('model',{}).get('source_pins')})
    project=config.get('project_executor') or {}
    if not project:
        return
    for name in ('owner_project_executor.py','owner_project_test_runner.py','owner_project_native.py',
                 'owner_project_planner.py','owner_project_model_client.py','owner_project_model_bridge.py'):
        try:
            raw,_=safe_read(SCRIPTS/name,500000)
            emit('PROJECT_RUNTIME_SOURCE',{'name':name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),
                'matches_module_pin':hashlib.sha256(raw).hexdigest()==config.get('module_pins',{}).get(name)})
        except (OSError,ValueError) as exc:
            emit('PROJECT_RUNTIME_SOURCE',{'name':name,'state':'UNAVAILABLE','error':type(exc).__name__})
    state, state_raw, _ = obj(ROOT/'state/dispatcher/state.json',32*1024*1024)
    rows=state.get('tasks',{})
    counts={}
    for task in rows.values():
        key=task.get('status','UNKNOWN');counts[key]=counts.get(key,0)+1
    emit('PROJECT_QUEUE',{'rows':len(rows),'counts':counts,'sha256':hashlib.sha256(state_raw).hexdigest()})
    exported=set();export_bytes=0
    for tid,task in rows.items():
        if not isinstance(task,dict) or task.get('handler')!='owner_native_project_work':continue
        row={key:task.get(key) for key in ('id','parent_task_id','queue_id','status','note','retries',
                                         'native_queue_sequence','original_task_accepted')}
        row['owner_claim']=task.get('owner_claim')
        result=task.get('result') or {};receipt=result.get('receipt') or {}
        row['result']={key:result.get(key) for key in ('verified','scope','receipt_sha256')}
        if receipt:
            row['receipt']={key:receipt.get(key) for key in ('schema','phase','task_id','parent_task_id',
                'queue_id','job_id','plan_sha256','source_sha256','scope','finished_at',
                'project_source_changed','live_service_deployed','original_task_accepted')}
            row['receipt_sha_matches']=hashlib.sha256(encoded(receipt)).hexdigest()==result.get('receipt_sha256')
            row['receipt_claim_matches']=receipt.get('claim')==task.get('owner_claim')
            row['s03']=s03_receipt_check(receipt)
            event=receipt.get('worker_result') or {};evidence=event.get('project_evidence') or {}
            row['worker_event']={key:event.get(key) for key in ('kind','role','pid','id','state','elapsed_ms','reason')}
            row['project_evidence']={key:evidence.get(key) for key in ('schema','state','task_id','claim',
                'plan_sha256','root_id','acceptance_scope','worker','project_source_changed',
                'integration_verified','postimages','tests_sha256','reason','trusted_tests_unchanged')}
            if evidence:
                row['project_evidence_sha_matches']=hashlib.sha256(encoded(evidence)).hexdigest()==event.get('project_evidence_sha256')
            tests=evidence.get('tests') or {}
            row['tests']={key:tests.get(key) for key in ('schema','completed','passed','modules','tests_run',
                'failures','errors','skipped','sandbox','log_sha256','log_bytes','elapsed_ms')}
            if tests.get('passed') is not True:
                row['tests']['output_tail']=redact_source(str(tests.get('output',''))[-4000:])
            planner=event.get('planner_receipt') or {}
            row['planner_receipt']=planner
            reference=event.get('reference') or {}
            if reference.get('plan_sha256'):
                plan_path=Path(project['package_root'])/'plans'/(reference['plan_sha256']+'.json')
                try:
                    plan,raw,_=obj(plan_path)
                    row['plan']={'sha256':hashlib.sha256(raw).hexdigest(),
                        'matches_reference':hashlib.sha256(raw).hexdigest()==reference['plan_sha256'],
                        'files':plan.get('files'), 'review_origin':plan.get('review_origin'),
                        'contract_sha256':plan.get('contract_sha256')}
                    if evidence.get('state')=='INTEGRATED' and plan.get('review_origin')=='MODEL_CANDIDATE':
                        root=Path(project['roots'][plan['root_id']]['path'])
                        for changed in plan.get('files',[]):
                            path=changed['path'];p=Path(path)
                            if (path in exported or p.is_absolute() or any(x in ('','..','.') for x in p.parts)
                                or str(p)!=path):continue
                            source,_=safe_read(root/path,100000)
                            digest=hashlib.sha256(source).hexdigest()
                            if digest!=changed['after_sha256']:continue
                            if export_bytes+len(source)>80000:continue
                            text=source.decode('utf-8')
                            if redact_source(text)!=text:
                                emit('PROJECT_MODEL_POSTIMAGE',{'path':path,'sha256':digest,'export_state':'REDACTION_REQUIRED'})
                                continue
                            export_bytes+=len(source);exported.add(path)
                            emit('PROJECT_MODEL_POSTIMAGE',{'task_id':tid,'path':path,'bytes':len(source),
                                'sha256':digest,'before_sha256':changed.get('before_sha256'),
                                'base64':base64.b64encode(source).decode()})
                except (OSError,ValueError,KeyError) as exc:
                    row['plan']={'state':'UNAVAILABLE','error':type(exc).__name__}
        # The full receipt remains canonical in native state and S03. This
        # bounded readback retains verification facts and exact source hashes.
        emit('PROJECT_EXECUTION',row)
    config_rows=config.get('catalog',{}).get('tasks',[])
    emit('PROJECT_CATALOG',{'rows':len(config_rows),'new_project_rows':[
        {key:t.get(key) for key in ('id','queue_id','deps','params','priority','resource')}
        for t in config_rows if t.get('handler')=='owner_native_project_work']})


def project_install_preservation():
    config,_,_=obj(ROOT/'config/owner_native_subagents.json')
    request=str(config.get('owner_request',''))
    if not re.fullmatch(r'[0-9]{1,24}',request):return
    base=ROOT/'state/dispatcher/complete_executor_rollback'/request
    try:
        before,_,_=obj(base/'final_stopped_queue_snapshot.json',32*1024*1024)
        after,_,_=obj(ROOT/'state/dispatcher/state.json',32*1024*1024)
        old=before['tasks'];new=after['tasks']
        historic={key:row for key,row in old.items() if row.get('status') in ('done','blocked','failed')}
        changed=[key for key,row in historic.items() if any(row.get(field)!=new.get(key,{}).get(field)
                                                         for field in ('owner_claim','result'))]
        emit('PROJECT_QUEUE_PRESERVATION',{'request':request,'old_count':len(old),'current_count':len(new),
            'missing_original_ids':sorted(set(old)-set(new)),'historical_checked':len(historic),
            'changed_claim_or_result':changed,'verified':not(set(old)-set(new)) and not changed})
        receipt,raw,_=obj(ROOT/'state/dispatcher'/('complete_executor_install_'+request+'.json'),4*1024*1024)
        emit('PROJECT_INSTALL_RECEIPT',{'sha256':hashlib.sha256(raw).hexdigest(),
            **{key:receipt.get(key) for key in ('schema','state','request','source_sha','started_at',
                'finished_at','previous_director','new_director','original_tasks_accepted',
                'protected_processes','training_started','model_restarted','preflight',
                'sandbox_preflight','native_sandbox_preflight','source_bootstrap')}})
    except (OSError,ValueError,KeyError) as exc:
        emit('PROJECT_QUEUE_PRESERVATION',{'request':request,'state':'UNAVAILABLE','error':type(exc).__name__})


def director_child_census():
    data,_,_=obj(ROOT/'status/agents_t856u.json')
    native=data.get('native_subexecutors') or {};pid=(native.get('director') or {}).get('pid')
    result=[]
    if type(pid) is int:
        for child in Path('/proc').iterdir():
            if not child.name.isdigit():continue
            observed=process(int(child.name))
            if observed.get('ppid')!=pid:continue
            try:
                raw=(child/'cmdline').read_bytes()[:4000]
                kind='MP_WORKER' if b'multiprocessing.spawn' in raw else (
                    'MP_RESOURCE_TRACKER' if b'resource_tracker' in raw else 'OTHER_CHILD')
            except OSError:kind='UNKNOWN'
            result.append({**observed,'kind':kind})
    emit('PROJECT_DIRECTOR_CHILDREN',{'director_pid':pid,'children':result,
        'native_fields':sorted(native),'last_admission':native.get('last_admission'),
        'close_reason':native.get('close_reason'),'state':native.get('state')})


def project_active_progress():
    import urllib.request
    try:
        req=urllib.request.Request('http://127.0.0.1:8098/slots',method='GET')
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req,timeout=5) as response:
            raw=response.read(200001)
        if len(raw)>200000:raise ValueError('SLOT_SIZE')
        slots=json.loads(raw)
        if not isinstance(slots,list):raise ValueError('SLOT_SHAPE')
        rows=[]
        keys=('id','id_task','is_processing','n_ctx','n_prompt_tokens','n_decoded','n_predict','n_past','state')
        for slot in slots[:4]:
            row=scalar_projection(slot,keys)
            for field in ('timings','next_token','params'):
                if isinstance(slot.get(field),dict):
                    row[field]=scalar_projection(slot[field],(
                        'n_predict','n_ctx','n_decoded','n_remaining','has_next_token',
                        'prompt_n','prompt_ms','predicted_n','predicted_ms',
                        'predicted_per_token_ms','predicted_per_second'))
            rows.append(row)
        emit('PROJECT_MODEL_SLOT_PROGRESS',{'slots':rows,'scope':'READ_ONLY_NO_PROMPT_OR_COMPLETION_CONTENT'})
    except (OSError,ValueError,TypeError) as exc:
        emit('PROJECT_MODEL_SLOT_PROGRESS',{'state':'UNAVAILABLE','error':type(exc).__name__})
    base=ROOT/'state/dispatcher/project_executor/run/attempts'
    rows=[]
    if base.exists() and not base.is_symlink():
        for path in sorted(base.glob('*/*/*/journal.json'))[-40:]:
            try:
                value,raw,info=obj(path,2000000)
                row=scalar_projection(value,('schema','state','task_id','claim','plan_sha256','reason','started_at','finished_at'))
                row.update({'journal_sha256':hashlib.sha256(raw).hexdigest(),'mtime_ns':info.st_mtime_ns})
                rows.append(row)
            except (OSError,ValueError):continue
    emit('PROJECT_ATTEMPT_PROGRESS',{'attempts':rows})


def main():
    emit('SNAPSHOT_A',runtime_snapshot())
    worker_status_sample()
    director_child_census()
    project_summary()
    project_install_preservation()
    project_execution_readback()
    project_active_progress()
    emit('LOCKS',locks())
    time.sleep(6)
    worker_status_sample()
    director_child_census()
    emit('SNAPSHOT_B',runtime_snapshot())
    print('NOX_MAINT_INSPECT_COMPLETE=true',flush=True)

if __name__=='__main__':main()
'''
out = BASE/'complete_executor/owner_complete_executor_observe.py'
out.write_text(helper+extra)
compile(out.read_text(),str(out),'exec')
print(out)
