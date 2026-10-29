"""E02 R07 offline adversarial regression: citations cannot outlive STOP.

Uses the EXISTING P02 ChatBridge with a mock shared store and Ollama; this
is NOT proof of a Windows host, native authorization, installed weights or mic.
"""
from __future__ import annotations
import importlib.util
import pathlib
import threading
import unittest

spec = importlib.util.spec_from_file_location(
    'p02_chat_bridge_r07', pathlib.Path(__file__).with_name('p02_chat_bridge.py'))
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class Store:
    def __init__(self): self.rows = []
    def history(self, tenant, principal, chat):
        assert (tenant, principal, chat) == ('tenant', 'principal', 'chat')
        return [{'role': k, 'content': v} for k, v in self.rows]
    def add_message(self, tenant, principal, chat, role, value):
        assert (tenant, principal, chat) == ('tenant', 'principal', 'chat')
        self.rows.append((role, value))


class Ollama:
    def __init__(self): self.stream_calls = 0
    def models(self): return ['installed:1']
    def stream(self, model, messages, stop):
        self.stream_calls += 1
        yield {'delta': 'answer', 'done': False}
        yield {'delta': '', 'done': True}


class RAGStopBoundaryR07(unittest.TestCase):
    def setUp(self):
        self.stop = threading.Event()
        self.store = Store()
        self.ollama = Ollama()
        self.chat = bridge.ChatBridge(self.store, self.ollama,
            rag_context=lambda *_: {'context': 'untrusted reference', 'sources': [
                {'source_id': 'primary', 'title': 'Primary source',
                 'verified': True, 'url': 'https://example.org/source'}]})

    def turn(self):
        return self.chat.send('tenant', 'principal', 'chat', 'installed:1',
                              'question', self.stop)

    def test_stop_after_chat_start_blocks_citations_before_emission(self):
        turn = self.turn()
        self.assertEqual(next(turn)['type'], 'chat.start')
        self.stop.set()
        tail = list(turn)
        self.assertEqual([event['type'] for event in tail], ['chat.error'])
        self.assertEqual(tail[0]['code'], 'STOP')
        self.assertEqual(self.ollama.stream_calls, 0)
        self.assertEqual(self.store.rows, [('user', 'question')])

    def test_stop_after_chat_sources_blocks_llm_lease(self):
        turn = self.turn()
        self.assertEqual(next(turn)['type'], 'chat.start')
        self.assertEqual(next(turn)['type'], 'chat.sources')
        self.stop.set()
        self.assertEqual([event['type'] for event in turn], ['chat.error'])
        self.assertEqual(self.ollama.stream_calls, 0)
        self.assertEqual(self.store.rows, [('user', 'question')])

    def test_valid_citation_and_successful_answer_unchanged(self):
        frames = list(self.turn())
        self.assertEqual([x['type'] for x in frames],
            ['chat.start', 'chat.sources', 'chat.delta', 'chat.complete'])
        self.assertEqual(frames[1]['sources'][0]['url'], 'https://example.org/source')
        self.assertEqual(self.store.rows,
            [('user', 'question'), ('assistant', 'answer')])
        self.assertEqual(self.ollama.stream_calls, 1)

    def test_no_rag_sources_stop_after_start_returns_single_stop_event(self):
        self.chat.rag_context = None
        turn = self.turn()
        self.assertEqual(next(turn)['type'], 'chat.start')
        self.stop.set()
        self.assertEqual([event['type'] for event in turn], ['chat.error'])
        self.assertEqual(self.ollama.stream_calls, 0)

if __name__ == '__main__': unittest.main(verbosity=2)
