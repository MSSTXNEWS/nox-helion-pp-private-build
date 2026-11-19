"""Read-only extension for the fixed observer, scoped to update 6966949947.

Call runtime_update_history_readback(ROOT, emit, obj, safe_read,
                                    s03_receipt_check) before observer completion.
No imports of serving code, leases, process signals or file writes are performed.
"""

UPDATE_HISTORY_REQUEST='6966949947'
UPDATE_HISTORY_CHANGED_IDS=(
    't168u.opt.T162U-01','t168u.opt.T162U-03','t168u.opt.T162U-05','t168u.opt.T162U-06',
    't168u.opt.T162U-07','t168u.opt.T162U-08','t168u.opt.T162U-10','t168u.opt.T162U-12',
    't168u.opt.T162U-15','t168u.opt.T162U-16','t168u.opt.T162U-17','t168u.opt.T162U-18',
    't168u.opt.T162U-19','t168u.opt.T162U-20','t168u.opt.T162U-21','t168u.opt.T162U-22',
    't168u.opt.T162U-23','t168u.opt.T162U-24','t168u.opt.T162U-26','t168u.opt.T162U-27',
    't168u.opt.T162U-28','t168u.opt.T162U-29','t168u.opt.T162U-30','t168u.opt.T168U-32',
    't168u.opt.T168U-33','t168u.opt.T168U-34','t168u.opt.T168U-35','t168u.opt.T168U-36',
    't168u.opt.T168U-38','t168u.opt.T168U-39','t168u.opt.T168U-40','t168u.opt.T168U-41',
    't168u.opt.T168U-42','t168u.opt.T168U-43','t168u.opt.T170U-37',
)

def runtime_update_history_readback(root,emit,obj,safe_read,s03_receipt_check):
    import collections
    import hashlib
    import json
    from pathlib import Path
    import re
    import stat
    import time
    root=Path(root)
    def canonical(value):
        return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
    def sha(raw):return hashlib.sha256(raw).hexdigest()
    def token(value):
        return value if isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}',value) else None
    def projection(row):
        claim=row.get('owner_claim') or {}
        return {'status':token(row.get('status')),'handler':token(row.get('handler')),
            'row_sha256':sha(canonical(row)),
            'claim_sha256':sha(canonical(row.get('owner_claim'))),
            'result_sha256':sha(canonical(row.get('result'))),
            'native_terminal_sha256':sha(canonical(row.get('native_project_terminal'))),
            'claim_pid':claim.get('pid') if type(claim.get('pid')) is int else None,
            'has_claim':bool(claim),'has_result':row.get('result') is not None}
    def compare(old,current):
        return {field:old.get(field)==current.get(field) for field in
            ('owner_claim','result','native_project_terminal')}
    try:
        at=time.time()
        receipt,receipt_raw,_=obj(root/'state/dispatcher'/('project_runtime_update_'+UPDATE_HISTORY_REQUEST+'.json'),2*1024*1024)
        expected=set(UPDATE_HISTORY_CHANGED_IDS)
        if (str(receipt.get('request'))!=UPDATE_HISTORY_REQUEST or
                set(receipt.get('history_preservation',{}).get('changed_claim_or_result_ids',[]))!=expected):
            raise ValueError('UPDATE_RECEIPT_SCOPE')
        backup=root/'state/dispatcher/project_runtime_update_rollback'/UPDATE_HISTORY_REQUEST
        before,before_raw,_=obj(backup/'final_stopped_queue_snapshot.json',32*1024*1024)
        if sha(before_raw)!=receipt.get('final_stopped_queue_sha256'):
            raise ValueError('STOPPED_SNAPSHOT_PIN')
        state,state_raw,_=obj(root/'state/dispatcher/state.json',32*1024*1024)
        old=before.get('tasks');current=state.get('tasks')
        if not isinstance(old,dict) or not isinstance(current,dict):raise ValueError('QUEUE_SCHEMA')
        missing=sorted(set(old)-set(current));changed=[];changed_by_old_status=collections.Counter()
        terminal_changed=[];terminal_count=0
        for tid,row in old.items():
            if not isinstance(row,dict):raise ValueError('QUEUE_ROW_SCHEMA')
            now=current.get(tid) or {};same=compare(row,now)
            if not all(same.values()):changed.append(tid);changed_by_old_status[token(row.get('status')) or 'UNKNOWN']+=1
            if row.get('status') in ('done','completed','failed','cancelled','canceled','blocked'):
                terminal_count+=1
                if not all(same.values()):terminal_changed.append(tid)
        for tid in UPDATE_HISTORY_CHANGED_IDS:
            previous=old.get(tid) or {};now=current.get(tid) or {}
            emit('PROJECT_UPDATE_CHANGED_ROW',{'id':tid,'before':projection(previous),'current':projection(now),
                'same':compare(previous,now),'old_present':tid in old,'current_present':tid in current})
        project_ids=sorted(tid for tid,row in old.items() if row.get('handler')=='owner_native_project_work')
        if len(project_ids)>32:raise ValueError('PROJECT_HISTORY_BOUND')
        projects=[]
        for tid in project_ids:
            previous=old[tid];now=current.get(tid) or {};same=compare(previous,now)
            result=now.get('result') or {};native_receipt=result.get('receipt')
            exact_claim=bool(isinstance(native_receipt,dict) and native_receipt.get('claim')==now.get('owner_claim'))
            exact_hash=bool(isinstance(native_receipt,dict) and result.get('receipt_sha256')==sha(canonical(native_receipt)))
            proof=s03_receipt_check(native_receipt) if isinstance(native_receipt,dict) else {'verified':False}
            record={'id':tid,'before':projection(previous),'current':projection(now),'same':same,
                'receipt_current_claim_matches':exact_claim,'receipt_sha256_matches':exact_hash,'s03':proof}
            emit('PROJECT_UPDATE_EXISTING_PROJECT_ROW',record);projects.append(record)
        source=root/'projects/owner_executor/source_workspace';baseline=receipt.get('source_before') or {};files=baseline.get('files')
        if baseline.get('root')!=str(source) or not isinstance(files,dict) or len(files)!=28:
            raise ValueError('SOURCE_BASELINE_SCOPE')
        source_rows=[];total=0
        for relative,previous in sorted(files.items()):
            path=Path(relative)
            if path.is_absolute() or any(part in ('','.','..') or part.startswith('.') for part in path.parts):
                raise ValueError('SOURCE_PATH_SCOPE')
            raw,info=safe_read(source/path,2*1024*1024);total+=len(raw)
            if total>16*1024*1024:raise ValueError('SOURCE_BYTES_BOUND')
            now={'sha256':sha(raw),'mode':stat.S_IMODE(info.st_mode),'size':len(raw)}
            source_rows.append({'path':relative,'before':previous,'current':now,'unchanged':previous==now})
        emit('PROJECT_UPDATE_SOURCE_PRESERVATION',{'request':UPDATE_HISTORY_REQUEST,'count':len(source_rows),
            'before_files_sha256':baseline.get('files_sha256'),'all_bytes_modes_unchanged':all(row['unchanged'] for row in source_rows),
            'current_files_sha256':sha(canonical({row['path']:row['current'] for row in source_rows})),
            'changed': [row for row in source_rows if not row['unchanged']],
            'source_tree_writes':0,'scope':'OBSERVED_SOURCE_DIFF_NOT_AN_AUTOMATIC_LOSS_CLASSIFICATION'})
        config_raw,_=safe_read(root/'config/owner_native_subagents.json',2*1024*1024)
        emit('PROJECT_UPDATE_HISTORY',{'request':UPDATE_HISTORY_REQUEST,'observed_at':at,
            'baseline_sha256':sha(before_raw),'current_state_sha256':sha(state_raw),'receipt_file_sha256':sha(receipt_raw),
            'old_count':len(old),'current_count':len(current),'missing_old_ids':missing,
            'changed_claim_or_result_count':len(changed),'changed_by_old_status':dict(changed_by_old_status),
            'changed_outside_reported_ids':[token(tid) for tid in changed if tid not in expected][:100],
            'terminal_status_rows_checked':terminal_count,'terminal_changed_ids':[token(tid) for tid in terminal_changed][:100],
            'existing_project_rows':len(projects),'all_existing_project_claim_results_unchanged':all(all(row['same'].values()) for row in projects),
            'all_existing_project_receipts_s03_verified':all(row['receipt_current_claim_matches'] and row['receipt_sha256_matches']
                and row['s03'].get('verified') is True for row in projects),
            'config_sha256':sha(config_raw),'config_matches_update':sha(config_raw)==receipt.get('installed_files',{}).get('config/owner_native_subagents.json'),
            'native_writes':0,'scope':'READ_ONLY_CURRENT_STATE_VS_EXACT_FINAL_STOPPED_SNAPSHOT'})
    except Exception as exc:
        reason=str(exc) if isinstance(exc,ValueError) and re.fullmatch(r'[A-Z_]{1,100}',str(exc)) else type(exc).__name__
        emit('PROJECT_UPDATE_HISTORY_ERROR',{'request':UPDATE_HISTORY_REQUEST,'reason':reason,'native_writes':0})
