"""Connect project plans to the existing sole dispatcher and persistent pool."""
from __future__ import annotations

import time

import owner_project_executor as executor
from owner_subagent_processes import GateError


class ProjectBinding:
    def __init__(self, native):
        self.native = native
        self.config = native.config['project_executor']
        executor.validate_config(self.config)
        self.terminal_cache = set()

    @staticmethod
    def reference(params):
        return {key:params[key] for key in ('plan_sha256', 'contract_sha256') if key in params}

    def validate_row(self, row):
        params = row['params']
        if (set(params) - {'parent_task_id', 'plan_sha256', 'contract_sha256'}
                or not isinstance(params.get('parent_task_id'), str)
                or row['source_sha256'] != self.native.source):
            raise GateError('HOLD_PROJECT_CATALOG_SCOPE')
        reference = self.reference(params)
        if 'plan_sha256' in reference:
            plan = executor.load_plan(reference, self.config)
        else:
            from owner_project_model_bridge import _check_pins
            _check_pins(self.config)
            plan = executor.load_contract_metadata(reference, self.config)
        if (plan['task_id'] != row['id'] or plan['queue_id'] != row.get('queue_id')
                or plan['parent_task_id'] != params['parent_task_id']):
            raise GateError('HOLD_PROJECT_CATALOG_PLAN_IDENTITY')
        return plan

    def claim(self, task, owner_pids):
        import owner_subagent_dispatcher as binding
        native = self.native
        plan = self.validate_row(task)
        if sorted(owner_pids) != sorted(row['pid'] for row in native.process_readback()):
            raise GateError('HOLD_SUBAGENT_POOL_IDENTITY_CHANGED')
        job_id = 'nox-project-' + binding.digest(binding.encoded({
            'task':task['id'], 'reference':self.reference(task['params'])}))[:24]
        admission = {'schema':binding.RECEIPT, 'phase':'PROJECT_QUEUE_ADMITTED_NOT_EXECUTED',
                     'task_id':task['id'], 'parent_task_id':plan['parent_task_id'],
                     'queue_id':task['queue_id'], 'job_id':job_id,
                     'plan_sha256':task['params'].get('plan_sha256'),
                     'contract_sha256':task['params'].get('contract_sha256'),
                     'source_sha256':native.source, 'original_task_accepted':False}
        row = {'id':task['id'], 'handler':executor.PROJECT_HANDLER,
               'class':'owner_order', 'lane':'owner_order', 'queue_id':task['queue_id'],
               'parent_task_id':plan['parent_task_id'], 'scope':plan['acceptance_scope'],
               'original_task_accepted':False, 'priority':binding.autonomy.PRIORITIES[task['priority']],
               'status':'blocked', 'deps':task['deps'], 'locks':[], 'retries':0, 'max_retries':1,
               'timeout_sec':180 if 'plan_sha256' in task['params'] else 1810,
               'title':task['title'], 'source':binding.SCHEMA,
               'params':{**task['params'], 'source_sha256':native.source, 'job_id':job_id},
               'native_admission':admission, 'note':'WAIT_S03_ADMISSION_READBACK'}
        with native.lock, native.ns['_qlock']:
            if native.stop_active() or not native.owner_allowed() or not native.writer_lease():
                raise GateError('HOLD_OWNER_STOP_OR_WRITER_LEASE')
            if task['id'] in native.state['tasks']:
                raise GateError('HOLD_SUBAGENT_DUPLICATE_TASK')
            rows = [value for value in native.state['tasks'].values()
                    if value.get('handler') in native.allowed_handlers()]
            if sum(value.get('status') in ('pending', 'running')
                   or value.get('note') == 'WAIT_S03_ADMISSION_READBACK' for value in rows) >= 3:
                raise GateError('HOLD_NATIVE_GLOBAL_WORKER_CAP')
            row['native_queue_sequence'] = 1 + max((value.get('native_queue_sequence', 0)
                for value in rows if type(value.get('native_queue_sequence', 0)) is int), default=0)
            native.state['tasks'][task['id']] = row
            native.ns['save_state'](native.state)
        proof = binding.remember(admission)
        with native.ns['_qlock']:
            row.update(status='pending', note='ADMITTED_NOT_EXECUTED', native_admission_s03=proof)
            native.ns['save_state'](native.state)
        native.admissions[task['id']] = admission
        return {'job_id':job_id}

    def _gate(self, task):
        native = self.native
        return (not native.stop_active() and native.owner_allowed() and native.writer_lease()
                and native._claim_current(task, durable=True))

    def _finish(self, task, event, execution_claim):
        import owner_subagent_dispatcher as binding
        native = self.native
        evidence = event['project_evidence']
        if (evidence.get('task_id') != task['id']
                or evidence.get('parent_task_id') != task['parent_task_id']
                or evidence.get('queue_id') != task['queue_id']
                or evidence.get('original_task_accepted') is not False
                or event.get('project_evidence_sha256') != binding.digest(binding.encoded(evidence))):
            raise GateError('HOLD_PROJECT_FINAL_EVIDENCE')
        integrated = evidence.get('state') == 'INTEGRATED'
        if integrated and (evidence.get('integration_verified') is not True
                or evidence.get('tests', {}).get('passed') is not True):
            raise GateError('HOLD_PROJECT_INTEGRATION_PROOF')
        # Sanitization is performed before the final digest and exact S03 write,
        # matching the existing native queue's own result sanitization.
        event = native.ns['owner_mentor'].clean(event)
        evidence = event['project_evidence']
        event['project_evidence_sha256'] = binding.digest(binding.encoded(evidence))
        result = {'schema':binding.RECEIPT,
                  'phase':'PROJECT_WORK_INTEGRATED_ORIGINAL_NOT_ACCEPTED' if integrated
                          else 'PROJECT_WORK_BLOCKED_ORIGINAL_NOT_ACCEPTED',
                  'task_id':task['id'], 'parent_task_id':task['parent_task_id'],
                  'queue_id':task['queue_id'], 'job_id':task['params']['job_id'],
                  'claim':task['owner_claim'], 'execution_claim':execution_claim,
                  'source_sha256':native.source, 'plan_sha256':evidence['plan_sha256'],
                  'scope':evidence['acceptance_scope'], 'worker_result':event,
                  'finished_at':time.time(), 'original_task_accepted':False,
                  'project_source_changed':evidence.get('project_source_changed'), 'live_service_deployed':False,
                  'recovery_required':evidence.get('state') == 'HOLD_RECOVERY_REQUIRED'}
        result['repository_export_required'] = integrated
        if not native.writer_lease() or not native._claim_current(task, durable=True):
            raise GateError('HOLD_PROJECT_RECEIPT_CURRENT_CLAIM')
        proof = binding.remember(result)
        receipt_sha = binding.digest(binding.encoded(result))
        info = {'schema':binding.RECEIPT, 'verified':True, 'scope':evidence['acceptance_scope'],
                'receipt':result, 's03':proof, 'receipt_sha256':receipt_sha,
                'original_task_accepted':False, 'project_source_changed':evidence.get('project_source_changed')}
        with native.ns['_qlock']:
            task['native_project_terminal'] = info
            native.ns['save_state'](native.state)
        self.terminal_cache.add(receipt_sha)
        return (True if integrated else False), info

    def _planner_failure(self, task, event, identity, contract, claim):
        import owner_subagent_dispatcher as binding
        receipt = event.get('planner_receipt')
        if (event.get('passed') is not False or not isinstance(receipt, dict)
                or receipt.get('task_id') != task['id']
                or receipt.get('contract_sha256') != task['params']['contract_sha256']
                or receipt.get('original_task_accepted') is not False
                or event.get('reference') != self.reference(task['params'])
                or event.get('prepared_claim') != claim):
            raise GateError('HOLD_PROJECT_PLANNER_RESULT_PROOF')
        evidence = {'schema':executor.EVIDENCE_SCHEMA, 'task_id':task['id'],
                    'parent_task_id':task['parent_task_id'], 'queue_id':task['queue_id'],
                    'plan_sha256':None, 'contract_sha256':task['params']['contract_sha256'],
                    'claim':claim, 'root_id':contract['root_id'],
                    'acceptance_scope':contract['acceptance_scope'], 'original_task_accepted':False,
                    'worker':{key:identity[key] for key in ('pid', 'ppid', 'process_starttime')},
                    'state':'BLOCKED_PLANNER', 'reason':str(event.get('state'))[:300],
                    'project_source_changed':False, 'model_commands_executed':False,
                    'finished_at':time.time()}
        event.update(project_evidence=evidence,
                     project_evidence_sha256=binding.digest(binding.encoded(evidence)))
        return self._finish(task, event, claim)

    def handle(self, task):
        import owner_subagent_dispatcher as binding
        native = self.native
        approved = next((row for row in native.catalog['tasks'] if row['id'] == task.get('id')), None)
        params = task.get('params') or {}
        if (approved is None or approved.get('handler') != executor.PROJECT_HANDLER
                or params.get('source_sha256') != native.source
                or {key:value for key,value in params.items() if key not in ('source_sha256', 'job_id')}
                    != approved['params']
                or task.get('queue_id') != approved['queue_id']
                or not native._claim_current(task, durable=True)):
            return False, 'HOLD_PROJECT_NATIVE_CLAIM'
        reference = self.reference(params)
        claim = task['owner_claim']['nonce']
        try:
            specification = self.validate_row(approved)
            if not self._gate(task):
                return 'wait', 'HOLD_OWNER_STOP_OR_WRITER_LEASE'
            # A previous source commit is adopted through exact journal/readback,
            # never by applying the patch again after losing its S03 ACK.
            prior = task.get('native_project_attempt')
            if prior and prior.get('claim') != claim:
                old_worker = prior.get('worker', {})
                live = binding.process_identity(old_worker.get('pid', -1))
                if live and live.get('process_starttime') == old_worker.get('process_starttime'):
                    owned = any(value['pid'] == live['pid'] and value['process_starttime'] == live['process_starttime']
                                for value in native.process_readback())
                    busy = native.pool and task['id'] in native.pool.active.values()
                    if not owned or busy:
                        return 'wait', 'HOLD_PROJECT_PREVIOUS_WORKER_NOT_RECONCILED'
                previous_reference = task.get('native_project_generated_reference') or reference
                if 'plan_sha256' in previous_reference:
                    recovered = executor.recover_interrupted(previous_reference, self.config, prior['claim'],
                                                             gate=lambda:self._gate(task))
                    if recovered['state'] == 'INTEGRATED':
                        event = {'state':'INTEGRATED', 'project_evidence':recovered,
                                 'project_evidence_sha256':binding.digest(binding.encoded(recovered)),
                                 'planner_receipt':task.get('native_project_planner_receipt'),
                                 'recovered_without_replay':True}
                        return self._finish(task, event, prior['claim'])
                    if (recovered['state'] in executor.TERMINAL_WITHOUT_CHANGES
                            and recovered.get('reason') != 'PREVIOUS_ATTEMPT_RECONCILED'):
                        event = {'state':recovered['state'], 'project_evidence':recovered,
                                 'project_evidence_sha256':binding.digest(binding.encoded(recovered)),
                                 'planner_receipt':task.get('native_project_planner_receipt'),
                                 'recovered_without_replay':True}
                        return self._finish(task, event, prior['claim'])
                with native.ns['_qlock']:
                    task.pop('native_project_generated_reference', None)
                    task.pop('native_project_planner_receipt', None)
            with native.lock:
                reason = native._fresh_admission_reason(leaf_only=True)
                if reason:
                    return 'wait', reason
                if native.pool is None and not native.ensure_processes(3):
                    return 'wait', 'HOLD_SUBAGENT_POOL_NOT_READY'
                role = next((role for role in binding.ROLES if role not in native.pool.active), None)
                if role is None:
                    return 'wait', 'WAIT_PROJECT_WORKER'
                identity = next((row for row in native.process_readback() if row['role'] == role), None)
                if identity is None:
                    return 'wait', 'HOLD_PROJECT_WORKER_IDENTITY'
                native.interrupted.pop(task['id'], None)
                with native.ns['_qlock']:
                    task['native_project_attempt'] = {'claim':claim, 'worker':identity,
                                                      'plan_sha256':reference.get('plan_sha256')}
                    native.ns['save_state'](native.state)
                native.pool.submit({'id':task['id'], 'subagent':role, 'task':task['title'], 'depends_on':[],
                    '_native_project_context':{'reference':reference, 'config':self.config, 'claim':claim}})
            deadline = time.monotonic() + (1800 if 'plan_sha256' not in reference else 170)
            event = None
            cancellation_at = None
            while time.monotonic() < deadline:
                if not self._gate(task):
                    with native.lock:
                        if native.pool:
                            native.pool.cancel(task['id'])
                    cancellation_at = cancellation_at or time.monotonic()
                    if time.monotonic() - cancellation_at > 3:
                        native.close_pool('WAIT_PROJECT_CANCEL_RECONCILIATION')
                        return 'wait', 'WAIT_PROJECT_CANCEL_RECONCILIATION'
                with native.lock:
                    reason = native.interrupted.pop(task['id'], None)
                    if reason:
                        return 'wait', reason
                    native._drain()
                    event = native.completed.pop(task['id'], None)
                if event is not None:
                    break
                time.sleep(.05)
            if event is None:
                native.close_pool('HOLD_PROJECT_WORKER_TIMEOUT')
                return 'wait', 'HOLD_PROJECT_WORKER_TIMEOUT_RECONCILE'
            if event.get('pid') != identity['pid']:
                raise GateError('HOLD_PROJECT_WORKER_PID')
            if 'plan_sha256' not in reference:
                if not event.get('project_evidence'):
                    return self._planner_failure(task, event, identity, specification, claim)
                generated = event.get('reference')
                if (not isinstance(generated, dict) or set(generated) != {'plan_sha256', 'contract_sha256'}
                        or generated.get('contract_sha256') != reference['contract_sha256']
                        or event.get('prepared_claim') != claim):
                    raise GateError('HOLD_PROJECT_GENERATED_REFERENCE')
                plan = executor.load_plan(generated, self.config)
                if plan['task_id'] != task['id'] or plan['parent_task_id'] != task['parent_task_id']:
                    raise GateError('HOLD_PROJECT_GENERATED_IDENTITY')
                reference = generated
                with native.ns['_qlock']:
                    if not native._claim_current(task, durable=True):
                        raise GateError('HOLD_PROJECT_GENERATED_CLAIM')
                    task['native_project_generated_reference'] = reference
                    task['native_project_planner_receipt'] = native.ns['owner_mentor'].clean(event.get('planner_receipt'))
                    task['native_project_attempt']['plan_sha256'] = reference['plan_sha256']
                    native.ns['save_state'](native.state)
            evidence = event.get('project_evidence') or {}
            worker = evidence.get('worker') or {}
            if (event.get('pid') != identity['pid'] or worker.get('pid') != identity['pid']
                    or worker.get('process_starttime') != identity['process_starttime']
                    or evidence.get('claim') != claim
                    or evidence.get('plan_sha256') != reference['plan_sha256']
                    or event.get('project_evidence_sha256') != binding.digest(binding.encoded(evidence))):
                raise GateError('HOLD_PROJECT_WORKER_PROOF')
            if event.get('state') == 'PREPARED':
                # The parent holds both its process lock and the existing sole
                # queue writer lock during the short journaled source commit.
                with native.lock, native.ns['_qlock']:
                    try:
                        outcome = executor.integrate_prepared(reference, self.config, claim,
                                                              gate=lambda:self._gate(task))
                    except executor.ProjectHold as exc:
                        if str(exc) == 'WAIT_PROJECT_INTEGRATION_LOCK':
                            return 'wait', str(exc)
                        # integrate_prepared contains its own rollback after it
                        # starts writing. An exception here is a pre-write gate.
                        outcome = {**evidence, 'state':'STOPPED' if str(exc) == 'STOPPED'
                                   else 'BLOCKED_SOURCE_CHANGED', 'reason':str(exc),
                                   'project_source_changed':False, 'finished_at':time.time()}
                event.update(state=outcome['state'], project_evidence=outcome,
                             project_evidence_sha256=binding.digest(binding.encoded(outcome)))
            return self._finish(task, event, claim)
        except (OSError, ValueError, executor.ProjectHold, GateError) as exc:
            # If source mutation may have started, retain the reservation until
            # the journal and worker have been reconciled. Do not report DONE.
            return 'wait', str(exc) if isinstance(exc, (executor.ProjectHold, GateError)) else 'HOLD_PROJECT_NATIVE_IO'

    def terminal_for_capacity(self, task):
        import owner_subagent_dispatcher as binding
        if task.get('status') not in ('blocked', 'failed', 'cancelled'):
            return False
        value = task.get('native_project_terminal') or {}
        receipt = value.get('receipt')
        if (not isinstance(receipt, dict) or receipt.get('task_id') != task.get('id')
                or receipt.get('phase') != 'PROJECT_WORK_BLOCKED_ORIGINAL_NOT_ACCEPTED'
                or receipt.get('original_task_accepted') is not False
                or value.get('receipt_sha256') != binding.digest(binding.encoded(receipt))):
            return False
        native = self.native
        if native.pool and task['id'] in native.pool.active.values():
            return False
        sha = value['receipt_sha256']
        if sha not in self.terminal_cache:
            if not binding.s03_readback(receipt):
                return False
            self.terminal_cache.add(sha)
        evidence = (receipt.get('worker_result') or {}).get('project_evidence') or {}
        return evidence.get('state') in executor.TERMINAL_WITHOUT_CHANGES

    def admitted(self, task):
        # A proved blocked attempt requires a new repaired plan/task identity.
        # Mentor prose may not silently revive and re-run the same failed plan.
        return not bool(task.get('native_project_terminal'))

    def reconcile(self):
        """Reconcile dead former workers before releasing or retrying claims."""
        import owner_subagent_dispatcher as binding
        native = self.native
        if native.stop_active() or not native.owner_allowed() or not native.writer_lease():
            return
        with native.lock, native.ns['_qlock']:
            for task in native.state['tasks'].values():
                if task.get('handler') != executor.PROJECT_HANDLER:
                    continue
                if task.get('native_project_terminal'):
                    # The generic mentor may propose retry; this adapter needs
                    # a new reviewed plan for a proved failed implementation.
                    info = task['native_project_terminal']
                    receipt = info.get('receipt') or {}
                    if (receipt.get('phase') == 'PROJECT_WORK_BLOCKED_ORIGINAL_NOT_ACCEPTED'
                            and task.get('status') in ('pending', 'retry', 'wait')
                            and (not native.pool or task['id'] not in native.pool.active.values())
                            and binding.s03_readback(receipt)):
                        task.update(status='blocked', note='PROJECT_ATTEMPT_TERMINAL_REPAIR_PLAN_REQUIRED')
                        native.ns['save_state'](native.state)
                    continue
                prior = task.get('native_project_attempt')
                owner = task.get('owner_claim') or {}
                if (task.get('status') != 'blocked' or not isinstance(prior, dict)
                        or owner.get('pid') == binding.os.getpid()
                        or not binding.CLAIM.fullmatch(str(prior.get('claim', '')))
                        or task.get('native_project_recovery_count', 0) >= 2):
                    continue
                worker = prior.get('worker') or {}
                alive = binding.process_identity(worker.get('pid', -1))
                if alive and alive.get('process_starttime') == worker.get('process_starttime'):
                    continue
                if binding.process_identity(owner.get('pid', -1)):
                    continue
                reference = task.get('native_project_generated_reference') or self.reference(task['params'])
                gate = lambda: (not native.stop_active() and native.owner_allowed() and native.writer_lease()
                                and task.get('status') == 'blocked' and task.get('owner_claim') == owner)
                try:
                    outcome = (executor.recover_interrupted(reference, self.config, prior['claim'], gate=gate)
                               if 'plan_sha256' in reference else {'state':'NO_PLAN_NO_SHARED_WRITE'})
                except (OSError, ValueError, executor.ProjectHold) as exc:
                    task['native_project_recovery_hold'] = str(exc)[:240]
                    native.ns['save_state'](native.state)
                    continue
                recovery = {'schema':binding.RECEIPT, 'phase':'PROJECT_INTERRUPTED_ATTEMPT_RECONCILED',
                            'task_id':task['id'], 'job_id':task['params']['job_id'],
                            'old_claim':owner, 'old_worker':worker, 'reference':reference,
                            'outcome':outcome['state'], 'source_sha256':native.source,
                            'original_task_accepted':False, 'reconciled_at':time.time()}
                proof = binding.remember(recovery)
                task.update(status='pending', note='PROJECT_PREVIOUS_WORKER_RECONCILED', next_try=0,
                            native_project_recovery=recovery, native_project_recovery_s03=proof,
                            native_project_recovery_count=task.get('native_project_recovery_count', 0)+1)
                native.ns['save_state'](native.state)

    def verify(self, task, evidence):
        import owner_subagent_dispatcher as binding
        if not isinstance(evidence, dict):
            return None
        receipt = evidence.get('receipt')
        if (not isinstance(receipt, dict) or receipt.get('task_id') != task.get('id')
                or receipt.get('phase') != 'PROJECT_WORK_INTEGRATED_ORIGINAL_NOT_ACCEPTED'
                or receipt.get('claim') != task.get('owner_claim')
                or receipt.get('parent_task_id') != task.get('parent_task_id')
                or receipt.get('queue_id') != task.get('queue_id')
                or receipt.get('original_task_accepted') is not False
                or receipt.get('source_sha256') != self.native.source
                or evidence.get('receipt_sha256') != binding.digest(binding.encoded(receipt))):
            return None
        proof = binding.s03_readback(receipt)
        if not proof:
            return None
        return {'kind':'bounded_native_project_change', 'task_id':task['id'],
                'parent_task_id':task['parent_task_id'], 'scope':receipt['scope'],
                'receipt_sha256':proof['receipt_sha256'], 'source_sha256':self.native.source,
                's03_item_id':proof['s03_item_id'], 'project_source_changed':True,
                'original_task_accepted':False, 'live_service_deployed':False}
