import importlib.util
import json
from pathlib import Path
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location('readset', Path(__file__).parents[1] / 'native_integration_readset.py')
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)

class ReadsetTests(unittest.TestCase):
    def test_source_is_data_and_only_binding_names_escape(self):
        source = '''import owner_component_tasks
PRIVATE_TOKEN = 'fixture_secret_never_export'
UNTRUSTED = __import__('os').system('must_never_execute')
HANDLERS = {'nox.integrations.drive.check.v1': callback}
def bind_dispatcher(namespace, password='second_secret_never_export'):
    namespace['HANDLERS']['drive'] = function
    return namespace.get('_nox_owner_task_admitted')
'''
        with mock.patch('os.system', side_effect=AssertionError('EXECUTED_SOURCE')):
            result = m.python_shape(source)
        text = json.dumps(result)
        for secret in ('fixture_secret_never_export', 'second_secret_never_export', 'must_never_execute'):
            self.assertNotIn(secret, text)
        self.assertEqual(result['mapping_keys']['HANDLERS'], ['nox.integrations.drive.check.v1'])
        self.assertIn('HANDLERS', result['mapping_keys']['namespace'])
        self.assertEqual(result['functions'][0]['parameters'], ['namespace', 'password'])
        config = m.json_shape(b'{"module_pins":{"owner.py":"hidden-value"},"assets":[{"url":"private-url"}]}')
        self.assertNotIn('hidden-value', json.dumps(config))
        self.assertNotIn('private-url', json.dumps(config))

if __name__ == '__main__':
    unittest.main()
