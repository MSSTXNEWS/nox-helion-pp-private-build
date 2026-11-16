"""Local bounded/archive tests; no keys generated and no native actions."""
import copy
import contextlib
import io
import json
import os
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import zipfile
import owner_checkpoint_backup_transport as core
import owner_checkpoint_backup_export as exporter


class CheckpointBackupTests(unittest.TestCase):
    def setUp(self):
        self.files={name:('public-fixture-'+name).encode() for name in core.CHECKPOINT_NAMES}
        self.files['trainer_state.json']=b'{"global_step":5}'
        lineage={'native_sha256':core.NATIVE_SHA,'dataset_sha256':core.DATASET_SHA}
        self.files['owner_lineage.json']=core.canonical(lineage)
        self.lineage_sha=core.digest(core.canonical(lineage))
        receipt={'schema':'NOX_T866U_FP32_ADAPTER_CONTINUATION_V1','native_sha256':core.NATIVE_SHA,
            'lineage_sha256':self.lineage_sha,'global_step':5,'start_step':0,'successful_optimizer_steps':0,
            'skipped_optimizer_steps':5,'loss':1.5,'before_tensor_sha256':core.TENSOR_SHA,
            'after_tensor_sha256':core.TENSOR_SHA,'adapter_delta_verified':False,'merged':False,'live_promoted':False,
            'checkpoint':{'path':str(core.OUTPUT/'checkpoint-5'),'global_step':5,
                'files_sha256':{name:core.digest(self.files[name]) for name in core.CHECKPOINT_NAMES}}}
        self.files['owner_receipt_step_5.json']=core.canonical(receipt)
        for item in [patch.object(core,'LINEAGE_SHA',self.lineage_sha),
                     patch.object(core,'RECEIPT_SHA',core.digest(self.files['owner_receipt_step_5.json']))]:
            item.start();self.addCleanup(item.stop)

    def test_nine_exact_files_roundtrip_without_extraction_or_positive_update_claim(self):
        raw,manifest=core.archive_payload(self.files);proof=core.verify_archive(raw,manifest)
        self.assertEqual(len(proof['manifest']['files']),9)
        self.assertEqual({r['filename']:r['sha256'] for r in proof['manifest']['files']},
                         {name:core.digest(value) for name,value in self.files.items()})
        self.assertEqual(proof['successful_optimizer_steps'],0)
        self.assertFalse(proof['adapter_delta_verified']);self.assertFalse(proof['full_model_backup'])
        self.assertFalse(proof['training_resume_tested']);self.assertFalse(proof['drive_copy_verified'])
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            self.assertEqual(z.namelist(),list(core.NAMES))
            self.assertTrue(all(i.compress_type==zipfile.ZIP_STORED for i in z.infolist()))

    def test_changed_checkpoint_and_extra_names_are_rejected_before_archive(self):
        bad=dict(self.files);bad['optimizer.pt']+=b'changed'
        with self.assertRaisesRegex(RuntimeError,'FILE_SHA'):core.archive_payload(bad)
        bad=dict(self.files);bad['credentials.json']=b'not admitted'
        with self.assertRaisesRegex(RuntimeError,'FILES'):core.archive_payload(bad)
        with patch.object(core,'MAX_ARCHIVE',100):
            with self.assertRaisesRegex(RuntimeError,'FILES'):core.archive_payload(self.files)

    def test_nonfinite_amp_gradient_diagnostic_is_archived_byte_exact(self):
        raw=b'{"global_step":5,"log_history":[{"step":5,"loss":1.5,"grad_norm":NaN}]}'
        files=dict(self.files);files['trainer_state.json']=raw
        receipt=json.loads(files['owner_receipt_step_5.json'])
        receipt['checkpoint']['files_sha256']['trainer_state.json']=core.digest(raw)
        files['owner_receipt_step_5.json']=core.canonical(receipt)
        with patch.object(core,'RECEIPT_SHA',core.digest(files['owner_receipt_step_5.json'])):
            archive,manifest=core.archive_payload(files)
            proof=core.verify_archive(archive,manifest)
            with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
                self.assertEqual(zipped.read('trainer_state.json'),raw)
            self.assertEqual(proof['successful_optimizer_steps'],0)
            row=next(item for item in proof['manifest']['files'] if item['filename']=='trainer_state.json')
            self.assertEqual(row['sha256'],core.digest(raw))

    def test_nonfinite_numbers_remain_forbidden_outside_exact_gradient_diagnostic(self):
        for token in ('NaN','Infinity','-Infinity','1e999'):
            raw=('{"global_step":5,"log_history":[{"grad_norm":'+token+'}]}').encode()
            self.assertEqual(core.trainer_state_step(raw),5)
            for bad in (('{"global_step":'+token+'}').encode(),
                        ('{"global_step":5,"loss":'+token+'}').encode(),
                        ('{"global_step":5,"log_history":[{"loss":'+token+'}]}').encode(),
                        ('{"global_step":5,"log_history":[{"nested":{"grad_norm":'+token+'}}]}').encode()):
                with self.assertRaises(RuntimeError):core.trainer_state_step(bad)
        for raw in (b'{"global_step":true}',b'{"global_step":5.0}',b'{"global_step":5,"global_step":5}'):
            with self.assertRaises(RuntimeError):core.trainer_state_step(raw)
        for field in ('loss','log_history'):
            with self.assertRaisesRegex(RuntimeError,'JSON_NUMBER'):
                core.decode_json(('{"'+field+'":NaN}').encode())

    def test_failed_child_exposes_only_fixed_stage_and_reason_never_stderr(self):
        value={'kind':'checkpoint_backup_export_failure','data':{
            'stage':'COLLECT_AND_SEAL','reason':'HOLD_CHECKPOINT_BACKUP_JSON_NUMBER'}}
        raw=('NOX_MAINT_REPAIR='+json.dumps(value)+'\n').encode()
        self.assertEqual(exporter.child_failure_projection(raw),value['data'])
        bad=copy.deepcopy(value);bad['data']['reason']='HOLD_PRIVATE_CREDENTIAL_VALUE'
        projection=exporter.child_failure_projection(('NOX_MAINT_REPAIR='+json.dumps(bad)).encode())
        self.assertNotIn('PRIVATE',json.dumps(projection))
        output=io.StringIO()
        with patch.dict(os.environ,{'NOX_OWNER_REQUEST_ID':'123','NOX_OWNER_SOURCE_SHA':'a'*40}), \
             patch.object(exporter,'bundle',return_value=b'{}'), \
             patch.object(exporter.subprocess,'run',return_value=SimpleNamespace(
                 returncode=2,stdout=raw,stderr=b'private token and file content')), \
             contextlib.redirect_stdout(output):
            with self.assertRaisesRegex(RuntimeError,'NATIVE_EXPORT_FAILED'):exporter.main()
        self.assertIn('COLLECT_AND_SEAL',output.getvalue())
        self.assertIn('HOLD_CHECKPOINT_BACKUP_JSON_NUMBER',output.getvalue())
        self.assertNotIn('private token',output.getvalue())

    def test_compressed_or_traversal_zip_is_never_restored(self):
        _,manifest=core.archive_payload(self.files)
        for malicious in ('compressed','traversal'):
            stream=io.BytesIO()
            with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_DEFLATED if malicious=='compressed' else zipfile.ZIP_STORED) as z:
                for name in core.NAMES:z.writestr('../'+name if malicious=='traversal' else name,self.files[name])
            raw=stream.getvalue();m=copy.deepcopy(manifest);m.update(archive_bytes=len(raw),archive_sha256=core.digest(raw))
            with self.assertRaises(RuntimeError):core.verify_archive(raw,m)

    def test_positive_or_changed_baseline_cannot_be_exported_by_zero_update_scope(self):
        bad=copy.deepcopy(self.files);value=json.loads(bad['owner_receipt_step_5.json'])
        value.update(successful_optimizer_steps=1,skipped_optimizer_steps=4)
        bad['owner_receipt_step_5.json']=core.canonical(value)
        with patch.object(core,'RECEIPT_SHA',core.digest(bad['owner_receipt_step_5.json'])):
            with self.assertRaisesRegex(RuntimeError,'ZERO_UPDATE_PROOF'):core.archive_payload(bad)

    def test_chunk_reorder_is_recoverable_but_duplicate_or_tamper_is_not(self):
        encoded='QUJD'*20000
        envelope={'schema':'NOX_CHECKPOINT_BACKUP_ENVELOPE_V1','aad':{},'wrapped_key':'AA==','nonce':'AA==',
                  'ciphertext_bytes':60000,'ciphertext_sha256':'1'*64,'ciphertext':encoded}
        outer=core.digest(core.canonical(envelope))
        header={'schema':'NOX_CHECKPOINT_BACKUP_TRANSFER_V1','envelope_sha256':outer,'chunks':2,
                'chunk_chars':60000,'ciphertext_chars':len(encoded),'metadata':{k:v for k,v in envelope.items() if k!='ciphertext'}}
        rows=[{'kind':'checkpoint_backup_ciphertext_header','data':header}]+[
            {'kind':'checkpoint_backup_ciphertext_chunk','data':{'envelope_sha256':outer,'index':i,'chunks':2,
              'ciphertext':encoded[i*60000:(i+1)*60000]}} for i in range(2)]
        self.assertEqual(core.assemble([rows[2],rows[0],rows[1]])[0],envelope)
        bad=copy.deepcopy(rows);bad[2]['data']['index']=0
        with self.assertRaises(RuntimeError):core.assemble(bad)
        bad=copy.deepcopy(rows);bad[1]['data']['ciphertext']='A'+bad[1]['data']['ciphertext'][1:]
        with self.assertRaisesRegex(RuntimeError,'ENVELOPE_SHA'):core.assemble(bad)
        with self.assertRaisesRegex(RuntimeError,'ROW_COUNT'):core.assemble([{}]*1202)

    def test_expired_public_metadata_and_unprepared_export_never_start_crypto_child(self):
        value={'schema':'NOX_CHECKPOINT_BACKUP_PUBLIC_KEY_V1','key_id':'1'*64,'public_key_pem':'',
               'transfer_id':'2'*32,'created_at':10,'expires_at':3610,'scope_sha256':core.scope_sha()}
        with self.assertRaisesRegex(RuntimeError,'KEY_CONTEXT'):core.public_key_metadata(value,now=3610)
        with patch.dict(os.environ,{'NOX_OWNER_REQUEST_ID':'123','NOX_OWNER_SOURCE_SHA':'a'*40}), \
             patch.object(exporter.subprocess,'run') as run:
            with self.assertRaisesRegex(RuntimeError,'BUNDLE_PIN'):exporter.main()
            run.assert_not_called()

    def test_native_child_compiles_and_no_module_creates_private_keys(self):
        compile(exporter.CHILD,'<checkpoint-child>','exec')
        for name in ('owner_checkpoint_backup_transport.py','owner_checkpoint_backup_export.py','owner_checkpoint_backup_local.py'):
            source=Path(__file__).with_name(name).read_text()
            self.assertNotIn('generate_private_key',source)


if __name__=='__main__':unittest.main()
