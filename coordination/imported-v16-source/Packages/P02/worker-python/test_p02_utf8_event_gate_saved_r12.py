"""R12 native events.v3 relay UTF-8 regression; owner source, host fixture only.

Run from worker-python: python -m unittest test_p02_utf8_event_gate_saved_r12 -v
Not evidence of real Ollama, Windows or native events.v3 integration.
"""
import unittest
import uuid
from p02_runtime import P02Error
from p02_capabilities import Identity
from p02_host_admission import NativeHostBinding, P02EventRelay, P02_TYPES

class UTF8RelayR12(unittest.TestCase):
    def setUp(self):
        self.out = []
        routes = {k: 'host.p02.' + k for k in P02_TYPES}
        self.relay = P02EventRelay(NativeHostBinding(
            Identity('tenant', 'user', 'core', 'persona', 'session'), True,
            frozenset(routes.values()), routes,
            lambda event_type, body: self.out.append((event_type, body))))
        self.run = uuid.uuid4().hex

    def start(self):
        self.relay.relay(dict(type='chat.start', run_id=self.run, model='valid'))

    def test_malformed_utf8_fails_closed_in_six_event_fields(self):
        cases = [
            ('chat.start', {'model': 'bad\ud800'}, False),
            ('chat.delta', {'text': 'bad\udfff'}, True),
            ('chat.sources', {'sources': [{'source_id':'\ud800','title':'ok'}]}, True),
            ('chat.sources', {'sources': [{'source_id':'ok','title':'\ud800'}]}, True),
            ('chat.sources', {'sources': [{'source_id':'ok','title':'ok','url':'https://example.org/\ud800'}]}, True),
            ('chat.error', {'code':'ERR','detail':'\udfff'}, True),
        ]
        for kind, data, start in cases:
            with self.subTest(kind=kind, data=list(data)):
                self.setUp()
                if start:
                    self.start()
                previous = list(self.out)
                with self.assertRaisesRegex(P02Error, 'P02_EVENT_NOT_SERIALIZABLE'):
                    self.relay.relay(dict(type=kind, run_id=self.run, **data))
                self.assertEqual(self.out, previous)

    def test_legitimate_multilingual_frames_publish(self):
        self.start()
        self.relay.relay(dict(type='chat.delta', run_id=self.run, text='Привет 🌍 ¡Hola!'))
        self.relay.relay(dict(type='chat.complete', run_id=self.run, chars=16))
        self.assertEqual(self.out[1][1]['text'], 'Привет 🌍 ¡Hola!')
        self.assertTrue(self.relay._finished)

    def test_dangerous_fields_stay_rejected(self):
        with self.assertRaises(PermissionError):
            self.relay.relay(dict(type='chat.start', run_id=self.run, model='x', shell='cmd'))
        self.assertEqual(self.out, [])

    def test_unhashable_type_stays_rejected(self):
        with self.assertRaises(P02Error):
            self.relay.relay(dict(type=[], run_id=self.run, model='x'))
        self.assertEqual(self.out, [])
