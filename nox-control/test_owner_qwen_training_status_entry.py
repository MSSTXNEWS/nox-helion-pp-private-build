import base64
import hashlib
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

import owner_qwen_training_status as reader
import owner_qwen_training_status_entry as entry


class QwenStatusEntryTests(unittest.TestCase):
    def setUp(self):
        bundle = {name + '.py': base64.b64encode(Path(name + '.py').read_bytes()).decode() for name in
                  ('owner_training_status_entry', 'owner_qwen_training_status',
                   'owner_qwen_training_observe', 'owner_training_status_binding')}
        change = patch.object(entry, 'BUNDLE', bundle); change.start(); self.addCleanup(change.stop)

    def test_exact_old_installer_and_stable_hooks_with_required_context(self):
        module = entry.configure()
        self.assertEqual(module.STATUS_SHA, entry.STATUS_SHA)
        self.assertEqual(module.PREVIOUS_STATUS_SHA, entry.PREVIOUS_STATUS_SHA)
        self.assertEqual(module.LAST_INSTALLED_STATUS_SHA, entry.PREVIOUS_STATUS_SHA)
        self.assertEqual(module.BINDING_SHA, '91df0894f52e07ae36f6f05bcb17c846c1b06da88427f45bfe52faf8e50fc1fa')
        self.assertEqual(module.STREAM_SHA, '5b7bafde0c25fa26d6b8f98dfbb4958f0faa42ee77292da561834a63097a2e8e')
        self.assertEqual(module.EVIDENCE_SHA, 'ea66e05f30472b066444058ac18d0c7af74def410bde760396d1e2431161e8b2')
        with patch.dict(module.os.environ, {'NOX_TRAINING_RECOVERY_CONTEXT': ''}):
            with self.assertRaisesRegex(RuntimeError, 'CONTEXT_REQUIRED'):
                module.read_context(reader)

    def test_pin_mismatch_cannot_execute_or_supply_reader(self):
        for name in ('owner_training_status_entry.py', 'owner_qwen_training_status.py', 'owner_qwen_training_observe.py'):
            with patch.dict(entry.BUNDLE, {name: base64.b64encode(b'raise AssertionError("foreign")').decode()}):
                with self.assertRaisesRegex(RuntimeError, 'BUNDLE_PIN'):
                    entry.configure()

    def test_only_owned_reader_observer_preimages_and_idempotent_rows(self):
        module = entry.configure()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); scripts = root / 'scripts'; scripts.mkdir(); (root / 'config').mkdir()
            for name in ('chat_proxy.py', 'nox_v137_owner_self_observation.py'):
                (scripts / name).write_bytes(b'unchanged fixture')
            for name in ('owner_training_status.py', 'owner_training_status_binding.py'):
                (scripts / name).write_bytes(Path(name).read_bytes())
            deploy = types.SimpleNamespace(ROOT=root, SCRIPTS=scripts, plain=lambda p: p, read=lambda p, *args: p.read_bytes())
            binding = types.SimpleNamespace(patch_proxy=lambda raw: raw, patch_self_observation=lambda raw: raw)
            context = dict(reader.INITIAL)
            rows = module.sources(deploy, reader, binding, context)
            self.assertEqual({r['path'].name for r in rows if r['changed']},
                             {'owner_training_status.py', 'owner_training_status.json', 'owner_qwen_training_observe.py'})
            for row in rows:
                row['path'].write_bytes(row['new'])
            self.assertFalse(any(r['changed'] for r in module.sources(deploy, reader, binding, context)))
            (scripts / 'owner_qwen_training_observe.py').write_bytes(b'foreign observer')
            with self.assertRaisesRegex(RuntimeError, 'OBSERVER_PREIMAGE'):
                module.sources(deploy, reader, binding, context)
            (scripts / 'owner_qwen_training_observe.py').write_bytes(Path('owner_qwen_training_observe.py').read_bytes())
            (scripts / 'owner_training_status.py').write_bytes(b'foreign reader')
            with self.assertRaisesRegex(RuntimeError, 'MODULE_PREIMAGE'):
                module.sources(deploy, reader, binding, context)

    def test_frozen_dependencies_and_sources_compile(self):
        for name, pin in (('owner_training_status_entry', entry.ENTRY_SHA),
                          ('owner_training_status', entry.PREVIOUS_STATUS_SHA),
                          ('owner_qwen_training_status', entry.STATUS_SHA),
                          ('owner_qwen_training_observe', entry.OBSERVER_SHA)):
            raw = Path(name + '.py').read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), pin)
            compile(raw, '<reviewed-source>', 'exec')


if __name__ == '__main__':
    unittest.main()
