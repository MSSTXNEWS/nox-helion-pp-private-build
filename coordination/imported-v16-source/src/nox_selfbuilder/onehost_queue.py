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
        if (type(epoch) is not int or epoch < 0 or
                kind not in ('SELF_WRITE','FORGE') or
                self.stop_requested() is not False or
                self.stop_epoch()!=epoch or
                self.authorize(scope,permission,payload) is not True):
            raise PermissionError('NATIVE_QUEUE_CONSENT_REQUIRED')
        frozen=json.loads(_json(payload))
        def require_live_permission():
            live_epoch = self.stop_epoch()
            if (self.stop_requested() is not False or type(live_epoch) is not int
                    or live_epoch != epoch or
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
        if (record['state']=='RUNNING' and
                (self._active_task != (tuple(scope_key(scope).values()),tid) or
                 self._thread is None or not self._thread.is_alive())):
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

    def record(self,scope,tid,state,result,*,expected_epoch=None,permission=None,permission_payload=None):
        # The exception path may append a nonaccepting HOLD. A terminal or
        # owner-review result ALWAYS requires the original native STOP/ACL grant.
        if expected_epoch is None:
            if (permission is not None or permission_payload is not None or
                    state != 'HOLD' or type(result) is not dict or
                    result.get('status') != 'HOLD' or result.get('weights_updated') is not False):
                raise PermissionError('NATIVE_RESULT_OWNER_FENCE_REQUIRED')
        elif (type(expected_epoch) is not int or expected_epoch < 0 or
              type(permission) is not str or not permission):
            raise ValueError('NATIVE_RESULT_EXACT_OWNER_FENCE_REQUIRED')
        authority = {'task_id': tid} if permission_payload is None else json.loads(_json(permission_payload))
        if (type(authority) is not dict or type(authority.get('task_id')) is not int or
                authority['task_id'] != tid or
                set(authority) - {'task_id', 'outcome'}):
            raise ValueError('NATIVE_RESULT_OWNER_PAYLOAD_REQUIRED')
        frozen=json.loads(_json(result))
        # An audit state cannot contradict the stored result. In particular,
        # no worker may persist a positive S03 state with a different status.
        if (type(state) is not str or not state or type(frozen) is not dict
                or frozen.get('status') != state):
            raise NativeQueueHold('S03_RESULT_STATUS_BINDING_HOLD')
        def require_live_result_owner():
            if expected_epoch is not None:
                observed_epoch=self.stop_epoch()
                if (self.stop_requested() is not False or
                        type(observed_epoch) is not int or observed_epoch != expected_epoch or
                        self.authorize(scope,permission,authority) is not True):
                    raise NativeQueueHold('NATIVE_RESULT_OWNER_REVOKED')
        def write(store):
            require_live_result_owner()
            work=self._read(store,scope,tid)
            if work.get('kind') == 'FORGE':
                # FORGE audit is evidence, not a model activation grant.
                # training.start/resume may publish only a bound original P04
                # receipt, never an invented COMPLETED or selected-model result.
                if (frozen.get('weights_updated') is not False or
                        ('activation_allowed' in frozen and frozen['activation_allowed'] is not False) or
                        (state != 'HOLD' and frozen.get('activation_allowed') is not False)):
                    raise NativeQueueHold('S03_FORGE_RESULT_ADMISSION_HOLD')
                if permission in ('training.start','training.resume') and state != 'HOLD':
                    proof=frozen.get('receipt_sha256')
                    if (state not in ('PAUSED','STOPPED','ADAPTER_CANDIDATE_PENDING_E07')
                            or frozen.get('run_id') != work.get('payload',{}).get('run_id')
                            or type(proof) is not str or len(proof) != 64
                            or any(c not in '0123456789abcdef' for c in proof)
                            or frozen.get('activation_allowed') is not False):
                        raise NativeQueueHold('S03_FORGE_RESULT_ADMISSION_HOLD')
                if permission == 'training.merge' and state != 'HOLD':
                    # A durable CLAIM alone is not a merged-weight receipt.
                    # Keep the original candidate-only status and both SHA witnesses.
                    proof_names = ('merge_receipt_sha256', 'merged_payload_sha256')
                    if (state != 'MERGED_CANDIDATE_PENDING_IMPORT' or any(
                            type(frozen.get(name)) is not str
                            or len(frozen[name]) != 64
                            or any(ch not in '0123456789abcdef' for ch in frozen[name])
                            for name in proof_names)):
                        raise NativeQueueHold('S03_FORGE_MERGE_RECEIPT_BINDING_HOLD')
            if work.get('kind') == 'FORGE' and state != 'HOLD':
                # A matching receipt-shaped hash is not proof that the native
                # GPU/QLoRA worker ever ran. Positive results must follow the
                # original owner-consented durable S03 CLAIM for this exact
                # task and permission, never a bare QUEUED job or stale claim.
                latest_claim = store.conn.execute(
                    "SELECT metadata FROM audit WHERE item_id=? AND action='NOX_NATIVE_WORK_CLAIM' ORDER BY id DESC LIMIT 1",
                    (tid,)).fetchone()
                claim = json.loads(latest_claim[0]) if latest_claim else {}
                if (work.get('state') != 'RUNNING'
                        or claim.get('state') != 'RUNNING'
                        or claim.get('scope') != scope_key(scope)
                        or claim.get('permission') != permission
                        or permission not in ('training.start', 'training.resume', 'training.merge')):
                    raise NativeQueueHold('S03_FORGE_UNCLAIMED_RESULT_HOLD')
            with store.conn:
                require_live_result_owner()
                if expected_epoch is None:
                    # The worker's error path may persist its first nonaccepting
                    # HOLD, but a later stale exception cannot replace an owner-
                    # authorized S03 RESULT or rewrite an already recorded HOLD.
                    # Original audit history and every earlier receipt stay intact.
                    prior = store.conn.execute(
                        "SELECT 1 FROM audit WHERE item_id=? AND action='NOX_NATIVE_WORK_RESULT' LIMIT 1",
                        (tid,)).fetchone()
                    if prior is not None:
                        raise NativeQueueHold('S03_UNFENCED_HOLD_AFTER_RESULT_DENIED')
                self._event(store,tid,'RESULT',{'scope':scope_key(scope),'state':state,'result':frozen})
                # STOP/ACL revocation during SQLite audit rolls back the result.
                require_live_result_owner()
            return True
        return self.actor.call(write)

    def _start(self,scope,tid,callback,permission,*,allowed_states=('QUEUED','PAUSED'),recover_interrupted=False):
        if not callable(callback):raise ValueError('NATIVE_CALLABLE_REQUIRED')
        epoch=self.stop_epoch()
        if type(epoch) is not int or epoch < 0:
            raise NativeQueueHold('NATIVE_STOP_EPOCH_INVALID')
        with self._lock:
            if self._closed or self._thread is not None and self._thread.is_alive():
                raise NativeQueueHold('EXISTING_HOST_WORKER_BUSY')
            def claim(store):
                row=self._read(store,scope,tid)
                # A previous process may have died after its durable CLAIM.
                # Only a freshly owner-consented training.resume may re-CLAIM
                # this exact interrupted S03 task; never revive a live worker.
                recovered = (recover_interrupted is True and
                             permission == 'training.resume' and
                             row['state'] == 'RUNNING' and
                             row.get('runtime_state') == 'INTERRUPTED_HOLD')
                if row['state'] not in allowed_states and not recovered:
                    raise NativeQueueHold('S03_TASK_ALREADY_CLAIMED_OR_TERMINAL')
                def require_live_claim_permission():
                    current_epoch=self.stop_epoch()
                    if (self.stop_requested() is not False or
                            type(current_epoch) is not int or current_epoch != epoch or
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
                    # SQLite CLAIM is not enduring authorization. Consent may be
                    # revoked after that transaction and before this worker starts.
                    # Never call self-write/Forge callbacks under a stale owner grant.
                    current_epoch=self.stop_epoch()
                    if (self.stop_requested() is not False or
                            type(current_epoch) is not int or current_epoch != epoch or
                            self.authorize(scope,permission,{'task_id':tid}) is not True):
                        raise NativeQueueHold('NATIVE_WORK_REVOKED_BEFORE_EXECUTION')
                    result=callback()
                    if not isinstance(result,dict):raise NativeQueueHold('INVALID_NATIVE_RESULT')
                    state=result.get('status','HOLD')
                    if self.stop_requested() is not False or self.stop_epoch()!=epoch:
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

    def forge_result(self,scope,job):
        """Exact owner-scoped S03 audit result; a P04 receipt file is not consent."""
        from .background_forge import ForgeJob
        if not isinstance(job,ForgeJob):
            raise PermissionError('EXACT_NATIVE_FORGE_JOB_REQUIRED')
        key=(tuple(scope_key(scope).values()),job.run_id)
        item=self._forge_jobs.get(key)
        if item is None or item[1] is not job:
            raise PermissionError('EXACT_NATIVE_FORGE_JOB_REQUIRED')
        return self.get(scope,item[0])

    def submit(self,scope,job,callback,*,resume=False):
        # The original native training.start is not an implicit restart.
        # A paused or previously interrupted RUNNING job requires a separate
        # explicit training.resume owner grant, validated again in _start.
        if type(resume) is not bool:
            raise PermissionError('EXPLICIT_NATIVE_FORGE_RESUME_FLAG_REQUIRED')
        key=(tuple(scope_key(scope).values()),job.run_id)
        item=self._forge_jobs.get(key)
        if item is None or item[1] is not job:raise PermissionError('EXACT_NATIVE_FORGE_JOB_REQUIRED')
        row=self.get(scope,item[0])
        interrupted=(row['state']=='RUNNING' and row.get('runtime_state')=='INTERRUPTED_HOLD')
        if resume:
            if row['state']!='PAUSED' and not interrupted:
                raise NativeQueueHold('FORGE_RESUME_REQUIRES_PAUSED_OR_INTERRUPTED_S03')
            return self._start(scope,item[0],callback,'training.resume',
                               allowed_states=('PAUSED',),recover_interrupted=interrupted)
        if row['state']!='QUEUED':
            raise NativeQueueHold('FORGE_START_REQUIRES_FRESH_QUEUED_S03')
        return self._start(scope,item[0],callback,'training.start',
                           allowed_states=('QUEUED',))

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
