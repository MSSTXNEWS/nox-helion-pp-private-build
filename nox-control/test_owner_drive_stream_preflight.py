import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('drive_preflight', Path(__file__).with_name('owner_drive_stream_preflight.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class DrivePreflightTests(unittest.TestCase):
    def probe(self, names='nox_drive:\nnox_pc:\n', identifier=None, free=400_000_000_000, stream_size=True, single_stat=True):
        calls = []
        def command(argv, **kwargs):
            calls.append(argv)
            verb = argv[1]
            if verb == 'version':
                raw = b'rclone v1.53.3-DEV\n'
            elif verb == 'listremotes':
                raw = names.encode()
            elif '--help' in argv or verb == 'help':
                raw = b'--json --drive-root-folder-id --drive-chunk-size' + (b' --stat' if single_stat else b'') + (b' --size' if stream_size else b'')
            elif verb == 'lsjson':
                raw = json.dumps({'ID': identifier or m.SENTINEL_ID, 'Name': m.SENTINEL,
                                  'Path': m.SENTINEL, 'Size': 3000, 'IsDir': False}).encode()
            elif verb == 'about':
                raw = json.dumps({'free': free, 'total': 500_000_000_000, 'used': 100_000_000_000}).encode()
            else:
                raise AssertionError('Unexpected command: ' + repr(argv))
            return {'returncode': 0, 'state': 'OK'}, raw
        profile = {'path': '/root/nox/state/cold_drive.conf', 'state': 'VERIFIED_PRIVATE_PROFILE_METADATA', 'contents_inspected': False}
        with patch.object(m.shutil, 'which', return_value='/usr/bin/rclone'), patch.object(m, 'documented_profile', return_value=profile), \
             patch.object(m, 'command', side_effect=command):
            result = m.drive_probe()
        return result, calls

    def test_read_only_ready_uses_one_exact_sentinel_and_fixed_folder(self):
        result, calls = self.probe()
        self.assertEqual(result['state'], 'READY_READ_ONLY_DRIVE_STREAM_PREFLIGHT')
        cloud = [x for x in calls if x[1] in ('about', 'lsjson') and '--help' not in x]
        self.assertEqual(len(cloud), 2)
        for argv in cloud:
            self.assertEqual(argv[argv.index('--config') + 1], '/root/nox/state/cold_drive.conf')
            self.assertEqual(argv[argv.index('--drive-root-folder-id') + 1], m.FOLDER)
            self.assertTrue(argv[2].startswith('nox_drive:'))
        self.assertEqual(cloud[0][2], m.REMOTE + m.SENTINEL)
        self.assertIn('--stat', cloud[0])
        self.assertEqual(len(result['folder_listing']['objects']), 1)
        self.assertEqual(result['write_permission'], 'NOT_EXERCISED_READ_ONLY')
        self.assertTrue(all(x[1] not in ('copy', 'copyto', 'move', 'delete', 'mkdir', 'config') for x in calls))
        self.assertTrue(all('--help' in x for x in calls if x[1] == 'rcat'))
        self.assertIn('--config', next(x for x in calls if x[1] == 'listremotes'))

    def test_legacy_lsjson_targets_only_the_same_file_without_stat(self):
        result, calls = self.probe(single_stat=False)
        self.assertEqual(result['state'], 'READY_READ_ONLY_DRIVE_STREAM_PREFLIGHT')
        listing = next(x for x in calls if x[1] == 'lsjson' and '--help' not in x)
        self.assertEqual(listing[2], m.REMOTE + m.SENTINEL)
        self.assertNotIn('--stat', listing)
        self.assertEqual(result['folder_listing']['objects'][0]['ID'], m.SENTINEL_ID)

    def test_documented_profile_uses_metadata_only_and_rejects_bad_mode_and_symlinks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'state').mkdir()
            path = root / 'state/cold_drive.conf'
            path.write_text('NEVER_READ_CONFIG_CONTENTS')
            path.chmod(0o600)
            with patch.object(m, 'ROOT', root), patch.object(m, 'read_regular', side_effect=AssertionError('profile content read')), \
                 patch('builtins.open', side_effect=AssertionError('profile content opened')):
                self.assertEqual(m.documented_profile()['state'], 'VERIFIED_PRIVATE_PROFILE_METADATA')
                path.chmod(0o644)
                self.assertEqual(m.documented_profile()['state'], 'HOLD_DOCUMENTED_PROFILE_OWNER_OR_MODE')
                path.unlink()
                path.symlink_to(root / 'elsewhere')
                self.assertEqual(m.documented_profile()['state'], 'HOLD_DOCUMENTED_PROFILE_SYMLINK')

    def test_missing_known_alias_never_probes_other_storage(self):
        result, calls = self.probe(names='unrelated:\nnox_pc:\n')
        self.assertEqual(result['state'], 'HOLD_KNOWN_DRIVE_REMOTE_MISSING')
        self.assertFalse(any(x[1] in ('about', 'lsjson') and '--help' not in x for x in calls))

    def test_wrong_id_and_insufficient_quota_do_not_pass(self):
        self.assertEqual(self.probe(identifier='other-file')[0]['state'], 'HOLD_EXPECTED_FOLDER_SENTINEL_NOT_VERIFIED')
        self.assertEqual(self.probe(free=100)[0]['state'], 'HOLD_DRIVE_QUOTA_BELOW_ESTIMATE')

    def test_stream_size_help_is_required_without_writing(self):
        self.assertEqual(self.probe(stream_size=False)[0]['state'], 'HOLD_RCLONE_STREAM_SIZE_CAPABILITY')

    def test_provider_error_is_classified_without_exporting_secret_text(self):
        secret = b'failed to get token: invalid_grant https://example.invalid/?token=DO_NOT_PRINT'
        state = m.error_class(secret, 1)
        self.assertEqual(state, 'HOLD_RCLONE_AUTH')
        self.assertNotIn('DO_NOT_PRINT', state)


if __name__ == '__main__':
    unittest.main()
