"""Offline tests for the one exact read-only repair bundle."""
import base64
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace
import unittest

import owner_native_operator as operator


def entry_module():
    path = operator.FILES['repair']
    assets = operator.repair_bundle_paths('repair', path, ())
    if assets != ('nox-control/owner_supervisor_background_probe.py',):
        raise AssertionError(assets)
    encoded = {Path(asset).name: base64.b64encode(Path(asset).read_bytes()).decode()
               for asset in assets}
    source = Path(path).read_text().replace('__NOX_BUNDLE_JSON__', json.dumps(encoded))
    module = ModuleType('nox_memory_census_entry_test')
    exec(compile(source, path, 'exec'), module.__dict__)
    return module


class BackgroundCensusTests(unittest.TestCase):
    def setUp(self):
        self.entry = entry_module()

    def test_bundle_cannot_signal_or_mutate_a_service(self):
        control = self.entry.native_control()
        self.assertIsNone(control.STOP_TARGET)
        for method, params in [('stopProcess', ('nox-fill-idle-t166u',)),
                               ('startProcess', ('nox-fill-idle-t166u',)),
                               ('getProcessInfo', ('outside-source-scope',))]:
            with self.subTest(method=method), self.assertRaisesRegex(
                    RuntimeError, 'RPC_METHOD_OUT_OF_SCOPE'):
                control.rpc(None, method, params)

    def test_resolves_inline_comments_and_keeps_private_socket_mode(self):
        control = self.entry.native_control()
        config = b'''[unix_http_server]
file=/tmp/supervisor.sock ; socket endpoint
chmod=0600 ; access limited to root
chown=root:root ; owner
[supervisorctl]
serverurl=unix:///tmp/supervisor.sock ; fixed transport
[rpcinterface:supervisor]
supervisor.rpcinterface_factory=supervisor.rpcinterface:make_main_rpcinterface
[include]
files=/etc/supervisor/conf.d/*.conf
'''
        expected = Path('/tmp/supervisor.sock')
        self.assertEqual(control.endpoint_config(config, Path('/etc/supervisor')),
                         (expected, expected, 0o600))
        with self.assertRaisesRegex(RuntimeError, 'SOCKET_MODE_CONFIG'):
            control.endpoint_config(config.replace(b'0600', b'0660'), Path('/etc/supervisor'))

    def test_reads_exact_pss_and_private_facts_without_summing_overlap(self):
        name = 'nox-fill-idle-t166u'
        values = b'Pss_Anon: 2048 kB\nPss_File: 10 kB\nPss_Shmem: 2 kB\nPrivate_Clean: 3 kB\nPrivate_Dirty: 1024 kB\n'
        control = SimpleNamespace(
            SUPERVISOR=(114, 12), PROC=Path('/proc'),
            rpc=lambda endpoint, method, args: {'group': name, 'name': name,
                                                 'statename': 'RUNNING', 'pid': 222},
            process=lambda pid: (55, 114, 222, b'S'), cgroup=lambda pid: b'0::/',
            need=self.entry.native_control().need, read=lambda path, limit: values,
        )
        result = self.entry.profile(control, None, name)
        self.assertEqual(result['memory_bytes']['Pss_Anon'], 2048 * 1024)
        self.assertEqual(result['memory_bytes']['Private_Dirty'], 1024 * 1024)


if __name__ == '__main__':
    unittest.main()
