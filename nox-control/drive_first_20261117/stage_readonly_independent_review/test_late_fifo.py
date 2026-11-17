"""One independent race fixture; no native paths are read or modified."""
import hashlib
import importlib.util
import json
import multiprocessing
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

SOURCE = Path(__file__).resolve().parents[1] / 'onehost_binding_projection/owner_runtime_stage_readonly_diagnostic.py'


def race_probe(root, connection):
    sys.dont_write_bytecode = True
    try:
        spec = importlib.util.spec_from_file_location('independent_ro_probe', SOURCE)
        probe = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(probe)
        target = Path(root) / 'source.py'
        raw = b'UNEXPORTED_SOURCE_LITERAL\n'
        target.write_bytes(raw)
        target.chmod(0o600)
        original_open = probe.os.open
        opened_flags = []

        def replace_leaf_before_open(name, flags, *args, **kwargs):
            if name == target.name and kwargs.get('dir_fd') is not None:
                opened_flags.append(flags)
                os.unlink(name, dir_fd=kwargs['dir_fd'])
                os.mkfifo(name, 0o600, dir_fd=kwargs['dir_fd'])
            return original_open(name, flags, *args, **kwargs)

        with mock.patch.object(probe.os, 'open', side_effect=replace_leaf_before_open):
            row = probe.inspect(target, expected=(len(raw), hashlib.sha256(raw).hexdigest()))
        connection.send({'row': row, 'opened_flags': opened_flags})
    except BaseException as error:
        connection.send({'error_type': type(error).__name__})
    finally:
        connection.close()


class LateFIFOTest(unittest.TestCase):
    def test_late_fifo_substitution_is_bounded_and_never_certified(self):
        """A regular leaf becomes FIFO after lstat but before open; must not block/read/hash it."""
        before = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
        with tempfile.TemporaryDirectory() as td:
            ctx = multiprocessing.get_context('fork')
            receive, send = ctx.Pipe(duplex=False)
            process = ctx.Process(target=race_probe, args=(td, send))
            process.start()
            send.close()
            try:
                self.assertTrue(receive.poll(2), 'Probe blocked on late FIFO substitution')
                result = receive.recv()
                process.join(1)
                self.assertFalse(process.is_alive(), 'Probe did not terminate after metadata rejection')
                self.assertEqual(process.exitcode, 0)
                self.assertNotIn('error_type', result)
                self.assertEqual(len(result['opened_flags']), 1)
                flags = result['opened_flags'][0]
                self.assertTrue(flags & os.O_NONBLOCK)
                self.assertTrue(flags & os.O_NOFOLLOW)
                row = result['row']
                self.assertEqual(row['status'], 'CHANGED_BEFORE_READ')
                self.assertEqual(row['bytes_read'], 0)
                self.assertFalse(row['matches_manifest'])
                self.assertIsNone(row['sha256'])
                self.assertNotIn('UNEXPORTED_SOURCE_LITERAL', json.dumps(result))
            finally:
                if process.is_alive():
                    process.terminate()
                process.join(1)
                receive.close()
        self.assertEqual(hashlib.sha256(SOURCE.read_bytes()).hexdigest(), before)


if __name__ == '__main__':
    unittest.main()
