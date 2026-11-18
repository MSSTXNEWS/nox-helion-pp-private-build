"""Actual preimage three-file transaction in TempFS, no services or network."""
import hashlib
import importlib
import os
from pathlib import Path
import tempfile
import unittest

import native_v24_dialog_installer as base_module
import native_v24_dialog_transform as transform_module
import native_context_counter_installer as installer_module

HERE = Path(__file__).resolve().parent


class ContextInstallTransactionTest(unittest.TestCase):
    def setUp(self):
        self.base = importlib.reload(base_module)
        self.installer = importlib.reload(installer_module)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)/'nox'
        self.scripts, self.state = self.root/'scripts', self.root/'state'
        self.scripts.mkdir(parents=True); self.state.mkdir()
        for name, value in [('ROOT',self.root),('SCRIPTS',self.scripts),('STATE',self.state)]:
            setattr(self.base,name,value)
        inputs = {
            'chat_proxy.py': HERE.parent/'model_identity_binding_20261118/private_postimages/chat_proxy.py',
            'owner_model_reference_binding.py': HERE.parent/'model_reference_wording_20261118/inputs/owner_model_reference_binding.py.before',
        }
        for name, source in inputs.items():
            raw=source.read_bytes(); pin=transform_module.TRANSFORMS[name]
            self.assertEqual(hashlib.sha256(raw).hexdigest(),pin['before_sha256'])
            self.assertEqual(len(raw),pin['before_bytes'])
            target=self.scripts/name;target.write_bytes(raw)
            target.chmod(0o644 if name=='chat_proxy.py' else 0o600)
        self.installer.configure()
        self.guard_calls=0

    def guard(self):
        self.guard_calls+=1

    def prepare(self,request):
        tx=self.installer.BindingTransaction(request);tx.prepare();return tx

    def test_actual_three_files_apply_final_readback_and_owned_rollback(self):
        tx=self.prepare('731001')
        untouched=self.state/'existing_four_queue_state.json'
        untouched.write_bytes(b'{"fixture":"unrelated current queues"}\n');untouched.chmod(0o600)
        original=(untouched.read_bytes(),untouched.stat().st_ino)
        tx.replace(self.guard)
        for name,pins in transform_module.TRANSFORMS.items():
            self.assertEqual(hashlib.sha256((self.scripts/name).read_bytes()).hexdigest(),pins['after_sha256'])
        new=self.scripts/'owner_context_budget.py'
        self.assertEqual(new.read_bytes(),self.installer.ARTIFACTS[new.name])
        self.assertEqual(new.stat().st_mode&0o777,0o600);self.assertEqual(new.stat().st_nlink,1)
        report={'completed':True,'status':'APPLIED_RELOADED_USE_PENDING',
                'files_after':{name:{'sha256':pins['after_sha256'],'bytes':pins['after_bytes']}
                               for name,pins in transform_module.TRANSFORMS.items()}}
        self.assertIs(self.installer.finalize_report(report)['installed'],True)
        self.assertEqual(report['source_files_modified'],['owner_model_reference_binding.py','chat_proxy.py'])
        self.assertEqual(report['new_artifact_paths'],[str(new)])
        tx.undo(self.guard)
        for name,raw in tx.original.items():
            self.assertEqual((self.scripts/name).read_bytes(),raw)
            self.assertEqual((self.scripts/name).stat().st_mode,tx.metadata[name]['mode'])
            self.assertEqual((self.scripts/name).stat().st_uid,tx.metadata[name]['uid'])
        self.assertFalse(new.exists())
        self.assertEqual((untouched.read_bytes(),untouched.stat().st_ino),original)
        self.assertGreaterEqual(self.guard_calls,6)

    def test_identical_foreign_postimage_on_either_existing_target_is_not_replaced(self):
        for ordinal,name in enumerate(self.installer.SOURCE_ORDER):
            with self.subTest(name=name):
                # Each subcase uses its own complete transaction namespace.
                if ordinal:
                    self.tearDown();self.setUp()
                tx=self.prepare('73101'+str(ordinal));tx.replace(self.guard)
                target=self.scripts/name;old_inode=target.stat().st_ino
                foreign=self.scripts/'foreign_exact_postimage.py'
                foreign.write_bytes(target.read_bytes());foreign.chmod(target.stat().st_mode&0o777)
                os.replace(foreign,target);inode=target.stat().st_ino
                self.assertNotEqual(old_inode,inode)
                with self.assertRaisesRegex(self.base.Hold,'HOLD_SOURCE_POSTIMAGE_OWNERSHIP_DRIFT'):
                    tx.undo(self.guard)
                self.assertEqual(target.stat().st_ino,inode)
                self.assertEqual(target.read_bytes(),tx.prepared[name])
                self.assertTrue((self.scripts/'owner_context_budget.py').exists())

    def test_foreign_new_helper_after_prepare_is_not_adopted_overwritten_or_removed(self):
        tx=self.prepare('731003')
        foreign=self.scripts/'owner_context_budget.py'
        foreign.write_bytes(b'# foreign helper\n');foreign.chmod(0o600)
        inode=foreign.stat().st_ino
        with self.assertRaisesRegex(self.base.Hold,'HOLD_NEW_ARTIFACT_APPEARED'):
            tx.replace(self.guard)
        self.assertEqual(foreign.read_bytes(),b'# foreign helper\n')
        self.assertEqual(foreign.stat().st_ino,inode)
        self.assertEqual(tx.replaced,[]);self.assertEqual(tx.new_created,[])
        for name,raw in tx.original.items():self.assertEqual((self.scripts/name).read_bytes(),raw)


if __name__=='__main__':
    unittest.main()
