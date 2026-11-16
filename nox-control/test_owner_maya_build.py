import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

spec = importlib.util.spec_from_file_location('maya_build', Path(__file__).with_name('owner_maya_build.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class NoopGuard:
    def check(self, *args, **kwargs):
        pass


class MayaBuildTests(unittest.TestCase):
    def test_no_owner_context_cannot_create_or_execute(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(m, 'owned_base') as create:
            with self.assertRaisesRegex(m.Hold, 'HOLD_OWNER_CONTEXT'):
                m.main()
        create.assert_not_called()

    def test_exact_native_resource_admission_and_reserves(self):
        good = {'disk_free_bytes': m.DISK_RESERVE + m.DISK_MAX,
                'memory_headroom_bytes': m.RAM_RESERVE + m.BUILD_RSS_MAX}
        m.admit(good)
        for field, error in [('disk_free_bytes', 'DISK'), ('memory_headroom_bytes', 'RAM')]:
            with self.assertRaisesRegex(m.Hold, error):
                m.admit(dict(good, **{field: good[field] - 1}))

    def test_real_stop_is_not_cleared_and_training_hold_is_not_global_stop(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'training.hold').write_text('held')
            m.stop(root)
            (root / 'STOP').write_text('owner')
            with self.assertRaisesRegex(m.Hold, 'HOLD_OWNER_STOP'):
                m.stop(root)
            self.assertEqual((root / 'STOP').read_text(), 'owner')

    def test_owned_directory_reuse_and_foreign_marker_refusal(self):
        with tempfile.TemporaryDirectory() as folder:
            base = m.owned_base(Path(folder))
            self.assertEqual(m.owned_base(Path(folder)), base)
            (base / '.owner.json').write_text('{}')
            with self.assertRaisesRegex(m.Hold, 'UNOWNED'):
                m.owned_base(Path(folder))

    def test_repeated_verified_inputs_keep_mtime_for_incremental_build(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'input.cpp'
            m.write(path, b'exact-source')
            os.utime(path, ns=(1234000000000, 1234000000000))
            m.write(path, b'exact-source')
            self.assertEqual(path.stat().st_mtime_ns, 1234000000000)

    def test_archive_paths_cannot_escape_owned_tree(self):
        for name in ('/etc/example', '../example', 'a/../example', '.git/config', 'a\\b', 'a\nfile'):
            with self.subTest(name=name), self.assertRaises(m.Hold):
                m.relative(name)

    def test_tar_symlink_is_rejected_before_file_write(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder); archive = base / 'input.tar.gz'
            with tarfile.open(archive, 'w:gz') as out:
                item = tarfile.TarInfo('llama.cpp-' + m.LLAMA + '/escape')
                item.type = tarfile.SYMTYPE; item.linkname = '/etc/example'
                out.addfile(item)
            with self.assertRaisesRegex(m.Hold, 'TAR_TYPE'):
                m.extract(base, 'llama.tar.gz', archive, NoopGuard())
            self.assertFalse((base / 'llama/escape').exists())

    def test_zip_expansion_is_capped(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder); archive = base / 'input.whl'
            with zipfile.ZipFile(archive, 'w') as z:
                z.writestr('cmake/data/bin/cmake', b'12345')
            spec = dict(m.ARTIFACTS['cmake.whl'], expanded_max=4)
            with patch.dict(m.ARTIFACTS, {'cmake.whl': spec}), self.assertRaisesRegex(m.Hold, 'EXPANSION'):
                m.extract(base, 'cmake.whl', archive, NoopGuard())
            self.assertFalse((base / 'cmake/bin/cmake').exists())

    def test_verified_archive_reuse_does_not_access_network(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder); data = b'pinned public source'
            (base / 'llama.tar.gz').write_bytes(data)
            spec = dict(m.ARTIFACTS['llama.tar.gz'], bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
            with patch.dict(m.ARTIFACTS, {'llama.tar.gz': spec}), patch.object(m.urllib.request, 'build_opener') as opener:
                self.assertEqual(m.download(base, 'llama.tar.gz', NoopGuard()), base / 'llama.tar.gz')
            opener.assert_not_called()
            with self.assertRaisesRegex(m.Hold, 'ALLOWLIST'):
                m.download(base, 'unrequested.whl', NoopGuard())

    def test_configure_is_pinned_sm70_and_build_is_one_target_two_jobs(self):
        base = Path('/root/nox/engine_builds/owned')
        configure, compile_argv = m.commands(base)
        self.assertIn('-DCMAKE_CUDA_ARCHITECTURES=70', configure)
        self.assertIn('-DSTRATA_PORTABLE=ON', configure)
        self.assertIn('-DSTRATA_BUILD_TESTS=OFF', configure)
        self.assertIn('-DFETCHCONTENT_FULLY_DISCONNECTED=ON', configure)
        self.assertIn('-DMAYA_BUILD_ID=' + m.MAYA, configure)
        self.assertEqual(compile_argv[-4:], ['--target', 'maya-ds4', '--parallel', '2'])
        self.assertEqual(m.environment(base)['CUDA_VISIBLE_DEVICES'], '')
        self.assertNotIn('HOME', m.environment(base))
        self.assertNotIn('--install', configure + compile_argv)

    def test_guard_stops_only_its_owned_child_session(self):
        class Halt:
            calls = 0
            def check(self, *args, **kwargs):
                self.calls += 1
                if self.calls >= 2:
                    raise m.Hold('HOLD_OWNER_STOP')
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder); (base / 'tmp').mkdir()
            unrelated = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
            try:
                with self.assertRaisesRegex(m.Hold, 'HOLD_OWNER_STOP'):
                    m.run([sys.executable, '-c', 'import time; time.sleep(30)'], 'compile', base, Halt())
                self.assertIsNone(unrelated.poll())
            finally:
                unrelated.terminate(); unrelated.wait(timeout=3)

    def test_binary_identity_hashes_without_executing(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'maya-ds4'; data = b'\x7fELF' + bytes(100001)
            path.write_bytes(data)
            with patch.object(m.subprocess, 'Popen', side_effect=AssertionError('binary executed')):
                result = m.binary_identity(path, NoopGuard())
            self.assertEqual(result['binary_sha256'], hashlib.sha256(data).hexdigest())


if __name__ == '__main__':
    unittest.main()
