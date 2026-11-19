"""Offline tests for the one exact read-only repair bundle."""
import base64
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

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

    def test_bundle_uses_only_fixed_status_for_named_services(self):
        control = self.entry.native_control()
        self.assertIsNone(control.STOP_TARGET)
        with self.assertRaisesRegex(RuntimeError, 'SUPERVISOR_STATUS_OUT_OF_SCOPE'):
            control.status('stopProcess')
        with patch.object(control.subprocess, 'run', return_value=SimpleNamespace(
                stdout='nox-fill-idle-t166u RUNNING pid 52, uptime 2 days, 01:03:04\n',
                stderr='', returncode=0)) as run:
            self.assertEqual(control.status('nox-fill-idle-t166u'),
                             {'statename': 'RUNNING', 'pid': 52})
        self.assertEqual(run.call_args.args[0], ['supervisorctl', 'status', 'nox-fill-idle-t166u'])

    def test_nonzero_exit_cannot_attest_a_running_pid(self):
        control = self.entry.native_control()
        with patch.object(control.subprocess, 'run', return_value=SimpleNamespace(
                stdout='nox-ds41-8098 RUNNING pid 52, uptime 01:03:04\n',
                stderr='', returncode=3)), self.assertRaisesRegex(
                    RuntimeError, 'SUPERVISOR_RUNNING_STATUS'):
            control.status('nox-ds41-8098')

    def test_reads_exact_pss_and_private_facts_without_summing_overlap(self):
        name = 'nox-fill-idle-t166u'
        values = b'Pss_Anon: 2048 kB\nPss_File: 10 kB\nPss_Shmem: 2 kB\nPrivate_Clean: 3 kB\nPrivate_Dirty: 1024 kB\n'
        control = SimpleNamespace(
            SUPERVISOR=(114, 12), PROC=Path('/proc'),
            status=lambda group: {'statename': 'RUNNING', 'pid': 222},
            process=lambda pid: (55, 114, 222, b'S'), cgroup=lambda pid: b'0::/',
            need=self.entry.native_control().need, read=lambda path, limit: values,
        )
        result = self.entry.profile(control, name)
        self.assertEqual(result['memory_bytes']['Pss_Anon'], 2048 * 1024)
        self.assertEqual(result['memory_bytes']['Private_Dirty'], 1024 * 1024)


if __name__ == '__main__':
    unittest.main()
