"""P01-SB-08: real Git fixture; read-only R3–R5 source catalogue contract."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

MODULE = Path(__file__).with_name('source_catalog.py')
spec = importlib.util.spec_from_file_location('nox_source_catalog_test', MODULE)
catalog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog)


class GitSource:
    def __init__(self, root):
        self.root = root

    def git(self, *args):
        process = subprocess.run(['git', '-C', str(self.root), *args],
                                 capture_output=True, check=True)
        return process.stdout.decode('utf-8', 'strict')

    def head(self):
        return self.git('rev-parse', 'HEAD').strip()

    def admitted(self, head):
        return self.head() == head and not self.git('status', '--porcelain', '--untracked-files=no').strip()


class SourceCatalogExactHeadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = GitSource(self.root)
        self.call('init', '-q')
        self.call('config', 'user.name', 'NOX Fixture')
        self.call('config', 'user.email', 'test@nox.local')

    def call(self, *args, input=None):
        return subprocess.run(['git', '-C', str(self.root), *args],
                              input=input, capture_output=True, check=True).stdout.decode('utf-8').strip()

    def write(self, path, contents='print(1)'):
        f = self.root / path
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(contents, encoding='utf-8')

    def commit(self):
        self.call('add', '-A')
        self.call('commit', '-qm', 'fixture')

    def test_regular_blob_provenance_and_owner_first_without_ingestion(self):
        self.write('modules/onehost.py')
        self.write('templates/дом.mjs')
        self.write('patches/fix.patch')
        self.write('integrations/bridge.cs')
        self.write('not-allowed.bin')
        self.commit()
        head = self.source.head()
        receipt = catalog.inspect_managed_sources(self.source, ('modules/onehost.py',))
        self.assertEqual(receipt['status'], 'SOURCE_INVENTORY_READ_ONLY')
        self.assertEqual(receipt['source_head'], head)
        self.assertEqual(receipt['supported_total'], 4)
        self.assertEqual(receipt['owner_admitted_total'], 1)
        self.assertEqual(receipt['items'][0]['path'], 'modules/onehost.py')
        self.assertEqual(receipt['items'][0]['git_blob_mode'], '100644')
        self.assertEqual(receipt['items'][0]['git_blob_sha'], self.call('rev-parse', 'HEAD:modules/onehost.py'))
        self.assertEqual(receipt['items'][0]['source_ref'], 'git:' + head + ':modules/onehost.py')
        self.assertIn('templates/дом.mjs', [x['path'] for x in receipt['items']])
        self.assertEqual(receipt['categories']['patches'], 1)
        self.assertEqual(receipt['categories']['integrations'], 2)
        self.assertFalse(receipt['all_sources_loaded'])
        self.assertFalse(receipt['imported_into_s03'])
        self.assertEqual(receipt['source_generation'], 'SEPARATE_NATIVE_CONSENT_REQUIRED')
        self.assertEqual(self.source.git('status', '--porcelain', '--untracked-files=no').strip(), '')

    def test_symlink_and_gitlink_are_not_real_code(self):
        self.write('safe.py')
        try:
            (self.root / 'evil.py').symlink_to('outside-secret')
        except (OSError, NotImplementedError):
            self.skipTest('filesystem symlink unavailable')
        self.commit()
        # A real Git symlink, plus a gitlink fixture carrying a valid commit ID.
        class WithGitlink(GitSource):
            def git(self, *args):
                content = super().git(*args)
                if args[0] == 'ls-tree':
                    return content + '160000 commit ' + self.head() + '\tmodule.py\0'
                return content
        result = catalog.inspect_managed_sources(WithGitlink(self.root),
                                                 ('safe.py', 'evil.py', 'module.py'))
        self.assertEqual(result['status'], 'SOURCE_INVENTORY_READ_ONLY')
        self.assertEqual(result['supported_total'], 1)
        self.assertEqual(result['owner_admitted_total'], 1)
        self.assertEqual([x['path'] for x in result['items']], ['safe.py'])

    def test_changed_tracked_file_makes_inventory_hold(self):
        self.write('good.py', 'before')
        self.commit()
        self.write('good.py', 'modified')
        result = catalog.inspect_managed_sources(self.source)
        self.assertEqual(result['status'], 'HOLD')
        self.assertEqual(result['reason'], 'EXACT_CLEAN_HEAD_REQUIRED')
        self.assertEqual(result['items'], [])

    def test_bad_owner_source_path_fail_closed(self):
        self.write('good.py')
        self.commit()
        for paths in ('good.py', ['good.py', 'good.py'], ['../good.py'], ['good.py\nHACK'], [123]):
            with self.subTest(paths=paths):
                result = catalog.inspect_managed_sources(self.source, paths)
                self.assertEqual(result['status'], 'HOLD')
                self.assertEqual(result['reason'], 'OWNER_SOURCE_PATH_CONFIG_INVALID')

    def test_bounded_result_and_owner_first(self):
        for i in range(130):
            self.write(f'modules/{i:03}.py')
        self.commit()
        out = catalog.inspect_managed_sources(self.source, ('modules/129.py',))
        self.assertEqual(out['status'], 'SOURCE_INVENTORY_READ_ONLY')
        self.assertEqual(out['supported_total'], 130)
        self.assertEqual(out['displayed'], 120)
        self.assertTrue(out['truncated'])
        self.assertEqual(out['items'][0]['path'], 'modules/129.py')

    def test_second_head_admission_blocks_race(self):
        self.write('good.py')
        self.commit()
        class ChangingSource(GitSource):
            times = 0
            def admitted(self, head):
                self.times += 1
                return self.times == 1
        out = catalog.inspect_managed_sources(ChangingSource(self.root))
        self.assertEqual(out['reason'], 'EXACT_CLEAN_HEAD_REQUIRED')
        self.assertEqual(out['items'], [])

    def test_malformed_tree_returns_hold(self):
        self.write('good.py')
        self.commit()
        class MalformedSource(GitSource):
            def git(self, *args):
                if args[0] == 'ls-tree':
                    return '100644 blob ' + 'a' * 40 + '\tgood.py'  # missing NUL
                return super().git(*args)
        out = catalog.inspect_managed_sources(MalformedSource(self.root))
        self.assertEqual(out['status'], 'HOLD')
        self.assertEqual(out['items'], [])


if __name__ == '__main__':
    unittest.main()
