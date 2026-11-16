import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('storage_preflight', Path(__file__).with_name('owner_storage_integration_preflight.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class StoragePreflightTests(unittest.TestCase):
    def test_profile_scope_is_only_three_documented_paths(self):
        self.assertEqual(m.PROFILES, ('/root/nox/state/cold_drive.conf',
                                    '/root/.config/rclone/rclone.conf', '/root/nox/rclone.conf'))

    def test_mount_output_cannot_include_network_credentials_or_options(self):
        raw = '1 0 8:1 / /mnt/other\\040disk rw,password=EXAMPLE - cifs //user:EXAMPLE@server/share username=user,password=EXAMPLE\n'
        rows = m.mount_rows(raw)
        self.assertEqual(rows, [{'mountpoint': '/mnt/other disk', 'device': '8:1', 'fstype': 'cifs', 'read_only': False}])
        self.assertNotIn('EXAMPLE', json.dumps(rows))

    def test_only_metadata_is_read_from_documented_profile(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'profile.conf'
            p.write_text('EXAMPLE_CREDENTIAL_MUST_NOT_BE_READ')
            p.chmod(0o600)
            with patch.object(Path, 'read_text', side_effect=AssertionError('profile content read')):
                row = m.profile_metadata(p)
            self.assertEqual(row['state'], 'PRIVATE_PROFILE_METADATA_VERIFIED')
            self.assertNotIn('EXAMPLE', json.dumps(row))
            p.chmod(0o644)
            self.assertEqual(m.profile_metadata(p)['state'], 'HOLD_PROFILE_OWNER_MODE')
            link = p.with_name('link.conf'); link.symlink_to(p)
            self.assertEqual(m.profile_metadata(link)['state'], 'HOLD_PROFILE_SYMLINK')

    def test_no_known_remote_never_queries_other_remote(self):
        with patch.object(m, 'run', return_value=({'state': 'OK'}, b'irrelevant_storage:\n')) as run:
            row = m.probe_drive('/usr/bin/rclone', [], 'default')
        self.assertEqual(row['state'], 'HOLD_KNOWN_DRIVE_REMOTE_MISSING')
        self.assertEqual(run.call_count, 1)

    def test_exact_folder_and_sentinel_required(self):
        calls = []
        def run(args, **kwargs):
            calls.append(args)
            if args[1] == 'listremotes': return {'state': 'OK'}, b'nox_drive:\n'
            if args[1] == 'about': return {'state': 'OK'}, b'{"free":999}'
            return {'state': 'OK'}, json.dumps([{'Name': m.SENTINEL, 'ID': 'wrong', 'IsDir': False}]).encode()
        with patch.object(m, 'run', side_effect=run):
            row = m.probe_drive('/usr/bin/rclone', ['--config', m.PROFILES[0]], 'documented')
        self.assertEqual(row['state'], 'HOLD_DRIVE_ACCESS_NOT_VERIFIED')
        self.assertEqual([x[1] for x in calls], ['listremotes', 'lsjson', 'about'])
        for args in calls[1:]:
            self.assertEqual(args[args.index('--drive-root-folder-id') + 1], m.FOLDER)
        self.assertEqual(calls[1][2], m.REMOTE + m.SENTINEL)

    def test_exact_sentinel_and_quota_is_read_access_not_write_acceptance(self):
        replies = [({'state': 'OK'}, b'nox_drive:\n'), ({'state': 'OK'}, json.dumps([
            {'Name': m.SENTINEL, 'ID': m.SENTINEL_ID, 'IsDir': False}]).encode()),
            ({'state': 'OK'}, b'{"free":123456789}')]
        with patch.object(m, 'run', side_effect=replies):
            row = m.probe_drive('/usr/bin/rclone', [], 'default')
        self.assertEqual(row['state'], 'EXISTING_GOOGLE_DRIVE_READ_ACCESS_VERIFIED')
        self.assertEqual(row['write_access'], 'NOT_EXERCISED')

    def test_provider_error_body_is_not_emitted(self):
        p = type('Completed', (), {'returncode': 1, 'stdout': b'EXAMPLE_SECRET', 'stderr': b'invalid_grant EXAMPLE_SECRET'})()
        with patch.object(m.subprocess, 'run', return_value=p):
            meta, raw = m.run(['/usr/bin/rclone', 'listremotes'])
        self.assertEqual(meta['state'], 'HOLD_DRIVE_AUTH')
        self.assertEqual(raw, b'')
        self.assertNotIn('EXAMPLE_SECRET', str(meta))


if __name__ == '__main__':
    unittest.main()
