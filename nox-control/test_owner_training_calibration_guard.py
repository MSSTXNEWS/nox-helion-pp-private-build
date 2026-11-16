import hashlib
import importlib.util
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

HERE=Path(__file__).parent


def load(name):
    spec=importlib.util.spec_from_file_location(name,HERE/(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


guard=load('owner_training_calibration_guard');installer=load('owner_training_calibration_guard_entry')
base=load('owner_training_disk_guard')


class GenericGuardTests(unittest.TestCase):
    def test_all_generic_dependency_pins_match_frozen_sources(self):
        continuation=load('owner_training_calibration_continue')
        for name,pin in continuation.PINS.items():
            self.assertEqual(hashlib.sha256((HERE/(name+'.py')).read_bytes()).hexdigest(),pin,name)
        self.assertEqual(guard.PROOF_SHA,continuation.PINS['owner_training_calibration_proof'])
        self.assertEqual(installer.GUARD_SHA,continuation.PINS['owner_training_calibration_guard'])

    def test_only_two_reviewed_installer_anchors_change_and_old_guard_file_stays_pinned(self):
        raw=(HERE/'owner_training_disk_guard_entry.py').read_bytes();updated=installer.transform(raw)
        expected=raw.decode().replace("load('owner_training_disk_guard',GUARD_SHA)","load('owner_training_calibration_guard',GUARD_SHA)")
        expected=expected.replace("guard_path=SCRIPTS/'owner_training_disk_guard.py'","guard_path=SCRIPTS/'owner_training_calibration_guard.py'")
        self.assertEqual(updated,expected)
        self.assertEqual(hashlib.sha256((HERE/'owner_training_disk_guard.py').read_bytes()).hexdigest(),guard.BASE_SHA)
        with self.assertRaisesRegex(RuntimeError,'INSTALLER_SOURCE'):installer.transform(raw+b'\n')

    def test_source_pin_is_checked_before_any_dependency_executes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);sentinel=root/'unexpected'
            (root/'owner_training_disk_guard.py').write_text('open('+repr(str(sentinel))+',"w").write("executed")')
            with patch.object(guard,'SCRIPTS',root),patch.object(guard,'_LOADED',[]):
                with self.assertRaisesRegex(RuntimeError,'SOURCE_PIN'):guard.runtime()
            self.assertFalse(sentinel.exists())

    def test_budget_uses_real_positive_checkpoint20_and_preserves_reserve_formula(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);checkpoint=root/'checkpoint-20';checkpoint.mkdir()
            for name in base.NAMES:(checkpoint/name).write_bytes(b'fixture')
            proof=types.SimpleNamespace(OUTPUT=root,checkpoint=lambda first,rehash:{'global_step':20})
            result=guard.budget_for({'targets':{'trainable_parameters':100,'trainable_dtype':'float32'}},{},base,proof)
            upper=100*16+128*1024**2
            self.assertEqual(result['checkpoint_global_step'],20)
            self.assertEqual(result['required_free_bytes'],4*1024**3+2*upper+256*1024**2)

    def test_scheduler_addition_is_exactly_reversible_and_duplicate_guard_is_rejected(self):
        original='def main():pass\nif __name__ == "__main__":\n    main()\n'
        context={'request':'123','source_sha':'a'*40,'receipt_sha256':'b'*64}
        updated=guard.patch_scheduler(original,hashlib.sha256(original.encode()).hexdigest(),context)
        self.assertEqual(updated.replace(guard.binding_text(context),'',1),original)
        with self.assertRaisesRegex(RuntimeError,'ALREADY_BOUND'):
            guard.patch_scheduler(updated,hashlib.sha256(updated.encode()).hexdigest(),context)


if __name__=='__main__':unittest.main()
