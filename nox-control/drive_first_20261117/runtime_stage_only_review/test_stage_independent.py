"""Independent fixture-only review of the frozen staging entry."""
import ast
import base64
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1] / 'runtime_stage_only'
ENTRY = ROOT / 'owner_runtime_source_stage_20261117.py'
ENTRY_SHA = '945451e072fda3d56cd5835f775c064907a3f6584ae385455988c9e0583a1aa8'
BUNDLE_SHA = 'ee142b97c81327edf0130e2aba46c431e1d1334396581b11922507310553aa2b'
raw = ENTRY.read_bytes()
if hashlib.sha256(raw).hexdigest() != ENTRY_SHA:
    raise RuntimeError('REVIEW_ENTRY_DRIFT')
spec = importlib.util.spec_from_file_location('reviewed_stage', ENTRY)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

def fixture():
    files = {path: "raise AssertionError('MUST_NOT_RUN_RUNTIME')\n" for path in m.EXPECTED_PATHS}
    return {'files': files, 'sha256': {path: hashlib.sha256(text.encode()).hexdigest() for path, text in files.items()}}

class IndependentStageReview(unittest.TestCase):
    def test_exact_payload_and_template_identity_without_importing_payload(self):
        bundle = m.unpack_bundle()
        self.assertEqual(m.BUNDLE_SHA, BUNDLE_SHA)
        self.assertEqual(len(bundle['files']), 12)
        manifest = json.loads((ROOT / 'STAGING_MANIFEST.json').read_text())
        self.assertEqual(sum(len(v.encode()) for v in bundle['files'].values()), 98385)
        self.assertEqual({row['path']: row['sha256'] for row in manifest['file_pins']}, bundle['sha256'])
        rebuilt = (ROOT / 'entry.template.py').read_text().replace('BUNDLE_SHA256_VALUE', m.BUNDLE_SHA).replace('BUNDLE_JSON_BASE64_VALUE', m.PACKED_BUNDLE_B64)
        self.assertEqual(rebuilt.encode(), raw)
        forbidden = {'exec', 'eval', '__import__', 'system', 'popen', 'Popen', 'urlopen', 'request'}
        calls = {n.func.id if isinstance(n.func, ast.Name) else n.func.attr if isinstance(n.func, ast.Attribute) else ''
                 for n in ast.walk(ast.parse(raw)) if isinstance(n, ast.Call)}
        self.assertFalse(forbidden.intersection(calls))

    def test_owner_arrival_stops_after_owned_partial_stage_without_replay(self):
        bundle = fixture(); sha = m.digest(m.canonical(bundle))
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); priority = root / 'state/priority'; priority.mkdir(parents=True)
            flag = priority / 'CHAT_ACTIVE'; flag.write_text('0\n')
            destination = root / 'extensions/staged'
            calls = []
            def boundary():
                calls.append(1)
                if len(calls) == 2:
                    flag.write_text('1\n')
                m.owner_idle()
            with mock.patch.object(m, 'ROOT', root):
                with self.assertRaisesRegex(m.Hold, 'HOLD_OWNER_CHAT_ACTIVE_OR_UNKNOWN'):
                    m.stage(bundle, sha, destination=destination, before_file=boundary)
            staged = list(destination.rglob('*.py'))
            self.assertEqual(len(staged), 1)
            self.assertEqual(staged[0].read_text(), "raise AssertionError('MUST_NOT_RUN_RUNTIME')\n")
            self.assertEqual(flag.read_text(), '1\n')

    def test_parent_symlink_and_nonregular_collision_never_write_or_block(self):
        bundle = fixture(); sha = m.digest(m.canonical(bundle)); first = sorted(bundle['files'])[0]
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); outside = root / 'outside'; outside.mkdir()
            dest = root / 'destination'; dest.mkdir(); (dest / 'runtime').symlink_to(outside, target_is_directory=True)
            with self.assertRaises((OSError, m.Hold)):
                m.stage(bundle, sha, destination=dest)
            self.assertEqual(list(outside.iterdir()), [])
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td); target = dest / first; target.parent.mkdir(parents=True)
            os.mkfifo(target, 0o600)
            with self.assertRaisesRegex(m.Hold, 'HOLD_STAGE_COLLISION'):
                m.stage(bundle, sha, destination=dest)
            self.assertTrue(target.exists())

if __name__ == '__main__':
    unittest.main()
