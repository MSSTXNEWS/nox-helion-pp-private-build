"""Focused real TempFS ownership/partial-effect tests; no native service calls."""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import native_current_recovery_install as native


@contextmanager
def fixture(request='7010000000'):
    with tempfile.TemporaryDirectory(prefix='nox-recovery-install-') as temporary:
        root = Path(temporary)
        for name in ('scripts','config','state'):
            (root/name).mkdir()
        lock = root/'state/owner_maintenance.lock'
        lock.touch(mode=0o600)
        info = lock.stat()
        paths = ['scripts/owner_subagent_dispatcher.py',
            'scripts/owner_subagent_instruction_truth.py','config/owner_native_subagents.json']
        for index,path in enumerate(paths):
            (root/path).write_bytes(('before-'+str(index)).encode())
            (root/path).chmod(0o600 if path.endswith('.json') else 0o644)
        with patch.object(native,'ROOT',root),patch.object(native,'PROTECTED',{}),patch.object(
                native,'LOCK_PIN',{'dev':info.st_dev,'ino':info.st_ino}),patch.object(
                native,'OWNER_UID',os.geteuid()),patch.object(native,'OWNER_GID',os.getegid()):
            installer = native.Installer(request,'a'*40)
            try:
                installer.acquire()
                for index,path in enumerate(paths):
                    installer.before[path] = installer.read_path(path)
                    installer.after[path] = ('after-'+str(index)).encode()
                installer.begin()
                for index,path in enumerate(paths):
                    installer.stage_file(path,index)
                yield installer,root,paths
            finally:
                installer.close()


class NativeRecoveryInstall(unittest.TestCase):
    def test_foreign_same_bytes_inode_holds_entire_rollback_set(self):
        with fixture() as (installer,root,paths):
            for index,path in enumerate(paths):
                installer.install_file(path,index)
            before = {path:(root/path).stat().st_ino for path in paths}
            path = paths[1]
            replacement = root/'scripts/foreign-same-bytes'
            replacement.write_bytes(installer.after[path]); replacement.chmod(0o644)
            replacement.replace(root/path)
            foreign = (root/path).stat().st_ino
            self.assertNotEqual(foreign,before[path])
            with self.assertRaisesRegex(native.Hold,'OWNED_POSTIMAGE_CAS'):
                installer.rollback_files()
            self.assertEqual(installer.rollback_attempts,[])
            for path in paths:
                self.assertEqual((root/path).read_bytes(),installer.after[path])
                self.assertEqual((root/path).stat().st_ino,foreign if path == paths[1] else before[path])

    def test_rename_ack_loss_reconciles_owned_inode_and_preserves_modes(self):
        with fixture('7010000001') as (installer,root,paths):
            replace = native.os.replace
            calls = []
            def lose_ack(*args,**kwargs):
                calls.append(args)
                replace(*args,**kwargs)
                raise TimeoutError('fixture rename completed but ACK lost')
            with patch.object(native.os,'replace',side_effect=lose_ack):
                with self.assertRaises(TimeoutError):
                    installer.install_file(paths[0],0)
            self.assertEqual(len(calls),1)
            self.assertEqual(installer.replace_attempts,[paths[0]])
            self.assertEqual(installer.owned_after(paths[0]).st_ino,installer.staged[paths[0]].st_ino)
            self.assertEqual(installer.rollback_files(),[paths[0]])
            for path in paths:
                raw,info = installer.before[path]
                self.assertEqual((root/path).read_bytes(),raw)
                self.assertEqual((root/path).stat().st_mode & 0o777,info.st_mode & 0o777)
            for index in range(3):
                backup = root/'state'/installer.attempt_name/f'original_{index}.bin'
                self.assertEqual(backup.stat().st_mode & 0o777,0o600)


if __name__ == '__main__':
    unittest.main()
