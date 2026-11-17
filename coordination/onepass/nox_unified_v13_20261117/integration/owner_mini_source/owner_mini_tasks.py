"""Authenticated mini task intake into the EXISTING architect refill/state queue.

HTTP authentication belongs to the existing bridge. This module receives the
trusted owner principal from that bridge, never from the request body. Intake
is allowed during STOP; only the existing dispatcher executes reviewed plans.
"""
from __future__ import annotations
import ast
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import time
from contextlib import contextmanager

MARKER = 'NOX_MINI_EXISTING_QUEUE_BIND_V1'
SOURCE = 'NOX_MINI_OWNER_TASK_V1'
REQUEST_ID = re.compile(r'^[A-Za-z0-9_.:-]{1,128}$')
TASK_ID = re.compile(r'^owner\.mini\.[a-f0-9]{40}$')
TYPED_INTENTS = ('audit', 'training_status')
# This server-owned mapping was checked against the current WEB source tree.
# Client page_path is a route key, never a filesystem path or file allowlist.
PAGE_NAMES = ('calendar','chat','cinema','dispatcher','downloads','index','install',
              'memory','models','projects','resonance','settings','studio','system',
              'tools','training','world')
ROUTE_SOURCES = {'/'+name+'.html': ['site/'+name+'.html'] for name in PAGE_NAMES}
ROUTE_MAP_SHA = hashlib.sha256(json.dumps(ROUTE_SOURCES,sort_keys=True,separators=(',',':')).encode()).hexdigest()
STOP_NAMES = ('STOP','STOP.flag','stop.flag','.stop','program/STOP','state/STOP',
              'state/STOP.flag','state/OWNER_MAINTENANCE.flag')
MAX_FILE = 16*1024*1024


class MiniTaskError(ValueError):
    def __init__(self, code, http_status=400):
        super().__init__(code); self.code=code; self.http_status=http_status


def encoded(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def digest(value): return hashlib.sha256(encoded(value)).hexdigest()


def _read(path, maximum=MAX_FILE):
    path=Path(path)
    if any(p.is_symlink() for p in (path,*path.parents)):
        raise MiniTaskError('MINI_PATH_UNSAFE',503)
    try:
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        with os.fdopen(fd,'rb') as f:
            before=os.fstat(f.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size>maximum:
                raise MiniTaskError('MINI_FILE_SCOPE',503)
            raw=f.read(maximum+1);after=os.fstat(f.fileno())
        if len(raw)>maximum or (before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns):
            raise MiniTaskError('MINI_READ_CHANGED',503)
        return raw
    except FileNotFoundError: raise
    except OSError as e: raise MiniTaskError('MINI_STORAGE_UNAVAILABLE',503) from e


def _doc(path, maximum=MAX_FILE):
    try:
        row=json.loads(_read(path,maximum))
        if not isinstance(row,dict): raise ValueError()
        return row
    except (ValueError,UnicodeError) as e:
        if isinstance(e,MiniTaskError): raise
        raise MiniTaskError('MINI_DOCUMENT_INVALID',503) from e


def _atomic(path, value):
    raw=encoded(value)+b'\n'
    if len(raw)>MAX_FILE: raise MiniTaskError('MINI_INTAKE_FULL',429)
    fd,name=tempfile.mkstemp(prefix='.mini-',dir=path.parent)
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,'wb') as stream:
            stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.replace(name,path)
        parent=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(parent)
        finally:os.close(parent)
    finally:
        if os.path.exists(name):os.unlink(name)


def _principal(value):
    if not isinstance(value,str) or not value or len(value)>256:
        raise MiniTaskError('MINI_OWNER_PRINCIPAL_REQUIRED',403)
    return hashlib.sha256(value.encode()).hexdigest()


def _request(value):
    if not isinstance(value,str) or not REQUEST_ID.fullmatch(value):
        raise MiniTaskError('MINI_REQUEST_ID_INVALID')
    return value


def task_id_for(principal_id, request_id):
    return 'owner.mini.'+digest({'owner':_principal(principal_id),'request_id':_request(request_id)})[:40]


def normalize_context(context):
    if context is None:context={'page_path':'/index.html','title':'','theme':'','scope':'page'}
    if not isinstance(context,dict) or set(context)-{'page_path','title','theme','scope','selected_object'}:
        raise MiniTaskError('MINI_CONTEXT_INVALID')
    path=context.get('page_path');scope=context.get('scope','page')
    if not isinstance(path,str) or any(s in path for s in ('..','?','#','%','\\',':')):
        raise MiniTaskError('MINI_PAGE_ROUTE_INVALID')
    if path=='/':path='/index.html'
    if path.startswith('/nox-web-v29/'):path=path[len('/nox-web-v29'):]
    if not path.startswith('/'):path='/'+path
    if path not in ROUTE_SOURCES or scope not in ('page','site'):
        raise MiniTaskError('MINI_PAGE_ROUTE_INVALID')
    result={'page_path':path,'scope':scope}
    for field,limit in (('title',240),('theme',80),('selected_object',240)):
        value=context.get(field,'')
        if not isinstance(value,str) or len(value)>limit or '\x00' in value:
            raise MiniTaskError('MINI_CONTEXT_INVALID')
        if field!='selected_object' or value:result[field]=value
    result['route_map_sha256']=ROUTE_MAP_SHA
    result['source_files']=(list(ROUTE_SOURCES[path]) if scope=='page' else
                            [v for values in ROUTE_SOURCES.values() for v in values])
    # Site scope is only the explicitly supplied enum; never inferred from text.
    result['site_scope_explicit']=scope=='site' and context.get('scope')=='site'
    result['change_policy']={'shared_asset_edits':'require_scope_expansion' if scope=='page' else 'allowed_within_site',
                             'page_isolation_required':scope=='page'}
    return result


def _paths(root):
    root=Path(root)
    directory=root/'state/dispatcher'
    if not root.is_absolute() or any(p.is_symlink() for p in (directory,*directory.parents)) or not directory.is_dir():
        raise MiniTaskError('MINI_EXISTING_QUEUE_UNAVAILABLE',503)
    return root,directory,directory/'architect_refill.json'


@contextmanager
def _locked(root):
    root,directory,inbox=_paths(root)
    path=directory/'architect_refill.lock'
    if path.is_symlink():raise MiniTaskError('MINI_PATH_UNSAFE',503)
    fd=os.open(path,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX)
        if not stat.S_ISREG(os.fstat(fd).st_mode) or (os.fstat(fd).st_dev,os.fstat(fd).st_ino)!=(path.stat().st_dev,path.stat().st_ino):
            raise MiniTaskError('MINI_LOCK_CHANGED',503)
        yield root,directory,inbox
    finally:os.close(fd)


def _state(directory):
    try:row=_doc(directory/'state.json')
    except FileNotFoundError as e:raise MiniTaskError('MINI_EXISTING_QUEUE_UNAVAILABLE',503) from e
    if not isinstance(row.get('tasks'),dict):raise MiniTaskError('MINI_EXISTING_QUEUE_SCHEMA',503)
    return row


def _inbox(path):
    try:row=_doc(path)
    except FileNotFoundError:return {'tasks':[]}
    if not isinstance(row.get('tasks'),list) or len(row['tasks'])>20000 or any(not isinstance(t,dict) for t in row['tasks']):
        raise MiniTaskError('MINI_INTAKE_SCHEMA',503)
    return row


def _installed(root):
    try:source=_read(root/'scripts/nox_dispatcher_t855u.py',2*1024*1024).decode()
    except (FileNotFoundError,UnicodeError):raise MiniTaskError('MINI_DISPATCHER_BINDING_MISSING',503)
    if MARKER not in source or 'owner_mini_tasks.ingest_existing(globals(), st)' not in source:
        raise MiniTaskError('MINI_DISPATCHER_BINDING_MISSING',503)


def _stopped(root):
    return any((root/p).exists() or (root/p).is_symlink() for p in STOP_NAMES) or Path('/workspace/NOX_STOP').exists() or Path('/workspace/NOX_STOP').is_symlink()


def capabilities(root,principal_id):
    _principal(principal_id)
    with _locked(root) as (root,directory,inbox):
        _state(directory);_installed(root)
        return {'available':True,'queue':'existing_dispatcher','typed_intents':list(TYPED_INTENTS),
            'free_text':'awaiting_plan','owner_stop':_stopped(root),'execution_started':False,
            'route_map_sha256':ROUTE_MAP_SHA,'scopes':['page','site']}


def _project(row,replayed=False):
    status=row.get('status','unknown')
    proposal=row.get('mini_verified_proposal')
    draft=(status=='draft' or (row.get('mini_intent') is None and not row.get('owner_plan_id')))
    planning_state='plan_review_required' if proposal and draft else 'awaiting_plan' if draft else status
    return {'task_id':row['id'],'request_id':row['mini_request_id'],'state':planning_state,
        'queue_state':status,'queue':'existing_dispatcher','replayed':replayed,'executable':not draft,
        'planner_pending':draft,'execution_started':bool(row.get('owner_claim')) and not draft,
        'planning_state':row.get('mini_planning_state'),
        'plan_proposal':copy.deepcopy(proposal),
        'text':row['mini_text'],'intent':row.get('mini_intent'),'context':row['mini_context'],
        'created_at':row.get('mini_created_at'),'reason':row.get('owner_plan_wait') or row.get('note'),
        'plan_id':row.get('owner_plan_id')}


def _owned(row,owner):
    return isinstance(row,dict) and row.get('source')==SOURCE and row.get('mini_owner_sha256')==owner


def submit(root,principal_id,request_id,text,intent=None,context=None):
    owner=_principal(principal_id);request_id=_request(request_id)
    if not isinstance(text,str) or not text.strip() or len(text)>16000 or '\x00' in text:
        raise MiniTaskError('MINI_TEXT_INVALID')
    text=text.strip();ctx=normalize_context(context)
    if intent is None:
        intent={'audit':'audit','status':'audit','статус':'audit','проверь состояние нокс':'audit',
                'статус обучения':'training_status','training status':'training_status'}.get(text.casefold())
    if intent is not None and intent not in TYPED_INTENTS:raise MiniTaskError('MINI_INTENT_NOT_REVIEWED')
    payload={'text':text,'intent':intent,'context':ctx};fingerprint=digest(payload)
    tid=task_id_for(principal_id,request_id)
    with _locked(root) as (root,directory,inbox):
        _installed(root);state=_state(directory);handoff=_inbox(inbox)
        existing=state['tasks'].get(tid) or next((r for r in handoff['tasks'] if r.get('id')==tid),None)
        if existing is not None:
            if not _owned(existing,owner) or existing.get('mini_payload_sha256')!=fingerprint:
                raise MiniTaskError('MINI_REQUEST_CONFLICT',409)
            return _project(existing,True)
        if sum(r.get('source')==SOURCE for r in handoff['tasks'])>=256:
            raise MiniTaskError('MINI_INTAKE_FULL',429)
        planning={'user_text':text,'context':ctx,'requires_existing_c01_c08_s03':True,
                  'state':'awaiting_plan' if intent is None else 'reviewed_typed_plan'}
        params={'context':ctx,'planning_input':planning}
        if intent is not None:params['plan']={'schema':'NOX_OWNER_PLAN_REQUEST_V1','intent':intent}
        row={'id':tid,'handler':'owner_order','class':'owner_order','priority':0,'deps':[],
            'status':'draft' if intent is None else 'pending','lane':'owner_order','locks':[],
            'retries':0,'max_retries':1,'timeout_sec':90,'title':text[:180], 'source':SOURCE,
            'params':params,'mini_owner_sha256':owner,'mini_request_id':request_id,
            'mini_payload_sha256':fingerprint,'mini_text':text,'mini_intent':intent,'mini_context':ctx,
            'mini_created_at':time.time()}
        handoff['tasks'].append(row);_atomic(inbox,handoff)
        reread=next((r for r in _inbox(inbox)['tasks'] if r.get('id')==tid),None)
        if reread!=row:raise MiniTaskError('MINI_INTAKE_READBACK',503)
        return _project(row)


def lookup(root,principal_id,task_id):
    owner=_principal(principal_id)
    if not isinstance(task_id,str) or not TASK_ID.fullmatch(task_id):raise MiniTaskError('MINI_TASK_ID_INVALID')
    with _locked(root) as (_,directory,inbox):
        state=_state(directory);row=state['tasks'].get(task_id)
        if row is None:row=next((r for r in _inbox(inbox)['tasks'] if r.get('id')==task_id),None)
        if not _owned(row,owner):raise MiniTaskError('MINI_TASK_NOT_FOUND',404)
        return _project(row)


def lookup_request(root,principal_id,request_id):
    return lookup(root,principal_id,task_id_for(principal_id,request_id))


def list_tasks(root,principal_id,limit=50):
    owner=_principal(principal_id)
    if type(limit) is not int or not 1<=limit<=100:raise MiniTaskError('MINI_LIMIT_INVALID')
    with _locked(root) as (_,directory,inbox):
        rows={r.get('id'):r for r in _inbox(inbox)['tasks']}
        rows.update(_state(directory)['tasks'])
        selected=[r for r in rows.values() if _owned(r,owner)]
        selected.sort(key=lambda r:r.get('mini_created_at',0),reverse=True)
        return {'tasks':[_project(r) for r in selected[:limit]],'queue':'existing_dispatcher','has_more':len(selected)>limit}


def ingest_existing(namespace,st):
    """Existing dispatcher calls this under its one queue-writer lease.

    Intake COW -> durable existing save_state -> clear existing handoff. A
    crash before clearing only replays IDs, never an accepted task execution.
    """
    with namespace['_qlock']:
        mentor=namespace.get('owner_mentor')
        require=getattr(mentor,'require_dispatcher_writer',None)
        if not callable(require):raise MiniTaskError('MINI_EXISTING_WRITER_LEASE_REQUIRED',503)
        require(namespace)
        with _locked(namespace['ROOT']) as (_,directory,inbox):
            if not inbox.exists():return 0
            doc=_inbox(inbox);added=0
            proposal={k:copy.deepcopy(v) for k,v in st.items() if k!='tasks'}
            proposal['tasks']={tid:copy.deepcopy({k:v for k,v in row.items() if not k.startswith('_')})
                               for tid,row in st.get('tasks',{}).items()}
            for raw in doc['tasks']:
                task=copy.deepcopy(raw);tid=task.get('id')
                if not isinstance(tid,str) or not tid:continue
                cur=proposal.setdefault('tasks',{}).get(tid)
                if task.get('source')==SOURCE and cur is not None:
                    if cur.get('mini_payload_sha256')!=task.get('mini_payload_sha256'):
                        raise MiniTaskError('MINI_REQUEST_CONFLICT',409)
                    continue
                task.setdefault('status','pending');task.setdefault('retries',0);task.setdefault('max_retries',3)
                task.setdefault('timeout_sec',0);task.setdefault('lane',task.get('class'));task.setdefault('locks',[])
                task.setdefault('source','architect_refill')
                if cur is None:
                    proposal['tasks'][tid]=task;added+=1
                elif cur.get('status')=='running':continue
                elif (cur.get('status') in ('done','failed') and task.get('status')=='pending'
                        and tid.startswith(('arch.','selfheal.floor','keep.'))):
                    cur.update({k:v for k,v in task.items() if k!='id'});cur['status']='pending';cur['retries']=0;added+=1
            # Save even on an idempotent replay, and read back before unlink.
            namespace['save_state'](proposal)
            durable=_state(directory)
            if durable.get('tasks')!={tid:{k:v for k,v in t.items() if not k.startswith('_')} for tid,t in proposal['tasks'].items()}:
                raise MiniTaskError('MINI_QUEUE_READBACK',503)
            # Preserve running task object identity and its opaque resource
            # locks: existing worker callbacks hold references to these dicts.
            for tid,row in proposal['tasks'].items():
                if tid not in st['tasks']:st['tasks'][tid]=row
                elif {k:v for k,v in st['tasks'][tid].items() if not k.startswith('_')}!=row:
                    target=st['tasks'][tid]
                    for key in list(target):
                        if not key.startswith('_') and key not in row:del target[key]
                    target.update(row)
            for key,value in proposal.items():
                if key!='tasks':st[key]=value
            inbox.unlink()
            fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(fd)
            finally:os.close(fd)
            return added


def patch_dispatcher(source,expected_sha256):
    if hashlib.sha256(source.encode()).hexdigest()!=expected_sha256:
        raise MiniTaskError('MINI_DISPATCHER_SOURCE_CHANGED',409)
    if MARKER in source:return source
    tree=ast.parse(source);nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='ingest_architect_patch']
    if len(nodes)!=1:raise MiniTaskError('MINI_DISPATCHER_ANCHOR',409)
    node=nodes[0];lines=source.splitlines(True)
    replacement='# '+MARKER+'\ndef ingest_architect_patch(st):\n    import owner_mini_tasks\n    return owner_mini_tasks.ingest_existing(globals(), st)\n'
    result=''.join(lines[:node.lineno-1])+replacement+''.join(lines[node.end_lineno:])
    compile(result,'<existing-dispatcher-mini-intake>','exec')
    return result
