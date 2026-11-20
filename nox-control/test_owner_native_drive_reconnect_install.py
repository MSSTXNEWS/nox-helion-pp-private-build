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
                          ('nox_drive_first.py','#!/usr/bin/env python3\npass\n'),
                          ('nox_drive_prefetch.py','#!/usr/bin/env python3\npass\n'),
                          ('nox_drive_native_binding.py','#!/usr/bin/env python3\npass\n'),
                          ('nox-drive-first.skill.md','# NOX Drive-first skill\n'),
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
    def test_drive_first_private_receipt_root_created(self):
        content=src.read_text()
        self.assertIn("DRIVE_FIRST_STATE = Path('/var/lib/nox-drive-first')",content)
        self.assertIn("private_dir(DRIVE_FIRST_STATE,create=True)",content)

    def test_native_workspace_does_not_modify_shared_nox_cache(self):
        content=src.read_text()
        self.assertNotIn("private_dir(ROOT/'cache'", content)
        self.assertNotIn("private_dir(ROOT/'private'", content)
        self.assertIn("private_dir(SCRIPTS/'private/drive-tasks',create=True)", content)
        self.assertIn("private_dir(STATE/'cache/warm-ssd',create=True)", content)


    def test_real_static_hook_syntax_compiles_without_owner_or_filesystem_access(self):
        from nox_drive_native_binding import stage_native_dispatcher_source
        value=stage_native_dispatcher_source(
            expected_bridge_sha="0"*64, hook_syntax_only=True)
        self.assertEqual(value["state"], "HOOK_SYNTAX_VALIDATED_ONLY")
        self.assertFalse(value["native_handler_registered"])

    def test_native_dispatcher_source_is_staged_not_claimed_live(self):
        source=src.read_text()
        import inspect
        from nox_drive_native_binding import stage_native_dispatcher_source
        implementation=inspect.getsource(stage_native_dispatcher_source)
        self.assertIn('stage_native_dispatcher_source(',source)
        self.assertIn('expected_bridge_sha=hashlib.sha256',source)
        self.assertIn("stages['dispatcher_registry_source']=registry['state']",source)
        self.assertIn("'dispatcher_source_staged':True",source)
        self.assertIn("'native_dispatcher_handler_registered':False",source)
        self.assertIn('"restarted": False',implementation)
        self.assertIn('SOURCE_STAGED_NOT_LIVE',implementation)
        self.assertIn('HOLD_DRIVE_NATIVE_NO_VERIFIED_RECEIPT',implementation)
        self.assertIn('owner_context()',implementation)
        self.assertIn('BACKUPS = Path(',implementation)
        self.assertNotIn("supervisorctl','restart",implementation)
        self.assertNotIn("systemctl restart",implementation)

    def test_registry_activation_rejects_unverified_source_before_any_restart(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'dispatcher.py'
            source.write_bytes(b'not an owner-reviewed dispatcher')
            with (mock.patch.object(m,'DISPATCHER_SOURCE',source),
                  mock.patch.object(m.subprocess,'run') as sub):
                with self.assertRaisesRegex(m.Hold,'HOLD_DRIVE_RECONNECT_ACTIVATION_SOURCE_SHA'):
                    m.activate_staged_dispatcher()
                sub.assert_not_called()

    def test_guarded_restart_never_weakens_weight_transfer_admission(self):
        code=src.read_text()
        self.assertIn('raw_free >= 64 * 1024**2',code)
        self.assertIn('entries.get("inactive_file", 0) >= 16 * 1024**3',code)
        self.assertIn('events.get("oom_kill") == 0',code)
        self.assertIn('abs(time.time() - native["observed_at"]) < 80',code)
        self.assertIn('and row.get("current_task") is None',code)
        self.assertIn('first == second',code)
        self.assertIn('DISPATCHER_RELOADED_THREE_WORKERS',code)
        self.assertIn("'live_registration_receipt': False",code)
        self.assertIn("'native_dispatcher_handler_registered':False",code)
        self.assertNotIn("supervisorctl restart nox-ds41",code)

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
