"""Read-only diagnostics must remain useful without exposing private log text."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('training_diagnostic', Path(__file__).with_name('owner_training_runtime_diagnostic.py'))
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)


class TrainingDiagnosticTests(unittest.TestCase):
    def test_log_projection_keeps_diagnosis_and_discards_private_text(self):
        private = 'PRIVATE_TRAINING_PROMPT_AND_SECRET'
        raw = ('FileNotFoundError: /private/' + private + '\n'
               "ModuleNotFoundError: No module named 'torch'\n"
               "ModuleNotFoundError: No module named '" + private + "'\n"
               'CUDA out of memory: ' + private + '\n'
               '{"state":"HOLD_QWEN_CGROUP_RESERVE","messages":"' + private + '"}\n').encode()
        result = diagnostic.projected_log(raw)
        encoded = json.dumps(result)
        self.assertNotIn(private, encoded)
        self.assertNotIn('/private/', encoded)
        self.assertIn('HOLD_QWEN_CGROUP_RESERVE', encoded)
        self.assertIn('CUDA_OUT_OF_MEMORY', encoded)
        self.assertIn('"missing_module": "torch"', encoded)
        self.assertIn('UNLISTED_MODULE', encoded)
        self.assertFalse(result['raw_logs_exported'])

    def test_metadata_exposes_only_whitelisted_scalars_not_content(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'receipt.json'
            path.write_text(json.dumps({'state': {'private': 'SECRET'}, 'phase': 'PRIVATE',
                'successful_optimizer_steps': 55, 'training_allowed': True, 'loss': 0.93,
                'messages': 'SECRET', 'api_key': 'SECRET', 'reason': 'HOLD_QWEN_CGROUP_RESERVE'}))
            result = diagnostic.metadata(path, project=True)
        self.assertEqual(result['fields'], {'successful_optimizer_steps': 55,
            'training_allowed': True, 'loss': 0.93, 'reason': 'HOLD_QWEN_CGROUP_RESERVE'})
        self.assertNotIn('SECRET', json.dumps(result))
        self.assertTrue(result['stable'])

    def test_symlink_ancestors_and_fifos_are_never_read(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            real = root / 'real'
            real.mkdir()
            (real / 'secret').write_text('SECRET')
            (root / 'alias').symlink_to(real, target_is_directory=True)
            fifo = root / 'pipe'
            os.mkfifo(fifo)
            for path in (root / 'alias/secret', fifo):
                with self.assertRaises((OSError, diagnostic.ReadHold)):
                    diagnostic.regular_read(path)

    def test_tail_is_bounded_and_hash_is_labeled_as_tail_only(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'log'
            path.write_bytes(b'x' * 100 + b'CUDA out of memory')
            raw, info = diagnostic.regular_read(path, 20, tail=True)
            self.assertEqual(len(raw), 20)
            self.assertEqual(info['hash_scope'], 'TAIL_ONLY')
            self.assertGreater(info['bytes'], info['read_bytes'])
            with self.assertRaises(diagnostic.ReadHold):
                diagnostic.regular_read(path, 20)

    def test_only_fixed_read_only_supervisor_commands_are_allowed(self):
        with patch.object(diagnostic.subprocess, 'run') as command:
            for action, channel in (('start', None), ('restart', None), ('stop', None),
                                    ('tail', 'other-service'), ('status', 'stderr')):
                with self.assertRaises(diagnostic.ReadHold):
                    diagnostic.supervisor(action, channel)
            command.assert_not_called()

    def test_observe_does_not_import_trainer_or_report_saved_steps_as_live(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'scripts').mkdir()
            (root / 'state').mkdir()
            (root / 'logs').mkdir()
            output = root / 'output'
            output.mkdir()
            (root / 'scripts/qwen_student_training_entry_revision.py').write_text('raise RuntimeError("DO_NOT_IMPORT")\n')
            (output / 'owner_progress.json').write_text('{"successful_optimizer_steps":55,"messages":"SECRET"}')
            (root / 'logs/train_volta_t866u.log').write_text('ModuleNotFoundError: No module named \'torch\'\nSECRET')
            config = root / 'service.conf'
            config.write_text('[program:nox-train-volta-t866u]\nstdout_logfile=/outside/secret-t866u\n')
            with patch.object(diagnostic, 'ROOT', root), patch.object(diagnostic, 'OUTPUT', output), \
                    patch.object(diagnostic, 'CONFIG', config), \
                    patch.object(diagnostic, 'memory_observation', return_value={'scope': 'FIXTURE'}), \
                    patch.object(diagnostic, 'supervisor', return_value={'state': 'FATAL', 'pid': None}):
                result = diagnostic.observe()
        self.assertEqual(result['state'], 'READ_ONLY_DIAGNOSIS_COMPLETE')
        self.assertEqual(result['metadata']['student_progress']['fields']['successful_optimizer_steps'], 55)
        self.assertFalse(result['trainer_imported'])
        self.assertFalse(result['live_optimizer_steps_verified'])
        self.assertFalse(result['checkpoint_payloads_verified'])
        self.assertEqual(result['files_written'], 0)
        self.assertEqual(result['service_mutations'], 0)
        self.assertNotIn('SECRET', json.dumps(result))
        self.assertNotIn('DO_NOT_IMPORT', json.dumps(result))
        self.assertNotIn('/outside/', json.dumps(result))


class MemoryDiagnosticTests(unittest.TestCase):
    def fixture(self, directory, pid=101, ticks=12345):
        proc = Path(directory) / 'proc'
        process = proc / str(pid)
        (process / 'fd').mkdir(parents=True)
        (process / 'ns').mkdir()
        fields = ['S', '114'] + ['0'] * 17 + [str(ticks)]
        (process / 'stat').write_text(str(pid) + ' (PRIVATE_PROCESS_NAME) ' + ' '.join(fields))
        (process / 'status').write_text('Name:\tPRIVATE_PROCESS_NAME\nNSpid:\t999\t' + str(pid) + '\n')
        (process / 'smaps_rollup').write_text(
            '00000000-ffffffff ---p /PRIVATE_MAPPING_PATH\n'
            'Rss: 4096 kB\nPss: 3072 kB\nPss_Anon: 512 kB\n'
            'Pss_File: 512 kB\nPss_Shmem: 2048 kB\nPrivate_Dirty: 512 kB\n'
            'PRIVATE_FIELD: 12345 kB\n')
        for name in ('pid', 'mnt', 'ipc', 'user'):
            (process / 'ns' / name).symlink_to(name + ':[123456]')
        backing = process / 'fd/memfd:PRIVATE_FD_NAME'
        backing.write_bytes(b'PRIVATE_CONTENT')
        for number in ('3', '4'):
            (process / 'fd' / number).symlink_to(backing.name)
        (process / 'fd/5').symlink_to('/PRIVATE_ORDINARY_FILE_PATH')
        (process / 'fd/anon_inode:[PRIVATE_ANONYMOUS_NAME]').touch()
        (process / 'fd/6').symlink_to('anon_inode:[PRIVATE_ANONYMOUS_NAME]')
        return proc

    def test_memory_projection_excludes_names_paths_and_payloads_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            proc = self.fixture(directory)
            with patch.object(diagnostic, 'PROC', proc):
                result, unique = diagnostic.process_memory(101, 12345, float('inf'))
        self.assertEqual(result['state'], 'OBSERVED_STABLE_IDENTITY')
        self.assertEqual(result['smaps_rollup_bytes']['Pss_Shmem'], 2048 * 1024)
        self.assertEqual(result['namespace_pids'], [999, 101])
        self.assertEqual(result['namespace_ids']['pid'], 123456)
        self.assertEqual(result['descriptors']['fd_counts']['memfd'], 2)
        self.assertEqual(result['descriptors']['fd_counts']['anonymous_inode'], 1)
        self.assertEqual(result['descriptors']['memfd_unique_inodes'], 1)
        self.assertEqual(result['descriptors']['memfd_logical_bytes'], len(b'PRIVATE_CONTENT'))
        self.assertEqual(len(unique), 1)
        self.assertFalse(result['descriptors']['logical_file_bytes_are_resident_memory'])
        self.assertNotIn('PRIVATE', json.dumps(result))

    def test_reused_pid_does_not_read_memory(self):
        with patch.object(diagnostic, 'process_identity', return_value={'pid': 101, 'ppid': 114, 'start_ticks': 12346}), \
                patch.object(diagnostic, 'regular_read') as read:
            result, unique = diagnostic.process_memory(101, 12345, float('inf'))
        read.assert_not_called()
        self.assertEqual(result['state'], 'IDENTITY_CHANGED_NO_MEMORY_READ')
        self.assertEqual(unique, {})
        self.assertNotIn('smaps_rollup_bytes', result)

    def test_pid_change_during_read_discards_attribution(self):
        with tempfile.TemporaryDirectory() as directory:
            proc = self.fixture(directory)
            before = {'pid': 101, 'ppid': 114, 'start_ticks': 12345}
            after = {**before, 'start_ticks': 12346}
            with patch.object(diagnostic, 'PROC', proc), \
                    patch.object(diagnostic, 'process_identity', side_effect=[before, after]):
                result, unique = diagnostic.process_memory(101, 12345, float('inf'))
        self.assertEqual(result['state'], 'IDENTITY_CHANGED_DURING_READ')
        self.assertEqual(unique, {})
        self.assertNotIn('smaps_rollup_bytes', result)

    def test_fd_scan_and_wall_budget_exhaustion_are_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            proc = self.fixture(directory)
            with patch.object(diagnostic, 'PROC', proc), patch.object(diagnostic, 'FD_LIMIT', 1):
                result, _ = diagnostic.fd_memory(101, float('inf'))
                exhausted, _ = diagnostic.fd_memory(101, 0)
        self.assertEqual(result['scanned'], 1)
        self.assertFalse(result['scan_complete'])
        self.assertEqual(exhausted['scanned'], 0)
        self.assertFalse(exhausted['scan_complete'])

    def test_only_fixed_identities_are_read_and_global_file_sizes_are_deduplicated(self):
        observed = {'state': 'OBSERVED_STABLE_IDENTITY',
                    'smaps_rollup_bytes': {'Pss': 100, 'Pss_Shmem': 40}}
        unavailable = {'state': 'UNAVAILABLE_SAFE_READ'}
        with patch.object(diagnostic, 'MEMORY_PROCESSES', {'chat': (101, 12345),
                'director': (102, 12346), 'worker_runtime': (103, 12347)}), \
                patch.object(diagnostic, 'memory_cgroup', return_value={'state': 'OBSERVED'}), \
                patch.object(diagnostic, 'anonymous_owner_census', return_value={'owners': []}), \
                patch.object(diagnostic, 'process_memory', side_effect=[
                    (observed, {(1, 9): ('memfd', 4096)}),
                    (observed, {(1, 9): ('memfd', 4096)}), (unavailable, {})]) as read:
            result = diagnostic.memory_observation()
        self.assertEqual([(call.args[0], call.args[1]) for call in read.call_args_list],
                         [(101, 12345), (102, 12346), (103, 12347)])
        self.assertEqual(result['stable_processes_observed'], 2)
        self.assertEqual(result['smaps_sums_bytes']['Pss_Shmem'], 80)
        self.assertEqual(result['smaps_field_process_counts']['Pss_Anon'], 0)
        self.assertEqual(result['unique_open_anonymous_files']['logical_bytes'], 4096)
        self.assertFalse(result['full_cgroup_memory_attribution'])
        self.assertFalse(result['reclaimable_memory_proven'])
        self.assertFalse(result['fd_payloads_read'])
        self.assertFalse(result['cmdline_environ_maps_read'])

    def test_census_finds_detached_owner_and_deduplicates_shared_inode(self):
        with tempfile.TemporaryDirectory() as directory:
            proc = self.fixture(directory, 101, 12345)
            self.fixture(directory, 202, 23456)
            second_backing = proc / '202/fd/memfd:PRIVATE_FD_NAME'
            second_backing.unlink()
            os.link(proc / '101/fd/memfd:PRIVATE_FD_NAME', second_backing)
            with patch.object(diagnostic, 'PROC', proc):
                result = diagnostic.anonymous_owner_census(float('inf'))
        self.assertTrue(result['census_complete'])
        self.assertEqual(result['owners_total'], 2)
        self.assertEqual(result['unique_inodes'], 1)
        self.assertEqual(result['shared_inodes'], 1)
        self.assertEqual(result['unique_logical_bytes'], len(b'PRIVATE_CONTENT'))
        self.assertEqual(result['per_process_logical_bytes_sum'], 2 * len(b'PRIVATE_CONTENT'))
        self.assertEqual(result['files'][0]['owner_count'], 2)
        self.assertEqual({row['pid'] for row in result['owners']}, {101, 202})
        self.assertFalse(result['logical_file_bytes_are_resident_memory'])
        self.assertNotIn('PRIVATE', json.dumps(result))

    def test_census_limits_and_identity_races_are_not_claimed_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            proc = self.fixture(directory, 101, 12345)
            self.fixture(directory, 202, 23456)
            with patch.object(diagnostic, 'PROC', proc), patch.object(diagnostic, 'PID_LIMIT', 1):
                result = diagnostic.anonymous_owner_census(float('inf'))
            self.assertEqual(result['pids_examined'], 1)
            self.assertFalse(result['census_complete'])
            before = {'pid': 101, 'ppid': 114, 'start_ticks': 12345}
            after = {**before, 'start_ticks': 12346}
            with patch.object(diagnostic, 'PROC', proc), patch.object(diagnostic, 'PID_LIMIT', 1), \
                    patch.object(diagnostic, 'process_identity', side_effect=[before, after]):
                changed = diagnostic.anonymous_owner_census(float('inf'))
            self.assertEqual(changed['unstable_processes'], 1)
            self.assertEqual(changed['unique_inodes'], 0)
            self.assertFalse(changed['census_complete'])


if __name__ == '__main__':
    unittest.main()
