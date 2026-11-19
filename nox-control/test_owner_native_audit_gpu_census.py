"""Read-only fixtures for the GPU consumer to /proc identity join."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('owner_native_audit', ROOT / 'owner_native_audit.py')
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)

GPU_UUID = 'GPU-58f4970e-117b-ea29-9c68-b65c5ca88fd0'


def add_proc(root, pid, *, ppid=1, start=100, nspid=None,
             cgroup='/service/nox-worker', cgroup_ns=None,
             argv=b'/opt/odd-daemon\0'):
    proc = Path(root) / str(pid)
    proc.mkdir(parents=True, exist_ok=True)
    fields = ['S', str(ppid), str(pid)] + ['0'] * 17
    fields[19] = str(start)
    (proc / 'stat').write_text(f'{pid} (odd-daemon) ' + ' '.join(fields) + '\n')
    nspid = nspid or [pid]
    (proc / 'status').write_text(
        f'Name:\todd-daemon\nState:\tS (sleeping)\nTgid:\t{pid}\nPid:\t{pid}\n'
        f'PPid:\t{ppid}\nUid:\t1000\t1000\t1000\t1000\n'
        f'NSpid:\t{" ".join(map(str, nspid))}\n')
    (proc / 'cgroup').write_text(f'0::{cgroup}\n')
    (proc / 'comm').write_text('odd-daemon\n')
    (proc / 'cmdline').write_bytes(argv)
    (proc / 'ns').mkdir(exist_ok=True)
    (proc / 'ns' / 'pid').symlink_to(f'pid:[{4026532781 + pid}]')
    (proc / 'ns' / 'mnt').symlink_to(f'mnt:[{4026532781 + pid}]')
    cgroup_ns = 4026532781 + pid if cgroup_ns is None else cgroup_ns
    (proc / 'ns' / 'cgroup').symlink_to(f'cgroup:[{cgroup_ns}]')
    (proc / 'exe').symlink_to('/usr/bin/odd-daemon')
    return proc


def replace_start(root, pid, start, ppid=1):
    proc = Path(root) / str(pid)
    fields = ['S', str(ppid), str(pid)] + ['0'] * 17
    fields[19] = str(start)
    (proc / 'stat').write_text(f'{pid} (odd-daemon) ' + ' '.join(fields) + '\n')


def add_proc_self(root):
    path = Path(root) / 'self' / 'ns'
    path.mkdir(parents=True, exist_ok=True)
    (path / 'pid').symlink_to('pid:[4026531993]')


def app_text(pid):
    return f'{pid}, {GPU_UUID}, 123\n'


class GpuConsumerCensusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.proc = Path(self.temp.name) / 'proc'
        self.proc.mkdir()
        add_proc_self(self.proc)

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def clock():
        values = iter(range(100, 200))
        return lambda: next(values)

    def test_identity_includes_nspid_namespaces_startticks_and_cgroup(self):
        add_proc(self.proc, 101, ppid=1, start=987, nspid=[9001, 101],
                 cgroup='/docker/container/service')
        row = MOD.read_proc_identity(self.proc, 101)
        self.assertEqual(row['start_ticks'], 987)
        self.assertEqual(row['nspid'], [9001, 101])
        self.assertEqual(row['pid_namespace'], 'pid:[4026532882]')
        self.assertEqual(row['cgroups'][0]['path'], '/docker/container/service')
        self.assertEqual(row['identity_state'], 'VERIFIED')

    def test_direct_pid_matches_supervisor_parent_chain(self):
        add_proc(self.proc, 200, start=200, cgroup='/service/nox-worker')
        add_proc(self.proc, 101, ppid=200, start=101, cgroup='/service/nox-worker')
        def runner(argv, seconds=12):
            if argv[0] == 'nvidia-smi':
                return 0, app_text(101)
            if argv == ['supervisorctl', 'status']:
                return 0, 'nox-worker RUNNING pid 200, uptime 0:00:01\n'
            return 1, ''
        census = MOD.gpu_process_census(self.proc, run_fn=runner, clock=self.clock())
        link = census['gpu_process_links'][0]
        self.assertEqual(link['classification'], 'MATCHED')
        self.assertEqual(link['visibility'], 'DIRECT_PROC')
        self.assertEqual(link['proc_identity']['pid'], 101)
        self.assertEqual(link['service_match']['service'], 'nox-worker')
        self.assertEqual(link['service_match']['relation'], 'PARENT_CHAIN')
        self.assertEqual(census['visible_proc_pids'], [101])

    def test_nspid_alias_maps_gpu_pid_to_local_service_process(self):
        add_proc(self.proc, 200, start=200, cgroup='/service/nox-worker')
        add_proc(self.proc, 101, ppid=200, start=101, nspid=[9001, 101],
                 cgroup='/service/nox-worker')
        def runner(argv, seconds=12):
            if argv[0] == 'nvidia-smi':
                return 0, app_text(9001)
            if argv == ['supervisorctl', 'status']:
                return 0, 'nox-worker RUNNING pid 200, uptime 0:00:01\n'
            return 1, ''
        census = MOD.gpu_process_census(self.proc, run_fn=runner, clock=self.clock())
        link = census['gpu_process_links'][0]
        self.assertEqual(link['classification'], 'NAMESPACE_ALIAS')
        self.assertEqual(link['gpu_pid'], 9001)
        self.assertEqual(link['proc_identity']['pid'], 101)
        self.assertEqual(link['service_match']['service'], 'nox-worker')

    def test_before_only_gpu_pid_is_gone_during_sample(self):
        add_proc(self.proc, 999, ppid=1, start=999)
        calls = 0
        def runner(argv, seconds=12):
            nonlocal calls
            if argv[0] == 'nvidia-smi':
                calls += 1
                return 0, app_text(901) if calls == 1 else ''
            if argv == ['supervisorctl', 'status']:
                return 0, 'idle RUNNING pid 999, uptime 0:00:01\n'
            return 1, ''
        census = MOD.gpu_process_census(self.proc, run_fn=runner, clock=self.clock())
        self.assertEqual(census['gpu_process_links'][0]['classification'],
                         'GONE_DURING_SAMPLE')
        self.assertEqual(census['gpu_process_links'][0]['inventory_presence'], 'BEFORE_ONLY')

    def test_persistent_gpu_pid_without_proc_visibility_is_not_visible(self):
        def runner(argv, seconds=12):
            if argv[0] == 'nvidia-smi':
                return 0, app_text(902)
            return 0, ''
        census = MOD.gpu_process_census(self.proc, run_fn=runner, clock=self.clock())
        self.assertEqual(census['gpu_process_links'][0]['classification'], 'NOT_VISIBLE')
        self.assertTrue(census['gpu_process_links'][0]['before_alias_scan_complete'])

    def test_visible_gpu_pid_without_service_relation_is_reported(self):
        add_proc(self.proc, 903, ppid=1, start=903, cgroup='/unmapped/container')
        add_proc(self.proc, 999, ppid=1, start=999)
        def runner(argv, seconds=12):
            if argv[0] == 'nvidia-smi':
                return 0, app_text(903)
            if argv == ['supervisorctl', 'status']:
                return 0, 'idle RUNNING pid 999, uptime 0:00:01\n'
            return 0, ''
        census = MOD.gpu_process_census(self.proc, run_fn=runner, clock=self.clock())
        link = census['gpu_process_links'][0]
        self.assertEqual(link['classification'], 'NO_SERVICE_ANCESTOR')
        self.assertEqual(link['proc_identity']['start_ticks'], 903)
        self.assertIsNone(link['service_match'])

    def test_shared_cgroup_does_not_establish_service_ownership(self):
        add_proc(self.proc, 2000, start=2000, cgroup='/shared/service')
        add_proc(self.proc, 906, start=906, cgroup='/shared/service')
        def runner(argv, seconds=12):
            if argv[0] == 'nvidia-smi':
                return 0, app_text(906)
            if argv == ['supervisorctl', 'status']:
                return 0, 'nox-worker RUNNING pid 2000, uptime 0:00:01\n'
            return 1, ''
        census = MOD.gpu_process_census(self.proc, run_fn=runner, clock=self.clock())
        self.assertEqual(census['gpu_process_links'][0]['classification'],
                         'NO_SERVICE_ANCESTOR')

    def test_same_namespace_shared_cgroup_still_does_not_establish_ownership(self):
        add_proc(self.proc, 2001, start=2001, cgroup='/shared/service', cgroup_ns=42)
        add_proc(self.proc, 907, start=907, cgroup='/shared/service', cgroup_ns=42)
        def runner(argv, seconds=12):
            if argv[0] == 'nvidia-smi':
                return 0, app_text(907)
            if argv == ['supervisorctl', 'status']:
                return 0, 'nox-worker RUNNING pid 2001, uptime 0:00:01\n'
            return 1, ''
        census = MOD.gpu_process_census(self.proc, run_fn=runner, clock=self.clock())
        link = census['gpu_process_links'][0]
        self.assertEqual(link['classification'], 'NO_SERVICE_ANCESTOR')
        self.assertIsNone(link['service_match'])

    def test_host_pid_collision_with_namespace_gpu_pid_is_ambiguous(self):
        add_proc(self.proc, 200, ppid=500, start=200, nspid=[200])
        add_proc(self.proc, 300, ppid=500, start=300, nspid=[9000, 200])
        add_proc(self.proc, 500, start=500, cgroup='/service/nox-worker')
        def runner(argv, seconds=12):
            if argv[0] == 'nvidia-smi':
                return 0, app_text(200)
            if argv == ['supervisorctl', 'status']:
                return 0, 'nox-worker RUNNING pid 500, uptime 0:00:01\n'
            return 1, ''
        census = MOD.gpu_process_census(self.proc, run_fn=runner, clock=self.clock())
        link = census['gpu_process_links'][0]
        self.assertEqual(link['classification'], 'NOT_VISIBLE')
        self.assertEqual(link['visibility'], 'AMBIGUOUS_NSPID_ALIAS')
        self.assertIsNone(link['proc_identity'])
        self.assertEqual(link['evidence_state'], 'COMPLETE')

    def test_failed_gpu_inventory_cannot_match_service(self):
        add_proc(self.proc, 910, ppid=500, start=910)
        add_proc(self.proc, 500, start=500)
        def runner(argv, seconds=12):
            if argv[0] == 'nvidia-smi':
                return 1, app_text(910)
            if argv == ['supervisorctl', 'status']:
                return 0, 'nox-worker RUNNING pid 500, uptime 0:00:01\n'
            return 1, ''
        census = MOD.gpu_process_census(self.proc, run_fn=runner, clock=self.clock())
        link = census['gpu_process_links'][0]
        self.assertEqual(link['classification'], 'NOT_VISIBLE')
        self.assertEqual(link['evidence_state'], 'INCOMPLETE')
        self.assertEqual(census['gpu_consumer_identities'], [])

    def test_truncated_gpu_inventory_cannot_match_service(self):
        add_proc(self.proc, 914, ppid=500, start=914)
        add_proc(self.proc, 500, start=500)
        def runner(argv, seconds=12):
            if argv[0] == 'nvidia-smi':
                return 0, app_text(914) + (' ' * 200000)
            if argv == ['supervisorctl', 'status']:
                return 0, 'nox-worker RUNNING pid 500, uptime 0:00:01\n'
            return 1, ''
        census = MOD.gpu_process_census(self.proc, run_fn=runner, clock=self.clock())
        link = census['gpu_process_links'][0]
        self.assertEqual(link['classification'], 'NOT_VISIBLE')
        self.assertEqual(link['evidence_state'], 'INCOMPLETE')
        self.assertEqual(census['gpu_consumer_identities'], [])

    def test_incomplete_supervisor_output_cannot_match_service(self):
        add_proc(self.proc, 911, ppid=500, start=911)
        add_proc(self.proc, 500, start=500)
        def runner(argv, seconds=12):
            if argv[0] == 'nvidia-smi':
                return 0, app_text(911)
            if argv == ['supervisorctl', 'status']:
                return 0, 'nox-worker RUNNING pid 500, uptime 0:00:01\npartial error\n'
            return 1, ''
        census = MOD.gpu_process_census(self.proc, run_fn=runner, clock=self.clock())
        link = census['gpu_process_links'][0]
        self.assertEqual(link['classification'], 'NOT_VISIBLE')
        self.assertEqual(link['evidence_state'], 'INCOMPLETE')
        self.assertEqual(census['gpu_consumer_identities'], [])

    def test_nonzero_supervisor_status_cannot_match_service(self):
        add_proc(self.proc, 916, ppid=500, start=916)
        add_proc(self.proc, 500, start=500)
        def runner(argv, seconds=12):
            if argv[0] == 'nvidia-smi':
                return 0, app_text(916)
            if argv == ['supervisorctl', 'status']:
                return 3, 'nox-worker RUNNING pid 500, uptime 0:00:01\n'
            return 1, ''
        census = MOD.gpu_process_census(self.proc, run_fn=runner, clock=self.clock())
        link = census['gpu_process_links'][0]
        self.assertEqual(link['classification'], 'NOT_VISIBLE')
        self.assertEqual(link['evidence_state'], 'INCOMPLETE')

    def test_running_supervisor_pid_without_proc_identity_blocks_census(self):
        add_proc(self.proc, 921, ppid=1, start=921)
        def runner(argv, seconds=12):
            if argv[0] == 'nvidia-smi':
                return 0, app_text(921)
            if argv == ['supervisorctl', 'status']:
                return 0, 'nox-worker RUNNING pid 922, uptime 0:00:01\n'
            return 1, ''
        census = MOD.gpu_process_census(self.proc, run_fn=runner, clock=self.clock())
        self.assertFalse(census['supervisor_services']['identity_complete'])
        self.assertFalse(census['supervisor_services']['complete'])
        self.assertEqual(census['supervisor_services']['services'][0]['identity_state'],
                         'UNAVAILABLE_OR_CHANGED')
        self.assertEqual(census['gpu_process_links'][0]['evidence_state'], 'INCOMPLETE')
        self.assertEqual(census['gpu_consumer_identities'], [])
        self.assertEqual(census['gpu_consumer_identities'], [])

    def test_nonzero_gpu_inventory_rc_cannot_export_consumer_identity(self):
        add_proc(self.proc, 917, ppid=1, start=917)
        calls = 0
        def runner(argv, seconds=12):
            nonlocal calls
            if argv[0] == 'nvidia-smi':
                calls += 1
                return (2, app_text(917)) if calls == 1 else (0, app_text(917))
            if argv == ['supervisorctl', 'status']:
                return 0, 'idle STOPPED\n'
            return 1, ''
        census = MOD.gpu_process_census(self.proc, run_fn=runner, clock=self.clock())
        self.assertEqual(census['gpu_apps_before']['return_code'], 2)
        self.assertEqual(census['gpu_process_links'][0]['evidence_state'], 'INCOMPLETE')
        self.assertEqual(census['gpu_consumer_identities'], [])

    def test_duplicate_gpu_app_inventory_cannot_export_consumer_identity(self):
        add_proc(self.proc, 920, ppid=1, start=920)
        duplicate = app_text(920) * 2
        def runner(argv, seconds=12):
            if argv[0] == 'nvidia-smi':
                return 0, duplicate
            if argv == ['supervisorctl', 'status']:
                return 0, 'idle STOPPED\n'
            return 1, ''
        census = MOD.gpu_process_census(self.proc, run_fn=runner, clock=self.clock())
        self.assertEqual(census['gpu_apps_before']['rejected_rows'], 1)
        self.assertFalse(census['gpu_apps_before']['complete'])
        self.assertEqual(census['gpu_consumer_identities'], [])

    def test_truncated_supervisor_output_cannot_match_service(self):
        add_proc(self.proc, 915, ppid=500, start=915)
        add_proc(self.proc, 500, start=500)
        def runner(argv, seconds=12):
            if argv[0] == 'nvidia-smi':
                return 0, app_text(915)
            if argv == ['supervisorctl', 'status']:
                return 0, 'nox-worker RUNNING pid 500, uptime 0:00:01\n' + ('x' * 200000)
            return 1, ''
        census = MOD.gpu_process_census(self.proc, run_fn=runner, clock=self.clock())
        link = census['gpu_process_links'][0]
        self.assertEqual(link['classification'], 'NOT_VISIBLE')
        self.assertEqual(link['evidence_state'], 'INCOMPLETE')

    def test_capped_nspid_scan_cannot_match_service(self):
        add_proc(self.proc, 912, ppid=500, start=912)
        add_proc(self.proc, 500, start=500)
        original_limit = MOD.MAX_PROC_ENTRIES
        MOD.MAX_PROC_ENTRIES = 1
        try:
            def runner(argv, seconds=12):
                if argv[0] == 'nvidia-smi':
                    return 0, app_text(912)
                if argv == ['supervisorctl', 'status']:
                    return 0, 'nox-worker RUNNING pid 500, uptime 0:00:01\n'
                return 1, ''
            census = MOD.gpu_process_census(self.proc, run_fn=runner, clock=self.clock())
        finally:
            MOD.MAX_PROC_ENTRIES = original_limit
        link = census['gpu_process_links'][0]
        self.assertEqual(link['classification'], 'NOT_VISIBLE')
        self.assertEqual(link['evidence_state'], 'INCOMPLETE')

    def test_pid_reuse_during_nspid_readback_invalidates_candidate(self):
        add_proc(self.proc, 913, start=913, nspid=[913])
        original_stat = MOD._proc_stat
        calls = 0
        def changing_stat(proc_dir, expected_pid):
            nonlocal calls
            if expected_pid == 913:
                calls += 1
                if calls == 2:
                    replace_start(self.proc, 913, start=1913)
            return original_stat(proc_dir, expected_pid)
        MOD._proc_stat = changing_stat
        try:
            aliases, complete = MOD._nspid_aliases(self.proc, {913})
        finally:
            MOD._proc_stat = original_stat
        self.assertFalse(complete)
        self.assertEqual(aliases[913], [])

    def test_pid_reuse_between_gpu_samples_is_gone_not_matched(self):
        add_proc(self.proc, 904, ppid=1, start=904)
        add_proc(self.proc, 999, ppid=1, start=999)
        calls = 0
        def runner(argv, seconds=12):
            nonlocal calls
            if argv[0] == 'nvidia-smi':
                calls += 1
                if calls == 2:
                    replace_start(self.proc, 904, start=1904)
                return 0, app_text(904)
            if argv == ['supervisorctl', 'status']:
                return 0, 'idle RUNNING pid 999, uptime 0:00:01\n'
            return 0, ''
        census = MOD.gpu_process_census(self.proc, run_fn=runner, clock=self.clock())
        link = census['gpu_process_links'][0]
        self.assertEqual(link['identity_stability'], 'CHANGED')
        self.assertEqual(link['classification'], 'GONE_DURING_SAMPLE')

    def test_gpu_consumer_bypasses_keyword_filter_with_fresh_exact_identity(self):
        add_proc(self.proc, 905, ppid=1, start=905, argv=b'/opt/odd-daemon\0--opaque\0')
        add_proc(self.proc, 999, ppid=1, start=999)
        def runner(argv, seconds=12):
            if argv[0] == 'nvidia-smi':
                return 0, app_text(905)
            if argv == ['supervisorctl', 'status']:
                return 0, 'idle RUNNING pid 999, uptime 0:00:01\n'
            return 1, ''
        census = MOD.gpu_process_census(self.proc, run_fn=runner, clock=self.clock())
        candidates = census['gpu_consumer_identities']
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]['pid'], 905)
        rows = MOD.process_rows(self.proc, include_gpu_identities=candidates)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['pid'], 905)
        self.assertTrue(rows[0]['gpu_consumer'])
        self.assertEqual(rows[0]['start_ticks'], 905)
        self.assertEqual(rows[0]['gpu_identity']['pid_namespace'], 'pid:[4026533686]')

    def test_pid_reuse_between_census_and_export_is_not_gpu_attributed(self):
        add_proc(self.proc, 918, ppid=1, start=918, argv=b'/opt/odd-daemon\0--opaque\0')
        add_proc(self.proc, 999, ppid=1, start=999)
        def runner(argv, seconds=12):
            if argv[0] == 'nvidia-smi':
                return 0, app_text(918)
            if argv == ['supervisorctl', 'status']:
                return 0, 'idle RUNNING pid 999, uptime 0:00:01\n'
            return 1, ''
        census = MOD.gpu_process_census(self.proc, run_fn=runner, clock=self.clock())
        candidates = census['gpu_consumer_identities']
        self.assertEqual(len(candidates), 1)
        replace_start(self.proc, 918, start=1918)
        rows = MOD.process_rows(self.proc, include_gpu_identities=candidates)
        self.assertEqual(rows, [])

    def test_pid_namespace_change_between_census_and_export_is_not_gpu_attributed(self):
        proc = add_proc(self.proc, 919, ppid=1, start=919, argv=b'/opt/odd-daemon\0--opaque\0')
        add_proc(self.proc, 999, ppid=1, start=999)
        def runner(argv, seconds=12):
            if argv[0] == 'nvidia-smi':
                return 0, app_text(919)
            if argv == ['supervisorctl', 'status']:
                return 0, 'idle RUNNING pid 999, uptime 0:00:01\n'
            return 1, ''
        census = MOD.gpu_process_census(self.proc, run_fn=runner, clock=self.clock())
        candidates = census['gpu_consumer_identities']
        self.assertEqual(len(candidates), 1)
        (proc / 'ns' / 'pid').unlink()
        (proc / 'ns' / 'pid').symlink_to('pid:[4026533999]')
        rows = MOD.process_rows(self.proc, include_gpu_identities=candidates)
        self.assertEqual(rows, [])

    def test_supervisor_status_parser_keeps_all_56_rows(self):
        text = '\n'.join(
            f'service-{i:02d} RUNNING pid {2000 + i}, uptime 0:00:01'
            for i in range(56))
        rows = MOD._parse_supervisor_status(text)
        self.assertEqual(len(rows), 56)
        self.assertEqual(rows[-1]['service'], 'service-55')

    def test_gpu_app_parser_keeps_uuid_and_memory_association(self):
        rows, rejected, unbounded = MOD.parse_gpu_apps(
            app_text(1964117) + f'1964117, {GPU_UUID.replace("58f4970e", "a8f4970e")}, 27648\n')
        self.assertEqual([row['gpu_pid'] for row in rows], [1964117, 1964117])
        self.assertEqual(rows[1]['used_gpu_memory'], '27648')
        self.assertEqual(rejected, 0)
        self.assertFalse(unbounded)


    def test_rc3_preserves_stopped_rows_and_degraded_health_but_not_command_success(self):
        def runner(argv, seconds=12):
            if argv == ['supervisorctl', 'status']:
                return 3, 'agent-a STOPPED\nagent-b STOPPED\n'
            return 0, ''
        result = MOD._capture_services(self.proc, runner, self.clock())
        self.assertEqual(result['command_rc'], 3)
        self.assertEqual(result['return_code'], 3)
        self.assertFalse(result['command_success'])
        self.assertFalse(result['complete'])
        self.assertTrue(result['inventory_complete'])
        self.assertEqual([row['state'] for row in result['services']], ['STOPPED', 'STOPPED'])
        self.assertEqual(result['service_health']['state'], 'DEGRADED')
        self.assertEqual(result['service_health']['counts'], {'STOPPED': 2})

    def test_rc3_with_malformed_output_keeps_rows_but_inventory_incomplete(self):
        def runner(argv, seconds=12):
            if argv == ['supervisorctl', 'status']:
                return 3, 'agent-a STOPPED\nmalformed status row\n'
            return 0, ''
        result = MOD._capture_services(self.proc, runner, self.clock())
        self.assertEqual(result['command_rc'], 3)
        self.assertEqual(len(result['services']), 1)
        self.assertEqual(result['rejected_lines'], 1)
        self.assertFalse(result['inventory_complete'])
        self.assertFalse(result['complete'])
        self.assertEqual(result['service_health']['state'], 'PARTIAL')

    def test_duplicate_supervisor_names_make_inventory_incomplete(self):
        add_proc(self.proc, 500, start=500)
        def runner(argv, seconds=12):
            if argv == ['supervisorctl', 'status']:
                row = 'agent RUNNING pid 500, uptime 0:00:01\n'
                return 0, row + row
            return 0, ''
        result = MOD._capture_services(self.proc, runner, self.clock())
        self.assertTrue(result['duplicate_service_names'])
        self.assertFalse(result['inventory_complete'])
        self.assertFalse(result['complete'])
        self.assertEqual(len(result['services']), 2)

    def test_all_pid_inventory_is_minimal_and_includes_pid_one(self):
        add_proc(self.proc, 1, ppid=1, start=1)
        add_proc(self.proc, 101, ppid=1, start=101, argv=b'/secret/argument\0--token\0')
        result = MOD._capture_process_identity_inventory(self.proc, self.clock())
        self.assertTrue(result['complete'])
        self.assertEqual(result['entries_seen'], 2)
        self.assertEqual(result['row_count'], 2)
        self.assertEqual([row['pid'] for row in result['rows']], [1, 101])
        row = result['rows'][1]
        self.assertEqual(row['identity_state'], 'VERIFIED')
        self.assertEqual(set(row), {'pid', 'ppid', 'uid', 'start_ticks', 'nspid',
                                    'namespaces', 'comm', 'exe', 'exe_state', 'identity_state'})
        self.assertNotIn('argv', row)
        self.assertNotIn('cmdline', row)
        self.assertNotIn('environ', row)
        self.assertEqual(result['omitted_fields'], ['argv', 'cmdline', 'environ', 'cgroup_paths'])

    def test_all_pid_inventory_cap_is_explicit_and_incomplete(self):
        add_proc(self.proc, 111, start=111)
        add_proc(self.proc, 112, start=112)
        old_cap = MOD.MAX_PROC_ENTRIES
        MOD.MAX_PROC_ENTRIES = 1
        try:
            result = MOD._capture_process_identity_inventory(self.proc, self.clock())
        finally:
            MOD.MAX_PROC_ENTRIES = old_cap
        self.assertTrue(result['truncated'])
        self.assertFalse(result['complete'])
        self.assertEqual(result['row_count'], 1)
        self.assertEqual(result['cap'], 1)

    def test_missing_exe_link_is_explicit_but_does_not_break_stable_identity(self):
        proc = add_proc(self.proc, 122, start=122)
        (proc / 'exe').unlink()
        result = MOD._capture_process_identity_inventory(self.proc, self.clock())
        row = next(row for row in result['rows'] if row['pid'] == 122)
        self.assertTrue(result['complete'])
        self.assertEqual(row['identity_state'], 'VERIFIED')
        self.assertIsNone(row['exe'])
        self.assertEqual(row['exe_state'], 'MISSING')

    def test_unreadable_exe_link_fails_inventory_closed(self):
        add_proc(self.proc, 123, start=123)
        original_readlink = MOD.os.readlink
        def deny_exe(path, *args, **kwargs):
            if Path(path).name == 'exe':
                raise PermissionError('fixture')
            return original_readlink(path, *args, **kwargs)
        MOD.os.readlink = deny_exe
        try:
            result = MOD._capture_process_identity_inventory(self.proc, self.clock())
        finally:
            MOD.os.readlink = original_readlink
        self.assertFalse(result['complete'])
        row = next(row for row in result['rows'] if row['pid'] == 123)
        self.assertEqual(row['exe_state'], 'UNREADABLE')
        self.assertIn('exe_read', row['missing_fields'])

    def test_rc3_valid_stopped_rows_keep_degraded_health_and_identity_links(self):
        add_proc(self.proc, 200, ppid=1, start=200)
        add_proc(self.proc, 101, ppid=200, start=101)
        def runner(argv, seconds=12):
            if argv[0] == 'nvidia-smi':
                return 0, app_text(101)
            if argv == ['supervisorctl', 'status']:
                return 3, ('nox-worker RUNNING pid 200, uptime 0:00:01\n'
                           'idle STOPPED\n')
            return 0, ''
        census = MOD.gpu_process_census(self.proc, run_fn=runner, clock=self.clock())
        services = census['supervisor_services']
        self.assertEqual(services['command_rc'], 3)
        self.assertFalse(services['complete'])
        self.assertTrue(services['inventory_complete'])
        self.assertEqual(services['service_health']['state'], 'DEGRADED')
        self.assertTrue(census['process_identity_inventory']['complete'])
        self.assertEqual(census['gpu_process_links'][0]['classification'], 'MATCHED')
        self.assertEqual(census['gpu_process_links'][0]['evidence_state'], 'COMPLETE')

    def test_all_pid_inventory_read_failure_is_explicit_and_incomplete(self):
        proc = add_proc(self.proc, 121, start=121)
        (proc / 'status').unlink()
        result = MOD._capture_process_identity_inventory(self.proc, self.clock())
        self.assertFalse(result['complete'])
        self.assertEqual(result['read_failure_count'], 1)
        self.assertEqual(result['read_failure_pids'], [121])
        self.assertEqual(result['rows'][0]['identity_state'], 'UNAVAILABLE_OR_CHANGED')

    def test_all_pid_inventory_pid_reuse_during_identity_read_fails_closed(self):
        add_proc(self.proc, 131, start=131)
        original_stat = MOD._proc_stat
        calls = 0
        def changing_stat(proc_dir, expected_pid):
            nonlocal calls
            if expected_pid == 131:
                calls += 1
                if calls == 2:
                    replace_start(self.proc, 131, start=1131)
            return original_stat(proc_dir, expected_pid)
        MOD._proc_stat = changing_stat
        try:
            result = MOD._capture_process_identity_inventory(self.proc, self.clock())
        finally:
            MOD._proc_stat = original_stat
        self.assertFalse(result['complete'])
        self.assertEqual(result['read_failure_count'], 1)
        self.assertEqual(result['rows'][0]['identity_state'], 'UNAVAILABLE_OR_CHANGED')

    def test_worker_emits_full_identity_inventory_without_argv(self):
        inventory = {'complete': True, 'rows': [{'pid': 1, 'start_ticks': 10}]}
        original = MOD.process_rows
        MOD.process_rows = lambda **kwargs: []
        try:
            result = MOD.worker((1, {'gpu_consumer_identities': [],
                                     'process_identity_inventory': inventory}))
        finally:
            MOD.process_rows = original
        self.assertEqual(result['bounded_process_identity_inventory'], inventory)


if __name__ == '__main__':
    unittest.main()
