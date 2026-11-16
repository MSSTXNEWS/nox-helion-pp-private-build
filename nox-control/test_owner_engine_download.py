#!/usr/bin/env python3
"""Offline contract and real-Git tests for source-only owner downloads."""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('owner_engine_download', Path(__file__).with_name('owner_engine_download.py'))
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'nox'
        self.root.mkdir(mode=0o700)
        self.row = dict(name='llama.cpp', repo='https://github.com/ggml-org/llama.cpp.git',
                        commit='a' * 40, source_max_bytes=8 * 1024 ** 2, git_max_bytes=8 * 1024 ** 2)

    def manifest(self, row=None):
        return m.canonical({'schema': 'NOX_ENGINE_SOURCES_V1', 'sources': [row or self.row]})

    def large_disk(self):
        return patch.object(m.shutil, 'disk_usage', return_value=SimpleNamespace(free=100 * m.GIB))

    def test_reviewed_manifest_has_six_unique_pinned_sources(self):
        raw = (Path(__file__).resolve().parents[1] / m.MANIFEST).read_bytes()
        rows = m.validate_manifest(raw)
        self.assertEqual(len(rows), 6)
        self.assertEqual({x['name'] for x in rows}, {'maya', 'strata', 'llama.cpp', 'bnk', 'rclone', 'prism-bonsai'})
        self.assertEqual(m.MAX_WORKERS, 6)
        self.assertEqual(m.RESERVE, 8 * m.GIB)

    def test_manifest_rejects_non_allowlisted_transport_and_unpinned_refs(self):
        cases = {
            'repo': ['http://github.com/a/b.git', 'file:///tmp/a.git', 'https://user:token@github.com/a/b.git',
                     'https://github.com.evil.test/a/b.git', 'https://github.com:443/a/b.git',
                     'https://github.com/a/b.git?ref=main', 'https://github.com/a/../b.git'],
            'commit': ['main', 'a' * 39, 'A' * 40, '0' * 40, 'a' * 40 + ';id'],
            'name': ['../maya', '/maya', 'a..b', 'a/b', 'a;id', '.hidden'],
            'source_max_bytes': [True, -1, 0, m.GIB + 1, '100'],
        }
        for key, values in cases.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    row = dict(self.row, **{key: value})
                    with self.assertRaises(m.Hold):
                        m.validate_manifest(self.manifest(row))
        with self.assertRaises(m.Hold):
            m.validate_manifest(self.manifest(dict(self.row, command='make install')))
        with self.assertRaises(m.Hold):
            m.validate_manifest(m.canonical({'schema': 'NOX_ENGINE_SOURCES_V1', 'sources': [self.row, self.row]}))

    def test_real_stop_blocks_before_mutation_but_training_hold_does_not(self):
        (self.root / 'TRAIN_HOLD').touch()
        m.check_stop(self.root)
        (self.root / 'STOP').touch()
        with patch.object(m.subprocess, 'Popen') as popen:
            with self.assertRaisesRegex(m.Hold, 'HOLD_OWNER_STOP'):
                m.stage_one(self.row, '123', 'b' * 64, m.Budget(self.root), self.root)
        popen.assert_not_called()
        self.assertFalse((self.root / 'engine_candidates').exists())

    def test_tracked_tree_rejects_paths_and_large_source_before_checkout(self):
        for path in ('../outside', '/outside', './file', 'a//b', 'a/.git/config', m.OWNER_FILE, m.HASH_FILE):
            with self.subTest(path=path), self.assertRaises(m.Hold):
                m.source_tree(b'100644 blob ' + b'a' * 40 + b' 1\t' + path.encode() + b'\0', self.row)
        with self.assertRaisesRegex(m.Hold, 'SOURCE_BUDGET'):
            m.source_tree(b'100644 blob ' + b'a' * 40 + b' 99999999\tlarge\0', self.row)
        with self.assertRaisesRegex(m.Hold, 'TRACKED_OBJECT'):
            m.source_tree(b'100644 commit ' + b'a' * 40 + b' 1\tfile\0', self.row)

    def test_unowned_partial_and_symlink_destination_are_never_overwritten(self):
        parent = m.directory(self.root / 'engine_candidates' / self.row['name'])
        partial = parent / (self.row['commit'] + '.partial')
        partial.mkdir(mode=0o700)
        untouched = partial / 'external.txt'
        untouched.write_text('keep')
        with self.large_disk(), patch.object(m.subprocess, 'Popen') as popen:
            with self.assertRaises((m.Hold, OSError)):
                m.stage_one(self.row, '123', 'b' * 64, m.Budget(self.root), self.root)
        self.assertEqual(untouched.read_text(), 'keep')
        self.assertEqual(list(parent.iterdir()), [partial])
        popen.assert_not_called()
        (parent / self.row['commit']).symlink_to(partial, target_is_directory=True)
        with self.large_disk(), self.assertRaisesRegex(m.Hold, 'SYMLINK_PATH'):
            m.stage_one(self.row, '124', 'b' * 64, m.Budget(self.root), self.root)

    def test_owned_partial_is_quarantined_without_deleting_bytes(self):
        partial = m.directory(self.root / 'candidate.partial')
        m.atomic(partial / m.OWNER_FILE, m.canonical(dict(schema='NOX_ENGINE_DOWNLOAD_OWNER_V1',
            **{k: self.row[k] for k in ('name', 'repo', 'commit')})))
        (partial / 'saved').write_bytes(b'partial payload')
        dest = Path(m.quarantine_partial(partial, self.row, '123'))
        self.assertFalse(partial.exists())
        self.assertEqual((dest / 'saved').read_bytes(), b'partial payload')

    def test_disk_and_git_budgets_are_enforced(self):
        budget = m.Budget(self.root)
        with patch.object(m.shutil, 'disk_usage', return_value=SimpleNamespace(free=m.RESERVE)):
            with self.assertRaisesRegex(m.Hold, 'DISK_ADMISSION'):
                budget.acquire(self.row)
        git = m.directory(self.root / '.git')
        (git / 'oversized').write_bytes(b'abcdef')
        with self.large_disk(), self.assertRaisesRegex(m.Hold, 'GIT_BUDGET'):
            budget.check(self.root, dict(self.row, git_max_bytes=5))

    def test_git_boundary_ignores_ambient_hooks_filters_credentials_and_exec(self):
        with patch.dict(os.environ, {'GIT_CONFIG_GLOBAL': '/tmp/secret-config', 'GIT_SSH_COMMAND': 'execute-me',
                                    'HOME': '/tmp/secret-home', 'GITHUB_TOKEN': 'do-not-copy'}):
            env = m.environment()
        self.assertEqual(env['GIT_CONFIG_GLOBAL'], '/dev/null')
        self.assertEqual(env['GIT_LFS_SKIP_SMUDGE'], '1')
        self.assertEqual(env['GIT_ALLOW_PROTOCOL'], 'https')
        self.assertNotIn('HOME', env)
        self.assertNotIn('GITHUB_TOKEN', env)
        self.assertNotIn('GIT_SSH_COMMAND', env)
        argv = m.git_argv(self.root, ['fetch', '--depth=1', self.row['repo'], self.row['commit']])
        for setting in ('core.hooksPath=/dev/null', 'submodule.recurse=false', 'filter.lfs.smudge=',
                        'credential.helper=', 'http.followRedirects=false', 'protocol.allow=never'):
            self.assertIn(setting, argv)
        for command in ('submodule', 'clone', 'pull', 'shell', 'make', 'install', 'config'):
            with self.subTest(command=command), self.assertRaises(m.Hold):
                m.git_argv(self.root, [command])

    def fixture_repo(self):
        fixture = Path(self.temp.name) / 'fixture'
        fixture.mkdir(mode=0o700)
        git = shutil.which('git')
        def call(*args):
            return subprocess.check_output([git, '-C', str(fixture), *args], env=m.environment(), stderr=subprocess.DEVNULL)
        call('init', '--quiet', '--template=')
        (fixture / 'README.txt').write_text('source fixture\n')
        (fixture / '.gitattributes').write_text('*.bin filter=lfs\n*.txt filter=trap\n')
        (fixture / 'weights.bin').write_text('version https://git-lfs.github.com/spec/v1\noid sha256:' + 'a' * 64 + '\nsize 9000000000\n')
        (fixture / 'link').symlink_to('README.txt')
        self.execution_marker = Path(self.temp.name) / 'EXECUTED'
        (fixture / 'engine.sh').write_text('#!/bin/sh\ntouch ' + str(self.execution_marker) + '\n')
        (fixture / 'engine.sh').chmod(0o700)
        call('add', '--all')
        call('-c', 'user.name=Offline test', '-c', 'user.email=offline@example.invalid', 'commit', '--quiet', '-m', 'fixture')
        self.row['commit'] = call('rev-parse', 'HEAD').decode().strip()
        original = m.run_git
        self.calls = []
        def transport(path, args, row, budget, root, **kwargs):
            self.calls.append(args)
            if args[0] == 'fetch':
                self.assertEqual(args, ['fetch', '--depth=1', '--no-tags', '--no-recurse-submodules', '--no-write-fetch-head',
                                        self.row['repo'], self.row['commit']])
                shutil.copytree(fixture / '.git/objects', path / '.git/objects', dirs_exist_ok=True)
                return b''
            return original(path, args, row, budget, root, **kwargs)
        return patch.object(m, 'run_git', side_effect=transport)

    def test_real_git_checkout_fsck_hashes_reuse_and_tamper_detection(self):
        transport = self.fixture_repo()
        template = Path(self.temp.name) / 'hostile-template'
        (template / 'hooks').mkdir(parents=True)
        hook = template / 'hooks/post-checkout'
        hook.write_text('#!/bin/sh\ntouch ' + str(self.execution_marker) + '\n')
        hook.chmod(0o700)
        hostile = Path(self.temp.name) / 'hostile-config'
        hostile.write_text('[filter "trap"]\n required = true\n smudge = touch ' + str(self.execution_marker) + '\n')
        with transport, self.large_disk(), patch.dict(os.environ, {'GIT_CONFIG_GLOBAL': str(hostile), 'GIT_TEMPLATE_DIR': str(template)}):
            result = m.stage_one(self.row, '123', 'b' * 64, m.Budget(self.root), self.root)
            self.assertEqual(result['state'], 'DOWNLOADED_AND_SHA_VERIFIED')
            self.assertTrue(result['git_fsck_passed'])
            self.assertEqual(result['lfs_pointer_files'], 1)
            self.assertEqual(result['symlinks_as_text'], 1)
            self.assertFalse(result['installed'] or result['built'] or result['executed'])
            target = Path(result['path'])
            self.assertEqual((target / 'link').read_text(), 'README.txt')
            self.assertFalse((target / 'link').is_symlink())
            files = json.loads((target / m.HASH_FILE).read_bytes())['files']
            readme = next(x for x in files if x['path'] == 'README.txt')
            self.assertEqual(readme['sha256'], hashlib.sha256(b'source fixture\n').hexdigest())
            reused = m.stage_one(self.row, '124', 'b' * 64, m.Budget(self.root), self.root)
            self.assertEqual(reused['state'], 'REUSED_AND_SHA_VERIFIED')
            self.assertEqual(sum(x[0] == 'fetch' for x in self.calls), 1)
            (target / 'README.txt').write_text('tampered\n')
            with self.assertRaisesRegex(m.Hold, 'GIT_DIFF'):
                m.stage_one(self.row, '125', 'b' * 64, m.Budget(self.root), self.root)
        self.assertFalse(self.execution_marker.exists())
        self.assertTrue(all(x[0] in {'init', 'fetch', 'checkout', 'rev-parse', 'fsck', 'ls-tree', 'diff'} for x in self.calls))

    def test_real_source_budget_refuses_checkout_and_never_publishes_target(self):
        transport = self.fixture_repo()
        self.row['source_max_bytes'] = 3
        with transport, self.large_disk(), self.assertRaisesRegex(m.Hold, 'SOURCE_BUDGET'):
            m.stage_one(self.row, '123', 'b' * 64, m.Budget(self.root), self.root)
        self.assertFalse(any(x[0] == 'checkout' for x in self.calls))
        self.assertFalse((self.root / 'engine_candidates' / self.row['name'] / self.row['commit']).exists())
        self.assertFalse(self.execution_marker.exists())

    def run_main(self, effect, rows=None):
        rows = rows or [self.row]
        output = io.StringIO()
        old_mask = os.umask(0o077)
        try:
            with patch.object(m, 'ROOT', self.root), patch.object(m, 'load_manifest', return_value=(self.manifest(), rows)), \
                 patch.object(m, 'native_metadata', return_value={'probe': 'offline'}), patch.object(m, 'stage_one', side_effect=effect), \
                 self.large_disk(), patch.dict(os.environ, {'NOX_OWNER_REQUEST_ID': '123', 'NOX_OWNER_SOURCE_SHA': 'c' * 40}), \
                 contextlib.redirect_stdout(output):
                code = m.main()
        finally:
            os.umask(old_mask)
        return code, output.getvalue(), json.loads((self.root / 'state/owner_engine_download/123.json').read_bytes())

    def test_partial_failure_never_emits_complete(self):
        rows = [self.row, dict(self.row, name='second')]
        def effect(row, *args):
            if row['name'] == 'second':
                raise m.Hold('HOLD_ENGINE_GIT_FETCH')
            return {'name': row['name'], 'state': 'DOWNLOADED_AND_SHA_VERIFIED'}
        code, output, receipt = self.run_main(effect, rows)
        self.assertEqual(code, 2)
        self.assertNotIn('NOX_MAINT_REPAIR_COMPLETE=true', output)
        self.assertEqual(receipt['state'], 'HOLD_PARTIAL_DOWNLOAD')
        self.assertEqual(len(receipt['results']), 2)

    def test_stop_at_completion_prevents_success_receipt(self):
        def effect(row, *args):
            (self.root / 'STOP').touch()
            return {'name': row['name'], 'state': 'DOWNLOADED_AND_SHA_VERIFIED'}
        code, output, receipt = self.run_main(effect)
        self.assertEqual(code, 2)
        self.assertTrue(receipt['stop_observed_at_completion'])
        self.assertNotIn('NOX_MAINT_REPAIR_COMPLETE=true', output)

    def test_all_verified_results_emit_only_staged_not_installed(self):
        code, output, receipt = self.run_main(lambda row, *args: {'name': row['name'], 'state': 'REUSED_AND_SHA_VERIFIED'})
        self.assertEqual(code, 0)
        self.assertEqual(receipt['state'], 'SOURCES_STAGED_NOT_INSTALLED')
        self.assertFalse(receipt['installed'] or receipt['built'] or receipt['services_changed'])
        self.assertEqual(output.count('NOX_MAINT_REPAIR_COMPLETE=true'), 1)


if __name__ == '__main__':
    unittest.main()
