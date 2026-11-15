"""NOX V61 strict synthetic archive QA. No age/private keys/OneHost/weights."""
from __future__ import annotations
import hashlib
import io
import json
import tarfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from nox_runpod.teacher_mesh.v61 import checkpoint_backup as backup


class TarManifestNoLoss(unittest.TestCase):
    def setUp(self):
        self.rows=[(f'NOX_CHECKPOINTS/ckpt-{i:02d}.pt',
                    f'fake optimizer {i:02d}'.encode()) for i in range(10)]
        self.records=[{'path':n,'size_bytes':len(data),
                       'sha256':hashlib.sha256(data).hexdigest()}
                      for n,data in self.rows]
        self.manifest={'schema':'NOX_V61_CHECKPOINT_OPTIMIZER_MANIFEST_V1',
                       'origin_instance_id':60509551,
                       'files':self.records,
                       'original_files_deleted':False}

    def bundle(self, *,extra=(),omit=(),duplicate=(),link=None,
               second_manifest=False,manifest=None,replace=None):
        manifest=self.manifest if manifest is None else manifest
        link={} if link is None else link
        buf=io.BytesIO()
        with tarfile.open(fileobj=buf,mode='w:gz') as tar:
            for name,data in [*self.rows,*extra,*duplicate]:
                if name in omit:continue
                if replace is not None and name==replace[0]:
                    data=replace[1]
                info=tarfile.TarInfo(name)
                info.mtime=0
                if name in link:
                    kind,target=link[name]
                    info.type=kind;info.linkname=target;info.size=0
                    tar.addfile(info)
                else:
                    info.size=len(data)
                    tar.addfile(info,io.BytesIO(data))
            raw=json.dumps(manifest,sort_keys=True).encode()
            meta=tarfile.TarInfo('RESTORE_MANIFEST.json')
            meta.size=len(raw)
            tar.addfile(meta,io.BytesIO(raw))
            if second_manifest:
                tar.addfile(meta,io.BytesIO(raw))
        return buf.getvalue()

    def test_original_exact_10_files_are_accepted(self):
        out=backup.verify_plaintext_tar(self.bundle())
        self.assertEqual(out['count'],10)
        self.assertEqual(out['total_bytes'],sum(map(lambda x:len(x[1]),self.rows)))

    def test_unlisted_valid_file_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError,'HOLD_TAR_MEMBER_COVERAGE'):
            backup.verify_plaintext_tar(self.bundle(extra=[
                ('NOX_CHECKPOINTS/EXTRA.pt',b'unlisted bytes')]))

    def test_missing_manifest_file_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError,'HOLD_TAR_MEMBER_COVERAGE'):
            backup.verify_plaintext_tar(self.bundle(omit={self.rows[0][0]},
                extra=[('NOX_CHECKPOINTS/UNLISTED.pt',b'other')]))

    def test_duplicate_member_with_same_bytes_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError,'HOLD_TAR_DUPLICATE_MEMBER'):
            backup.verify_plaintext_tar(self.bundle(duplicate=[self.rows[0]]))

    def test_duplicate_restore_manifest_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError,'HOLD_TAR_DUPLICATE_MEMBER'):
            backup.verify_plaintext_tar(self.bundle(second_manifest=True))

    def test_symlink_member_not_followed(self):
        name=self.rows[0][0]
        with self.assertRaisesRegex(RuntimeError,'HOLD_TAR_UNSAFE_MEMBER'):
            backup.verify_plaintext_tar(self.bundle(link={
                name:(tarfile.SYMTYPE,self.rows[1][0])}))

    def test_hardlink_member_not_followed(self):
        name=self.rows[0][0]
        with self.assertRaisesRegex(RuntimeError,'HOLD_TAR_UNSAFE_MEMBER'):
            backup.verify_plaintext_tar(self.bundle(link={
                name:(tarfile.LNKTYPE,self.rows[1][0])}))

    def test_path_traversal_in_manifest_fails_closed(self):
        manifest={**self.manifest,'files':[dict(row) for row in self.records]}
        manifest['files'][0]['path']='NOX_CHECKPOINTS/../secret'
        with self.assertRaisesRegex(RuntimeError,'HOLD_MANIFEST_PATH'):
            backup.verify_plaintext_tar(self.bundle(manifest=manifest))

    def test_tampered_original_file_sha_is_never_accepted(self):
        replacement=(self.rows[0][0],b'fake optimizer XXX')
        with self.assertRaisesRegex(RuntimeError,'HOLD_CHECKPOINT_RESTORE_HASH'):
            backup.verify_plaintext_tar(self.bundle(replace=replacement))

    def test_integrated_age_decryption_route_uses_strict_audit(self):
        raw=self.bundle()
        with patch.object(backup.subprocess,'run',return_value=SimpleNamespace(
                returncode=0,stdout=raw)) as runner:
            out=backup.verify(Path('cipher.age'),Path('test_identity.agekey'))
        self.assertEqual(out['count'],10)
        self.assertEqual(out['plaintext_sha256'],hashlib.sha256(raw).hexdigest())
        self.assertEqual(runner.call_args.args[0][:4],['age','-d','-i','test_identity.agekey'])

    def test_decrypt_failure_never_accepted(self):
        with patch.object(backup.subprocess,'run',return_value=SimpleNamespace(
                returncode=2,stdout=b'')):
            with self.assertRaisesRegex(RuntimeError,'HOLD_TEST_RESTORE_DECRYPT'):
                backup.verify(Path('bad.age'),Path('test_identity.agekey'))


if __name__=='__main__':unittest.main()
