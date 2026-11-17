"""One targeted rollback-ownership regression, entirely in real TempFS."""
from pathlib import Path
import os
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'fixed_inputs'))
import test_native_model_binding_installer as author

author.INPUT = HERE.parent / 'resonance_native_20261118/source_inputs_private'
author.UI = HERE.parent / 'web29_original_chat_audit_20261117/source_v13/site/nox-ui.js'


class SourceRollbackOwnership(author.InstallerTests):
    def test_identical_postimage_on_foreign_inode_is_not_replaced_by_rollback(self):
        tx = self.transaction('246801')
        tx.replace(self.quiescent)
        name = self.module.SOURCE_ORDER[-1]
        target = self.scripts / name
        owned_inode = target.stat().st_ino
        foreign = self.scripts / 'controlled-foreign-postimage.py'
        foreign.write_bytes(target.read_bytes())
        foreign.chmod(target.stat().st_mode & 0o777)
        os.replace(foreign, target)
        foreign_inode = target.stat().st_ino
        self.assertNotEqual(foreign_inode, owned_inode)
        with self.assertRaises(self.base.Hold):
            tx.undo(self.quiescent)
        self.assertEqual(target.stat().st_ino, foreign_inode)
        self.assertEqual(target.read_bytes(), tx.prepared[name])


if __name__ == '__main__':
    unittest.main()
