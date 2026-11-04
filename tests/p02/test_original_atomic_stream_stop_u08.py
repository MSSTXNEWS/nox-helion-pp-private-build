"""Original native P02 chat/STOP/atomic exchange regression, source-only.

The client/store below are deliberately test doubles. These tests NEVER claim
an installed model, actual inference, Windows IPC, or independent E07 PASS.
"""
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'proposals/NOX-PACK01-50/native_bridge.py'
SPEC = importlib.util.spec_from_file_location('nox_original_native_u08', SOURCE)
native = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = native
SPEC.loader.exec_module(native)


class TestLocalModelClient:
    def __init__(self, chunks=None):
        self.chunks = chunks if chunks is not None else [
            {'delta': 'local ', 'done': False}, {'delta': 'answer', 'done': True}]
        self.stop_calls = 0
        self.requested = []

    def models(self):
        return ['test-only:local']

    def stream(self, model, messages):
        self.requested.append((model, messages))
        for chunk in self.chunks:
            yield chunk

    def stop(self):
        self.stop_calls += 1


class TestAtomicStore:
    def __init__(self):
        self.exchanges = []
        self.messages = []
        self.before_commit = None

    def history(self, tenant, principal, chat_id, limit=100):
        return []

    def add_message(self, *args, **kwargs):
        self.messages.append((args, kwargs))
        raise AssertionError('Original P02 must not split an atomic exchange')

    def add_exchange(self, tenant, principal, chat_id, prompt, answer, *, authorize):
        authorize()
        if self.before_commit is not None:
            self.before_commit()
        authorize()
        self.exchanges.append((tenant, principal, chat_id, prompt, answer))
        return 'test-only-exchange'

    def store_file(self, *args, **kwargs):
        raise AssertionError('Unexpected attachment write')


class NativeAtomicStreamStopU08(unittest.TestCase):
    def setUp(self):
        self.client = TestLocalModelClient()
        self.store = TestAtomicStore()
        self.events = []
        self.session = native.NativeSession('local', 'owner', 'default',
            allowed=frozenset({'helion.chat', 'chat.stop'}))
        self.adapter = native.ExistingP02Adapter(
            self.client, self.store, event_sink=self.events.append)

    def invoke(self, model='test-only:local'):
        return self.adapter.chat(self.session, {'text': 'hello', 'model': model})

    def test_real_native_adapter_uses_one_atomic_exchange(self):
        output = self.invoke()
        self.assertEqual(output, {'answer': 'local answer', 'done': True})
        self.assertEqual([x['delta'] for x in self.events], ['local ', 'answer'])
        self.assertEqual(len(self.store.exchanges), 1)
        self.assertEqual(self.store.exchanges[0][-2:], ('hello', 'local answer'))
        self.assertEqual(self.store.messages, [])
        self.assertEqual(self.client.stop_calls, 0)

    def test_stop_during_delta_prevents_any_atomic_commit(self):
        def sink(event):
            self.events.append(event)
            self.adapter.stop(self.session, {})
        self.adapter.event_sink = sink
        with self.assertRaises(native.HostDenied):
            self.invoke()
        self.assertEqual(self.store.exchanges, [])
        self.assertEqual(self.client.stop_calls, 1)

    def test_stop_during_commit_authorization_prevents_write(self):
        self.store.before_commit = lambda: self.adapter.stop(self.session, {})
        with self.assertRaises(native.HostDenied):
            self.invoke()
        self.assertEqual(self.store.exchanges, [])
        self.assertEqual(self.client.stop_calls, 1)

    def test_unknown_model_fails_without_stream_or_write(self):
        with self.assertRaises(native.HostHold):
            self.invoke('not-installed')
        self.assertEqual(self.client.requested, [])
        self.assertEqual(self.store.exchanges, [])

    def test_malformed_delta_fails_without_exchange(self):
        self.client.chunks = [{'delta': 22, 'done': True}]
        with self.assertRaises(native.HostHold):
            self.invoke()
        self.assertEqual(self.store.exchanges, [])

    def test_missing_terminal_done_fails_without_exchange(self):
        self.client.chunks = [{'delta': 'partial', 'done': False}]
        with self.assertRaises(native.HostHold):
            self.invoke()
        self.assertEqual(self.store.exchanges, [])

    def test_answer_limit_stops_provider_without_exchange(self):
        self.client.chunks = [{'delta': 'x' * (native.MAX_ANSWER + 1), 'done': True}]
        with self.assertRaises(native.HostHold):
            self.invoke()
        self.assertEqual(self.store.exchanges, [])
        self.assertEqual(self.client.stop_calls, 1)

    def test_failed_event_sink_never_commits(self):
        def sink(_event):
            raise RuntimeError('test-only transport disconnected')
        self.adapter.event_sink = sink
        with self.assertRaisesRegex(RuntimeError, 'transport disconnected'):
            self.invoke()
        self.assertEqual(self.store.exchanges, [])


if __name__ == '__main__':
    unittest.main()
