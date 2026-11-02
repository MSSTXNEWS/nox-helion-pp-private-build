"""Bounded native work on the ORIGINAL S03 tasks/audit, without a new schema.

Only the native host calls this adapter. Renderer payloads cannot register Python
callbacks, paths or ForgeJob objects. One in-process job executes at a time;
interrupted RUNNING work stays HOLD until an explicit native resubmission.
"""
from __future__ import annotations
from datetime import datetime, timezone
import json
import hashlib
from dataclasses import asdict
import threading

class NativeQueueHold(RuntimeError):
    pass

def scope_key(scope):
    values = [getattr(scope,k,None) for k in ('tenant','principal','chat_id')]
    if any(type(v) is not str or not 1 <= len(v) <= 128 for v in values):
        raise PermissionError('AUTHENTICATED_NATIVE_SCOPE_REQUIRED')
    return dict(zip(('tenant','principal','chat_id'),values))

def _json(value):
    text=json.dumps(value,ensure_ascii=False,sort_keys=True,allow_nan=False)
    if len(text.encode('utf-8'))>160000:
        raise NativeQueueHold('S03_RESULT_QUOTA')
    return text

class NativeWorkQueue:
    def __init__(self, actor, *, authorize, stop_requested, stop_epoch=None):
        if not callable(getattr(actor,'call',None)) or not all(callable(x) for x in (authorize,stop_requested)):
            raise ValueError('ORIGINAL_STORE_ACTOR_NATIVE_CALLBACKS_REQUIRED')
        self.actor,self.authorize,self.stop_requested=actor,authorize,stop_requested
        self._lock=threading.Lock();self._thread=None;self._closed=False
        self.stop_epoch=stop_epoch if callable(stop_epoch) else (lambda:0)
        self._forge_jobs={}
        self._active_task=None

    def _event(self,store,tid,action,data):
        # The unchanged original _audit inserts into the existing S03 audit table.
        _json(data)
        store._audit('NOX_NATIVE_WORK_'+action,tid,data)

    def enqueue(self, scope, *, kind, payload, permission):
        key=scope_key(scope)
        epoch=self.stop_epoch()
        if (kind not in ('SELF_WRITE','FORGE') or self.stop_requested() or
                self.stop_epoch()!=epoch or
                self.authorize(scope,permission,payload) is not True):
            raise PermissionError('NATIVE_QUEUE_CONSENT_REQUIRED')
        frozen=json.loads(_json(payload))
        def require_live_permission():
            if (self.stop_requested() or self.stop_epoch()!=epoch or
                    self.authorize(scope,permission,frozen) is not True):
                raise PermissionError('NATIVE_QUEUE_REVOKED')
        def write(store):
            require_live_permission()
            # Preserve the original tasks schema and DRAFT status until OWNER review.
            title=str(frozen.get('task',kind))[:500].strip()
            if not title:raise ValueError('BOUNDED_TASK_TITLE_REQUIRED')
            with store.conn:
                now=datetime.now(timezone.utc).isoformat()
                tid=store.conn.execute('INSERT INTO tasks(title,created_at,updated_at) VALUES(?,?,?)',(title,now,now)).lastrowid
                store._audit('TASK_DRAFT_CREATED',tid,{})
                self._event(store,tid,'CREATED',{'scope':key,'kind':kind,'payload':frozen,'state':'QUEUED'})
                # Revoke within the original SQLite transaction to undo tasks AND audit.
                require_live_permission()
            return tid
        return self.actor.call(write)

    def _read(self,store,scope,tid):
        row=store.conn.execute("SELECT metadata FROM audit WHERE item_id=? AND action='NOX_NATIVE_WORK_CREATED' ORDER BY id DESC LIMIT 1",(tid,)).fetchone()
        if row is None:raise NativeQueueHold('S03_TASK_NOT_FOUND')
        record=json.loads(row[0])
        if record.get('scope')!=scope_key(scope):raise PermissionError('S03_TASK_SCOPE_DENIED')
        latest=store.conn.execute("SELECT action,metadata,at FROM audit WHERE item_id=? AND action LIKE 'NOX_NATIVE_WORK_%' ORDER BY id DESC LIMIT 1",(tid,)).fetchone()
        state=json.loads(latest[1]);record.update(task_id=tid,state=state.get('state','HOLD'),last_at=latest[2])
        if record['state']=='RUNNING' and self._active_task != (tuple(scope_key(scope).values()),tid):
            record['runtime_state']='INTERRUPTED_HOLD'
        if 'result' in state:record['result']=state['result']
        return record

    def get(self,scope,tid):
        if type(tid) is not int or tid<1:raise ValueError('S03_TASK_ID_REQUIRED')
        return self.actor.call(lambda store:self._read(store,scope,tid))

    def list(self,scope,*,limit=30):
        if type(limit) is not int or not 1<=limit<=100:raise ValueError('BOUNDED_QUEUE_READ_REQUIRED')
        def read(store):
            rows=store.conn.execute("SELECT item_id,metadata FROM audit WHERE action='NOX_NATIVE_WORK_CREATED' ORDER BY id DESC LIMIT 1000").fetchall()
            ids=[tid for tid,raw in rows if json.loads(raw).get('scope')==scope_key(scope)][:limit]
            return [self._read(store,scope,tid) for tid in ids]
        return list(self.actor.call(read))

    def record(self,scope,tid,state,result,*,expected_epoch=None,permission=None):
        # A worker's provisional RESULT is not accepted after native STOP,
        # epoch change or scoped owner lease revocation. HOLD receipts made by
        # the exception path intentionally do not claim an owner permission.
        if expected_epoch is not None and (type(expected_epoch) is not int or
                                           type(permission) is not str or not permission):
            raise ValueError('NATIVE_RESULT_EXACT_OWNER_FENCE_REQUIRED')
        frozen=json.loads(_json(result))
        def require_live_result_owner():
            if expected_epoch is not None and (
                    self.stop_requested() or self.stop_epoch()!=expected_epoch or
                    self.authorize(scope,permission,{'task_id':tid}) is not True):
                raise NativeQueueHold('NATIVE_RESULT_OWNER_REVOKED')
        def write(store):
            require_live_result_owner()
            self._read(store,scope,tid)
            with store.conn:
                require_live_result_owner()
                self._event(store,tid,'RESULT',{'scope':scope_key(scope),'state':state,'result':frozen})
                # The original S03 audit may block; roll back DONE (and its
                # audit row) if STOP/ACL/consent was revoked during the insert.
                require_live_result_owner()
            return True
        return self.actor.call(write)

    def _start(self,scope,tid,callback,permission,*,allowed_states=('QUEUED','PAUSED')):
        if not callable(callback):raise ValueError('NATIVE_CALLABLE_REQUIRED')
        epoch=self.stop_epoch()
        with self._lock:
            if self._closed or self._thread is not None and self._thread.is_alive():
                raise NativeQueueHold('EXISTING_HOST_WORKER_BUSY')
            def claim(store):
                row=self._read(store,scope,tid)
                if row['state'] not in allowed_states:
                    raise NativeQueueHold('S03_TASK_ALREADY_CLAIMED_OR_TERMINAL')
                def require_live_claim_permission():
                    if (self.stop_requested() or self.stop_epoch()!=epoch or
                            self.authorize(scope,permission,{'task_id':tid}) is not True):
                        raise PermissionError('NATIVE_WORK_REVOKED')
                require_live_claim_permission()
                with store.conn:
                    self._event(store,tid,'CLAIM',{'scope':scope_key(scope),'state':'RUNNING','permission':permission})
                    # STOP/ACL/epoch revocation during SQLite audit must roll back CLAIM.
                    require_live_claim_permission()
                return True
            self.actor.call(claim)
            self._active_task=(tuple(scope_key(scope).values()),tid)
            def run():
                try:
                    if self.stop_requested() or self.stop_epoch()!=epoch:raise NativeQueueHold('NATIVE_STOP')
                    result=callback()
                    if not isinstance(result,dict):raise NativeQueueHold('INVALID_NATIVE_RESULT')
                    state=result.get('status','HOLD')
                    if self.stop_requested() or self.stop_epoch()!=epoch:
                        result={'status':'HOLD','reason':'NATIVE_STOP_EPOCH_CHANGED','weights_updated':False};state='HOLD'
                    self.record(scope,tid,state,result,expected_epoch=epoch,permission=permission)
                except Exception as exc:
                    # Public records contain stable class/code only, never source prompts/paths.
                    code=str(exc) if str(exc).replace('_','').isalnum() and len(str(exc))<=100 else type(exc).__name__
                    self.record(scope,tid,'HOLD',{'status':'HOLD','reason':code,'weights_updated':False})
                finally:
                    self._active_task=None
            self._thread=threading.Thread(target=run,name='NOX-existing-S03-task',daemon=True)
            self._thread.start()
        return {'status':'QUEUED','task_id':tid,'durable_s03':True,'execution_completed':False}

    def submit_source(self,scope,tid,callback):
        return self._start(scope,tid,callback,'selfbuilder.propose')

    def register_forge(self,scope,job):
        """Native configuration only. Never accepts a dictionary from renderer."""
        from .background_forge import ForgeJob
        if not isinstance(job,ForgeJob):raise ValueError('NATIVE_FORGE_JOB_REQUIRED')
        key=(tuple(scope_key(scope).values()),job.run_id)
        seal=hashlib.sha256(json.dumps(asdict(job),sort_keys=True,default=str).encode()).hexdigest()
        def existing(store):
            rows=store.conn.execute("SELECT item_id,metadata FROM audit WHERE action='NOX_NATIVE_WORK_CREATED' ORDER BY id DESC").fetchall()
            for tid,raw in rows:
                row=json.loads(raw)
                if row.get('scope')==scope_key(scope) and row.get('kind')=='FORGE' and row.get('payload',{}).get('run_id')==job.run_id:
                    if row['payload'].get('job_sha256')!=seal:raise NativeQueueHold('FORGE_JOB_IDENTITY_DRIFT')
                    return tid
            return None
        tid=self.actor.call(existing)
        if tid is None:
            tid=self.enqueue(scope,kind='FORGE',payload={'task':job.task_id,'run_id':job.run_id,'task_id':job.task_id,'job_sha256':seal},permission='training.start')
        self._forge_jobs[key]=(tid,job)
        return tid

    def resolve(self,scope,job_id):
        item=self._forge_jobs.get((tuple(scope_key(scope).values()),job_id))
        if item is None:raise NativeQueueHold('NATIVE_FORGE_JOB_NOT_CONFIGURED')
        self.get(scope,item[0])
        return item[1]

    def submit(self,scope,job,callback):
        key=(tuple(scope_key(scope).values()),job.run_id)
        item=self._forge_jobs.get(key)
        if item is None or item[1] is not job:raise PermissionError('EXACT_NATIVE_FORGE_JOB_REQUIRED')
        permission='training.resume' if self.get(scope,item[0])['state']=='PAUSED' else 'training.start'
        return self._start(scope,item[0],callback,permission)

    def submit_followup(self,scope,job,callback,permission='training.merge'):
        """CAS a completed native FORGE task to its approved merge operation.

        Rehydrate only an existing exact job; merge never creates/requeues a task.
        """
        from .background_forge import ForgeJob
        if not isinstance(job,ForgeJob) or permission!='training.merge':
            raise PermissionError('EXACT_NATIVE_MERGE_FOLLOWUP_REQUIRED')
        key=(tuple(scope_key(scope).values()),job.run_id)
        seal=hashlib.sha256(json.dumps(asdict(job),sort_keys=True,default=str).encode()).hexdigest()
        def resolve_existing(store):
            rows=store.conn.execute("SELECT item_id,metadata FROM audit WHERE action='NOX_NATIVE_WORK_CREATED' ORDER BY id DESC").fetchall()
            for tid,raw in rows:
                created=json.loads(raw)
                if created.get('scope')==scope_key(scope) and created.get('kind')=='FORGE' and created.get('payload',{}).get('run_id')==job.run_id:
                    if created['payload'].get('job_sha256')!=seal:raise NativeQueueHold('FORGE_JOB_IDENTITY_DRIFT')
                    current=self._read(store,scope,tid)
                    if current['state']!='ADAPTER_CANDIDATE_PENDING_E07':raise NativeQueueHold('COMPLETED_ADAPTER_REQUIRED_FOR_MERGE')
                    return tid
            raise NativeQueueHold('DURABLE_COMPLETED_FORGE_TASK_REQUIRED')
        tid=self.actor.call(resolve_existing)
        self._forge_jobs[key]=(tid,job)
        return self._start(scope,tid,callback,permission,allowed_states=('ADAPTER_CANDIDATE_PENDING_E07',))

    def last_run(self,scope,job):
        key=(tuple(scope_key(scope).values()),job.run_id)
        item=self._forge_jobs.get(key)
        if item is None:raise NativeQueueHold('NATIVE_FORGE_JOB_NOT_CONFIGURED')
        def read(store):
            self._read(store,scope,item[0])
            # Cadence belongs to the scope, not a fresh run_id (which would bypass it).
            rows=store.conn.execute("SELECT a.at,c.metadata,a.metadata FROM audit a JOIN audit c ON c.item_id=a.item_id AND c.action='NOX_NATIVE_WORK_CREATED' WHERE a.action='NOX_NATIVE_WORK_CLAIM' ORDER BY a.id DESC").fetchall()
            for at,raw,claim_raw in rows:
                if json.loads(claim_raw).get('permission','training.start') not in ('training.start','training.resume'):continue
                created=json.loads(raw)
                if created.get('scope')==scope_key(scope) and created.get('kind')=='FORGE':return at
            return None

        value=self.actor.call(read)
        return datetime.fromisoformat(value) if value else None

    def load_transaction(self,scope,transaction_id):
        if type(transaction_id) is not str or not 1<=len(transaction_id)<=128:raise ValueError('TRANSACTION_ID_REQUIRED')
        def read(store):
            rows=store.conn.execute("SELECT metadata FROM audit WHERE action='NOX_MODEL_SELECTION_TRANSACTION' ORDER BY id DESC").fetchall()
            for (raw,) in rows:
                record=json.loads(raw)
                if record.get('scope')==scope_key(scope) and record.get('record',{}).get('transaction_id')==transaction_id:return record['record']
            return None
        return self.actor.call(read)

    def record_transaction(self,scope,transaction_id,record):
        if type(record) is not dict or record.get('transaction_id')!=transaction_id:raise ValueError('TRANSACTION_ID_MISMATCH')
        frozen=json.loads(_json(record));key=scope_key(scope)
        transitions={None:{'PREPARED'},'PREPARED':{'SELECTED_PENDING_NATIVE_E07','PREVIOUS_MODEL_SELECTION_RESTORED'},
                     'SELECTED_PENDING_NATIVE_E07':{'PREVIOUS_MODEL_SELECTION_RESTORED'},'PREVIOUS_MODEL_SELECTION_RESTORED':set()}
        def write(store):
            previous=None
            rows=store.conn.execute("SELECT metadata FROM audit WHERE action='NOX_MODEL_SELECTION_TRANSACTION' ORDER BY id DESC").fetchall()
            for (raw,) in rows:
                row=json.loads(raw)
                if row.get('scope')==key and row.get('record',{}).get('transaction_id')==transaction_id:previous=row['record'];break
            if previous==frozen:return True
            old=previous.get('status') if previous else None
            if frozen.get('status') not in transitions.get(old,set()):raise NativeQueueHold('MODEL_TRANSACTION_CAS_HOLD')
            if previous and {k:v for k,v in previous.items() if k!='status'}!={k:v for k,v in frozen.items() if k!='status'}:
                raise NativeQueueHold('MODEL_TRANSACTION_IDENTITY_DRIFT')
            with store.conn:store._audit('NOX_MODEL_SELECTION_TRANSACTION',0,{'scope':key,'record':frozen})
            return True
        return self.actor.call(write)

    def is_busy(self):
        with self._lock:return self._thread is not None and self._thread.is_alive()

    def close(self,timeout=5):
        with self._lock:self._closed=True;thread=self._thread
        if thread is not None:thread.join(timeout=timeout)
        if thread is not None and thread.is_alive():raise NativeQueueHold('NATIVE_TASK_NOT_DRAINED')
