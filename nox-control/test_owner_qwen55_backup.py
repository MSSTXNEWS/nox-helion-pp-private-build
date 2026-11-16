"""Synthetic temp filesystem + actual crypto; no native, owner private key or network."""
import ast
import base64
import copy
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import time
import types
import unittest
from contextlib import ExitStack, redirect_stdout
from unittest.mock import Mock, patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

import owner_qwen55_backup_stream as core
import owner_qwen55_backup_local as local
import owner_qwen55_backup_runner as runner


class CryptoArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=4096)

    def patch(self, obj, key, value):
        self.stack.enter_context(patch.object(obj, key, value))

    def write(self, path, raw, mode=0o600):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw); path.chmod(mode)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.stack = ExitStack()
        self.root = Path(self.tmp.name)
        self.output = self.root / 'lora/qwen35_9b/6907283384'
        self.cp = self.output / core.CHECKPOINT
        self.cp.mkdir(parents=True)
        self.state = self.root / 'state'; self.state.mkdir()
        self.scripts = self.root / 'scripts'; self.scripts.mkdir()
        self.area = self.state / 'owner_qwen_execution_revisions' / core.EXPECTED_REFERENCE['request']
        self.area.mkdir(parents=True)
        self.proc = self.root / 'proc'
        self.write(self.proc / 'sys/kernel/random/boot_id', core.EXPECTED_PROCESS['boot_id'].encode() + b'\n')
        for key,value in {'ROOT':self.root,'OUTPUT':self.output,'SCRIPTS':self.scripts,'STATE':self.state,
                          'AREA':self.area,'PROC':self.proc,'OWNER_UID':os.getuid()}.items():
            self.patch(core,key,value)
        self.source_raw = {name: ('public synthetic pinned source ' + name).encode() for name in (
            'owner_qwen_revision_install.py','owner_qwen_execution_revision.py',
            'qwen_student_training_entry_revision.py',core.GUARD_NAME,'owner_qwen_successor_watch.py',
            'owner_qwen_training_observe.py','owner_qwen_install_entry.py','old_entry.py')}
        native_pins = {n:core.digest(b) for n,b in self.source_raw.items()}
        for key,name in {'INSTALLER_SHA':'owner_qwen_revision_install.py',
                         'SHARED_SHA':'owner_qwen_execution_revision.py',
                         'STUDENT_SHA':'qwen_student_training_entry_revision.py',
                         'GUARD_SHA':core.GUARD_NAME,'WATCHER_SHA':'owner_qwen_successor_watch.py'}.items():
            self.patch(core,key,native_pins[name])
        for name,raw in self.source_raw.items(): self.write(self.scripts/name,raw,0o644)
        self.lineage = {'schema':'TEST_LOCAL_SYNTHETIC_ONLY', 'tokenized_corpus':{'splits':[{'split':'holdout','accepted_rows':16}]}}
        self.patch(core,'LINEAGE_SHA',core.digest(core.canonical(self.lineage)))
        self.patch(core,'LINEAGE_FILE_SHA',core.digest(core.canonical(self.lineage)+b'\n'))
        now=time.time(); self.now=now
        predecessor={'request':'synthetic-predecessor','student_profile':{'successful_updates_goal':1000}}
        prior_raw=core.canonical(predecessor)+b'\n'
        prior={'reference':{'request':'previous','source_sha':'a'*40,'receipt_sha256':'b'*64},
               'descriptor_sha256':'c'*64,'admission_sha256':core.digest(prior_raw)}
        self.desc={'schema':'NOX_QWEN_EXECUTION_SUCCESSOR_DESCRIPTOR_V1',
            'request':core.EXPECTED_REFERENCE['request'],'source_sha':core.EXPECTED_REFERENCE['source_sha'],
            'created_at':now-60,'origin':{'acceptance_sha256':'UNPREPARED','lineage_sha256':core.LINEAGE_SHA},
            'runtime_sources':{'qwen_student_training_entry_revision.py':core.STUDENT_SHA,
                               'owner_qwen_execution_revision.py':core.SHARED_SHA},
            'consumer_sources':{core.GUARD_NAME:core.GUARD_SHA},
            'activation_issuer_sha256':core.INSTALLER_SHA,'activation_watcher_sha256':core.WATCHER_SHA}
        updates=[{'step':i+1,'adapter_sha_after':core.digest(str(i+1).encode())} for i in range(55)]
        cert={'schema':'NOX_QWEN35_9B_UPDATE_PROOF_V1','state':'STUDENT_RESTART_AND_UPDATES_VERIFIED',
              'successful_optimizer_steps':6,'new_successful_optimizer_steps':1,'attempted_steps':6,'skipped_steps':0,
              'reload_verified':True,'independent_holdout_accepted':True,'holdout_finite':True,
              'holdout_evaluated_successful_total':6,'base_manifest_sha256':core.BASE_MANIFEST_SHA,
              'lineage_sha256':core.LINEAGE_SHA,'checkpoint_manifest_sha256':core.ACCEPTED_MANIFEST_SHA,
              'checkpoint':str(self.output/core.ACCEPTED_CHECKPOINT),'update_evidence':updates[:6],
              'final_adapter_tensor_sha256':core.digest(b'6')}
        cert_raw=core.canonical(cert)+b'\n';self.patch(core,'ACCEPTANCE_SHA',core.digest(cert_raw))
        self.desc['origin']['acceptance_sha256']=core.ACCEPTANCE_SHA
        desc_raw=core.canonical(self.desc)+b'\n';self.patch(core,'DESCRIPTOR_SHA',core.digest(desc_raw))
        admission={'request':core.EXPECTED_REFERENCE['request'],'source_sha':core.EXPECTED_REFERENCE['source_sha'],
                   'created_at':now-59,'student_profile':{'successful_updates_goal':1000}}
        admission_raw=core.canonical(admission)+b'\n';self.patch(core,'ADMISSION_SHA',core.digest(admission_raw))
        wrapper=b'fixed synthetic wrapper, never executed\n'
        receipt={'schema':'NOX_QWEN_EXECUTION_SUCCESSOR_ADMISSION_V1',
            'state':'EXECUTION_REVISION_INSTALLED_EVALUATION_REQUIRED','request':core.EXPECTED_REFERENCE['request'],
            'source_sha':core.EXPECTED_REFERENCE['source_sha'],'descriptor_sha256':core.DESCRIPTOR_SHA,
            'new_admission_sha256':core.ADMISSION_SHA,'wrapper_sha256':core.digest(wrapper),
            'predecessor_execution_revision':prior['reference'],'predecessor_descriptor_sha256':prior['descriptor_sha256'],
            'previous_admission_sha256':prior['admission_sha256'],'origin_window':{'synthetic':'original'},
            'origin_lineage_sha256':core.LINEAGE_SHA,'anchor_checkpoint_manifest_sha256':'d'*64,
            'activation_watcher_sha256':core.WATCHER_SHA,'runtime_sources':self.desc['runtime_sources']}
        receipt_raw=core.canonical(receipt)+b'\n'
        ref=dict(core.EXPECTED_REFERENCE,receipt_sha256=core.digest(receipt_raw));self.patch(core,'EXPECTED_REFERENCE',ref)
        binding={'schema':'NOX_QWEN_EXECUTION_BINDING_V1','execution_revision':ref,
                 'descriptor_sha256':core.DESCRIPTOR_SHA,'admission_sha256':core.ADMISSION_SHA,
                 'origin_lineage_sha256':core.LINEAGE_SHA,'runtime_entry_sha256':core.STUDENT_SHA,
                 'verifier_sha256':core.SHARED_SHA}
        witness={'schema':'NOX_QWEN_EVALUATION_WITNESS_V1','execution_binding':binding,'kind':'PERIODIC',
                 'process_identity':dict(core.EXPECTED_PROCESS),'evaluated_successful_total':55,
                 'holdout_examples':16,'holdout_loss':1.3216557949781418,'before':{'successful_total':55},
                 'after':{'successful_total':55}}
        saved={'successful_total':55,'attempted_total':55,'skipped_total':0,
               'holdout_evaluated_successful_total':55,'last_holdout_loss':witness['holdout_loss'],
               'update_evidence':updates,'execution_binding':binding,'last_evaluation_witness':witness}
        self.data={n:b'opaque bytes, never unpickle: '+n.encode() for n in core.CHECKPOINT_NAMES}
        for name,value in [('lineage.json',self.lineage),('student_state.json',saved),
                           ('adapter_config.json',{'rank':8}),('python_rng.json',{'state':[1,2,3]})]:
            self.data[name]=core.canonical(value)+b'\n'
        total=sum(map(len,self.data.values()));payloads={n:core.digest(b) for n,b in self.data.items()}
        self.patch(core,'PAYLOAD_SHA',payloads);self.patch(core,'CHECKPOINT_BYTES',total)
        manifest={'schema':'NOX_QWEN35_9B_CHECKPOINT_V1','directory':core.CHECKPOINT,
                  'successful_total':55,'attempted_total':55,'lineage_sha256':core.LINEAGE_SHA,
                  'files_sha256':payloads,'adapter_tensor_sha256':core.digest(b'55'),
                  'execution_binding':binding,'process_identity':dict(core.EXPECTED_PROCESS),
                  'holdout_loss':saved['last_holdout_loss']}
        self.data['checkpoint_manifest.json']=core.canonical(manifest)+b'\n'
        self.patch(core,'MANIFEST_SHA',core.digest(self.data['checkpoint_manifest.json']))
        self.data['owner_acceptance.json']=cert_raw;self.data['execution_descriptor.json']=desc_raw
        pointer=core.canonical({'directory':core.CHECKPOINT,'manifest_sha256':core.MANIFEST_SHA})+b'\n'
        self.patch(core,'POINTER_SHA',core.digest(pointer))
        for name in core.CHECKPOINT_NAMES+('checkpoint_manifest.json',):self.write(self.cp/name,self.data[name])
        self.write(self.output/'owner_acceptance.json',cert_raw);self.write(self.output/'owner_lineage.json',self.data['lineage.json'])
        self.write(self.output/'latest_checkpoint.json',pointer)
        for name,raw in [('descriptor.json',desc_raw),('admission_receipt.json',receipt_raw),('predecessor_admission.json',prior_raw)]:self.write(self.area/name,raw)
        self.write(self.state/'owner_training_admission.json',admission_raw)
        self.write(self.scripts/'run_train_volta_t866u.sh',wrapper,0o700)
        cfg={'schema':'NOX_QWEN_EXECUTION_REVISION_CONFIG_V1','enabled':True,'source_sha256':core.SHARED_SHA,'execution_revision':ref}
        self.write(self.root/'config/owner_qwen_execution_revision.json',core.canonical(cfg)+b'\n')
        self.shared=types.SimpleNamespace(CONFIG=self.root/'config/owner_qwen_execution_revision.json',
            ADMISSION=self.state/'owner_training_admission.json',WRAPPER=self.scripts/'run_train_volta_t866u.sh',
            GUARD_CONFIG=self.root/'config/owner_qwen_training_guard.json',ENTRY='qwen_student_training_entry_revision.py',
            SELF='owner_qwen_execution_revision.py',WATCHER='owner_qwen_successor_watch.py',
            CONFIG_SCHEMA=cfg['schema'],RECEIPT_SCHEMA=receipt['schema'],PREDECESSOR=prior,
            ORIGIN_WINDOW=receipt['origin_window'],ANCHOR={'manifest_sha256':'d'*64},GUARD_POLICY={'synthetic':True},
            ORIGINAL_SOURCES={'old_entry.py':native_pins['old_entry.py']},
            HISTORICAL={n:native_pins[n] for n in ('owner_qwen_training_observe.py','owner_qwen_install_entry.py')},
            descriptor=lambda value:value,make_admission=lambda *args:admission,
            make_wrapper=lambda *args:wrapper,make_argv=lambda *args:['/python','exact-synthetic-argv'],
            parse=core.document,finite=lambda n:type(n) in (int,float) and math.isfinite(n),
            integer=lambda n:type(n) is int,process_identity_valid=lambda v:isinstance(v,dict) and set(v)=={'pid','start_ticks','boot_id'},
            evaluation_witness=lambda ctx,value:value)
        self.dead={'service':{'state':'FATAL','pid':None},'process_identity':None}
        def global_stop():core.require(not (self.root/'STOP').exists(),'OWNER_STOP')
        self.native=types.SimpleNamespace(PROTECTED={'old_entry.py':native_pins['old_entry.py']},
            PINS={'shared':core.SHARED_SHA,'student':core.STUDENT_SHA},SHARED_ASSET='shared',STUDENT_ASSET='student',
            protected=Mock(),global_stop=global_stop,trainer=Mock(return_value=self.dead))
        self.config={'source_sha256':core.GUARD_SHA,'execution_revision':ref,'policy':self.shared.GUARD_POLICY}
        self.config_raw=core.canonical(self.config)+b'\n';self.config_sha=core.digest(self.config_raw)
        self.write(self.shared.GUARD_CONFIG,self.config_raw)
        self.pause=b'synthetic exact private quality pause\n'
        self.flags={'TRAIN_HOLD.flag':('OWNER_QWEN_WINDOW_FAILED request='+ref['request']+' goal=1000\n').encode(),
                    'TRAIN_PAUSE_REQUEST.flag':self.pause}
        for name,raw in self.flags.items():self.write(self.state/name,raw)
        self.patch(core,'FLAG_PINS',{n:(core.digest(b),len(b)) for n,b in self.flags.items()})
        self.guard=types.SimpleNamespace(GuardHold=RuntimeError,
            checked_config=lambda **kwargs:(self.config,self.config_sha),
            bindings=lambda cfg,pin,ctx:{'source':cfg['source_sha256'],'config':pin,'execution':ctx['context'],
                                        'descriptor':ctx['execution']['descriptor_sha256']},
            pause_token=lambda row:self.pause)
        quality=dict(core.EXPECTED_QUALITY,latched_at=now-2);self.patch(core,'EXPECTED_QUALITY',quality)
        self.row={'state':'INHIBITED','policy_state':quality,'sampled_at':now,
            'checkpoint':{'manifest_sha256':core.MANIFEST_SHA,'student_state_sha256':payloads['student_state.json'],
                'pointer_sha256':core.POINTER_SHA,'successful_updates':55,'attempted_updates':55,'skipped_updates':0,
                'evaluated_at_update':55,'holdout_loss':saved['last_holdout_loss']}}
        self.guard_path=self.state/'owner_qwen_training_guard.json';self.write(self.guard_path,core.canonical(self.row))
        def previous_state(expected):
            row=core.read_record(self.guard_path,private=True)
            return core.document(row['raw']),row['sha256']
        self.guard.previous_state=previous_state
        permit={'issued_at':now-40,'fixture':'historical accepted permission, not current resume'}
        permission={'active':True,'bootstrap_pending':False,'baseline_successful_total':25,
                    'initial_process_identity':dict(core.EXPECTED_PROCESS),'permit':permit}
        watcherpid={'pid':2024,'start_ticks':19990,'boot_id':core.EXPECTED_PROCESS['boot_id']}
        ready={'schema':'NOX_QWEN_SUCCESSOR_WATCHER_READY_V1','execution_revision':ref,
            'watcher_source_sha256':core.WATCHER_SHA,'issuer_source_sha256':core.INSTALLER_SHA,
            'verifier_sha256':core.SHARED_SHA,'start_capability':False,'process_identity':watcherpid,'armed_at':now-50}
        readyraw=core.canonical(ready)+b'\n'
        start={'schema':'NOX_QWEN_SUCCESSOR_START_RECEIPT_V1','execution_revision':ref,
            'start_command_issued':True,'start_command_returncode':0,
            'trainer':{'process_identity':dict(core.EXPECTED_PROCESS),'service':{'state':'RUNNING','pid':2023}},
            'watcher_ready_sha256':core.digest(readyraw),'started_at':now-49,'sampled_at':now-48}
        startraw=core.canonical(start)+b'\n'
        result={'schema':'NOX_QWEN_SUCCESSOR_WATCHER_RESULT_V1','execution_revision':ref,
            'state':'EXECUTION_REVISION_ACTIVE_FRESH_EVALUATION_VERIFIED','active':True,
            'optimizer_permission_issued':True,'ordinary_guard_verified':True,'finalizer_called_once':True,
            'watcher_source_sha256':core.WATCHER_SHA,'process_identity':watcherpid,
            'start_receipt_sha256':core.digest(startraw),'finished_at':now-39}
        journals={'watcher_ready.json':readyraw,'start_receipt.json':startraw,
                  'watcher_result.json':core.canonical(result)+b'\n','activation.json':core.canonical(permit)+b'\n'}
        for name,raw in journals.items():self.write(self.area/name,raw)
        self.patch(core,'JOURNAL_PINS',{n:core.digest(b) for n,b in journals.items()})
        permission['permit_sha256']=core.JOURNAL_PINS['activation.json']
        self.shared.activation_status=Mock(return_value=permission)
        modules={'owner_qwen_revision_install.py':self.native,'owner_qwen_execution_revision.py':self.shared,
                 core.GUARD_NAME:self.guard}
        self.patch(core,'native_module',lambda name,pin:modules[name])
        self.patch(core,'process_observer',lambda shared:types.SimpleNamespace())
        public=self.key.public_key()
        self.public={'schema':core.KEY_SCHEMA,'scope_sha256':core.scope_sha(),'transfer_id':'f'*32,
            'created_at':int(now)-1,'expires_at':int(now)+600,
            'public_key_pem':public.public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode(),
            'key_id':core.digest(public.public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo))}

    def tearDown(self):
        self.stack.close();self.tmp.cleanup()

    def export(self):
        out=io.BytesIO();native=core.export(self.public,'b'*40,'123',out,core.Budget())
        return out.getvalue(),native

    def parts(self,wire,native,sub='parts'):
        sink=runner.CipherParts(self.root/sub)
        for offset in range(0,len(wire),619):sink.write(wire[offset:offset+619])
        sink.close();sink.readback()
        receipt={'schema':local.RECEIPT_SCHEMA,'state':'CIPHERTEXT_READY_LOCAL_VERIFICATION_REQUIRED',
                 'scope_sha256':core.scope_sha(),'ciphertext_bytes':len(wire),'ciphertext_sha256':core.digest(wire),
                 'parts':sink.rows,'native':native}
        return sink.directory,local.receipt_document(core.canonical(receipt))

    def test_actual_crypto_full_file_restore_and_private_parts(self):
        wire, native = self.export()
        self.assertNotIn(b'opaque bytes', wire)
        directory, receipt = self.parts(wire, native)
        destination = self.root / 'restore'
        result = local.verify(directory, receipt, self.public, self.key, 'b' * 40, '123', destination)
        self.assertTrue(result['all_file_sha256_verified'])
        self.assertEqual(set(result['files']), set(core.NAMES))
        self.assertEqual({n: r['sha256'] for n, r in result['files'].items()}, {n: core.digest(self.data[n]) for n in core.NAMES})
        self.assertFalse(result['drive_copy_verified'])
        self.assertFalse(result['gpu_restart_performed'])
        for row in result['plaintext_archive_parts']:
            p = destination / row['name']
            self.assertEqual(p.stat().st_mode & 0o777, 0o600)
            self.assertEqual(core.digest(p.read_bytes()), row['sha256'])
        self.assertTrue((destination / 'QWEN55_RESTORE_MANIFEST.json').is_file())
        readback = local.verify_restore(destination, result, 'b' * 40, '123')
        self.assertTrue(readback['all_file_sha256_verified'])
        self.assertFalse(readback['private_key_required'])
        self.assertEqual(readback['verified_files'], 13)

    def test_plaintext_restore_parts_are_independently_verified_without_key(self):
        wire, native = self.export(); directory, receipt = self.parts(wire, native)
        destination = self.root / 'restore'
        result = local.verify(directory, receipt, self.public, self.key, 'b' * 40, '123', destination)
        p = destination / result['plaintext_archive_parts'][0]['name']
        original = p.read_bytes(); p.write_bytes(original[:-1] + b'x')
        with self.assertRaises(core.Hold):
            local.verify_restore(destination, result, 'b' * 40, '123')

    def test_modified_gcm_tag_fails_before_plaintext_publication(self):
        wire, native = self.export()
        damaged = wire[:-1] + bytes([wire[-1] ^ 1])
        native = {**native, 'ciphertext_sha256': core.digest(damaged)}
        directory, receipt = self.parts(damaged, native)
        destination = self.root / 'never_created'
        with self.assertRaises(Exception):
            local.verify(directory, receipt, self.public, self.key, 'b' * 40, '123', destination)
        self.assertFalse(destination.exists())

    def test_metadata_mutation_fails_before_ciphertext(self):
        (self.cp / 'student_state.json').write_bytes(b'{"successful_total":7}')
        buffer = io.BytesIO()
        with self.assertRaises(core.Hold):
            core.export(self.public, 'b' * 40, '123', buffer, core.Budget())
        self.assertEqual(buffer.getvalue(), b'')

    def test_post_stream_source_mutation_never_releases_tag(self):
        output = io.BytesIO()
        original = core.Snapshot.reverify
        def change(snapshot):
            path = self.cp / 'optimizer.pt'; path.write_bytes(b'changed')
            return original(snapshot)
        with patch.object(core.Snapshot, 'reverify', change), self.assertRaises(core.Hold):
            core.export(self.public, 'b' * 40, '123', output, core.Budget())
        wire = output.getvalue()
        size = struct.unpack('>I', wire[8:12])[0]
        header = core.document(wire[12:12 + size])
        self.assertEqual(len(wire), 12 + size + header['archive_bytes'])

    def test_symlink_member_rejected_before_any_export(self):
        p = self.cp / 'optimizer.pt'; p.unlink(); p.symlink_to(self.cp / 'scaler.pt')
        buffer = io.BytesIO()
        with self.assertRaises(OSError):
            core.export(self.public, 'b' * 40, '123', buffer, core.Budget())
        self.assertEqual(buffer.getvalue(), b'')

    def test_expired_public_key_and_wrong_run_rejected(self):
        with self.assertRaises(core.Hold):
            core.public_key(self.public, now=self.public['expires_at'] + 1)
        wire, native = self.export(); directory, receipt = self.parts(wire, native)
        with self.assertRaises(core.Hold):
            local.verify(directory, receipt, self.public, self.key, 'c' * 40, '123')

    def test_missing_reordered_or_changed_part_rejected(self):
        wire, native = self.export()
        with patch.object(core, 'PART_BYTES', 4096):
            directory, receipt = self.parts(wire, native)
            self.assertGreater(len(receipt['parts']), 1)
            bad = json.loads(core.canonical(receipt)); bad['parts'].reverse()
            with self.assertRaises(core.Hold):
                local.receipt_document(core.canonical(bad))
            p = directory / receipt['parts'][0]['name']
            p.write_bytes(b'x' * p.stat().st_size)
            with self.assertRaises(core.Hold):
                local.verify(directory, receipt, self.public, self.key, 'b' * 40, '123')

    def test_private_key_permissions_checked_without_log_contents(self):
        p = self.root / 'synthetic_private.pem'
        p.write_bytes(self.key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        p.chmod(0o644)
        with self.assertRaisesRegex(core.Hold, 'PRIVATE_KEY_PERMISSIONS'):
            local.private_key(p, self.public)
        p.chmod(0o600)
        self.assertEqual(local.private_key(p, self.public).private_numbers(), self.key.private_numbers())

    def test_binary_runner_stream_receives_no_plaintext_or_huge_log(self):
        wire, native = self.export()
        code = ('import sys,base64;sys.stdin.buffer.read();'
                'sys.stdout.buffer.write(base64.b64decode(' + repr(base64.b64encode(wire).decode()) + '));'
                'sys.stderr.write(' + repr('NOX_QWEN55_EXPORT=' + core.canonical(native).decode() + '\n') + ')')
        original = subprocess.Popen
        def local_child(*_args, **kwargs):
            return original([sys.executable, '-c', code], **kwargs)
        parts = runner.CipherParts(self.root / 'pipe-parts')
        with patch.object(runner.subprocess, 'Popen', local_child):
            header, observed = runner.receive([], 'ignored', b'pass\n', self.public, parts)
        self.assertEqual(observed, native)
        self.assertEqual(parts.hash.hexdigest(), core.digest(wire))
        self.assertEqual(header['archive_format'], 'USTAR_UNCOMPRESSED')

    def test_native_failure_surfaces_only_safe_reason_and_no_receipt(self):
        code = "import sys;sys.stdin.buffer.read();sys.stderr.write('private arbitrary text\\nNOX_QWEN55_EXPORT_HOLD=HOLD_QWEN55_BACKUP_POST_EXPORT_SHA\\n');sys.exit(2)"
        original = subprocess.Popen
        def local_child(*_args, **kwargs):
            return original([sys.executable, '-c', code], **kwargs)
        parts = runner.CipherParts(self.root / 'failed-pipe')
        with patch.object(runner.subprocess, 'Popen', local_child), self.assertRaisesRegex(core.Hold, '^HOLD_QWEN55_BACKUP_POST_EXPORT_SHA$'):
            runner.receive([], 'ignored', b'pass\n', self.public, parts)
        self.assertFalse((parts.directory / 'QWEN55_CIPHER_RECEIPT.json').exists())

    def test_archive_and_metadata_limits_are_real(self):
        with patch.object(core, 'MAX_TOTAL', 1):
            with self.assertRaises(core.Hold):
                self.export()
        with self.assertRaises(core.Hold):
            core.document(b'{"a":NaN}')
        with self.assertRaises(core.Hold):
            core.document(b'{"a":1,"a":2}')

    def test_cert6_is_historical_prefix_not_acceptance55(self):
        self.assertEqual(core.validate_documents(self.data)['successful_total'],55)
        cert=core.document(self.data['owner_acceptance.json'])
        cert['successful_optimizer_steps']=55
        changed=dict(self.data,**{'owner_acceptance.json':core.canonical(cert)+b'\n'})
        with patch.object(core,'ACCEPTANCE_SHA',core.digest(changed['owner_acceptance.json'])):
            with self.assertRaisesRegex(core.Hold,'HISTORICAL_SIX_CERTIFICATE'):core.validate_documents(changed)

    def test_quality_heartbeat_keeps_latch_and_never_grants_resume(self):
        binding=core.HeldExecution()
        row=copy.deepcopy(self.row);row['sampled_at']=time.time()
        row['policy_state']=dict(row['policy_state'],last_free_bytes=17000000000,last_sample_at=time.time())
        self.write(self.guard_path,core.canonical(row))
        binding.reverify(self.data)
        wire,native=self.export()
        self.assertTrue(native['quality_hold_preserved'])
        self.assertFalse(native['permission_to_resume'])
        self.assertFalse(native['checkpoint_quality_accepted'])
        self.assertEqual(native['execution_revision'],core.EXPECTED_REFERENCE)
        self.assertEqual(native['after_exit_full_proof_sha256'],core.FULL_PROOF_SHA)

    def test_each_training_flag_change_before_or_during_export_is_a_hold(self):
        for name in core.FLAG_PINS:
            path=self.state/name;raw=path.read_bytes()
            for mode in ('content','removed','permissions','same_bytes_foreign_inode'):
                self.write(path,raw)
                held=core.HeldExecution()
                if mode=='content':path.write_bytes(b'foreign-token')
                elif mode=='removed':path.unlink()
                elif mode=='permissions':path.chmod(0o644)
                else:
                    temp=path.with_suffix('.replacement');self.write(temp,raw);os.replace(temp,path)
                with self.subTest(name=name,mode=mode),self.assertRaises((core.Hold,OSError)):
                    held.check()
                self.write(path,raw)

    def test_source_pointer_admission_or_wrapper_drift_prevents_complete_envelope(self):
        paths=[self.scripts/'old_entry.py',self.output/'latest_checkpoint.json',
               self.state/'owner_training_admission.json',self.shared.WRAPPER]
        for path in paths:
            raw=path.read_bytes();mode=path.stat().st_mode&0o777
            held=core.HeldExecution();path.write_bytes(raw+b' ')
            with self.subTest(path=path.name),self.assertRaises(core.Hold):held.check()
            self.write(path,raw,mode)
        old=core.Snapshot.reverify
        def change(snapshot):
            self.write(self.shared.WRAPPER,b'foreign-wrapper',0o700)
            return old(snapshot)
        out=io.BytesIO()
        with patch.object(core.Snapshot,'reverify',change),self.assertRaises(core.Hold):
            core.export(self.public,'b'*40,'123',out,core.Budget())
        wire=out.getvalue();size=struct.unpack('>I',wire[8:12])[0];header=core.document(wire[12:12+size])
        self.assertEqual(len(wire),12+size+header['archive_bytes'])

    def test_new_child_pid_reuse_missing_activation_or_wrong_history_rejected(self):
        held=core.HeldExecution()
        self.native.trainer.return_value={'service':{'state':'RUNNING','pid':2023},'process_identity':core.EXPECTED_PROCESS}
        with self.assertRaisesRegex(core.Hold,'TRAINER_NOT_STABLY_EXITED'):held.check()
        self.native.trainer.return_value=self.dead
        (self.proc/str(core.EXPECTED_PROCESS['pid'])).mkdir()
        with self.assertRaisesRegex(core.Hold,'WRITER_PID_PRESENT_OR_REUSED'):held.check()
        (self.proc/str(core.EXPECTED_PROCESS['pid'])).rmdir()
        original=self.shared.activation_status.return_value
        self.shared.activation_status.return_value={'active':False,'bootstrap_pending':False}
        with self.assertRaisesRegex(core.Hold,'ACTIVATION_REQUIRED'):core.HeldExecution()
        self.shared.activation_status.return_value=original
        for name in ('start_receipt.json','watcher_ready.json','watcher_result.json','activation.json'):
            path=self.area/name;raw=path.read_bytes();path.write_bytes(raw+b' ')
            with self.subTest(name=name),self.assertRaises(core.Hold):core.HeldExecution()
            self.write(path,raw)

    def test_global_stop_stale_or_changed_quality_prevents_export_without_flag_changes(self):
        held=core.HeldExecution();before={n:(self.state/n).read_bytes() for n in core.FLAG_PINS}
        self.write(self.root/'STOP',b'owner')
        with self.assertRaisesRegex(core.Hold,'OWNER_STOP'):held.check()
        (self.root/'STOP').unlink()
        for changed in [dict(self.row,sampled_at=time.time()-31),dict(self.row,state='MONITORING'),
                        dict(self.row,policy_state=dict(self.row['policy_state'],inhibit=False))]:
            self.write(self.guard_path,core.canonical(changed))
            with self.assertRaises(core.Hold):held.check()
        self.assertEqual(before,{n:(self.state/n).read_bytes() for n in core.FLAG_PINS})

    def test_all_native_export_file_opens_are_read_only_and_corpus_is_unread(self):
        before={str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        original=os.open;seen=[]
        def check(path,flags,*args,**kwargs):
            self.assertFalse(flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND))
            seen.append(str(path));self.assertNotIn('qwen_corpus',str(path))
            return original(path,flags,*args,**kwargs)
        with patch.object(os,'open',side_effect=check):wire,native=self.export()
        self.assertTrue(wire)
        self.assertEqual(native['native_service_actions'],0)
        self.assertEqual(native['native_plaintext_files_written'],0)
        self.assertEqual(before,{str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        self.assertGreater(len(seen),13)

    def test_binding_callback_runs_during_stream_and_deadline_is_not_resume(self):
        budget=core.Budget();counter=Mock();budget.binding_check=counter
        budget.check();counter.assert_called_once()
        budget.deadline=time.monotonic()-1
        with self.assertRaisesRegex(core.Hold,'TIME_BOUND'):budget.check()
        self.assertEqual(counter.call_count,1)


class TransportScopeTests(unittest.TestCase):
    def event(self,scope='QWEN55'):
        return {'inputs':{'allow_native':'YES','checkpoint_scope':scope,'source_sha':'a'*40},
                'sender':{'id':runner.OWNER_ID},'repository':{'owner':{'id':runner.OWNER_ID}}}

    def environment(self,path):
        return {'GITHUB_EVENT_PATH':str(path),'GITHUB_EVENT_NAME':'workflow_dispatch',
            'GITHUB_REPOSITORY':runner.REPO,'GITHUB_ACTOR':'MSSTXNEWS','GITHUB_ACTOR_ID':str(runner.OWNER_ID),
            'GITHUB_RUN_ATTEMPT':'1','NOX_PINNED_SOURCE_SHA':'a'*40,'GITHUB_SHA':'a'*40,'GITHUB_RUN_ID':'123',
            'GITHUB_WORKFLOW_REF':runner.REPO+'/'+runner.WORKFLOW+'@refs/heads/reviewed-qwen55'}

    def test_manual_owner_first_attempt_exact_source_and_only55_scope(self):
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'event.json';path.write_text(json.dumps(self.event()));env=self.environment(path)
            with patch.dict(os.environ,env,clear=True),patch.object(runner.subprocess,'check_output',return_value='a'*40+'\n'):
                self.assertEqual(runner.authorize_event(),('a'*40,'123'))
            for delta in ({'GITHUB_EVENT_NAME':'push'},{'GITHUB_EVENT_NAME':'issue_comment'},
                          {'GITHUB_RUN_ATTEMPT':'2'},{'GITHUB_ACTOR_ID':'1'},{'GITHUB_ACTOR':'another'},
                          {'GITHUB_SHA':'b'*40},{'NOX_PINNED_SOURCE_SHA':'b'*40}):
                with self.subTest(delta=delta),patch.dict(os.environ,{**env,**delta},clear=True),self.assertRaises(core.Hold):
                    runner.authorize_event()
            path.write_text(json.dumps(self.event('QWEN6')))
            with patch.dict(os.environ,env,clear=True),self.assertRaises(core.Hold):runner.authorize_event()

    def test_actual_local_auth_prefix_scope_is_unchanged_and_has_no_payload(self):
        ns=runner.authentication_namespace()
        self.assertEqual(ns['INSTANCE'],60509551);self.assertIsNone(ns['MASTER'])
        self.assertNotIn('payload',ns['run_native'].__code__.co_names)
        self.assertEqual(runner.AUTH_PREFIX_SHA,'a7ecbac3748bffa23bade4370491132a0f29be1b02cb4b8da3e0cc506da48e31')
        self.assertEqual(runner.SSH_HELPER_SHA,'0d38365146c6e580dbcdc04f4b7c9a973bacd2713adcbff4cf39eb334765969b')

    def test_public_key_source_native_length_and_expiry_before_authentication(self):
        public=core.document((runner.REPOSITORY/'nox-control/owner_qwen55_backup_public.json').read_bytes())
        with patch.object(runner.time,'time',return_value=public['created_at']):raw,checked=runner.package()
        self.assertEqual(core.digest(raw),runner.CORE_SHA)
        self.assertEqual(checked['expires_at']-checked['created_at'],7200)
        script=runner.native_script(raw,checked,'a'*40,'123')
        self.assertLess(len(script),65536);compile(script,'<synthetic-native-script-no-run>','exec')
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'event.json';path.write_text(json.dumps(self.event()));env=self.environment(path)
            with patch.dict(os.environ,env,clear=True),patch.object(runner.subprocess,'check_output',return_value='a'*40+'\n'),\
                 patch.object(runner.time,'time',return_value=public['expires_at']+1),\
                 patch.object(sys,'argv',['test','--native']),patch.object(runner,'authentication_namespace') as auth,\
                 patch.object(runner,'receive') as receive,redirect_stdout(io.StringIO()) as out:
                self.assertEqual(runner.main(),2)
            auth.assert_not_called();receive.assert_not_called()
            self.assertEqual(out.getvalue().strip(),'HOLD_QWEN55_BACKUP_PUBLIC_KEY_EXPIRED')

    def test_frozen6_modules_remain_byte_exact_and_crypto_algorithm_is_preserved(self):
        pins={'owner_qwen6_backup_stream.py':'e9a78cd60c5cada7d9f3df5ce82c872bd11b805e8d31aee4707983a94d01c353',
              'owner_qwen6_backup_runner.py':'782e9cf2894e7a5fbf7142cc5fcb152216fa63e847e630da2cc35209e693d815',
              'owner_qwen6_backup_local.py':'e0230fc066f8538e62800537898956e2c97a0cd1088dcf8d67d225482ed9beeb',
              'owner_qwen6_backup_public.json':'a3b9e621ef8e27742be88cc2d7b217dd789f57ce03a6692638897918cffd0b13'}
        for name,pin in pins.items():self.assertEqual(core.digest((Path(__file__).parent/name).read_bytes()),pin)
        old=ast.parse((Path(__file__).parent/'owner_qwen6_backup_stream.py').read_text())
        new=ast.parse(Path(core.__file__).read_text())
        for name in ('HashReader','public_key','archive_size','hash_fd'):
            a=next(n for n in old.body if getattr(n,'name',None)==name)
            b=next(n for n in new.body if getattr(n,'name',None)==name)
            self.assertEqual(ast.dump(a),ast.dump(b))
        self.assertEqual(core.ALGORITHM,'RSA4096-OAEP-SHA256+A256GCM')
        self.assertEqual(core.MAX_SECONDS,900);self.assertEqual(core.MAX_TOTAL,1024**3)
        self.assertEqual(core.PART_BYTES,80*1024**2)
        self.assertEqual(set(core.EXTRA_NAMES),{'checkpoint_manifest.json','owner_acceptance.json','execution_descriptor.json'})

    def test_stable_ref_workflow_preserves_all_legacy_and6_routes(self):
        root=runner.REPOSITORY/'coordination/onepass'
        candidate=(root/'nox-v61-qwen55-stable-ref-workflow.yml').read_text()
        base=candidate.split('\n  qwen55-export:',1)[0].rstrip()+'\n'
        base=base.replace("options: ['LEGACY', 'QWEN6', 'QWEN55']","options: ['LEGACY', 'QWEN6']",1)
        base=base.replace("description: 'For QWEN6 or QWEN55: exact reviewed 40-character commit, equal to the selected workflow ref HEAD'",
                          "description: 'For QWEN6 only: exact reviewed 40-character commit, equal to the selected workflow ref HEAD'",1)
        base=base.replace("description: 'LEGACY unchanged; QWEN6 is accepted6; QWEN55 is exact quality-held progress55'",
                          "description: 'LEGACY preserves the original V61 operation; QWEN6 exports only the accepted six-update checkpoint'",1)
        self.assertEqual(core.digest(base.encode()),'cb377ecf9983a780d45f50e6b95c1c801b38b379d0fca69653dd380ff64d4556')
        manual=(root/'nox-v61-qwen6-qwen55-manual-registration.yml').read_text()
        self.assertEqual(candidate.split('  qwen55-export:',1)[1],manual.split('  qwen55-export:',1)[1])

    def test_manual_proposal_preserves6_job_and_only_uploads_ciphertext55(self):
        root=runner.REPOSITORY/'coordination/onepass'
        text=(root/'nox-v61-qwen6-qwen55-manual-registration.yml').read_text()
        header=text.split('permissions:\n',1)[0]
        self.assertEqual(re.findall(r'^  ([a-z_]+):$',header,re.M),['workflow_dispatch'])
        self.assertIn("options: ['QWEN6', 'QWEN55']\n        default: 'QWEN6'",header)
        self.assertIn("default: 'NO'",header)
        existing_job=text.split('  qwen6-export:',1)[1].split('\n  qwen55-export:',1)[0].rstrip().encode()
        self.assertEqual(core.digest(existing_job),'1b1e9db9021079538ec2124f9c93138879e4398d1dad2592e0aa3089f10cff4e')
        job=text.split('  qwen55-export:',1)[1]
        self.assertIn("github.event_name == 'workflow_dispatch'",job)
        self.assertIn("inputs.allow_native == 'YES'",job)
        self.assertIn("inputs.checkpoint_scope == 'QWEN55'",job)
        self.assertIn("github.actor == 'MSSTXNEWS'",job)
        paths=re.findall(r'^          path: (.+)$',job,re.M)
        expected=[f'artifacts/qwen55-checkpoint-backup/qwen55-cipher.part{i:03d}' for i in range(7)]
        expected.append('artifacts/qwen55-checkpoint-backup/QWEN55_CIPHER_RECEIPT.json')
        self.assertEqual(paths,expected);self.assertEqual(job.count('uses: actions/upload-artifact@v4'),8)
        self.assertNotIn('if: always()\n        uses: actions/upload-artifact',job)


if __name__=='__main__':unittest.main()
