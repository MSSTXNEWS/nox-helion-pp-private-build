"""Offline test: derived original WEB ZIP stays immutable, owner stage is gated."""
import hashlib
from pathlib import Path
import posixpath
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from coordination.onepass import build_legacy_compat_v2 as overlay


class OnepassNativeCompat(unittest.TestCase):
    def setUp(self):
        self.root=Path(tempfile.mkdtemp())
        self.addCleanup(lambda:__import__('shutil').rmtree(self.root))
        self.script=Path('coordination/onepass/nox-legacy-chat-bridge-v293.js')
        self.client=("const rd=r.body.getReader(),dec=new TextDecoder();let buf='',out='',err=null;\n"
          "if(ev.type==='done'&&!out&&ev.note)err=ev.note;\n"
          "if(err&&!out)throw new Error(err);return out};").encode()
    def test_native_owner_receipt_gate_and_windows_no_loss(self):
        with patch.object(overlay,'KIT_SHA',overlay.digest(self.client)):
            modified=overlay.patch_legacy_client(self.client).decode()
        self.assertIn('HOLD_NATIVE_DONE_NOT_VERIFIED',modified)
        self.assertIn("ownerStage=window.NOX_NATIVE_OWNER===true",modified)
        self.assertIn('if(err&&(ownerStage||!out))',modified)
        self.assertIn('if(ownerStage&&!doneVerified)',modified)
        self.assertIn('return out};',modified)
    def test_nested_original_owner_mount_paths(self):
        for name in overlay.PAGES:
            page=overlay.patch_html(b'<html><head></head><body></body></html>',name).decode()
            ref=page.split('src="',1)[1].split('"',1)[0]
            resolved=posixpath.normpath(posixpath.join(posixpath.dirname(name),ref))
            self.assertEqual(resolved,overlay.NATIVE_SCRIPT)
        self.assertEqual(len(overlay.PAGES),14)
    def test_zip_source_sha_and_exact_change_set(self):
        archive=self.root/'source.zip'
        with zipfile.ZipFile(archive,'w') as z:
            for path in overlay.PAGES:
                z.writestr(path,'<html><head></head><body>Owner HTML</body></html>')
            z.writestr(overlay.SSE_CLIENT,self.client)
            z.writestr('site/safe-existing.txt','untouched')
        sha=overlay.sha_file(archive)
        out=self.root/'derived.zip'
        with patch.object(overlay,'BASE_SHA',sha),patch.object(overlay,'BASE_COUNT',16),patch.object(overlay,'KIT_SHA',overlay.digest(self.client)):
            receipt=overlay.build(archive,out,self.script)
        self.assertEqual(receipt['html_pages_injected'],14)
        self.assertEqual(receipt['base_entries_unchanged'],1)
        self.assertFalse(receipt['new_backend'])
        with zipfile.ZipFile(archive) as before,zipfile.ZipFile(out) as after:
            self.assertEqual(after.testzip(),None)
            self.assertEqual(after.read('site/safe-existing.txt'),before.read('site/safe-existing.txt'))
            self.assertEqual(after.read(overlay.NATIVE_SCRIPT),self.script.read_bytes())
            self.assertEqual(len(after.namelist()),17)
        self.assertEqual(overlay.sha_file(archive),sha)
    def test_unknown_zip_fails_before_output(self):
        bad=self.root/'wrong.zip'
        bad.write_bytes(b'bad source')
        with self.assertRaisesRegex(ValueError,'HOLD_BASE_SHA'):
            overlay.build(bad,self.root/'no.zip',self.script)
        self.assertFalse((self.root/'no.zip').exists())


if __name__=='__main__':
    unittest.main()
