#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location('nox_drive_reconnect', Path(__file__).with_name('nox_drive_reconnect.py'))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

class ReconnectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.state = self.root / 'state'; self.state.mkdir(mode=0o700)
        self.cg = self.root / 'cg'; self.cg.mkdir(mode=0o700)
        (self.cg/'memory.max').write_text(str(6*1024**3))
        (self.cg/'memory.current').write_text(str(1024**3))
        self.config = self.root/'rclone.conf'
        self.calls = []
    def conf(self, folder=m.APPROVED_FOLDER_ID, token='{"refresh_token":"private"}'):
        self.config.write_text('[noxdrive]\ntype = drive\nroot_folder_id = '+folder+'\ntoken = '+token+'\n')
        self.config.chmod(0o600)
    def fake_run(self, args, **kw):
        self.calls.append(args)
        return SimpleNamespace(returncode=0, stderr=b'', stdout=b'private names should never print')
    def probe(self, **kwargs):
        params=dict(config_path=self.config,state_dir=self.state,which=lambda name:'/usr/bin/rclone',
                    run=self.fake_run,now=lambda:100000,stop_flags=(),cgroup_root=str(self.cg))
        params.update(kwargs)
        return m.check_once(**params)
    def test_missing_config_has_no_remote_call(self):
        r=self.probe();self.assertEqual(r['state'],'HOLD_CONFIG_MISSING')
        self.assertFalse(self.calls);self.assertFalse(r['connected'])
    def test_pinned_root_enforced(self):
        self.conf(folder='other-folder')
        r=self.probe();self.assertEqual(r['state'],'HOLD_PROJECT_ROOT_NOT_PINNED')
        self.assertFalse(self.calls)
    def test_success_uses_read_only_rclone_without_leaking_names(self):
        self.conf()
        r=self.probe();self.assertEqual(r['state'],'CONNECTED');self.assertTrue(r['connected'])
        self.assertEqual(self.calls[0][0:4],['rclone','--config',str(self.config),'lsf'])
        self.assertNotIn('private names',str(r))
        self.assertEqual((self.state/'status.json').stat().st_mode & 0o077,0)
    def test_valid_refresh_error_needs_owner_without_secrets(self):
        self.conf()
        def invalid(*a,**kw):return SimpleNamespace(returncode=1,stderr=b'failed token invalid_grant SECRET',stdout=b'')
        r=self.probe(run=invalid)
        self.assertEqual(r['state'],'OWNER_REAUTH_REQUIRED')
        self.assertNotIn('SECRET',str(r))
        self.assertGreater(r['next_retry_unix'],100000)
    def test_retry_wait_and_resume_after_timeout(self):
        self.conf()
        failed=lambda *a,**kw:SimpleNamespace(returncode=1,stderr=b'network error',stdout=b'')
        first=self.probe(run=failed)
        self.assertEqual(first['state'],'RETRYABLE_TRANSPORT_OR_AUTH')
        second=self.probe(now=lambda:100001)
        self.assertEqual(second['state'],'WAIT_BACKOFF')
        third=self.probe(now=lambda:100016)
        self.assertEqual(third['state'],'CONNECTED')
    def test_stop_and_resource_pressure_skip(self):
        self.conf()
        stop=self.root/'STOP';stop.write_text('stop')
        r=self.probe(stop_flags=(str(stop),))
        self.assertEqual(r['state'],'HOLD_OWNER_STOP');self.assertFalse(self.calls)
        stop.unlink()
        (self.cg/'memory.current').write_text(str(6*1024**3-2))
        r=self.probe()
        self.assertEqual(r['state'],'DEFERRED_CGROUP_RAM');self.assertFalse(self.calls)
    def test_symlinked_config_and_public_config_refused(self):
        self.conf();self.config.chmod(0o644)
        r=self.probe();self.assertEqual(r['state'],'HOLD_OWNER_PERMISSIONS')
        self.config.chmod(0o600)
        alt=self.root/'linked';alt.symlink_to(self.config)
        with self.assertRaisesRegex(m.Hold,'HOLD_SYMLINK_PATH'):
            m.authorized_config(alt)
    def test_fixed_backoff_bound(self):
        self.assertEqual(m.next_delay(1),15)
        self.assertEqual(m.next_delay(100),1800)

if __name__=='__main__':unittest.main()
