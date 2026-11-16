"""The second recovery may reuse only the exact unstarted, valid-LF corpus."""
import hashlib
import importlib.util
import json
from pathlib import Path
import types
import unittest
from unittest.mock import Mock, patch

HERE=Path(__file__).parent
spec=importlib.util.spec_from_file_location('jsonl_recovery_test',HERE/'owner_training_jsonl_recovery.py')
entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)


class JsonlRecoveryTests(unittest.TestCase):
    def proof(self):
        return {'state':'EXACT_DATASET_DELIMITERS_VERIFIED','dataset_sha256':entry.DATASET_SHA,
            'source_bytes':305243573,'full_sha256_verified':True,'lf_jsonl_valid':True,
            'actual_lf_valid_records':136714,'actual_lf_invalid_records':0,'legacy_splitlines_invalid':True,
            'first_legacy_failure':{'exception':'JSONDecodeError'}}

    def recovery(self):
        return types.SimpleNamespace(unstarted_output=Mock(return_value={'dataset_sha256':entry.DATASET_SHA,
            'checkpoint_count':0,'optimizer_updates_before_recovery':0}),DATASET_BYTES=305243573)

    def test_exact_reviewed_runtime_pins_and_failed_flag(self):
        for name,pin in [('owner_training_recovery_entry.py',entry.RECOVERY_SHA),
                         ('owner_training_recovery_chain.py',entry.CHAIN_SHA),
                         ('owner_training_disk_guard_entry.py',entry.INSTALLER_SHA),
                         ('owner_training_corpus_probe.py',entry.CORPUS_PROBE_SHA),
                         ('owner_training_disk_guard.py',entry.GUARD_SHA),('hybrid_training_entry.py',entry.HYBRID_AFTER)]:
            self.assertEqual(entry.digest((HERE/name).read_bytes()),pin,name)
        self.assertEqual(entry.digest(('OWNER_HYBRID_FAILED request='+entry.FAILED_REQUEST+'\n').encode()),entry.FAILED_HOLD_SHA)

    def test_lf_preflight_is_recorded_before_model_work_and_cached_only_after_identity_check(self):
        recovery=self.recovery();original=recovery.unstarted_output;corpus=types.SimpleNamespace(read_only_probe=Mock(return_value=self.proof()))
        entry.configure_recovery(recovery,corpus)
        first=recovery.unstarted_output();second=recovery.unstarted_output()
        self.assertEqual(first,second);self.assertEqual(first['jsonl_lf_preflight'],self.proof())
        self.assertEqual(original.call_count,2);corpus.read_only_probe.assert_called_once()
        self.assertEqual(recovery.FAILED_REQUEST,entry.FAILED_REQUEST)
        self.assertEqual(recovery.HYBRID_BEFORE,entry.HYBRID_BEFORE);self.assertEqual(recovery.HYBRID_AFTER,entry.HYBRID_AFTER)

    def test_invalid_lf_or_changed_dataset_blocks_before_model_loading(self):
        for change in ({'lf_jsonl_valid':False},{'actual_lf_valid_records':136713},
                       {'actual_lf_invalid_records':1},{'dataset_sha256':'0'*64},{'full_sha256_verified':False}):
            recovery=self.recovery();corpus=types.SimpleNamespace(read_only_probe=lambda:{**self.proof(),**change})
            entry.configure_recovery(recovery,corpus)
            with self.subTest(change=change),self.assertRaisesRegex(RuntimeError,'LF_PREFLIGHT'):recovery.unstarted_output()
        recovery=self.recovery();recovery.unstarted_output.return_value['dataset_sha256']='0'*64
        corpus=types.SimpleNamespace(read_only_probe=Mock())
        entry.configure_recovery(recovery,corpus)
        with self.assertRaisesRegex(RuntimeError,'DATASET_CHANGED'):recovery.unstarted_output()
        corpus.read_only_probe.assert_not_called()

    def test_exact_failed_receipt_pin_precedes_any_other_read(self):
        recovery=types.SimpleNamespace(read=lambda path:b'{}',document=Mock())
        with self.assertRaisesRegex(RuntimeError,'FAILED_RECEIPT_PIN'):entry.failed_evidence(recovery,None,None)
        recovery.document.assert_not_called()

    def test_different_failed_owner_source_cannot_be_recovered(self):
        old={'schema':'NOX_OWNER_TRAINING_RESUME_V1','request':entry.FAILED_REQUEST,'source_sha':'0'*40}
        raw=json.dumps(old).encode();recovery=types.SimpleNamespace(read=lambda path:raw,document=lambda path:{},
            POINTER=Path('/tmp/fixture'),PREPARATION_SHA='c'*64,DATASET_BYTES=305243573)
        with patch.object(entry,'FAILED_RECEIPT_SHA',entry.digest(raw)):
            with self.assertRaisesRegex(RuntimeError,'FAILED_LINEAGE'):entry.failed_evidence(recovery,None,None)


if __name__=='__main__':unittest.main()
