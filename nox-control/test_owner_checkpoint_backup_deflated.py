"""Lossless codec and pinned-wrapper tests; no keys or native actions."""
import ast
import base64
import copy
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import zipfile

import owner_checkpoint_backup_deflated as codec
import owner_checkpoint_backup_deflated_entry as entry
import owner_checkpoint_backup_deflated_local as local
import owner_checkpoint_backup_transport as original

ROOT=Path(__file__).parent


class DeflatedBackup(unittest.TestCase):
    def setUp(self):
        self.original=(ROOT/'owner_checkpoint_backup_transport.py').read_bytes()
        self.core=codec.core_module(self.original)
        c=self.core
        self.files={name:('public-fixture-'+name).encode() for name in c.CHECKPOINT_NAMES}
        self.files['adapter_model.safetensors']=b'public-synthetic-header'+b'\0'*(1024*1024)
        self.files['trainer_state.json']=b'{"global_step":5,"log_history":[{"grad_norm":NaN}]}'
        lineage={'native_sha256':c.NATIVE_SHA,'dataset_sha256':c.DATASET_SHA}
        self.files['owner_lineage.json']=c.canonical(lineage)
        c.LINEAGE_SHA=c.digest(c.canonical(lineage))
        receipt={'schema':'NOX_T866U_FP32_ADAPTER_CONTINUATION_V1','native_sha256':c.NATIVE_SHA,
            'lineage_sha256':c.LINEAGE_SHA,'global_step':5,'start_step':0,'successful_optimizer_steps':0,
            'skipped_optimizer_steps':5,'loss':1.5,'before_tensor_sha256':c.TENSOR_SHA,
            'after_tensor_sha256':c.TENSOR_SHA,'adapter_delta_verified':False,'merged':False,'live_promoted':False,
            'checkpoint':{'path':str(c.OUTPUT/'checkpoint-5'),'global_step':5,
                'files_sha256':{name:c.digest(self.files[name]) for name in c.CHECKPOINT_NAMES}}}
        self.files['owner_receipt_step_5.json']=c.canonical(receipt)
        c.RECEIPT_SHA=c.digest(self.files['owner_receipt_step_5.json'])

    def test_compression_restores_all_nine_original_hashes_and_nan_bytes(self):
        c=self.core;raw,manifest=c.archive_payload(self.files)
        proof=c.verify_archive(raw,manifest)
        self.assertEqual(manifest['archive_format'],'ZIP_DEFLATED')
        self.assertLess(len(raw),sum(map(len,self.files.values()))//10)
        self.assertEqual({row['filename']:row['sha256'] for row in proof['manifest']['files']},
                         {name:c.digest(value) for name,value in self.files.items()})
        with zipfile.ZipFile(io.BytesIO(raw)) as zipped:
            self.assertEqual(zipped.namelist(),list(c.NAMES))
            for name,value in self.files.items():self.assertEqual(zipped.read(name),value)
        self.assertEqual(proof['successful_optimizer_steps'],0)
        for name in ('training_resume_tested','adapter_delta_verified','full_model_backup','drive_copy_verified'):
            self.assertIs(proof[name],False)

    def test_crypto_context_and_all_noncodec_functions_are_byte_identical(self):
        before=ast.parse(self.original.decode());after=ast.parse(codec.transform_core(self.original).decode())
        for tree in (before,after):
            tree.body=[node for node in tree.body if not (isinstance(node,ast.FunctionDef) and node.name in codec.FUNCTIONS)]
        self.assertEqual(ast.dump(before),ast.dump(after))
        for function in ('seal','decrypt','assemble','scope','read_native_archive','public_key_metadata','validate_payload'):
            left=next(n for n in ast.parse(self.original.decode()).body if isinstance(n,ast.FunctionDef) and n.name==function)
            right=next(n for n in ast.parse(codec.transform_core(self.original).decode()).body if isinstance(n,ast.FunctionDef) and n.name==function)
            self.assertEqual(ast.get_source_segment(self.original.decode(),left),
                ast.get_source_segment(codec.transform_core(self.original).decode(),right))

    def test_original_and_compressed_verifiers_remain_format_separate(self):
        c=self.core;compressed,manifest=c.archive_payload(self.files)
        with patch.object(original,'LINEAGE_SHA',c.LINEAGE_SHA),patch.object(original,'RECEIPT_SHA',c.RECEIPT_SHA):
            with self.assertRaisesRegex(RuntimeError,'MANIFEST'):original.verify_archive(compressed,manifest)
            stored,old_manifest=original.archive_payload(self.files)
        with self.assertRaisesRegex(RuntimeError,'MANIFEST'):c.verify_archive(stored,old_manifest)

    def test_member_path_method_count_and_total_uncompressed_bounds_reject(self):
        c=self.core;_,manifest=c.archive_payload(self.files)
        for change in ('path','stored','extra'):
            stream=io.BytesIO()
            with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_DEFLATED) as zipped:
                for name in c.NAMES:
                    zipped.writestr('../'+name if change=='path' else name,self.files[name],
                        compress_type=zipfile.ZIP_STORED if change=='stored' else zipfile.ZIP_DEFLATED)
                if change=='extra':zipped.writestr('foreign.txt',b'public')
            raw=stream.getvalue();m=copy.deepcopy(manifest)
            m.update(archive_bytes=len(raw),archive_sha256=c.digest(raw))
            with self.assertRaises(RuntimeError):c.verify_archive(raw,m)
        m=copy.deepcopy(manifest)
        m['files'][0]['bytes']=c.MAX_ARCHIVE
        with self.assertRaisesRegex(RuntimeError,'ARCHIVE_BOUND'):c.validate_manifest(m)
        raw,manifest=c.archive_payload(self.files)
        with patch.object(c,'MAX_ARCHIVE',len(raw)-1):
            with self.assertRaises(RuntimeError):c.verify_archive(raw,manifest)

    def test_changed_bytes_or_positive_update_are_not_accepted(self):
        c=self.core;files=dict(self.files);files['optimizer.pt']+=b'changed'
        with self.assertRaisesRegex(RuntimeError,'FILE_SHA'):c.archive_payload(files)
        files=dict(self.files);receipt=json.loads(files['owner_receipt_step_5.json'])
        receipt.update(successful_optimizer_steps=1,skipped_optimizer_steps=4)
        files['owner_receipt_step_5.json']=c.canonical(receipt)
        with patch.object(c,'RECEIPT_SHA',c.digest(files['owner_receipt_step_5.json'])):
            with self.assertRaisesRegex(RuntimeError,'ZERO_UPDATE'):c.archive_payload(files)

    def test_entry_uses_only_exact_sources_and_separate_private_stage(self):
        bundle={name:base64.b64encode((ROOT/name).read_bytes()).decode() for name in entry.PINS}
        with patch.object(entry,'BUNDLE',bundle):configured=entry.configured_entry()
        pager=base64.b64decode(configured.BUNDLE['owner_checkpoint_backup_pager.py'])
        self.assertIn(b"AREA=Path('/dev/shm/nox_checkpoint_backup_deflated_pages')",pager)
        self.assertIn(b"'archive_format':aad['manifest']['archive_format']",pager)
        self.assertIn(codec.CORE_BASE_SHA.encode(),pager)
        compile(configured.CHILD,'<child>','exec')
        self.assertEqual(configured.PUBLIC_METADATA_SHA,entry.PUBLIC_METADATA_SHA)
        with patch.object(entry,'BUNDLE',dict(bundle,**{'owner_checkpoint_backup_transport.py':base64.b64encode(self.original+b'\n').decode()})):
            with self.assertRaisesRegex(RuntimeError,'BUNDLE_PIN'):entry.configured_entry()
        with self.assertRaisesRegex(RuntimeError,'PREIMAGE'):codec.transform_core(self.original+b'\n')

    def test_local_wrapper_loads_pinned_compressed_verifier_without_replacing_sources(self):
        hashes={name:codec.digest((ROOT/name).read_bytes()) for name in local.PINS}
        module=local.local_module()
        self.assertEqual(codec.digest(self.original),codec.CORE_BASE_SHA)
        self.assertIsNot(module.transport,original)
        with patch.object(module.transport,'LINEAGE_SHA',self.core.LINEAGE_SHA), \
             patch.object(module.transport,'RECEIPT_SHA',self.core.RECEIPT_SHA):
            raw,manifest=self.core.archive_payload(self.files)
            self.assertEqual(module.transport.verify_archive(raw,manifest)['manifest']['files'],manifest['files'])
        self.assertEqual(hashes,{name:codec.digest((ROOT/name).read_bytes()) for name in local.PINS})
        for name in ('owner_checkpoint_backup_deflated.py','owner_checkpoint_backup_deflated_entry.py',
                     'owner_checkpoint_backup_deflated_local.py'):
            self.assertNotIn('generate_private_key',(ROOT/name).read_text())


if __name__=='__main__':unittest.main()
