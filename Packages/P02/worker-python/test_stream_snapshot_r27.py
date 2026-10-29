"""Run epoch/terminal snapshots on exact P02 sources; no installed Ollama."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from p02_runtime import OllamaClient, P02Error
from p02_chat_bridge import ChatBridge


class StreamSnapshotTests(unittest.TestCase):
    def client(self):
        class Response:
            def __iter__(self):
                yield b'{"message":{"content":"first"},"done":false}\n'
                yield b'{"message":{"content":"last"},"done":true}\n'
            def close(self): pass
        class Client(OllamaClient):
            def _open(self, *_): return Response()
        return Client()

    def test_consumer_cannot_promote_partial_chunk_to_terminal(self):
        chunks = self.client().stream('local', [{'role': 'user', 'content': 'go'}])
        self.addCleanup(chunks.close)
        first = next(chunks)
        first['done'] = True
        rest = list(chunks)
        self.assertEqual([r['delta'] for r in rest], ['last'])

    def test_consumer_cannot_revoke_actual_terminal_chunk(self):
        chunks = self.client().stream('local', [{'role': 'user', 'content': 'go'}])
        self.addCleanup(chunks.close)
        next(chunks)
        terminal = next(chunks)
        terminal['done'] = False
        self.assertEqual(list(chunks), [])

    def test_adapter_mutation_during_delta_cannot_complete_partial_turn(self):
        class Store:
            def __init__(self): self.rows = []
            def history(self, *_): return []
            def add_message(self, tenant, principal, chat, role, text):
                self.rows.append((role, text))
        first = {'delta': 'first', 'done': False}
        class Provider:
            def models(self): return ['local']
            def stream(self, *_):
                yield first
                yield {'delta': 'last', 'done': True}
        store = Store()
        events = ChatBridge(store, Provider()).send('t', 'p', 'c', 'local', 'go')
        self.addCleanup(events.close)
        self.assertEqual(next(events)['type'], 'chat.start')
        self.assertEqual(next(events)['text'], 'first')
        first['done'] = True
        rest = list(events)
        self.assertEqual([r['type'] for r in rest], ['chat.delta', 'chat.complete'])
        self.assertEqual(store.rows[-1], ('assistant', 'firstlast'))


if __name__ == '__main__': unittest.main()
