"""E02 R05: deterministic stream-close regressions for ONE Ollama transport.

The retained stream intentionally prevents CPython refcount cleanup from hiding
an absent explicit close().  This is an offline component suite; no microphone,
installed Ollama weights, WebView2 or Windows EXE is claimed.
"""
from __future__ import annotations
import importlib.util
import pathlib
import threading
import unittest

spec = importlib.util.spec_from_file_location(
    'owner_p02_chat_bridge_r05', pathlib.Path(__file__).with_name('p02_chat_bridge.py'))
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class RetainedStream:
    def __init__(self, frames, callback=None):
        self.frames = iter(frames)
        self.callback = callback
        self.closed = False
        self.next_calls = 0
    def __iter__(self): return self
    def __next__(self):
        self.next_calls += 1
        if self.callback: self.callback()
        return next(self.frames)
    def close(self): self.closed = True


class Store:
    def __init__(self): self.rows = []
    def history(self, tenant, principal, chat):
        if (tenant, principal, chat) != ('tenant','user','chat'):
            raise PermissionError('unowned')
        return [{'role':r,'content':c} for r,c in self.rows]
    def add_message(self, tenant, principal, chat, role, content):
        if (tenant, principal, chat) != ('tenant','user','chat'):
            raise PermissionError('unowned')
        self.rows.append((role,content))


class RetainingOllama:
    def __init__(self, frames, callback=None):
        self.frames, self.callback = frames, callback
        self.current = None
        self.global_stop_called = 0
    def models(self): return ['installed:1']
    def stop(self): self.global_stop_called += 1
    def stream(self, model, messages, stop):
        self.current = RetainedStream(self.frames, self.callback)
        return self.current


class StreamLifecycleR05(unittest.TestCase):
    def setUp(self):
        self.stop = threading.Event()
        self.store = Store()
        self.ollama = RetainingOllama([
            {'delta':'hello','done':False}, {'delta':'','done':True}])
        self.chat = bridge.ChatBridge(self.store, self.ollama)
    def send(self):
        return self.chat.send('tenant','user','chat','installed:1','prompt',self.stop)
    def test_successful_completion_explicitly_closes_inner_transport(self):
        self.assertEqual([e['type'] for e in self.send()],
                         ['chat.start','chat.delta','chat.complete'])
        self.assertTrue(self.ollama.current.closed)
        self.assertEqual(self.ollama.global_stop_called,0)
    def test_ui_close_mid_delta_closes_retained_transport_without_global_stop(self):
        outer = self.send()
        self.assertEqual(next(outer)['type'],'chat.start')
        self.assertEqual(next(outer)['type'],'chat.delta')
        current = self.ollama.current
        outer.close()
        self.assertTrue(current.closed)
        self.assertEqual(self.ollama.global_stop_called,0)
        self.assertEqual(self.store.rows,[('user','prompt')])
    def test_stop_after_delta_closes_retained_transport(self):
        outer = self.send()
        next(outer); next(outer)
        self.stop.set()
        self.assertEqual([x['code'] for x in outer if x['type']=='chat.error'],['STOP'])
        self.assertTrue(self.ollama.current.closed)
        self.assertEqual(self.store.rows,[('user','prompt')])
    def test_truncated_protocol_closes_retained_transport(self):
        self.ollama.frames = [{'delta':'partial','done':False}]
        result = list(self.send())
        self.assertEqual(result[-1]['code'],'OLLAMA_ERROR')
        self.assertTrue(self.ollama.current.closed)
        self.assertEqual(self.store.rows,[('user','prompt')])
    def test_runaway_reply_closes_transport_and_signals_existing_stop(self):
        self.ollama.frames = [{'delta':'x'*1_000_001,'done':False}]
        result = list(self.send())
        self.assertEqual(result[-1]['code'],'OLLAMA_ERROR')
        self.assertTrue(self.ollama.current.closed)
        self.assertEqual(self.ollama.global_stop_called,1)
        self.assertEqual(self.store.rows,[('user','prompt')])
    def test_cancel_during_next_blocks_late_delta_and_closes(self):
        self.ollama.callback = self.stop.set
        result = list(self.send())
        self.assertEqual([x['type'] for x in result],['chat.start','chat.error'])
        self.assertEqual(result[-1]['code'],'STOP')
        self.assertTrue(self.ollama.current.closed)
        self.assertEqual(self.store.rows,[('user','prompt')])
    def test_stop_after_start_does_not_allocate_ollama_stream(self):
        outer = self.send()
        next(outer); self.stop.set()
        self.assertEqual([x['type'] for x in outer],['chat.error'])
        self.assertIsNone(self.ollama.current)
        self.assertEqual(self.store.rows,[('user','prompt')])
    def test_model_rejection_never_allocates_stream_or_db_write(self):
        with self.assertRaises(bridge.P02Error):
            list(self.chat.send('tenant','user','chat','missing','prompt',self.stop))
        self.assertIsNone(self.ollama.current)
        self.assertEqual(self.store.rows,[])

if __name__ == '__main__': unittest.main(verbosity=2)
