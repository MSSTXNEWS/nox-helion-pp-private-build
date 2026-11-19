"""Synthetic Maya read bounds: no native services, model execution or network."""
import hashlib
import os
from pathlib import Path
import signal
import tempfile
import unittest
from unittest.mock import patch

import owner_native_inspect as INSPECT


class MayaReadBoundsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / 'nox'
        self.path = self.root / INSPECT.MAYA_P0_BINARY_REL
        self.path.parent.mkdir(parents=True)
        self.elf = (b'\x7fELF' + bytes([2, 1]) + b'\0' * 12 +
                    (62).to_bytes(2, 'little') + b'\0' * 44 + b'body' * 8)
        self.path.write_bytes(self.elf)
        self.path.chmod(0o700)
        self.sha256 = hashlib.sha256(self.elf).hexdigest()

    def test_regular_elf_keeps_existing_metadata_only_contract(self):
        with patch.object(INSPECT.subprocess, 'run', side_effect=AssertionError('must not execute')):
            result = INSPECT.maya_p0_binary_readback(self.root, self.sha256)
        self.assertEqual(result['state'], 'SHA_PIN_MATCH_ELF_ONLY')
        self.assertEqual(result['bytes'], len(self.elf))
        self.assertEqual(result['observed_sha256'], self.sha256)
        self.assertEqual(result['real_inference'], 'NOT_TESTED')
        self.assertFalse(result['native_model_promotion'])

    @unittest.skipUnless(hasattr(os, 'mkfifo') and hasattr(signal, 'setitimer'), 'POSIX FIFO test')
    def test_fifo_does_not_block_before_regular_file_rejection(self):
        self.path.unlink()
        os.mkfifo(self.path, 0o700)
        alarm_fired = []

        def alarm(_signum, _frame):
            alarm_fired.append(True)
            raise TimeoutError('synthetic FIFO liveness guard')

        previous = signal.signal(signal.SIGALRM, alarm)
        signal.setitimer(signal.ITIMER_REAL, 1.0)
        try:
            result = INSPECT.maya_p0_binary_readback(self.root)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous)
        self.assertFalse(alarm_fired, 'FIFO must be rejected without waiting for a writer')
        self.assertEqual(result['state'], 'HOLD_NOT_EXECUTABLE_REGULAR')
        self.assertIsNone(result['observed_sha256'])

    def test_regular_leaf_replaced_by_fifo_before_open_still_does_not_block(self):
        real_open = INSPECT.os.open
        attempts = []

        def substitute_leaf(path, flags, *args, **kwargs):
            if path == self.path.name and 'dir_fd' in kwargs:
                self.path.unlink()
                os.mkfifo(self.path, 0o700)
                attempts.append(flags)
                self.assertTrue(flags & os.O_NONBLOCK,
                                'nonblocking open required even after a regular lstat')
            return real_open(path, flags, *args, **kwargs)

        with patch.object(INSPECT.os, 'open', side_effect=substitute_leaf):
            result = INSPECT.maya_p0_binary_readback(self.root)
        self.assertEqual(len(attempts), 1)
        self.assertEqual(result['state'], 'HOLD_NOT_EXECUTABLE_REGULAR')
        self.assertIsNone(result['observed_sha256'])

    def test_growing_file_is_not_followed_to_eof_or_hashed_past_initial_size(self):
        real_fdopen = INSPECT.os.fdopen
        counters = {'reads': 0, 'bytes': 0}
        target = self.path

        class GrowingStream:
            def __init__(self, stream):
                self.stream = stream

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return self.stream.__exit__(*args)

            def read(self, size=-1):
                counters['reads'] += 1
                if counters['reads'] > 6:
                    raise AssertionError('reader chased a continuously growing file')
                if counters['reads'] > 1:
                    with target.open('ab') as writer:
                        writer.write(b'x')
                data = self.stream.read(size)
                counters['bytes'] += len(data)
                return data

        def wrap(fd, *args, **kwargs):
            return GrowingStream(real_fdopen(fd, *args, **kwargs))

        with patch.object(INSPECT.os, 'fdopen', side_effect=wrap):
            result = INSPECT.maya_p0_binary_readback(self.root, self.sha256)
        self.assertEqual(result['state'], 'HOLD_BINARY_CHANGED_DURING_READ')
        self.assertLessEqual(counters['bytes'], len(self.elf) + 1)
        self.assertIsNone(result['observed_sha256'])

    def test_symlink_above_explicit_root_is_not_followed(self):
        container = self.base / 'real_parent'
        container.mkdir()
        self.root.rename(container / 'nox')
        link = self.base / 'linked_parent'
        link.symlink_to(container, target_is_directory=True)
        result = INSPECT.maya_p0_binary_readback(link / 'nox', self.sha256)
        self.assertEqual(result['state'], 'HOLD_UNSAFE_PARENT')
        self.assertIsNone(result['observed_sha256'])

    def test_expired_read_deadline_does_not_start_hashing(self):
        with patch.object(INSPECT.time, 'monotonic', side_effect=[0.0, 13.0]), \
                patch.object(INSPECT.os, 'fdopen', side_effect=AssertionError('deadline already expired')):
            result = INSPECT.maya_p0_binary_readback(self.root, self.sha256)
        self.assertEqual(result['state'], 'HOLD_BINARY_READ_DEADLINE')
        self.assertIsNone(result['observed_sha256'])


if __name__ == '__main__':
    unittest.main()
