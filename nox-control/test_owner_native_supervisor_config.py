import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    'owner_native_inspect', ROOT / 'owner_native_inspect.py')
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)

CONFIG_NAME = 'nox-dispatcher-t855u.conf'
SERVICE = 'nox-dispatcher-t855u'


class SupervisorConfigReadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.path = self.directory / CONFIG_NAME

    def tearDown(self):
        self.temp.cleanup()

    def write(self, text, name=CONFIG_NAME):
        path = self.directory / name
        path.write_text(text)
        return path

    def query(self):
        return MOD.supervisor_config_readonly(
            config_path=self.path, conf_dir=self.directory, now=lambda: 123.0)

    def test_exact_config_reports_sha_and_effective_fields(self):
        self.write(
            '[program:nox-dispatcher-t855u]\n'
            'command=/usr/bin/python3 /root/nox/scripts/nox_dispatcher_t855u.py\n'
            'stopasgroup=false\n'
            'killasgroup=false\n'
            'autorestart=false\n')
        row = self.query()
        self.assertEqual(row['state'], 'VERIFIED')
        self.assertEqual(row['path'], str(self.path))
        self.assertEqual(row['service'], SERVICE)
        self.assertEqual(row['command'],
                         '/usr/bin/python3 /root/nox/scripts/nox_dispatcher_t855u.py')
        self.assertTrue(row['command_matches_expected'])
        self.assertEqual(row['stopsignal'], 'TERM')
        self.assertFalse(row['stopasgroup'])
        self.assertFalse(row['killasgroup'])
        self.assertEqual(row['autorestart'], 'false')
        self.assertEqual(len(row['config_sha256']), 64)
        self.assertEqual(row['duplicates_found'], 0)

    def test_unexpected_command_is_redacted_but_pinned(self):
        self.write(
            '[program:nox-dispatcher-t855u]\n'
            'command=/bin/sh -c "echo bearer-secret"\n')
        row = self.query()
        self.assertEqual(row['command'], '[REDACTED_UNRECOGNIZED_COMMAND]')
        self.assertFalse(row['command_matches_expected'])
        self.assertEqual(len(row['command_sha256']), 64)
        self.assertEqual(row['stopsignal'], 'TERM')
        self.assertEqual(row['autorestart'], 'unexpected')

    def test_duplicate_service_section_in_another_file_holds(self):
        self.write(
            '[program:nox-dispatcher-t855u]\n'
            'command=/usr/bin/python3 /root/nox/scripts/nox_dispatcher_t855u.py\n')
        self.write(
            '[program:nox-dispatcher-t855u]\n'
            'command=/bin/true\n', name='duplicate.conf')
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_OR_WRONG_PATH'):
            self.query()

    def test_missing_command_holds(self):
        self.write('[program:nox-dispatcher-t855u]\nautorestart=false\n')
        with self.assertRaisesRegex(ValueError, 'COMMAND_MISSING_OR_OVERSIZED'):
            self.query()

    def test_unknown_command_content_never_leaks(self):
        secret = 'TOKEN_do_not_print'
        self.write(
            '[program:nox-dispatcher-t855u]\n'
            'command=/bin/sh -c "' + secret + '"\n')
        row = self.query()
        self.assertNotIn(secret, str(row))
        self.assertEqual(row['command'], '[REDACTED_UNRECOGNIZED_COMMAND]')

    def test_wrong_path_name_holds(self):
        wrong = self.directory / 'other.conf'
        wrong.write_text(
            '[program:nox-dispatcher-t855u]\n'
            'command=/usr/bin/python3 /root/nox/scripts/nox_dispatcher_t855u.py\n')
        with self.assertRaisesRegex(ValueError, 'CONFIG_PATH'):
            MOD.supervisor_config_readonly(config_path=wrong, conf_dir=self.directory)

    def test_action_is_wired_as_read_only_owner_route(self):
        operator = (ROOT / 'owner_native_operator.py').read_text()
        self.assertIn("'supervisor_config': 'nox-control/owner_native_inspect.py'", operator)
        self.assertIn("NOX_READONLY_ACTION=supervisor-config", operator)
        source = (ROOT / 'owner_native_inspect.py').read_text()
        self.assertIn('NOX_MAINT_SUPERVISOR_CONFIG_COMPLETE=true', source)


if __name__ == '__main__':
    unittest.main()
