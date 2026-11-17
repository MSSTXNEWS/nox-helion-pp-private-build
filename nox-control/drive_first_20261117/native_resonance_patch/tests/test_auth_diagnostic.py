import importlib.util
import json
from pathlib import Path
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location('authdiag', Path(__file__).parents[1] / 'native_auth_path_diagnostic.py')
m = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(m)

class DiagnosticTests(unittest.TestCase):
    def test_import_conditional_unpack_shapes_without_values_or_execution(self):
        reader = "\nCHAT_PASSWORD_PATH = SECRETS / 'private_file_never_export'\ndef _read_chat_password():\n try:\n  return CHAT_PASSWORD_PATH.read_text(encoding='utf-8').strip()\n except OSError:\n  return ''\n"
        sources = (
            "from private_config import SECRETS\n" + reader,
            "if READY:\n SECRETS = Path('/root/nox/private_dir_never_export')\n" + reader,
            "ROOT, SECRETS = map(Path, ['/root/nox', '/root/nox/private_dir_never_export'])\n" + reader,
            "from private_config import *\n" + reader,
        )
        for source in sources:
            source += "\nUNRELATED = __import__('os').system('must_never_execute')\n"
            with mock.patch('os.system', side_effect=AssertionError('EXECUTED')):
                result = m.describe_source(source)
            text = json.dumps(result)
            for forbidden in ('private_file_never_export', 'private_dir_never_export', 'must_never_execute', '/root/nox'):
                self.assertNotIn(forbidden, text)
            self.assertIn('CHAT_PASSWORD_PATH', result['dependency_identifiers'])
            self.assertIn('SECRETS', result['dependency_identifiers'])
            self.assertEqual(len(result['password_readers']), 1)
        imported = m.describe_source(sources[0])
        self.assertTrue(any(r.get('identifier') == 'SECRETS' and r.get('binding_kind') == 'ImportFrom' and r.get('module') == 'private_config' for r in imported['bindings']))
        conditional = m.describe_source(sources[1])
        self.assertTrue(any(r.get('identifier') == 'SECRETS' and 'If.body' in r['context'] for r in conditional['bindings']))
        unpacked = m.describe_source(sources[2])
        self.assertTrue(any(r.get('identifier') == 'SECRETS' and r['statement_shape']['targets'][0]['node'] == 'Tuple' for r in unpacked['bindings']))
        self.assertEqual(m.describe_source(sources[3])['wildcard_imports'][0]['import_name'], '*')

if __name__ == '__main__': unittest.main()
