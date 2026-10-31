"""Verified P04 GPU training bridge: no other trainer, downloader or cloud fallback.

Owner's P04 path (Packages/P04/train_qlora.py) is the only training engine.
The caller must validate consent, model lock, rights/holdout and current GPU
before handing back exact invocation to the preexisting native P04 runner.
"""
from __future__ import annotations
import re
SHA=re.compile(r'^[a-f0-9]{64}$')
class ForgeHold(RuntimeError):pass

def request_gpu_training(*, model_sha, dataset_sha, owner_consent, rights_verified,
                         original_p04_readiness, profile='BALANCED'):
    if owner_consent is not True:raise ForgeHold('FORGE_OWNER_CONSENT_REQUIRED')
    if rights_verified is not True:raise ForgeHold('FORGE_DATA_RIGHTS_HOLD')
    if not (isinstance(model_sha,str) and SHA.fullmatch(model_sha) and isinstance(dataset_sha,str) and SHA.fullmatch(dataset_sha)):
        raise ForgeHold('MODEL_DATASET_SHA_REQUIRED')
    if profile not in {'ECO','BALANCED','INTENSIVE'}:raise ForgeHold('PROFILE_INVALID')
    if not isinstance(original_p04_readiness,dict):raise ForgeHold('P04_NATIVE_GPU_PREFLIGHT_REQUIRED')
    if original_p04_readiness.get('status')!='HARDWARE_READY_ONLY' or original_p04_readiness.get('runtime_training_verified') is not False:
        raise ForgeHold('P04_CUDA_HARDWARE_HOLD')
    # P04 preflight returns hardware-only, not rights/model proof or trained weights.
    return {'schema':'NOX-FORGE-ORIGINAL-P04-HANDOFF-v1',
        'status':'HANDOFF_TO_EXISTING_P04_NOT_TRAINED','base_sha256':model_sha,
        'dataset_sha256':dataset_sha,'profile':profile,'training_steps':0,'weights_updated':False,
        'trainer':'Packages/P04/train_qlora.py','next':'NATIVE_P04_APPROVED_TRAINER_RUN_AND_E07'}


class ExistingP04NativePorts:
    """Approved PACK01 route adapter, using native-selected jobs and one runner.

    No page-provided paths/permissions and no additional transport. Host submit
    runs the callable on its existing executor, so PAUSE/global STOP stay live.
    """
    METHODS = {
        'gpu.preflight': 'preflight', 'training.start': 'start',
        'training.pause': 'pause', 'training.resume': 'resume',
        'training.checkpoints': 'checkpoints', 'training.evaluate': 'evaluate',
    }

    def __init__(self, background, *, job_resolver, last_run, native_submit):
        if not all(callable(x) for x in (job_resolver, last_run, native_submit)):
            raise ForgeHold('NATIVE_JOB_SCHEDULER_REQUIRED')
        self.background, self.resolve, self.last_run, self.submit = (
            background, job_resolver, last_run, native_submit)

    def _job(self, scope, args):
        if (type(args) is not dict or set(args) != {'job_id'}
                or not isinstance(args['job_id'], str)
                or not re.fullmatch(r'[A-Za-z0-9._:-]{1,128}', args['job_id'])):
            raise ForgeHold('TRUSTED_JOB_ID_REQUIRED_NO_UI_PATHS')
        from .background_forge import ForgeJob
        job = self.resolve(scope, args['job_id'])
        if not isinstance(job, ForgeJob):
            raise ForgeHold('APPROVED_NATIVE_JOB_MISSING')
        return job

    def preflight(self, scope, args):
        return self.background.preflight(self._job(scope, args))

    def start(self, scope, args):
        # Explicit consented manual route; no assertion that the user is idle.
        job = self._job(scope, args)
        last = self.last_run(scope, job)
        return self.submit(scope, job, lambda: self.background.run_one(job, last_run_utc=last, require_idle=False))

    def pause(self, scope, args):
        job = self._job(scope, args)  # native resolver authorizes caller scope
        return self.background.request_pause(job)

    def resume(self, scope, args):
        job = self._job(scope, args)
        last = self.last_run(scope, job)
        return self.submit(scope, job, lambda: self.background.run_one(job, last_run_utc=last, resume=True, require_idle=False))

    def checkpoints(self, scope, args):
        job = self._job(scope, args)
        events = self.background.event_snapshot(job)
        try:
            receipt = self.background.verified_receipt(job)
        except (ValueError, OSError, RuntimeError):
            return {'status':'HOLD', 'reason':'AWAITING_VERIFIED_CHECKPOINT',
                    'events':events, 'checkpoint':None, 'weights_updated':False,
                    'activation_allowed':False}
        return {'status': receipt['status'], 'checkpoint': receipt['checkpoint'],
                'events':events, 'weights_updated': False, 'activation_allowed': False}

    def evaluate(self, scope, args):
        receipt = self.background.verified_receipt(self._job(scope, args))
        # Return real trainer holdout results, never fabricate a new evaluation.
        return {'status': 'HOLD' if receipt['status'] != 'COMPLETED' else 'CANDIDATE_ONLY',
                'evaluation': receipt['training'], 'weights_updated': False,
                'activation_allowed': False, 'independent_e07': 'DEFERRED'}

    def request_stop(self):
        # Native global STOP/revoke hook; no invented training.stop route.
        return self.background.request_stop()


class ExistingP04ModelTransaction:
    """Native-only selection/rollback after an independently attested P03 import.

    HF safetensors produced by merge are NOT Ollama tags. Only a trusted P03
    verifier may bind their merged SHA to an installed tag/digest. The previous
    model remains installed. This uses the one P02 client and original S03 audit
    callbacks; no model conversion, downloading, or second registry is created.
    """
    def __init__(self, p02, *, native_approve, verify_import, model_digest,
                 record_transaction, load_transaction):
        checks = (native_approve, verify_import, model_digest, record_transaction, load_transaction)
        if not all(callable(x) for x in checks):
            raise ForgeHold('NATIVE_MODEL_TRANSACTION_CALLBACKS_REQUIRED')
        self.p02 = p02
        self.approve, self.verify_import, self.digest = native_approve, verify_import, model_digest
        self.record, self.load = record_transaction, load_transaction

    def _lock(self):
        method = getattr(self.p02, 'selection_transaction', None)
        if not callable(method):
            raise ForgeHold('EXISTING_P02_ATOMIC_MODEL_SELECTION_REQUIRED')
        return method()

    def activate(self, scope, *, transaction_id, merged_payload_sha256):
        if (not isinstance(transaction_id, str) or not re.fullmatch(r'[A-Za-z0-9._:-]{1,128}', transaction_id)
                or not isinstance(merged_payload_sha256, str) or not SHA.fullmatch(merged_payload_sha256)):
            raise ForgeHold('EXACT_MERGE_TRANSACTION_ID_REQUIRED')
        intent = {'transaction_id':transaction_id, 'merged_payload_sha256':merged_payload_sha256}
        if self.approve(scope, 'training.activate', intent) is not True:
            raise ForgeHold('MODEL_ACTIVATION_EXPLICIT_NATIVE_CONSENT_REQUIRED')
        if self.load(scope, transaction_id) is not None:
            raise ForgeHold('MODEL_TRANSACTION_ALREADY_EXISTS')
        attestation = self.verify_import(scope, merged_payload_sha256)
        if (not isinstance(attestation, dict) or attestation.get('status') != 'VERIFIED'
                or attestation.get('merged_payload_sha256') != merged_payload_sha256):
            return {'status':'HOLD', 'reason':'P03_VERIFIED_IMPORT_REQUIRED_HF_SAFETENSORS_NOT_OLLAMA',
                    'weights_updated':False, 'activation_allowed':False}
        target, target_digest = attestation.get('model_tag'), attestation.get('model_digest')
        if not isinstance(target, str) or not target or not isinstance(target_digest, str) or not SHA.fullmatch(target_digest):
            raise ForgeHold('P03_IMPORT_ATTESTATION_INCOMPLETE')
        with self._lock():
            previous = self.p02.selected_model()
            if not previous or previous == target:
                raise ForgeHold('DISTINCT_PREVIOUS_MODEL_REQUIRED_FOR_ROLLBACK')
            previous_digest = self.digest(scope, previous)
            if (not isinstance(previous_digest, str) or not SHA.fullmatch(previous_digest)
                    or self.digest(scope, target) != target_digest):
                raise ForgeHold('INSTALLED_MODEL_DIGEST_HOLD')
            record = {**intent, 'previous_model':previous, 'previous_digest':previous_digest,
                      'target_model':target, 'target_digest':target_digest, 'status':'PREPARED'}
            # Persist rollback identity BEFORE selection. Recovery never guesses.
            self.record(scope, transaction_id, record)
            if self.approve(scope, 'training.activate', intent) is not True:
                raise ForgeHold('MODEL_ACTIVATION_REVOKED')
            epoch = self.p02._stop_epoch
            selected = self.p02.list_models(scope, {'model':target})
            if selected.get('selectedModel') != target:
                raise ForgeHold('EXISTING_P02_SELECTION_NOT_CONFIRMED')
            # Local metadata/lineage reads can yield to global STOP. Do not
            # leave a late selected model active after its grant was revoked.
            if (self.p02._stop_epoch != epoch or
                    self.approve(scope, 'training.activate', intent) is not True):
                if self.digest(scope, previous) == previous_digest:
                    self.p02.list_models(scope, {'model':previous})
                    self.record(scope, transaction_id, {**record,'status':'PREVIOUS_MODEL_SELECTION_RESTORED'})
                raise ForgeHold('MODEL_ACTIVATION_REVOKED_DURING_SELECTION')
            record['status'] = 'SELECTED_PENDING_NATIVE_E07'
            try:
                self.record(scope, transaction_id, record)
            except Exception:
                # Undo this transaction's selection on audit failure only if no
                # other model took its place and previous bytes still match.
                if self.p02.selected_model() == target and self.digest(scope, previous) == previous_digest:
                    self.p02.list_models(scope, {'model':previous})
                raise
            return {**record, 'weights_updated':False, 'native_inference_verified':False,
                    'independent_e07':'DEFERRED'}

    def rollback(self, scope, *, transaction_id):
        record = self.load(scope, transaction_id)
        if not isinstance(record, dict) or record.get('status') not in ('PREPARED','SELECTED_PENDING_NATIVE_E07'):
            raise ForgeHold('S03_MODEL_TRANSACTION_REQUIRED')
        if self.approve(scope, 'training.rollback', {'transaction_id':transaction_id}) is not True:
            raise ForgeHold('MODEL_ROLLBACK_EXPLICIT_NATIVE_CONSENT_REQUIRED')
        with self._lock():
            if self.p02.selected_model() != record['target_model']:
                raise ForgeHold('MODEL_SELECTION_CHANGED_SINCE_TRANSACTION')
            if self.digest(scope, record['previous_model']) != record['previous_digest']:
                raise ForgeHold('PREVIOUS_MODEL_DIGEST_CHANGED')
            if self.approve(scope, 'training.rollback', {'transaction_id':transaction_id}) is not True:
                raise ForgeHold('MODEL_ROLLBACK_REVOKED_BEFORE_SELECTION')
            selected = self.p02.list_models(scope, {'model':record['previous_model']})
            if selected.get('selectedModel') != record['previous_model']:
                raise ForgeHold('MODEL_ROLLBACK_NOT_CONFIRMED')
            record = {**record, 'status':'PREVIOUS_MODEL_SELECTION_RESTORED'}
            self.record(scope, transaction_id, record)
            return {**record, 'weights_updated':False, 'native_inference_verified':False}


class ExistingP04Pipeline:
    """Existing native command chain from real P04 candidate to P03/P02.

    import.prepare/record are private native-pipe operations: the Windows host
    must reject them from WebView and construct their payload after native
    consent/P03 completion. Public commands contain only a configured job_id.
    """
    PUBLIC = frozenset({'training.merge','training.activate','training.rollback'})
    INTERNAL = frozenset({'training.import.prepare','training.import.record'})

    def __init__(self, background, queue, p02, *, job_resolver, authorize,
                 model_digest, receipt_root):
        from pathlib import Path
        if not all(callable(x) for x in (job_resolver, authorize, model_digest)):
            raise ForgeHold('NATIVE_FORGE_PIPELINE_CALLBACKS_REQUIRED')
        self.background, self.queue, self.p02 = background, queue, p02
        self.resolve, self.authorize, self.model_digest = job_resolver, authorize, model_digest
        self.receipt_root = Path(receipt_root).absolute()

    def _merged(self, job):
        return job.output_dir.parent / (job.run_id + '.merged')

    def _merge_proof(self, job):
        import importlib.util
        background = self.background
        trained = background.verified_receipt(job)
        if trained['status'] != 'COMPLETED':
            raise ForgeHold('COMPLETED_TRAINING_RECEIPT_REQUIRED')
        directory = self._merged(job)
        background.trainer.reject_reparse_ancestors(directory)
        spec = importlib.util.spec_from_file_location('_nox_p04_pipeline_merge', background.p04/'merge_qlora_adapter.py')
        merger = importlib.util.module_from_spec(spec); spec.loader.exec_module(merger)
        receipt = merger.read_object(directory/'merge-receipt.json')
        actual = merger.tree_sha256(directory, skip_merge_receipt=True)
        train_sha = background.trainer.sha256_file(job.output_dir/'training-receipt.json')
        if (receipt.get('schema') != 'NOX-QLORA-MERGE-RECEIPT-v1' or receipt.get('status') != 'CREATED'
                or receipt.get('merged_payload_sha256') != actual
                or receipt.get('training_receipt_sha256') != train_sha
                or receipt.get('adapter_sha256') != trained['adapter_sha256']
                or receipt.get('model_snapshot_sha256') != trained['model']['snapshot_sha256']):
            raise ForgeHold('EXISTING_MERGE_PROOF_MISMATCH')
        merger.verified_loss_improvement(receipt.get('baseline_eval_loss'), receipt.get('adapter_eval_loss'))
        return directory, receipt, trained

    def prepare_import(self, scope, job, approval_id):
        from urllib.parse import urlparse
        directory, merged, trained = self._merge_proof(job)
        t = self.background.trainer
        # Original rights executable re-attests current exact manifest/data.
        rights = t.verify_manifest(job.dataset_manifest, job.train_jsonl, job.holdout_jsonl, job.rights_verifier)
        if (rights['_rights_attestation_id'] != trained['dataset']['rights_attestation_id']
                or rights['_rights_attestation_sha256'] != trained['dataset']['rights_attestation_sha256']):
            raise ForgeHold('P03_IMPORT_RIGHTS_REATTESTATION_MISMATCH')
        lock = t.read_object(job.model_lock)
        license_source = job.license_source or lock.get('license_source') or lock.get('license_url')
        parsed = urlparse(license_source) if isinstance(license_source,str) else None
        if (parsed is None or parsed.scheme != 'https' or not parsed.netloc
                or parsed.username or parsed.password or parsed.fragment):
            raise ForgeHold('REVIEWED_MODEL_LICENSE_HTTPS_SOURCE_REQUIRED')
        if not isinstance(approval_id,str) or not re.fullmatch(r'[A-Za-z0-9._:-]{1,128}',approval_id):
            raise ForgeHold('ACTUAL_NATIVE_APPROVAL_ID_REQUIRED')
        return {'directory':str(directory),'mergedPayloadSha256':merged['merged_payload_sha256'],
                'mergeReceiptSha256':t.sha256_file(directory/'merge-receipt.json'),
                'trainingReceiptPath':str(job.output_dir/'training-receipt.json'),
                'trainingReceiptSha256':t.sha256_file(job.output_dir/'training-receipt.json'),
                'rightsAttestationId':rights['_rights_attestation_id'],
                'rightsAttestationSha256':rights['_rights_attestation_sha256'],
                'licenseSource':license_source,'nativeApprovalId':approval_id,
                'nativeRightsVerified':True}

    def _import_receipt(self, scope, job, receipt_path):
        from pathlib import Path
        directory, merged, trained = self._merge_proof(job)
        t = self.background.trainer
        path = Path(receipt_path).absolute();t.reject_reparse_ancestors(path)
        if path.parent.resolve() != self.receipt_root.resolve():
            raise ForgeHold('EXISTING_P03_RECEIPT_ROOT_REQUIRED')
        receipt = t.read_object(path)
        job_guid = str(receipt.get('jobId','')).replace('-','')
        if not re.fullmatch(r'[a-fA-F0-9]{32}',job_guid) or path.name != job_guid+'.json':
            raise ForgeHold('EXACT_P03_RECEIPT_JOB_PATH_REQUIRED')
        if (receipt.get('schema') != 'NOX_P03_INSTALL_RECEIPT_V1'
                or receipt.get('operation') != 'safetensors-import'
                or receipt.get('mergedPayloadSha256') != merged['merged_payload_sha256']
                or receipt.get('localSha256') != merged['merged_payload_sha256']
                or receipt.get('mergeReceiptSha256') != t.sha256_file(directory/'merge-receipt.json')
                or receipt.get('trainingReceiptSha256') != t.sha256_file(job.output_dir/'training-receipt.json')
                or receipt.get('rightsAttestationId') != trained['dataset']['rights_attestation_id']
                or receipt.get('rightsAttestationSha256') != trained['dataset']['rights_attestation_sha256']
                or not isinstance(receipt.get('nativeApprovalId'),str) or not receipt['nativeApprovalId']):
            raise ForgeHold('EXISTING_P03_IMPORT_RECEIPT_BINDING_HOLD')
        files = receipt.get('importedFiles')
        if not isinstance(files,list) or not files:
            raise ForgeHold('EXACT_IMPORTED_FILE_MANIFEST_REQUIRED')
        actual = {p.relative_to(directory).as_posix():p for p in directory.rglob('*')
                  if p.is_file() and p != directory/'merge-receipt.json'}
        claimed = {}
        for item in files:
            if not isinstance(item,dict) or item.get('path') in claimed:
                raise ForgeHold('IMPORTED_FILE_MANIFEST_DUPLICATE')
            name = item.get('path');file = actual.get(name)
            if (file is None or item.get('sha256') != t.sha256_file(file)
                    or type(item.get('sizeBytes')) is not int or item['sizeBytes'] != file.stat().st_size):
                raise ForgeHold('IMPORTED_FILE_SHA_OR_SIZE_MISMATCH')
            claimed[name] = item
        if set(actual) != set(claimed):
            raise ForgeHold('IMPORTED_FILE_COVERAGE_MISMATCH')
        digest = receipt.get('ollamaDigest')
        if not isinstance(digest,str) or not re.fullmatch(r'sha256:[a-f0-9]{64}',digest):
            raise ForgeHold('P03_INSTALLED_MANIFEST_DIGEST_REQUIRED')
        if self.model_digest(scope,receipt.get('modelTag')) != digest[7:]:
            raise ForgeHold('P03_INSTALLED_MODEL_CHANGED')
        return receipt, path

    def _store_import(self, scope, job, receipt_path):
        import json
        from .onehost_queue import scope_key
        receipt,path = self._import_receipt(scope,job,receipt_path)
        data = {'scope':scope_key(scope),'run_id':job.run_id,'receipt_path':str(path),
                'receipt_sha256':self.background.trainer.sha256_file(path)}
        def write(store):
            with store.conn:store._audit('NOX_FORGE_VERIFIED_P03_IMPORT',0,data)
            return True
        self.queue.actor.call(write)
        return {'status':'IMPORTED_NOT_ACTIVATED','modelTag':receipt['modelTag'],
                'mergedPayloadSha256':receipt['mergedPayloadSha256'],'weights_updated':False}

    def _attestation(self, scope, job, merged_sha):
        import json
        from .onehost_queue import scope_key
        def read(store):
            for (raw,) in store.conn.execute("SELECT metadata FROM audit WHERE action='NOX_FORGE_VERIFIED_P03_IMPORT' ORDER BY id DESC"):
                item=json.loads(raw)
                if item.get('scope')==scope_key(scope) and item.get('run_id')==job.run_id:return item
            return None
        item=self.queue.actor.call(read)
        if item is None:return None
        receipt,path=self._import_receipt(scope,job,item['receipt_path'])
        if (self.background.trainer.sha256_file(path)!=item['receipt_sha256']
                or receipt['mergedPayloadSha256']!=merged_sha):
            raise ForgeHold('P03_S03_IMPORT_RECEIPT_CHANGED')
        return {'status':'VERIFIED','merged_payload_sha256':merged_sha,
                'model_tag':receipt['modelTag'],'model_digest':receipt['ollamaDigest'][7:]}

    def command(self, scope, args):
        if type(args) is not dict or args.get('action') not in self.PUBLIC | self.INTERNAL:
            raise ForgeHold('APPROVED_NATIVE_FORGE_COMMAND_REQUIRED')
        action=args['action'];allowed={'action','job_id'}
        if action=='training.import.prepare':allowed.add('native_approval_id')
        if action=='training.import.record':allowed.add('receipt_path')
        if set(args)!=allowed or not isinstance(args.get('job_id'),str):
            raise ForgeHold('NATIVE_FORGE_JOB_ONLY_NO_UI_PATHS')
        permission='training.import' if action in self.INTERNAL else action
        if self.authorize(scope,permission,{'job_id':args['job_id']}) is not True:
            raise ForgeHold('EXPLICIT_NATIVE_FORGE_COMMAND_CONSENT_REQUIRED')
        job=self.resolve(scope,args['job_id'])
        if action=='training.merge':
            return self.queue.submit_followup(scope,job,lambda:self.background.merge_candidate(job,
                output_dir=self._merged(job),owner_approve=lambda *_:self.authorize(scope,action,{'job_id':job.run_id})),
                permission='training.merge')
        if action=='training.import.prepare':return self.prepare_import(scope,job,args['native_approval_id'])
        if action=='training.import.record':return self._store_import(scope,job,args['receipt_path'])
        tx=ExistingP04ModelTransaction(self.p02,native_approve=self.authorize,
            verify_import=lambda session,sha:self._attestation(session,job,sha),model_digest=self.model_digest,
            record_transaction=self.queue.record_transaction,load_transaction=self.queue.load_transaction)
        if action=='training.activate':
            _directory,merged,_trained=self._merge_proof(job)
            return tx.activate(scope,transaction_id=job.run_id+':activation',merged_payload_sha256=merged['merged_payload_sha256'])
        return tx.rollback(scope,transaction_id=job.run_id+':activation')
