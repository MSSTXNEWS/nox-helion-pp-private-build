import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import owner_training_source_delta as probe


class SourceDeltaTests(unittest.TestCase):
    def test_exact_admission_reports_one_changed_source_without_exporting_content(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);state=root/'state';scripts=root/'scripts';output=root/'output'
            for path in (state,scripts,output):path.mkdir()
            pins={}
            for index in range(20):
                path=scripts/('source_'+str(index)+'.py');raw=b'PRIVATE_SOURCE_TEXT'
                path.write_bytes(raw);pins[str(path)]=probe.digest(raw)
            pointer={'schema':'NOX_OWNER_TRAINING_ADMISSION_V1','sources':pins}
            old={'schema':'NOX_OWNER_TRAINING_RESUME_V1','request':'123','source_sha':'a'*40,'admission':pointer}
            raw=json.dumps(old).encode();(state/'owner_maintenance_123.json').write_bytes(raw)
            context={'request':'123','source_sha':'a'*40,'receipt_sha256':probe.digest(raw)}
            raw=json.dumps(pointer).encode();(state/'owner_training_admission.json').write_bytes(raw)
            pointer_sha=probe.digest(raw)
            (scripts/'source_7.py').write_bytes(b'CHANGED_PRIVATE_SOURCE')
            native=scripts/'train_qlora_35b_t866u.py';native.write_bytes(b'PRIVATE_NATIVE_SOURCE')
            checkpoint=output/'checkpoint-5';checkpoint.mkdir();hashes={}
            for filename in probe.FILES:
                raw=('PRIVATE_CHECKPOINT_'+filename).encode();(checkpoint/filename).write_bytes(raw);hashes[filename]=probe.digest(raw)
            baseline={'checkpoint':{'global_step':5,'path':str(checkpoint),'files_sha256':hashes}}
            raw=json.dumps(baseline).encode();(output/'owner_receipt_step_5.json').write_bytes(raw)
            with patch.multiple(probe,ROOT=root,STATE=state,SCRIPTS=scripts,OUTPUT=output,
                CONTEXT=context,POINTER_SHA=pointer_sha,BASELINE_SHA=probe.digest(raw),
                NATIVE_SHA=probe.digest(native.read_bytes())),patch.object(probe,'service',return_value={'state':'FATAL'}):
                result=probe.snapshot()
            self.assertEqual(result['mismatched_source_count'],1)
            self.assertEqual([row['filename'] for row in result['source_rows'] if not row['matches_expected']],['scripts/source_7.py'])
            self.assertTrue(result['current_pointer']['matches_sealed_admission'])
            self.assertTrue(result['pointer_unchanged_during_snapshot'])
            self.assertTrue(result['baseline_checkpoint']['seven_files_match'])
            self.assertNotIn('PRIVATE_',json.dumps(result))
            self.assertEqual((state/'owner_training_admission.json').read_bytes(),json.dumps(pointer).encode())

    def test_fifo_and_symlink_are_rejected_without_blocking(self):
        with tempfile.TemporaryDirectory() as name:
            path=Path(name)/'fifo';os.mkfifo(path)
            with self.assertRaisesRegex(RuntimeError,'FILE_SCOPE'):probe.read(path)
            link=Path(name)/'link';link.symlink_to(path)
            with self.assertRaisesRegex(RuntimeError,'SYMLINK'):probe.read(link)

    def test_source_outside_fixed_tree_is_not_read(self):
        with self.assertRaisesRegex(RuntimeError,'PATH_SCOPE'):
            probe.file_row(Path('/etc/shadow'),'a'*64)

    def test_wrong_receipt_hash_cannot_supply_source_paths(self):
        with tempfile.TemporaryDirectory() as name:
            path=Path(name)/'receipt';path.write_bytes(b'{"private":"not exported"}')
            with self.assertRaisesRegex(RuntimeError,'SEALED_RECEIPT'):probe.document(path,'a'*64)


if __name__=='__main__':unittest.main()
