"""Single regression bundle for active NX03 source staging (never E07)."""
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import nx03_reviewed_uninstall_stage as nx

class NX03OwnedStageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)
        self.owner=root/'R11'/'Installer'/'Remove-InstalledPayload.ps1'
        self.reviewed=root/'C09'/'Installer'/'Remove-InstalledPayload.ps1'
        self.owner.parent.mkdir(parents=True)
        self.reviewed.parent.mkdir(parents=True)
        self.original=b'ARCHIVE-EXACT-PREIMAGE-NX03'
        self.source=("$ErrorActionPreference = 'Stop'\n" +
            "  $actual = (Get-FileHash -LiteralPath $Entry.Full -Algorithm SHA256).Hash.ToLowerInvariant()\n" +
            "\n".join(nx._REQUIRED)+"\n").encode()
        self.owner.write_bytes(self.original)
        self.reviewed.write_bytes(self.source)
        self.patches=[mock.patch.object(nx,'_REVIEWED_BLOB',nx._blob(self.source)),
            mock.patch.object(nx,'_ARCHIVED_BYTES',len(self.original)),
            mock.patch.object(nx,'_ARCHIVED_SHA256',hashlib.sha256(self.original).hexdigest())]
        for p in self.patches:
            p.start();self.addCleanup(p.stop)
    def pending(self):
        return list(self.owner.parent.glob('.nox-nx03-*.pending'))
    def test_exact_reviewed_source_only_and_idempotence(self):
        result=nx.stage_reviewed_remove(self.owner,self.reviewed)
        self.assertTrue(result['changed'])
        self.assertEqual(self.owner.read_bytes(),nx._ps51_uninstall_stage(self.source))
        self.assertEqual(self.reviewed.read_bytes(),self.source)
        self.assertEqual(self.pending(),[])
        self.assertFalse(nx.stage_reviewed_remove(self.owner,self.reviewed)['changed'])
    def test_unknown_r11_preimage_preserved(self):
        self.owner.write_bytes(b'foreign-owner-content')
        with self.assertRaisesRegex(nx.ReviewedRemoveHold,'UNKNOWN_R11_PREIMAGE'):
            nx.stage_reviewed_remove(self.owner,self.reviewed)
        self.assertEqual(self.owner.read_bytes(),b'foreign-owner-content')
        self.assertEqual(self.pending(),[])
    def test_modified_reviewed_source_refused(self):
        self.reviewed.write_bytes(self.source+b'FOREIGN')
        with self.assertRaisesRegex(nx.ReviewedRemoveHold,'UNAPPROVED_BLOB'):
            nx.stage_reviewed_remove(self.owner,self.reviewed)
        self.assertEqual(self.owner.read_bytes(),self.original)
    def test_hardlinked_owner_cannot_truncate_other_path(self):
        foreign=self.owner.parent/'protected_foreign.bin'
        os.link(self.owner,foreign)
        with self.assertRaisesRegex(nx.ReviewedRemoveHold,'NONEXCLUSIVE_FILE_HOLD'):
            nx.stage_reviewed_remove(self.owner,self.reviewed)
        self.assertEqual(foreign.read_bytes(),self.original)
        self.assertEqual(self.owner.read_bytes(),self.original)
    def test_failure_before_replace_preserves_original_and_cleans_owned_temp(self):
        with mock.patch.object(nx.os,'replace',side_effect=OSError('inject')):
            with self.assertRaisesRegex(nx.ReviewedRemoveHold,'ATOMIC_STAGE_IO_HOLD'):
                nx.stage_reviewed_remove(self.owner,self.reviewed)
        self.assertEqual(self.owner.read_bytes(),self.original)
        self.assertEqual(self.pending(),[])
    def test_foreign_owner_change_during_staging_refused_without_loss(self):
        real_read=Path.read_bytes
        def read(path):
            if path == self.owner and self.pending():
                path.write_bytes(b'foreign-update-during-staging')
            return real_read(path)
        with mock.patch.object(Path,'read_bytes',read):
            with self.assertRaisesRegex(nx.ReviewedRemoveHold,'FOREIGN_OWNER_CHANGED_HOLD'):
                nx.stage_reviewed_remove(self.owner,self.reviewed)
        self.assertEqual(self.owner.read_bytes(),b'foreign-update-during-staging')
        self.assertEqual(self.pending(),[])
    def test_symlink_owner_denied(self):
        self.owner.unlink()
        foreign=self.owner.parent/'user_file.bin';foreign.write_bytes(self.original)
        self.owner.symlink_to(foreign)
        with self.assertRaises(nx.ReviewedRemoveHold):
            nx.stage_reviewed_remove(self.owner,self.reviewed)
        self.assertEqual(foreign.read_bytes(),self.original)

if __name__=='__main__':unittest.main()
