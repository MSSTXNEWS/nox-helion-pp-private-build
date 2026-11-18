"""Read-only diagnostics must remain useful without exposing private log text."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('training_diagnostic', Path(__file__).with_name('owner_training_runtime_diagnostic.py'))
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)


class TrainingDiagnosticTests(unittest.TestCase):
    def test_log_projection_keeps_diagnosis_and_discards_private_text(self):
        private = 'PRIVATE_TRAINING_PROMPT_AND_SECRET'
        raw = ('FileNotFoundError: /private/' + private + '\n'
               "ModuleNotFoundError: No module named 'torch'\n"
               "ModuleNotFoundError: No module named '" + private + "'\n"
               'CUDA out of memory: ' + private + '\n'
               '{"state":"HOLD_QWEN_CGROUP_RESERVE","messages":"' + private + '"}\n').encode()
        result = diagnostic.projected_log(raw)
        encoded = json.dumps(result)
        self.assertNotIn(private, encoded)
        self.assertNotIn('/private/', encoded)
        self.assertIn('HOLD_QWEN_CGROUP_RESERVE', encoded)
        self.assertIn('CUDA_OUT_OF_MEMORY', encoded)
        self.assertIn('"missing_module": "torch"', encoded)
        self.assertIn('UNLISTED_MODULE', encoded)
        self.assertFalse(result['raw_logs_exported'])

    def test_metadata_exposes_only_whitelisted_scalars_not_content(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'receipt.json'
            path.write_text(json.dumps({'state': {'private': 'SECRET'}, 'phase': 'PRIVATE',
                'successful_optimizer_steps': 55, 'training_allowed': True, 'loss': 0.93,
                'messages': 'SECRET', 'api_key': 'SECRET', 'reason': 'HOLD_QWEN_CGROUP_RESERVE'}))
            result = diagnostic.metadata(path, project=True)
        self.assertEqual(result['fields'], {'successful_optimizer_steps': 55,
            'training_allowed': True, 'loss': 0.93, 'reason': 'HOLD_QWEN_CGROUP_RESERVE'})
        self.assertNotIn('SECRET', json.dumps(result))
        self.assertTrue(result['stable'])

    def test_symlink_ancestors_and_fifos_are_never_read(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            real = root / 'real'
            real.mkdir()
            (real / 'secret').write_text('SECRET')
            (root / 'alias').symlink_to(real, target_is_directory=True)
            fifo = root / 'pipe'
            os.mkfifo(fifo)
            for path in (root / 'alias/secret', fifo):
                with self.assertRaises((OSError, diagnostic.ReadHold)):
                    diagnostic.regular_read(path)

    def test_tail_is_bounded_and_hash_is_labeled_as_tail_only(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'log'
            path.write_bytes(b'x' * 100 + b'CUDA out of memory')
            raw, info = diagnostic.regular_read(path, 20, tail=True)
            self.assertEqual(len(raw), 20)
            self.assertEqual(info['hash_scope'], 'TAIL_ONLY')
            self.assertGreater(info['bytes'], info['read_bytes'])
            with self.assertRaises(diagnostic.ReadHold):
                diagnostic.regular_read(path, 20)

    def test_only_fixed_read_only_supervisor_commands_are_allowed(self):
        with patch.object(diagnostic.subprocess, 'run') as command:
            for action, channel in (('start', None), ('restart', None), ('stop', None),
                                    ('tail', 'other-service'), ('status', 'stderr')):
                with self.assertRaises(diagnostic.ReadHold):
                    diagnostic.supervisor(action, channel)
            command.assert_not_called()

    def test_observe_does_not_import_trainer_or_report_saved_steps_as_live(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'scripts').mkdir()
            (root / 'state').mkdir()
            (root / 'logs').mkdir()
            output = root / 'output'
            output.mkdir()
            (root / 'scripts/qwen_student_training_entry_revision.py').write_text('raise RuntimeError("DO_NOT_IMPORT")\n')
            (output / 'owner_progress.json').write_text('{"successful_optimizer_steps":55,"messages":"SECRET"}')
            (root / 'logs/train_volta_t866u.log').write_text('ModuleNotFoundError: No module named \'torch\'\nSECRET')
            config = root / 'service.conf'
            config.write_text('[program:nox-train-volta-t866u]\nstdout_logfile=/outside/secret-t866u\n')
            with patch.object(diagnostic, 'ROOT', root), patch.object(diagnostic, 'OUTPUT', output), \
                    patch.object(diagnostic, 'CONFIG', config), \
                    patch.object(diagnostic, 'supervisor', return_value={'state': 'FATAL', 'pid': None}):
                result = diagnostic.observe()
        self.assertEqual(result['state'], 'READ_ONLY_DIAGNOSIS_COMPLETE')
        self.assertEqual(result['metadata']['student_progress']['fields']['successful_optimizer_steps'], 55)
        self.assertFalse(result['trainer_imported'])
        self.assertFalse(result['live_optimizer_steps_verified'])
        self.assertFalse(result['checkpoint_payloads_verified'])
        self.assertEqual(result['files_written'], 0)
        self.assertEqual(result['service_mutations'], 0)
        self.assertNotIn('SECRET', json.dumps(result))
        self.assertNotIn('DO_NOT_IMPORT', json.dumps(result))
        self.assertNotIn('/outside/', json.dumps(result))


if __name__ == '__main__':
    unittest.main()
