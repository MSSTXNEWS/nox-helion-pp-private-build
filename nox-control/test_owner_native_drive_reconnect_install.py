import base64
import hashlib
import types
from pathlib import Path
import tempfile
import unittest

src=Path(__file__).with_name('owner_native_drive_reconnect_install.py')
m=types.ModuleType('owner_native_drive_reconnect_install')
content=src.read_text().replace('BUNDLE = __NOX_BUNDLE_JSON__','BUNDLE = {}')
exec(compile(content,str(src),'exec'),m.__dict__)

class InstallContractTests(unittest.TestCase):
    def test_bundle_rejects_unverified_hash(self):
        good={}
        for name,text in [('nox_drive_reconnect.py','#!/usr/bin/env python3\npass\n'),
                          ('nox_drive_reconnect_loop.sh','#!/bin/sh\nexit 0\n'),
                          ('nox-drive-reconnect.conf','[program:nox-drive-reconnect]\n')]:
            raw=text.encode()
            good[name]={'content':base64.b64encode(raw).decode(), 'sha256':hashlib.sha256(raw).hexdigest()}
        verified=m.decode_bundle(good)
        self.assertEqual(set(verified),m.EXPECTED)
        good['nox_drive_reconnect.py']['sha256']='0'*64
        with self.assertRaisesRegex(m.Hold,'HOLD_DRIVE_RECONNECT_BUNDLE_HASH'):
            m.decode_bundle(good)
    def test_immutable_backup_and_exact_readback(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'script.py'
            p.write_bytes(b'old')
            self.assertEqual(m.atomic_install(p,b'new'),'INSTALLED_VERIFIED')
            self.assertEqual(p.read_bytes(),b'new')
            self.assertEqual(m.atomic_install(p,b'new'),'ALREADY_CURRENT')
            backups=list(Path(d).glob('.script.py.previous-*'))
            self.assertEqual(len(backups),1)
            self.assertEqual(backups[0].read_bytes(),b'old')
    def test_symlink_destination_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            t=Path(d)/'target'
            t.write_text('original')
            link=Path(d)/'link'
            link.symlink_to(t)
            with self.assertRaisesRegex(m.Hold,'HOLD_DRIVE_RECONNECT_DEST_LINK'):
                m.atomic_install(link,b'changed')
            self.assertEqual(t.read_text(),'original')

if __name__=='__main__':unittest.main()
