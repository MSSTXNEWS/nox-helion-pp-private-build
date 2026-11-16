import importlib.util
import json
import os
from pathlib import Path
import types
import unittest
from unittest.mock import Mock, patch

HERE=Path(__file__).parent
spec=importlib.util.spec_from_file_location('jsonl_observe_test',HERE/'owner_training_jsonl_observe.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class ObserveTransitionTests(unittest.TestCase):
    def test_exact_pins_are_frozen_and_source_consistent(self):
        self.assertEqual(module.digest((HERE/'owner_training_jsonl_recovery.py').read_bytes()),module.JSONL_ENTRY_SHA)
        self.assertEqual(module.digest((HERE/'owner_training_recovery_observe.py').read_bytes()),module.OBSERVER_SHA)

    def test_pending_context_requires_all_three_exact_identifiers(self):
        value={'request':'123','source_sha':'a'*40,'receipt_sha256':'b'*64}
        with patch.dict(os.environ,{'NOX_TRAINING_RECOVERY_CONTEXT':json.dumps(value)}):
            self.assertEqual(module.read_context(),value)
        with patch.dict(os.environ,{'NOX_TRAINING_RECOVERY_CONTEXT':json.dumps({'request':'123'})}):
            with self.assertRaisesRegex(RuntimeError,'PENDING_CONTEXT'):module.read_context()

    def test_configuring_context_does_not_start_training_or_parse_corpus(self):
        recovery=types.SimpleNamespace(main=Mock(),unstarted_output=Mock())
        corpus=types.SimpleNamespace(read_only_probe=Mock())
        def configure(r,c):r.HYBRID_AFTER='f2';r.FAILED_REQUEST='6905505383'
        entry=types.SimpleNamespace(RECOVERY_SHA='r',CORPUS_PROBE_SHA='c',configure_recovery=Mock(side_effect=configure),
            load=lambda name,pin:recovery if name=='owner_training_recovery_entry' else corpus)
        observer=types.SimpleNamespace(main=Mock())
        selected=module.configure_observer(entry,observer)
        self.assertIs(selected,recovery);self.assertEqual(observer.load_recovery().HYBRID_AFTER,'f2')
        recovery.main.assert_not_called();recovery.unstarted_output.assert_not_called()
        corpus.read_only_probe.assert_not_called();observer.main.assert_not_called()

    def test_observation_cannot_reuse_initial_owner_request(self):
        value={'request':'123','source_sha':'a'*40,'receipt_sha256':'b'*64}
        with patch.dict(os.environ,{'NOX_OWNER_REQUEST_ID':'123','NOX_OWNER_SOURCE_SHA':'c'*40,
                                   'NOX_TRAINING_RECOVERY_CONTEXT':json.dumps(value)},clear=True),patch.object(module,'load') as load:
            with self.assertRaisesRegex(RuntimeError,'NEW_REQUEST_REQUIRED'):module.main()
            load.assert_not_called()


if __name__=='__main__':unittest.main()
