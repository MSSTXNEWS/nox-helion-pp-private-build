#!/usr/bin/env python3
"""Backup consistency and deletion-gate tests; no network, credentials or GPU."""
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

SPEC = importlib.util.spec_from_file_location('nox_pc_export', Path(__file__).with_name('nox_pc_export.py'))
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)
COLD_SPEC = importlib.util.spec_from_file_location('nox_cold_drive', Path(__file__).with_name('nox_cold_drive.py'))
cold = importlib.util.module_from_spec(COLD_SPEC)
COLD_SPEC.loader.exec_module(cold)


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def put(self, name, content=b'model'):
        p = self.root/name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
        return p

    def test_wal_sqlite_snapshot_contains_committed_rows(self):
        source = self.root/'S03.db'
        with sqlite3.connect(source) as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE chat (body TEXT)')
            db.execute('INSERT INTO chat VALUES (?)', ('latest committed message',))
            db.commit()
            target = self.root/'snapshot.db'
            m.snapshot_sqlite(source, target)
            with sqlite3.connect(target) as copied:
                self.assertEqual(copied.execute('SELECT body FROM chat').fetchone()[0], 'latest committed message')
                self.assertEqual(copied.execute('PRAGMA quick_check').fetchone()[0], 'ok')

    def test_plan_preserves_training_state_but_excludes_credentials(self):
        self.put('training/checkpoint-10/optimizer.pt')
        self.put('training/checkpoint-10/rng_state.pth')
        self.put('training/checkpoint-10/scheduler.pt')
        self.put('training/checkpoint-10/scaler.pt')
        self.put('models/active.gguf')
        self.put('models/inactive.gguf')
        (self.root/'models/current.gguf').symlink_to('active.gguf')
        self.put('.env', b'VAST_API_KEY=abcdefghijklmnopqrstuvwxyz')
        self.put('state/cold_drive.conf', b'[drive]\ntoken = abcdefghijklmnopqrstuvwxyz')
        self.put('state/cold_drive.conf.new', b'[drive]\ntoken = abcdefghijklmnopqrstuvwxyz')
        self.put('state/cold_drive.conf.bak', b'[drive]\ntoken = abcdefghijklmnopqrstuvwxyz')
        self.put('state/rclone.conf.new', b'[drive]\ntoken = abcdefghijklmnopqrstuvwxyz')
        self.put('config.json', b'{"access_token":"abcdefghijklmnopqrstuvwxyz123456"}')
        self.put('journal.jsonl', b'{"event":"training started"}\n')
        with mock.patch.object(m, 'active_paths', return_value=[str(self.root/'models/active.gguf'),str(self.root/'training')]):
            plan = m.build_plan(self.root, 'test-session')
        rows = {row['restore_rel']:row for row in plan['files']}
        for name in ('optimizer.pt','rng_state.pth','scheduler.pt','scaler.pt'):
            self.assertIn('training/checkpoint-10/'+name, rows)
            self.assertFalse(rows['training/checkpoint-10/'+name]['evict_candidate'])
        self.assertNotIn('.env', rows)
        self.assertNotIn('state/cold_drive.conf', rows)
        self.assertNotIn('state/cold_drive.conf.new', rows)
        self.assertNotIn('state/cold_drive.conf.bak', rows)
        self.assertNotIn('state/rclone.conf.new', rows)
        self.assertNotIn('config.json', rows)
        self.assertEqual(rows['journal.jsonl']['kind'], 'file_snapshot')
        self.assertTrue(rows['models/inactive.gguf']['evict_candidate'])
        self.assertFalse(rows['models/active.gguf']['evict_candidate'])
        self.assertEqual(plan['aliases'][0]['target'], 'models/active.gguf')
        self.assertEqual(plan['total_bytes'], sum(x['bytes'] for x in rows.values()))

    def test_resume_rebuilds_selection_after_interrupted_publication(self):
        self.put('models/model.gguf')
        self.put('journal.jsonl', b'{"step":10}\n')
        plan = m.build_plan(self.root, 'interrupted')
        stage = self.root/'state/pc_exports/interrupted'
        digest = m.sha256(stage/'manifest.json')
        (stage/'selected.txt').unlink()
        # A resume must reuse the published snapshot, not rehash live files.
        with mock.patch.object(m, 'sha256', side_effect=AssertionError('unexpected rehash')):
            resumed = m.build_plan(self.root, 'interrupted')
        self.assertEqual(resumed, plan)
        self.assertEqual(m.sha256(stage/'manifest.json'), digest)
        self.assertEqual((stage/'selected.txt').read_text().splitlines(),
                         [row['source_rel'] for row in plan['files']])
        self.assertEqual((stage/'selected.txt').stat().st_mode & 0o777, 0o600)

    def test_resume_rejects_invalid_manifest_before_creating_selection(self):
        self.put('models/model.gguf')
        plan = m.build_plan(self.root, 'invalid')
        stage = self.root/'state/pc_exports/invalid'
        (stage/'selected.txt').unlink()
        for mutation in ('root', 'traversal', 'mapping', 'identity', 'total', 'duplicate'):
            bad = json.loads(json.dumps(plan))
            if mutation == 'root': bad['root'] = '/another/root'
            if mutation == 'traversal': bad['files'][0]['source_rel'] = '../outside'
            if mutation == 'mapping': bad['files'][0]['restore_rel'] = 'models/other.gguf'
            if mutation == 'identity': bad['files'][0]['identity'][2] += 1
            if mutation == 'total': bad['total_bytes'] += 1
            if mutation == 'duplicate': bad['files'].append(dict(bad['files'][0]))
            (stage/'manifest.json').write_text(json.dumps(bad))
            with self.subTest(mutation=mutation), self.assertRaises(RuntimeError):
                m.build_plan(self.root, 'invalid')
            self.assertFalse((stage/'selected.txt').exists())

    def test_refuse_path_escape_and_windows_collision(self):
        for path in ('../elsewhere','/root/file','a/../../b','a\\b','a\nfile','C:/secret','a/CON.txt'):
            with self.subTest(path=path), self.assertRaises(RuntimeError):
                m.safe_relative(path)
        self.put('Data.gguf')
        self.put('data.gguf')
        with self.assertRaisesRegex(RuntimeError, 'CASE_COLLISION'):
            m.build_plan(self.root, 'test-collision')

    def test_no_symlink_traversal(self):
        self.put('real/file.gguf')
        (self.root/'linked').symlink_to(self.root/'real', target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, 'SYMLINK'):
            m.plain_source(self.root, 'linked/file.gguf')

    def test_changed_snapshot_source_fails(self):
        source = self.put('status.json', b'{}')
        with mock.patch.object(m, 'identity', side_effect=[[1,2,3,4,5],[1,2,4,5,6]]):
            with self.assertRaisesRegex(RuntimeError, 'MUTABLE_FILE_CHANGED'):
                m.copy_snapshot(source, self.root/'snapshot.json')
        self.assertFalse((self.root/'snapshot.json').exists())

    def test_receipt_requires_both_full_shas_and_exact_remote(self):
        digest = '1'*64
        manifest = {'session':'test-session','files':[{'source_rel':'models/model.gguf','bytes':5,'sha256':digest}]}
        receipt = {'schema_version':1,'session':'test-session','manifest_sha256':'2'*64,'all_verified':True,
                   'drive_remote':'nox_drive:test-session','files':[{'source_rel':'models/model.gguf','bytes':5,
                   'local_sha256':digest,'drive_sha256':digest}]}
        self.assertEqual(m.validate_receipt(manifest, receipt, '2'*64), 'nox_drive:test-session')
        for mutation in ('drive_sha','local_sha','remote','manifest','boolean','size'):
            bad = json.loads(json.dumps(receipt))
            if mutation=='drive_sha': bad['files'][0]['drive_sha256']='3'*64
            if mutation=='local_sha': bad['files'][0]['local_sha256']='3'*64
            if mutation=='remote': bad['drive_remote']='other:somewhere'
            if mutation=='manifest': bad['manifest_sha256']='3'*64
            if mutation=='boolean': bad['all_verified']='true'
            if mutation=='size': bad['files'][0]['bytes']=6
            with self.subTest(mutation=mutation), self.assertRaises(RuntimeError):
                m.validate_receipt(manifest, bad, '2'*64)

    def test_evict_candidates_only_inactive_gguf(self):
        for name in ('models/cold.gguf','judge/cold.gguf','models/weight.safetensors',
                     'checkpoints/old.gguf','training/checkpoint-10/model.gguf','S03/memory.gguf'):
            p = self.put(name)
            expected = name in ('models/cold.gguf','judge/cold.gguf')
            self.assertEqual(m.evict_candidate(self.root, p, []), expected)
        active = self.root/'models/cold.gguf'
        self.assertFalse(m.evict_candidate(self.root, active, [str(active)]))
        self.assertFalse(m.evict_candidate(self.root, active, [str(active.parent)]))

    def prepared_finalize(self):
        source = self.put('models/cold.gguf')
        with mock.patch.object(m, 'active_paths', return_value=[]):
            manifest = m.build_plan(self.root, 'finalize')
        stage = self.root/'state/pc_exports/finalize'
        receipt = {'schema_version':1, 'session':'finalize', 'all_verified':True,
                   'manifest_sha256':m.sha256(stage/'manifest.json'),
                   'drive_remote':'nox_drive:finalize', 'files':[
                       {'source_rel':row['source_rel'], 'bytes':row['bytes'],
                        'local_sha256':row['sha256'], 'drive_sha256':row['sha256']}
                       for row in manifest['files']]}
        (stage/'verified.json').write_text(json.dumps(receipt))
        config = self.put('state/cold_drive.conf', b'[nox_drive]\ntype = drive\n')
        config.chmod(0o600)
        return source, config

    def test_finalize_refuses_nonprivate_config_before_remote_access(self):
        source, config = self.prepared_finalize()
        config.chmod(0o644)
        with mock.patch.dict(sys.modules, {'nox_cold_drive':cold}), \
                mock.patch.object(cold, 'stream_sha256') as stream:
            with self.assertRaisesRegex(RuntimeError, '0600_REQUIRED'):
                m.finalize(self.root, 'finalize', evict=True)
            stream.assert_not_called()
        self.assertTrue(source.is_file())

    def test_finalize_preserves_source_when_independent_drive_readback_differs(self):
        source, config = self.prepared_finalize()
        with mock.patch.dict(sys.modules, {'nox_cold_drive':cold}), \
                mock.patch.dict(m.os.environ, {}, clear=False), \
                mock.patch.object(m, 'active_paths', return_value=[]), \
                mock.patch.object(cold, 'stream_sha256', return_value='0'*64) as stream, \
                mock.patch.object(cold, 'evict_verified') as evict:
            result = m.finalize(self.root, 'finalize', evict=True)
            stream.assert_called_once_with('nox_drive:finalize/models/cold.gguf', 5, 24*3600)
            evict.assert_not_called()
        self.assertEqual(source.read_bytes(), b'model')
        self.assertEqual(result['evicted'], [])
        self.assertEqual(result['held'], [{'path':'models/cold.gguf', 'reason':'REMOTE_SHA_MISMATCH'}])

    def test_finalize_refuses_symlinked_receipt(self):
        source, config = self.prepared_finalize()
        receipt = self.root/'state/pc_exports/finalize/verified.json'
        saved = receipt.with_name('saved.json')
        receipt.rename(saved)
        receipt.symlink_to(saved.name)
        with self.assertRaisesRegex(RuntimeError, 'SYMLINK_SOURCE'):
            m.finalize(self.root, 'finalize', evict=True)
        self.assertTrue(source.is_file())

    def test_disk_reserve_blocks_snapshot_before_copy(self):
        self.put('journal.json', b'{}')
        usage = type('Usage', (), {'free':m.GIB})()
        with mock.patch.object(m.shutil, 'disk_usage', return_value=usage):
            with self.assertRaisesRegex(RuntimeError, 'RESERVE'):
                m.build_plan(self.root, 'low-disk')

    def test_archives_with_credentials_are_held(self):
        clean = self.root/'clean.zip'
        with zipfile.ZipFile(clean, 'w') as z:
            z.writestr('models/old.gguf', b'model')
            z.writestr('state/summary.json', b'{"step":10}')
        self.assertTrue(m.archive_safe(clean))
        private = self.root/'private.zip'
        with zipfile.ZipFile(private, 'w') as z:
            z.writestr('project/.env', b'password=abcdefghijklmnopqrstuvwxyz')
        self.assertFalse(m.archive_safe(private))
        self.assertFalse(m.archive_safe(self.put('uninspected.tar.zst')))

if __name__=='__main__':
    unittest.main()
