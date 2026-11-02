"""Live SELF-BUILDER composition on the original OneHost S03/P02 services.

Candidates are staged outside the managed Git checkout; nothing here merges,
executes generated source, changes the installed EXE, or changes model weights.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import threading
from .evolution import EvolutionWorker, EvolutionHold
from .seed import attest_seed
from .onehost_queue import scope_key
from .source_catalog import inspect_managed_sources
from .a1_initiative_bridge import A1InitiativeBridge
from .firstboot_coordinator import FirstBootCoordinator

_HEAD=re.compile(r'^[a-f0-9]{40}(?:[a-f0-9]{24})?$')

def _without_transient_preview(receipt):
    """Retain durable S03 proof, never the raw source/diff/test preview."""
    if not isinstance(receipt, dict) or 'preview' not in receipt:
        return receipt
    return {key: value for key, value in receipt.items() if key != 'preview'}


class ManagedSource:
    def __init__(self,root):self.root=Path(root) if root is not None else None
    def git(self,*args):
        if self.root is None or not (self.root/'.git').exists() or (self.root/'.git').is_symlink():raise EvolutionHold('MANAGED_GIT_SOURCE_REQUIRED')
        if any(p.is_symlink() for p in (self.root,*self.root.parents)):raise EvolutionHold('SOURCE_REPARSE_HOLD')
        p=subprocess.run(['git','-C',str(self.root),*args],stdin=subprocess.DEVNULL,capture_output=True,timeout=10,check=False)
        if p.returncode or len(p.stdout)>2_000_000:raise EvolutionHold('MANAGED_GIT_READ_HOLD')
        return p.stdout.decode('utf-8','strict')
    def head(self):
        value=self.git('rev-parse','HEAD').strip()
        if not _HEAD.fullmatch(value):raise EvolutionHold('SOURCE_HEAD_REQUIRED')
        return value
    def admitted(self,head):
        return self.head()==head and self.git('status','--porcelain','--untracked-files=no').strip()==''
    def verify_memory(self,row,head):
        ref=row.get('source_ref','')
        prefix='git:'+head+':'
        if row.get('kind')!='OWNER_FACT' or not ref.startswith(prefix):return None
        path=ref[len(prefix):]
        if not path or PurePosixPath(path).is_absolute() or any(x in ('','..','.') for x in path.split('/')) or '\\' in path:return None
        data=self.git('show',head+':'+path)
        excerpt=row.get('content')
        if not isinstance(excerpt,str) or not excerpt or excerpt not in data:return None
        return {'source_id':ref,'text':excerpt[:5000],'verified':True,
                'source_sha256':hashlib.sha256(data.encode()).hexdigest(),
                'verification':'S03_OWNER_FACT_MATCHED_EXACT_GIT_HEAD'}

class OneHostSelfBuilder:
    def __init__(self, *, queue, coder, memory_scope, authorize, stop_requested,
                 source_root=None, workspace=None, seed_archive=None, model_inventory=None, source_paths=(), stop_epoch=None, request_stop=None):
        if not all(callable(x) for x in (coder,memory_scope,authorize,stop_requested)):
            raise ValueError('EXISTING_ONEHOST_CALLBACKS_REQUIRED')
        self.queue,self.coder,self.memory_scope=queue,coder,memory_scope
        self.authorize,self.native_stop=authorize,stop_requested
        self.source=ManagedSource(source_root)
        self.workspace=Path(workspace) if workspace is not None else None
        self.seed_archive=Path(seed_archive) if seed_archive is not None else None
        self.model_inventory=model_inventory
        self._stop=threading.Event()
        self.request_stop=request_stop
        self.stop_epoch=stop_epoch if callable(stop_epoch) else (lambda:0)
        if not isinstance(source_paths,(tuple,list)) or len(source_paths)>30 or any(
                type(p) is not str or not p or PurePosixPath(p).is_absolute() or
                any(x in ('','..','.') for x in p.split('/')) or '\\' in p or
                PurePosixPath(p).suffix.lower() not in ('.py','.cs','.mjs','.js','.css','.html','.json','.md')
                for p in source_paths) or len(set(source_paths))!=len(source_paths):
            raise ValueError('BOUNDED_NATIVE_SOURCE_PATHS_REQUIRED')
        self.source_paths=tuple(source_paths)
        # The original OneHost owner MAY attach existing A ports after native
        # SID/ACL/policy setup. No scheduler, thread, service or S03 DB is made.
        self._a_native_bridge = None
        self._a_firstboot = None
        self._a_owner_session = None
        self._a_native_epoch = None

    def bind_native_megapat_a(self, session, *, initiative_bridge, firstboot):
        """Connect already-reviewed A1–A6 callbacks to this existing owner.

        This method must be called by authenticated native startup code,
        never by renderer JSON or generated model/website text.
        """
        self._read_scope(session)
        if (not isinstance(initiative_bridge, A1InitiativeBridge) or
                not isinstance(firstboot, FirstBootCoordinator) or
                self._a_native_bridge is not None or
                self._a_firstboot is not None or
                self.native_stop() is not False or self._stop.is_set() or
                self.authorize(session, 'evolution.autonomy.read', {}) is not True):
            raise PermissionError('A_EXISTING_NATIVE_OWNER_BINDING_REQUIRED')
        epoch = self.stop_epoch()
        if type(epoch) is not int or epoch < 0:
            raise PermissionError('A_NATIVE_STOP_EPOCH_REQUIRED')
        self._a_native_bridge = initiative_bridge
        self._a_firstboot = firstboot
        self._a_owner_session = session
        self._a_native_epoch = epoch
        return {'schema': 'NOX-A-NATIVE-OWNER-BINDING-v1',
                'state': 'PORTS_BOUND_AWAITING_NATIVE_STARTUP',
                'native_windows_acceptance': False,
                'firstboot_executed': False,
                'existing_idle_tick_invoked': False}

    def native_a_boot(self, session, *, now):
        """Native startup hook; use ORIGINAL FirstBoot and A.1 only."""
        self._a_guard(session)
        first = self._a_firstboot.run(session, now=now)
        self._a_guard(session)
        # Installation and public research have INDEPENDENT native consent.
        # Missing optional P01/P03 download approval must not silently grant
        # downloads, nor block separately signed read-only research.
        if (type(first) is not dict or
                first.get('schema') != 'NOX-FIRSTBOOT-RECEIPT-v1'):
            raise PermissionError('A_ORIGINAL_FIRSTBOOT_RECEIPT_REQUIRED')
        first_state = first.get('status')
        accepted = ('HOLD', 'STOPPED', 'QUEUED_NOT_INSTALLED',
                    'ALREADY_QUEUED_NOT_INSTALLED', 'ALREADY_PRESENT')
        if first_state not in accepted or first_state == 'STOPPED':
            return {'schema': 'NOX-A-NATIVE-BOOT-v1',
                    'state': 'HOLD', 'firstboot': first,
                    'initiative': None, 'e07': False,
                    'firstboot_download_approved_by_a1': False}
        # A1InitiativeBridge.boot separately verifies ORIGINAL signed research
        # policy, exact source HEAD, owner ACL and STOP epoch before enabling.
        initiative = self._a_native_bridge.boot(session, now=now)
        self._a_guard(session)
        ready = (type(initiative) is dict and
                 initiative.get('state') == 'READY_FOR_EXISTING_IDLE_TICK')
        return {'schema': 'NOX-A-NATIVE-BOOT-v1',
                'state': 'READY_FOR_EXISTING_IDLE_TICK' if ready else 'HOLD',
                'firstboot': first, 'initiative': initiative, 'e07': False,
                'firstboot_pending_separate_consent': first_state == 'HOLD',
                'firstboot_download_approved_by_a1': False}

    def native_a_tick(self, session, *, now):
        """Called ONLY by preexisting OneHost idle scheduler, not a new agent."""
        self._a_guard(session)
        result = self._a_native_bridge.tick(session, now=now)
        self._a_guard(session)
        return result

    def _a_guard(self, session):
        self._read_scope(session)
        if (self._a_native_bridge is None or
                self._a_firstboot is None or
                session != self._a_owner_session or
                self.native_stop() is not False or
                self._stop.is_set() or
                self.stop_epoch() != self._a_native_epoch or
                self.authorize(session, 'evolution.autonomy.read', {}) is not True):
            raise PermissionError('A_NATIVE_STOP_SCOPE_OR_POLICY_HOLD')
    def _read_scope(self,session):
        scope_key(session)
        validate=getattr(session,'validate',None)
        if not callable(validate):raise PermissionError('NATIVE_SESSION_REQUIRED')
        validate()
        if 'chat.commands' not in session.allowed:raise PermissionError('NATIVE_COMMAND_SCOPE_DENIED')
    def reset_for_native_consent(self,session):
        if self.queue.is_busy() or self.native_stop() or self.authorize(session,'selfbuilder.propose',{}) is not True:
            raise PermissionError('FRESH_IDLE_NATIVE_CONSENT_REQUIRED')
        self._stop.clear()
    def _stopped(self):return self._stop.is_set() or self.native_stop() is True
    def recall(self,session,task,sources=()):
        scope=self.memory_scope(session)
        if type(scope) is not dict or set(scope)!= {'project_id','persona_id','core_id'}:
            raise EvolutionHold('NATIVE_PERSONA_PROJECT_CORE_REQUIRED')
        head=self.source.head()
        rows=self.queue.actor.call(lambda store:store.core_memories.recall(**scope,query='',limit=30))
        evidence=[]
        for row in rows:
            if self.source_paths and row.get('source_ref') not in {'git:'+head+':'+p for p in self.source_paths}:continue
            verified=self.source.verify_memory(row,head)
            if verified is not None and (not sources or verified['source_id'] in sources):evidence.append(verified)
        return evidence
    def _capabilities(self,session):
        reason=None
        try:
            head=self.source.head()
            if not self.source.admitted(head):raise EvolutionHold('MANAGED_SOURCE_DIRTY')
            if self.workspace is None or not self.workspace.is_dir():raise EvolutionHold('TRUSTED_STAGING_REQUIRED')
            if self.workspace.resolve().is_relative_to(self.source.root.resolve()):raise EvolutionHold('STAGING_MUST_BE_OUTSIDE_LIVE_SOURCE')
            if not self.source_paths and not self.recall(session,'source coverage'):raise EvolutionHold('VERIFIED_S03_SOURCE_REQUIRED')
        except (EvolutionHold,OSError,ValueError,PermissionError):
            head=None;reason='MANAGED_SOURCE_OR_S03_EVIDENCE_HOLD'
        actions={}
        for action in ('selfbuilder.worker.status','selfbuilder.study.queue','selfbuilder.learning.proofs','selfbuilder.coding.models'):
            available=action!='selfbuilder.coding.models' or callable(self.model_inventory)
            actions[action]={'available':available,'status':'AVAILABLE' if available else 'HOLD','ownerConsent':False}
        # Read-only owner inventory stays callable even when source configuration
        # is absent; the response then explicitly reports HOLD, not fake loading.
        actions['selfbuilder.sources.inspect']={'available':True,'status':'NATIVE_REQUEST_AVAILABLE','ownerConsent':False}
        seed_ok=self.seed_archive is not None and self.seed_archive.is_file()
        actions['selfbuilder.seed.inspect']={'available':seed_ok,'status':'AVAILABLE' if seed_ok else 'HOLD','ownerConsent':False}
        permit=reason is None and not self._stopped()
        for action in ('selfbuilder.propose','selfbuilder.worker.start'):
            actions[action]={'available':bool(permit),'status':'AVAILABLE' if permit else 'HOLD','ownerConsent':True}
        actions['selfbuilder.worker.stop']={'available':True,'status':'AVAILABLE','ownerConsent':True}
        actions['selfbuilder.feedback']={'available':True,'status':'OWNER_REVIEW_REQUIRED','ownerConsent':True}
        actions['selfbuilder.train.request']={'available':False,'status':'USE_EXISTING_P04_APPROVED_JOB','ownerConsent':True}
        return {'actions':actions,'source_head':head,'reason':reason,'status':'SOURCE_SERVICE','weights_updated':False}
    def command(self,session,args):
        self._read_scope(session)
        if type(args) is not dict or type(args.get('action')) is not str:raise ValueError('EXACT_SELFBUILDER_ACTION_REQUIRED')
        action=args['action']
        if action=='selfbuilder.capabilities':return self._capabilities(session)
        if action=='selfbuilder.sources.inspect':
            return inspect_managed_sources(self.source,self.source_paths)
        if action=='selfbuilder.worker.status':
            return {'status':'STOPPED' if self._stopped() else 'READY_FOR_OWNER_TASK',
                    'tasks':self.queue.list(session),'weights_updated':False}
        if action in ('selfbuilder.study.queue','selfbuilder.learning.proofs'):
            rows=self.queue.list(session)
            if action.endswith('proofs'):rows=[x for x in rows if x.get('result')]
            return {'status':'S03_READ','tasks':rows,'weights_updated':False}
        if action=='selfbuilder.seed.inspect':
            if self.seed_archive is None:raise EvolutionHold('ORIGINAL_SEED_NOT_CONFIGURED')
            return attest_seed(self.seed_archive)
        if action=='selfbuilder.coding.models':
            if not callable(self.model_inventory):raise EvolutionHold('P02_MODEL_INVENTORY_UNAVAILABLE')
            return {'status':'DISCOVERY_RESPONDED','models':self.model_inventory(),'download_performed':False}
        if action=='selfbuilder.worker.stop':
            if self.authorize(session,action,{}) is not True:raise PermissionError('NATIVE_STOP_SCOPE_DENIED')
            self._stop.set()
            if callable(self.request_stop):self.request_stop(session)
            token=getattr(self.coder,'stop_event',None)
            if isinstance(token,threading.Event):token.set()
            return {'status':'STOP_REQUESTED','weights_updated':False}
        if action=='selfbuilder.feedback':return self._feedback(session,args)
        if action not in ('selfbuilder.propose','selfbuilder.worker.start'):raise ValueError('UNKNOWN_SELFBUILDER_ACTION')
        if action=='selfbuilder.worker.start' and 'task' not in args:
            if set(args)-{'action','task_id'}:raise ValueError('EXACT_QUEUED_TASK_REQUIRED')
            if self.authorize(session,'selfbuilder.propose',args) is not True:raise PermissionError('NATIVE_QUEUE_RESUME_CONSENT_REQUIRED')
            rows=[self.queue.get(session,args['task_id'])] if 'task_id' in args else self.queue.list(session)
            queued=next((r for r in reversed(rows) if r.get('kind')=='SELF_WRITE' and r.get('state')=='QUEUED'),None)
            if queued is None:return {'status':'IDLE','weights_updated':False}
            if not self.source.admitted(queued['payload']['source_head']):raise EvolutionHold('QUEUED_SOURCE_HEAD_DRIFT')
            if self.native_stop():raise EvolutionHold('GLOBAL_STOP_OR_REVOKE')
            self._stop.clear()
            return self._submit_payload(session,queued['task_id'],queued['payload'])
        if set(args)-{'action','task'}:raise ValueError('UI_SOURCE_TICKET_OR_PATH_NOT_ALLOWED')
        task=args.get('task')
        if type(task) is not str or not 15<=len(task)<=3000:raise ValueError('TASK_REQUIRED_15_TO_3000')
        if self._stop.is_set():self.reset_for_native_consent(session)
        if self._stopped():raise EvolutionHold('GLOBAL_STOP_OR_REVOKE')
        head=self.source.head()
        if not self.source.admitted(head):raise EvolutionHold('EXACT_CLEAN_SOURCE_HEAD_REQUIRED')
        if self.authorize(session,'selfbuilder.propose',{'head':head,'task':task}) is not True:
            raise PermissionError('NATIVE_SOURCE_GENERATION_CONSENT_REQUIRED')
        self._import_sources(session,head)
        evidence=self.recall(session,task)
        if not evidence:raise EvolutionHold('VERIFIED_S03_SOURCE_REQUIRED')
        if self.workspace is None or not self.workspace.is_dir():raise EvolutionHold('TRUSTED_STAGING_REQUIRED')
        if self.workspace.resolve().is_relative_to(self.source.root.resolve()):raise EvolutionHold('STAGING_MUST_BE_OUTSIDE_LIVE_SOURCE')
        if self.source_paths and {r['source_id'] for r in evidence} != {'git:'+head+':'+p for p in self.source_paths}:
            raise EvolutionHold('CONFIGURED_SOURCE_COVERAGE_HOLD')
        payload={'task':task,'source_head':head,'source_ids':[r['source_id'] for r in evidence]}
        tid=self.queue.enqueue(session,kind='SELF_WRITE',payload=payload,permission='selfbuilder.propose')
        return self._submit_payload(session,tid,payload)
    def _submit_payload(self,session,tid,payload):
        host=_EvolutionHost(self,session,tid,payload)
        def execute():
            result=EvolutionWorker(host,workspace=str(self.workspace)).tick()
            return {'status':result.status,'task_id':tid,'receipt':_without_transient_preview(result.receipt),'weights_updated':False}
        ack=self.queue.submit_source(session,tid,execute)
        return {**ack,'ack':True,'run_id':'S03-'+str(tid),'source_head':payload['source_head']}
    def _import_sources(self,session,head):
        """Explicitly consented exact-HEAD excerpts into ORIGINAL scoped S03."""
        if not self.source_paths:return
        scope=self.memory_scope(session)
        prepared=[]
        for path in self.source_paths:
            text=self.source.git('show',head+':'+path)
            if not text.strip():raise EvolutionHold('NATIVE_SOURCE_EMPTY')
            prepared.append(('git:'+head+':'+path,text[:5000].strip()))
        if not self.source.admitted(head):raise EvolutionHold('SOURCE_HEAD_DRIFT')
        def write(store):
            if self._stopped() or self.authorize(session,'selfbuilder.propose',{'head':head}) is not True:
                raise PermissionError('SOURCE_IMPORT_REVOKED')
            current=store.core_memories.recall(**scope,query='',limit=100)
            known={r['source_ref']:r for r in current}
            for ref,text in prepared:
                if ref in known:
                    if known[ref]['content']!=text or known[ref]['kind']!='OWNER_FACT':raise EvolutionHold('S03_SOURCE_REFERENCE_DRIFT')
                    continue
                store.core_memories.remember(**scope,content=text,kind='OWNER_FACT',source_ref=ref,owner_confirmed=True)
            return True
        self.queue.actor.call(write)

    def _feedback(self,session,args):
        tid=args.get('task_id');outcome=args.get('outcome')
        if outcome not in ('ACCEPTED','REJECTED','NO_GAIN'):raise ValueError('OWNER_OUTCOME_REQUIRED')
        if self.authorize(session,'selfbuilder.feedback',{'task_id':tid,'outcome':outcome}) is not True:
            raise PermissionError('OWNER_REVIEW_REQUIRED')
        row=self.queue.get(session,tid)
        result=row.get('result',{})
        receipt=result.get('receipt')
        if row.get('kind')!='SELF_WRITE' or not isinstance(receipt,dict) or not receipt.get('patch_sha256'):
            raise EvolutionHold('DURABLE_CANDIDATE_RECEIPT_REQUIRED')
        lesson={'schema':'NOX-SELFBUILDER-OWNER-LESSON-v1','task_id':tid,'outcome':outcome,
                'patch_sha256':receipt['patch_sha256'],'source_head':receipt['source_head'],
                'reviewer':scope_key(session),'weights_updated':False,'integrated':False}
        self.queue.record(session,tid,'OWNER_'+outcome,{'status':'OWNER_'+outcome,'receipt':receipt,'lesson':lesson})
        return {'status':'OWNER_REVIEW_RECORDED','task_id':tid,'S03_WRITE_PERFORMED':True,'integrated':False,'weights_updated':False}

class _EvolutionHost:
    def __init__(self,service,session,tid,payload):self.service,self.session,self.tid,self.payload=service,session,tid,payload;self.claimed=False;self.epoch=service.stop_epoch()
    def worker_enabled(self):return self.service.authorize(self.session,'selfbuilder.propose',{'task_id':self.tid}) is True
    def stop_requested(self):return self.service._stopped() or self.service.stop_epoch()!=self.epoch
    def claim_task(self):
        if self.claimed:return None
        self.claimed=True
        return {**self.payload,'task_id':'S03-'+str(self.tid),'kind':'SELF_WRITE','candidate_language':'multilang','session':self.session}
    def native_authorize(self,session,route,args):
        return not self.stop_requested() and self.service.authorize(session,route,args) is True and self.source_admission(self.payload['source_head'])
    def source_admission(self,head):return self.service.source.admitted(head)
    def current_source_head(self):return self.service.source.head()
    def target_admission(self,head,paths):
        if not self.source_admission(head):return False
        tracked=set(self.service.source.git('ls-tree','-r','--name-only',head).splitlines())
        return not any(p in tracked or (self.service.source.root/p).exists() for p in paths)
    def release_ticket(self,task):
        return {'task_id':task['task_id'],'owner_id':'1','head':self.current_source_head(),
                'existing_code_checked':bool(self.recall(self.session,task['task'],task['source_ids'])),
                'critical_sources_complete':bool(self.payload['source_ids']),'overlapping_owner_paths':False,
                'required_scope_fixed':True,'code_preimage_sha':'ABSENT'}
    def recall(self,*args):return self.service.recall(*args)
    def generate(self,*args):return self.service.coder(*args)
    def record_result(self,tid,status,receipt):
        return self.service.queue.record(self.session,self.tid,status,{'status':status,'receipt':_without_transient_preview(receipt),'weights_updated':False})
    def finish_task(self,tid,status):
        # Completion is audit-only; original task is never marked OWNER ACCEPTED here.
        return self.service.queue.get(self.session,self.tid).get('state')==status
