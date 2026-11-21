"""Hermetic regression for SHA-bound offline native-refill request reconstruction."""
from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import owner_refill_request_refresh as refresh

ROOT = Path(__file__).parent
PREVIOUS = (ROOT / 'mission_pack_v1/package/relay'
    / 'ae6181de5b6970ab4b572aa0c5a2e9bc24632668dd31e6a15327de5f8bf507d4.json')


def fixture():
    previous, _ = refresh.read_document(PREVIOUS)
    previous = copy.deepcopy(previous)
    previous['missions'] = []
    sha = refresh.digest(previous)
    state = {
        '0B04': {'status': 'blocked'},
        '3A01.relay.legacy_task.0123456789abcdef': {'status': 'pending'},
    }
    pins = {}
    capacity = {'slots_available': 1, 'callback_sha256': 'a' * 64,
                'now': 1, 'manifest_sha256': sha}
    return previous, sha, state, pins, capacity


class ExactRefillRefreshTests(unittest.TestCase):
    def test_reconstructed_request_is_exact_and_not_native_write(self):
        previous, sha, state, pins, capacity = fixture()
        request = refresh.generate(previous, sha, state, pins, capacity)
        self.assertEqual(request['previous_manifest_sha256'], sha)
        self.assertFalse(request['original_task_accepted'])
        self.assertEqual(request['original_task_states'], [
            {'task_id': '0B04', 'status': 'blocked'},
            {'task_id': '3A01.relay.legacy_task.0123456789abcdef', 'status': 'pending'}])
        self.assertEqual(request['original_task_states_sha256'],
                         refresh.digest(request['original_task_states']))
        self.assertEqual(request['request_id'], refresh.digest({
            'manifest_sha256': sha, 'source_pins': pins,
            'outcomes': [], 'original_task_states': request['original_task_states']}))
        self.assertNotIn('native_write_performed', request)
        self.assertNotIn('original_task_acceptance_added', request)

    def test_snapshot_change_changes_request_id_without_replaying(self):
        previous, sha, state, pins, capacity = fixture()
        before = refresh.generate(previous, sha, state, pins, capacity)
        state = copy.deepcopy(state)
        state['0B04']['status'] = 'done'
        after = refresh.generate(previous, sha, state, pins, capacity)
        self.assertNotEqual(before['request_id'], after['request_id'])
        self.assertEqual(after['original_task_states'][0]['status'], 'done')

    def test_manifest_and_capacity_drift_hold(self):
        previous, sha, state, pins, capacity = fixture()
        with self.assertRaisesRegex(ValueError, 'REFRESH_MANIFEST_SHA'):
            refresh.generate(previous, 'b' * 64, state, pins, capacity)
        capacity = copy.deepcopy(capacity)
        capacity['manifest_sha256'] = 'b' * 64
        with self.assertRaisesRegex(ValueError, 'REFRESH_CAPACITY_MANIFEST_SHA'):
            refresh.generate(previous, sha, state, pins, capacity)

    def test_unexhausted_work_does_not_emit_refill_request(self):
        previous, sha, state, pins, capacity = fixture()
        with patch.object(refresh, 'select_next',
                          return_value={'state': 'REVIEWED_BATCH_READY', 'refill_request': None}):
            with self.assertRaisesRegex(ValueError, 'REFRESH_NOT_EXHAUSTED'):
                refresh.generate(previous, sha, state, pins, capacity)

    def test_invalid_selector_request_is_not_promoted(self):
        previous, sha, state, pins, capacity = fixture()
        valid = refresh.generate(previous, sha, state, pins, capacity)
        forged = copy.deepcopy(valid)
        forged['original_task_states'] = []
        with patch.object(refresh, 'select_next',
                          return_value={'state': 'REFILL_REQUIRED', 'refill_request': forged}):
            with self.assertRaisesRegex(ValueError, 'ORIGINAL_TASK_STATE_SNAPSHOT_SHA'):
                refresh.generate(previous, sha, state, pins, capacity)

    def test_cli_pins_every_input_and_prints_only_request(self):
        previous, sha, state, pins, capacity = fixture()
        with tempfile.TemporaryDirectory() as folder:
            args = []
            for name, data in (('manifest', previous), ('state-snapshot', state),
                               ('source-pins', pins), ('capacity', capacity)):
                path = Path(folder) / (name + '.json')
                raw = refresh.canonical(data)
                path.write_bytes(raw)
                args.extend(['--' + name, str(path),
                             '--' + name + '-sha256', hashlib.sha256(raw).hexdigest()])
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(refresh.main(args), 0)
            document = json.loads(output.getvalue())
            self.assertEqual(document['original_task_states_sha256'],
                             refresh.digest(document['original_task_states']))
            # A stale owner pin cannot be refreshed silently.
            wrong = args[:]
            wrong[-1] = 'a' * 64
            with self.assertRaisesRegex(ValueError, 'REFRESH_INPUT_CHANGED'):
                refresh.main(wrong)

    def test_symlink_source_is_rejected(self):
        previous, _, _, _, _ = fixture()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'state.json'
            path.write_bytes(refresh.canonical(previous))
            link = Path(folder) / 'linked.json'
            link.symlink_to(path)
            with self.assertRaises((ValueError, OSError)):
                refresh.load_pinned(link, hashlib.sha256(path.read_bytes()).hexdigest())


if __name__ == '__main__':
    unittest.main()
