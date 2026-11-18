"""Only exact inode aggregates and private command hashes may leave this probe."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('inode_diagnostic', Path(__file__).with_name('owner_training_inode_diagnostic.py'))
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)


class InodeDiagnosticTests(unittest.TestCase):
    def process(self, proc, pid, ticks, ppid=1, maps=b''):
        directory = proc / str(pid)
        directory.mkdir(parents=True)
        fields = ['S', str(ppid)] + ['0'] * 17 + [str(ticks)]
        (directory / 'stat').write_text(str(pid) + ' (PRIVATE_PROCESS_NAME) ' + ' '.join(fields))
        (directory / 'cmdline').write_bytes(b'/usr/bin/python3\0-c\0PRIVATE_INLINE_CODE_AND_SECRET\0')
        (directory / 'maps').write_bytes(maps)
        return {'pid': pid, 'start_ticks': ticks, 'ppid': ppid}

    def test_exact_device_and_inode_and_offset_coverage(self):
        raw = (b'1000-5000 r--p 00000000 00:01 131095 /PRIVATE_MODEL_PATH\n'
               b'9000-b000 rw-s 00002000 00:01 131095 /PRIVATE_MODEL_PATH\n'
               b'd000-e000 r--p 00000000 00:02 131095 /PRIVATE_OTHER_DEVICE\n'
               b'f000-ffff r--p 00000000 00:01 131096 /PRIVATE_OTHER_INODE\n')
        result, ranges = diagnostic.project_maps(raw)
        self.assertEqual(result['mapping_count'], 2)
        self.assertEqual(result['mapped_virtual_bytes'], 24576)
        self.assertEqual(result['unique_file_bytes_mapped'], 16384)
        self.assertEqual(diagnostic.coverage(ranges), 16384)
        self.assertNotIn('PRIVATE', json.dumps(result))
        self.assertNotIn('1000', json.dumps(result))

    def test_unknown_command_content_is_only_hashed(self):
        raw = b'/private/bin/python3\0-c\0SECRET_DATA_PRIVATE_SCRIPT\0--token\0SECRET\0'
        result = diagnostic.command_projection(raw)
        self.assertEqual(result['invocation_class'], 'PYTHON_NAME_ONLY')
        self.assertTrue(result['inline_command_argument_present'])
        self.assertEqual(result['approved_script_arguments'], [])
        self.assertFalse(result['role_established'])
        self.assertFalse(result['raw_command_exported'])
        self.assertNotIn('SECRET', json.dumps(result))
        self.assertNotIn('/private/', json.dumps(result))
        approved = b'python3\0/root/nox/scripts/owner_qwen_memfd.py\0SECRET'
        self.assertEqual(diagnostic.command_projection(approved)['approved_script_arguments'],
                         ['/root/nox/scripts/owner_qwen_memfd.py'])

    def test_process_reader_rejects_payloads_environment_and_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            proc = Path(temporary) / 'proc'
            self.process(proc, 101, 1001)
            with patch.object(diagnostic, 'PROC', proc):
                for name in ('environ', 'mem', 'fd/3', '../maps'):
                    with self.assertRaises(diagnostic.ReadHold):
                        diagnostic.process_file(101, name, 1024)
                (proc / '101/maps').unlink()
                (proc / '101/maps').symlink_to('/etc/passwd')
                with self.assertRaises(OSError):
                    diagnostic.process_file(101, 'maps', 1024)

    def test_live_census_deduplicates_file_ranges_across_processes(self):
        with tempfile.TemporaryDirectory() as temporary:
            proc = Path(temporary) / 'proc'
            maps = b'1000-5000 r--p 00000000 00:01 131095 /PRIVATE_MODEL_PATH\n'
            chat = self.process(proc, 101, 1001, maps=maps)
            keeper = self.process(proc, 202, 2002, ppid=303)
            parent = self.process(proc, 303, 3003)
            self.process(proc, 404, 4004, maps=maps)
            with patch.object(diagnostic, 'PROC', proc), patch.object(diagnostic, 'CHAT', chat), \
                    patch.object(diagnostic, 'KEEPER', keeper):
                result = diagnostic.mapping_census(float('inf'), parent)
        self.assertTrue(result['census_complete'])
        self.assertEqual(result['mapper_count'], 2)
        self.assertEqual(result['mapped_virtual_bytes_sum'], 32768)
        self.assertEqual(result['unique_file_bytes_mapped_all_processes'], 16384)
        self.assertEqual(result['known_processes']['chat']['mapping_count'], 1)
        self.assertEqual(result['known_processes']['keeper']['mapping_count'], 0)
        self.assertFalse(result['mapped_bytes_are_resident_memory'])
        self.assertNotIn('PRIVATE', json.dumps(result))

    def test_read_bound_reports_unknown_instead_of_false_no_mapping(self):
        with tempfile.TemporaryDirectory() as temporary:
            proc = Path(temporary) / 'proc'
            maps = b'1000-5000 r--p 00000000 00:01 131095 /PRIVATE\n' * 20
            chat = self.process(proc, 101, 1001, maps=maps)
            keeper = self.process(proc, 202, 2002, ppid=303)
            parent = self.process(proc, 303, 3003)
            with patch.object(diagnostic, 'PROC', proc), patch.object(diagnostic, 'CHAT', chat), \
                    patch.object(diagnostic, 'KEEPER', keeper), patch.object(diagnostic, 'MAP_LIMIT', 20):
                result = diagnostic.mapping_census(float('inf'), parent)
        self.assertFalse(result['census_complete'])
        self.assertEqual(result['known_processes']['chat']['state'], 'UNAVAILABLE_SAFE_READ')
        self.assertGreater(result['map_read_bytes_upper_bound'], 0)

    def test_reused_pid_at_end_discards_mapping_attribution(self):
        parent = {'pid': 303, 'ppid': 1, 'start_ticks': 3003}
        chat = {'pid': 101, 'ppid': 1, 'start_ticks': 1001}
        keeper = {'pid': 202, 'ppid': 303, 'start_ticks': 2002}
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(diagnostic, 'PROC', Path(temporary)), patch.object(diagnostic, 'CHAT', chat), \
                    patch.object(diagnostic, 'KEEPER', keeper), patch.object(diagnostic, 'PID_LIMIT', 1), \
                    patch.object(diagnostic, 'identity', side_effect=[chat, {**chat, 'start_ticks': 9999}]), \
                    patch.object(diagnostic, 'process_file', return_value=b'1000-5000 r--p 00000000 00:01 131095 /PRIVATE\n'):
                result = diagnostic.mapping_census(float('inf'), parent)
        self.assertFalse(result['census_complete'])
        self.assertEqual(result['unstable_processes'], 1)
        self.assertEqual(result['mapper_count'], 0)
        self.assertEqual(result['unique_file_bytes_mapped_all_processes'], 0)

    def test_observe_binds_keeper_file_and_parent_without_reading_payload(self):
        with tempfile.TemporaryDirectory() as temporary:
            proc = Path(temporary) / 'proc'
            chat = self.process(proc, 101, 1001)
            keeper = self.process(proc, 202, 2002, ppid=303)
            self.process(proc, 303, 3003)
            descriptors = proc / '202/fd'
            descriptors.mkdir()
            backing = descriptors / 'memfd:PRIVATE_FD_NAME'
            backing.write_bytes(b'PRIVATE_WEIGHT_PAYLOAD')
            (descriptors / '3').symlink_to(backing.name)
            info = backing.stat()
            target = {'device': info.st_dev, 'inode': info.st_ino, 'logical_bytes': info.st_size}
            device = f'{os.major(info.st_dev):02x}:{os.minor(info.st_dev):02x}'
            (proc / '101/maps').write_text(f'1000-2000 r--p 00000000 {device} {info.st_ino} /PRIVATE_MAPPING\n')
            with patch.object(diagnostic, 'PROC', proc), patch.object(diagnostic, 'CHAT', chat), \
                    patch.object(diagnostic, 'KEEPER', keeper), patch.object(diagnostic, 'TARGET', target):
                result = diagnostic.observe()
            self.assertEqual(backing.read_bytes(), b'PRIVATE_WEIGHT_PAYLOAD')
        self.assertEqual(result['state'], 'READ_ONLY_INODE_DIAGNOSIS_COMPLETE')
        self.assertTrue(result['target_stable'])
        self.assertEqual(result['mappings']['mapper_count'], 1)
        self.assertEqual(result['mappings']['unique_file_bytes_mapped_all_processes'], target['logical_bytes'])
        self.assertFalse(result['memory_released'])
        self.assertFalse(result['release_authorized'])
        self.assertFalse(result['weight_payloads_read'])
        self.assertEqual(result['files_written'], 0)
        self.assertNotIn('PRIVATE', json.dumps(result))


if __name__ == '__main__':
    unittest.main()
