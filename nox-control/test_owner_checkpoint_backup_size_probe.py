"""Small exact-byte compression tests; no native calls, keys or archives written."""
import json
import os
import struct
import types
import unittest
from unittest.mock import patch

import owner_checkpoint_backup_transport as core
import owner_checkpoint_backup_size_probe as probe


class CheckpointSizeProbeTests(unittest.TestCase):
    def fixture(self,bad_offsets=False):
        header={'base.layer.lora_A.weight':{'dtype':'F32','shape':[64], 'data_offsets':[0,256]},
                'base.layer.lora_B.weight':{'dtype':'F32','shape':[4096], 'data_offsets':[256 if not bad_offsets else 255,16640]}}
        encoded=core.canonical(header)
        tensor=struct.pack('<Q',len(encoded))+encoded+struct.pack('<64f',*(n*.01 for n in range(64)))+bytes(16384)
        files={name:('public fixture '+name).encode() for name in core.CHECKPOINT_NAMES}
        files['adapter_model.safetensors']=tensor
        files['trainer_state.json']=b'{"global_step":5,"log_history":[{"grad_norm":NaN}]}'
        lineage={'native_sha256':core.NATIVE_SHA,'dataset_sha256':core.DATASET_SHA}
        files['owner_lineage.json']=core.canonical(lineage);lineage_sha=core.digest(core.canonical(lineage))
        receipt={'schema':'NOX_T866U_FP32_ADAPTER_CONTINUATION_V1','native_sha256':core.NATIVE_SHA,
            'lineage_sha256':lineage_sha,'global_step':5,'start_step':0,'successful_optimizer_steps':0,
            'skipped_optimizer_steps':5,'loss':1.5,'before_tensor_sha256':core.TENSOR_SHA,
            'after_tensor_sha256':core.TENSOR_SHA,'adapter_delta_verified':False,'merged':False,'live_promoted':False,
            'checkpoint':{'path':str(core.OUTPUT/'checkpoint-5'),'global_step':5,
                'files_sha256':{name:core.digest(files[name]) for name in core.CHECKPOINT_NAMES}}}
        files['owner_receipt_step_5.json']=core.canonical(receipt)
        return files,lineage_sha,core.digest(files['owner_receipt_step_5.json'])

    def perform(self,bad=False):
        files,lineage_sha,receipt_sha=self.fixture(bad)
        namespace={};exec(compile(probe.PROBE_BODY,'<tested-probe>','exec'),namespace)
        with patch.object(core,'LINEAGE_SHA',lineage_sha),patch.object(core,'RECEIPT_SHA',receipt_sha):
            stored,manifest=core.archive_payload(files)
            with patch.object(core,'read_native_archive',return_value=(stored,manifest)):
                return namespace['perform'](core)

    def test_measured_compression_preserves_all_hashes_and_reports_aggregate_zero_B(self):
        result=self.perform()
        self.assertTrue(result['all_nine_file_hashes_preserved'])
        self.assertLess(result['zip_deflated_level6']['archive_bytes'],result['zip_stored']['archive_bytes'])
        self.assertEqual(result['tensor_byte_partition']['lora_B'],{'tensors':1,'bytes':16384,'all_zero_bytes':16384})
        self.assertEqual(result['tensor_byte_partition']['lora_A']['all_zero_bytes'],0)
        self.assertEqual(result['successful_optimizer_steps'],0)
        self.assertEqual(result['files_written'],0)
        self.assertFalse(result['ciphertext_exported']);self.assertFalse(result['current_training_pointer_read'])
        self.assertNotIn('base.layer',json.dumps(result))

    def test_overlapping_tensor_offsets_cannot_support_compression_partition(self):
        with self.assertRaisesRegex(RuntimeError,'TENSOR_COVERAGE'):self.perform(True)

    def test_bad_bundle_never_runs_native_child(self):
        with patch.dict(os.environ,{'NOX_OWNER_REQUEST_ID':'123','NOX_OWNER_SOURCE_SHA':'a'*40}), \
             patch.object(probe,'BUNDLE',{}),patch.object(probe.subprocess,'run') as run:
            with self.assertRaisesRegex(RuntimeError,'SOURCE_PIN'):probe.main()
            run.assert_not_called()


if __name__=='__main__':unittest.main()
