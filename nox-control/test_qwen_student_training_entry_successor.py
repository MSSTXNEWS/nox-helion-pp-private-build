"""Temp-only successor retention tests; no CUDA, model, network or native main."""
import ast
import copy
from contextlib import ExitStack, contextmanager
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
STUDENT = HERE / 'qwen_student_training_entry_successor.py'
PREVIOUS = HERE / 'qwen_student_training_entry_transport_budget.py'
SHARED = HERE / 'owner_qwen_execution_successor.py'
STUDENT_SHA = '0982a4ab5e28d1217d5f4ee02d13a8a349cd53c27824dcbb3b5d93ed60042d03'
PREVIOUS_SHA = 'ce7dcbef53c61c63ebab96553ef4c48d9f138a3c426008fa329eb5fd66ee041c'
SHARED_SHA = 'd3b2905c568d088cde2d8267f02f9e913f9fe1d3e46f590992c3a7fcb138ae14'
OLD_SHARED_SHA = '0dbb06d3384b3436165056ccf4e35bff937fda4f85d96ab2a97ab16a6619998e'
DEPENDENCIES = {
    'owner_qwen_training_contract': (Path('/tmp/nox_qwen_owner_qwen_training_contract.py'),
        '7108da4d4949887414f33f5693fe901e3eb5fc63eb97f2b98d1371fed912f50a'),
    'owner_qwen_memfd': (Path('/tmp/nox_qwen_owner_qwen_memfd.py'),
        '938335009efe691a9cef7b41daa7c55f3c8d3d8618a10a5eb5db125fd45afa82'),
}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def load(path, name):
    value = types.ModuleType(name); value.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec'), value.__dict__)
    return value


with patch.dict(sys.modules):
    for name, (path, pin) in DEPENDENCIES.items():
        if digest(path.read_bytes()) != pin:
            raise RuntimeError('Pinned fixture dependency changed')
        sys.modules[name] = load(path, name)
    S = load(STUDENT, '_successor_student_fixture')
V = load(SHARED, '_successor_shared_fixture')


@contextmanager
def fixture():
    with tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
        root = Path(temp); output = root / 'lora/qwen35_9b/fixture'; output.mkdir(parents=True)
        scripts = root / 'scripts'; scripts.mkdir()
        (scripts / S.EXECUTION_MODULE).write_bytes(SHARED.read_bytes())
        lineage = {'fixture': 'same-scientific-origin'}
        paths = {}; rows = []
        # Neither retained25 is latest/previous/best; accepted6 is independent
        # of mutable owner_acceptance, which deliberately points at35 below.
        for label, number, generation, loss in (
            ('obsolete5', 5, 1, 1.8), ('accepted6', 6, 2, 1.7), ('best10', 10, 3, .9),
            ('original25', 25, 4, 1.4), ('predecessor25', 25, 5, 1.3),
            ('previous30', 30, 6, 1.2), ('latest35', 35, 7, 1.1)):
            name = f'checkpoint-u{number:08d}-a{number:08d}-g{generation:020d}'
            path = output / name; path.mkdir(); payload = path / 'owned.bin'; payload.write_bytes(label.encode())
            record = {'schema': 'NOX_QWEN35_9B_CHECKPOINT_V1', 'directory': name,
                      'lineage_sha256': S.canonical_sha(lineage), 'files_sha256': {'owned.bin': S.sha256_file(payload)}}
            S.atomic_json(path / 'checkpoint_manifest.json', record)
            row = {'directory': name, 'manifest_sha256': S.sha256_file(path / 'checkpoint_manifest.json'),
                'successful_total': number, 'attempted_total': number, 'evaluated_at_current_step': True,
                'holdout_loss': loss, 'retained': True}
            paths[label] = path; rows.append(row)
        ledger_path = output / 'owner_checkpoints.json'
        S.atomic_json(ledger_path, {'schema': 'NOX_QWEN_OWNED_CHECKPOINTS_V1',
            'lineage_sha256': S.canonical_sha(lineage), 'checkpoints': rows})
        S.atomic_json(output / 'latest_checkpoint.json', {k: rows[-1][k] for k in ('directory', 'manifest_sha256')})
        current_certificate = {'checkpoint': str(paths['latest35']), 'checkpoint_manifest_sha256': rows[-1]['manifest_sha256']}
        origin_certificate = {'checkpoint': str(paths['accepted6']), 'checkpoint_manifest_sha256': rows[1]['manifest_sha256']}
        S.atomic_json(output / 'owner_acceptance.json', current_certificate)
        anchors = []
        for row, template in ((rows[3], V.ORIGINAL_ANCHOR), (rows[4], V.ANCHOR)):
            anchors.append(dict(template, directory=row['directory'], manifest_sha256=row['manifest_sha256']))
        # Only fixture constants change; the real pinned validator runs and
        # rejects a removed/changed retention list before any unlink.
        stack.enter_context(patch.object(V, 'ORIGINAL_ANCHOR', anchors[0]))
        stack.enter_context(patch.object(V, 'ANCHOR', anchors[1]))
        descriptor = {'schema': V.DESCRIPTOR_SCHEMA, 'request': '90001', 'source_sha': 'a' * 40, 'created_at': 100.0,
            'origin': copy.deepcopy(V.ORIGIN), 'runtime_sources': {V.ENTRY: STUDENT_SHA, V.SELF: SHARED_SHA},
            'consumer_sources': {name: 'b' * 64 for name in V.CONSUMERS}, 'activation_issuer_sha256': 'c' * 64,
            'activation_watcher_sha256': 'd' * 64, 'predecessor': copy.deepcopy(V.PREDECESSOR),
            'anchor': copy.deepcopy(anchors[1]), 'retained_anchors': copy.deepcopy(anchors), 'scheduler': dict(V.SCHEDULER),
            'bootstrap': {'expires_at': 3700.0, 'hold_sha256': V.PREDECESSOR_HOLD_SHA, 'pause_sha256': None}}
        ctx = {'execution': {'descriptor': descriptor}, 'certificate': origin_certificate}
        stack.enter_context(patch.object(S, 'ROOT', root))
        stack.enter_context(patch.object(S, '__file__', str(scripts / V.ENTRY)))
        stack.enter_context(patch.object(S, 'EXECUTION_CONTEXT', ctx))
        stack.enter_context(patch.object(S, 'EXECUTION_VERIFIER', V))
        def verify_certificate(value, *, lineage: object, minimum_updates):
            if value not in (origin_certificate, current_certificate) or minimum_updates != 6:
                raise S.Hold('HOLD_FIXTURE_BAD_CERTIFICATE')
        stack.enter_context(patch.object(S, 'verify_proof', side_effect=verify_certificate))
        yield types.SimpleNamespace(root=root, output=output, lineage=lineage, paths=paths, rows=rows, ctx=ctx,
            anchors=anchors, ledger_path=ledger_path, scripts=scripts)


class RetentionTests(unittest.TestCase):
    def test_accepted6_both25_best_previous_and_latest_survive_latest35(self):
        with fixture() as f:
            immutable = {name: (path / 'checkpoint_manifest.json').read_bytes() for name, path in f.paths.items()}
            result = S.prune_checkpoints(f.output, f.lineage)
            self.assertFalse(f.paths['obsolete5'].exists())
            expected = set(f.paths) - {'obsolete5'}
            for name in expected:
                self.assertTrue(f.paths[name].is_dir(), name)
                self.assertEqual((f.paths[name] / 'checkpoint_manifest.json').read_bytes(), immutable[name])
            self.assertEqual(set(result['retained']), {f.paths[name].name for name in expected})
            self.assertEqual(result['deleted_verified_own_checkpoints'], 1)
            ledger = S.read_json(f.ledger_path)
            self.assertEqual([row['directory'] for row in ledger['checkpoints'] if row['retained'] is False],
                             [f.paths['obsolete5'].name])
            self.assertEqual(S.read_json(f.output / 'latest_checkpoint.json')['directory'], f.paths['latest35'].name)

    def test_missing_either_anchor_in_ledger_prevents_every_deletion(self):
        for label in ('original25', 'predecessor25'):
            with self.subTest(label=label), fixture() as f:
                ledger = S.read_json(f.ledger_path)
                ledger['checkpoints'] = [row for row in ledger['checkpoints'] if row['directory'] != f.paths[label].name]
                S.atomic_json(f.ledger_path, ledger); before = f.ledger_path.read_bytes()
                with self.assertRaisesRegex(S.Hold, 'MIGRATION_ANCHOR'):
                    S.prune_checkpoints(f.output, f.lineage)
                self.assertTrue(all(path.is_dir() for path in f.paths.values()))
                self.assertEqual(f.ledger_path.read_bytes(), before)

    def test_changed_either_anchor_manifest_prevents_every_deletion(self):
        for label in ('original25', 'predecessor25'):
            with self.subTest(label=label), fixture() as f:
                (f.paths[label] / 'checkpoint_manifest.json').write_bytes(b'foreign metadata')
                before = f.ledger_path.read_bytes()
                with self.assertRaisesRegex(S.Hold, 'MIGRATION_ANCHOR'):
                    S.prune_checkpoints(f.output, f.lineage)
                self.assertTrue(all(path.is_dir() for path in f.paths.values()))
                self.assertEqual(f.ledger_path.read_bytes(), before)

    def test_missing_either_anchor_file_prevents_every_deletion(self):
        for label in ('original25', 'predecessor25'):
            with self.subTest(label=label), fixture() as f:
                (f.paths[label] / 'checkpoint_manifest.json').unlink()
                before = f.ledger_path.read_bytes()
                with self.assertRaises((S.Hold, FileNotFoundError)):
                    S.prune_checkpoints(f.output, f.lineage)
                self.assertTrue(all(path.is_dir() for path in f.paths.values()))
                self.assertEqual((f.paths['obsolete5'] / 'owned.bin').read_bytes(), b'obsolete5')
                self.assertEqual(f.ledger_path.read_bytes(), before)

    def test_unvalidated_retained_list_or_changed_shared_source_prevents_deletion(self):
        for field in ('retention', 'shared-source'):
            with self.subTest(field=field), fixture() as f:
                if field == 'retention':
                    f.ctx['execution']['descriptor']['retained_anchors'].pop(0)
                else:
                    (f.scripts / S.EXECUTION_MODULE).write_bytes(b'foreign source')
                before = f.ledger_path.read_bytes()
                with self.assertRaises(S.Hold): S.prune_checkpoints(f.output, f.lineage)
                self.assertTrue(all(path.is_dir() for path in f.paths.values()))
                self.assertEqual(f.ledger_path.read_bytes(), before)

    def test_missing_accepted6_fails_even_when_current_acceptance_points_to35(self):
        with fixture() as f:
            ledger = S.read_json(f.ledger_path)
            ledger['checkpoints'] = [row for row in ledger['checkpoints'] if row['directory'] != f.paths['accepted6'].name]
            S.atomic_json(f.ledger_path, ledger); before = f.ledger_path.read_bytes()
            with self.assertRaisesRegex(S.Hold, 'ORIGIN_ACCEPTANCE_MISSING'):
                S.prune_checkpoints(f.output, f.lineage)
            self.assertTrue(all(path.is_dir() for path in f.paths.values()))
            self.assertEqual(f.ledger_path.read_bytes(), before)


class SourceDeltaTests(unittest.TestCase):
    def test_exact_bytes_inverse_is_only_verifier_pin_and_retention_function(self):
        old = PREVIOUS.read_bytes(); new = STUDENT.read_bytes()
        self.assertEqual(digest(old), PREVIOUS_SHA)
        self.assertEqual(digest(new), STUDENT_SHA)
        self.assertEqual(digest(SHARED.read_bytes()), SHARED_SHA)
        old_text, new_text = old.decode(), new.decode()
        old_tree, new_tree = ast.parse(old_text), ast.parse(new_text)
        old_prune = next(n for n in old_tree.body if isinstance(n, ast.FunctionDef) and n.name == 'prune_checkpoints')
        new_prune = next(n for n in new_tree.body if isinstance(n, ast.FunctionDef) and n.name == 'prune_checkpoints')
        restored = new_text.replace(SHARED_SHA, OLD_SHARED_SHA, 1).replace(
            ast.get_source_segment(new_text, new_prune), ast.get_source_segment(old_text, old_prune), 1)
        self.assertEqual(restored.encode(), old)
        self.assertEqual(S.PublicTransportRevision.STAGING_SECONDS, 2400.0)

    def test_optimizer_restore_science_scheduler_and_permission_flow_ast_unchanged(self):
        old_tree, new_tree = [ast.parse(p.read_bytes()) for p in (PREVIOUS, STUDENT)]
        definitions = lambda tree: {n.name: ast.dump(n, include_attributes=False) for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        old, new = definitions(old_tree), definitions(new_tree)
        self.assertEqual(set(old), set(new))
        self.assertEqual([name for name in old if old[name] != new[name]], ['prune_checkpoints'])
        self.assertEqual(S.EXECUTION_MODULE_SHA, SHARED_SHA)
        self.assertEqual(S.EVALUATION_ROWS, 16)


if __name__ == '__main__':
    unittest.main()
