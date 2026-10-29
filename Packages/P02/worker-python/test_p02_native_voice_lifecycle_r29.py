"""Real immutable PACK01 + original VoiceSession; offline providers, no staging.

Run with NOX_ORIGINAL_SOURCE_ZIP pointing at the verified 729-source archive.
The original package is imported directly by zipimport, without rewriting it.
"""
import hashlib
import os
import pathlib
import sys
import json
import threading
import unittest
import test_p02_owner_route_ports as fixture
from test_p02_loader_existing_pack_r29 import host, CATALOG
from p02_native_ingress import NativeIngress, ProtocolHold
from p02_owner_route_ports import register_with_existing_pack01
from p02_runtime import OllamaClient

archive = pathlib.Path(os.environ['NOX_ORIGINAL_SOURCE_ZIP'])
assert hashlib.sha256(archive.read_bytes()).hexdigest() == 'ff8e2848c7c7ab776b90cbd8ac28e41e3815e96373c3c5f635d7587284629e9a'
sys.path.insert(0, str(archive))
from helion_voice.control import VoiceSession, VoiceCancelled

class NativeVoiceLifecycle(unittest.TestCase):
    tearDown = fixture.RouteTests.tearDown
    def setUp(self):
        fixture.RouteTests.setUp(self)
        self.dispatcher = host.NoxPackHost(CATALOG)
        self.client = OllamaClient()
        self.client.models = lambda: ['offline-fixture']
        host.ExistingP02Adapter(self.client, self.store).register(self.dispatcher, receipt='TEST')
        self.current = host.NativeSession('tenant', 'alice', 'chat', frozenset(self.dispatcher.routes), frozenset(self.dispatcher.routes))
        self.original = self.current
        self.ingress = NativeIngress(self.dispatcher, lambda: self.current,
                                     expected_run_id='voice-run', enable_voice_stop=True)
        register_with_existing_pack01(self.dispatcher, host.BoundPort, lambda _: self.scope,
            self.ports, receipt='TEST', native_stop_from_session=self.ingress.voice_stop_token)
        self.nonce = 0
        self.outputs = []
        self.ports.store_output_audio = lambda scope, audio: self.outputs.append(audio) or 'b'*32

    def packet(self, route, payload=None, **extra):
        self.nonce += 1
        value = dict(protocol='NOX-P02-NATIVE-v1', runId='voice-run', requestId=f'{self.nonce:032x}', route=route, payload=payload or {})
        value.update(extra)
        return json.dumps(value).encode()

    def call(self, route, payload=None, **extra):
        return json.loads(self.ingress.handle(self.packet(route, payload, **extra)))

    def voice_call(self):
        return self.call('chat.voice', dict(capture_id='a'*32, source='ru', target='es', voice='es-v'))

    def test_actual_authorized_stop_reaches_same_original_voice_session(self):
        seen = []
        observations = {}
        def asr(scope, data, language, token):
            original = self.ingress.voice_session_from_native(self.original)
            seen.append(original)
            observations['exact_class'] = type(original) is VoiceSession
            observations['exact_event'] = token is original._cancelled
            answer = self.call('chat.stop')
            observations['ack'] = answer['result'].get('voiceStopped')
            observations['set_at_stop_ack'] = token.is_set()
            return 'привет'
        self.voice.asr = asr
        with self.assertRaises(ProtocolHold): self.voice_call()
        self.assertEqual(observations, dict(exact_class=True, exact_event=True, ack=True, set_at_stop_ack=True))
        self.assertEqual(self.outputs, [])
        self.assertTrue(seen[0].stopped)
        with self.assertRaisesRegex(ProtocolHold, 'ACTIVE_VOICE'): self.ingress.voice_stop_token(self.original)

    def test_cross_session_and_stale_target_stop_cannot_cancel(self):
        def asr(scope, data, language, token):
            self.current = host.NativeSession('tenant', 'alice', 'chat', self.original.allowed, self.original.private_approved)
            with self.assertRaisesRegex(ProtocolHold, 'VOICE_SESSION_MISMATCH'): self.call('chat.stop')
            with self.assertRaises(ProtocolHold): self.ingress.voice_stop_token(self.current)
            self.current = self.original
            with self.assertRaisesRegex(ProtocolHold, 'VOICE_REQUEST_MISMATCH'):
                self.call('chat.stop', {'voice_request_id':'f'*32})
            self.assertFalse(token.is_set())
            return 'привет'
        self.voice.asr = asr
        self.assertEqual(self.voice_call()['status'], 'OK')
        self.assertEqual(len(self.outputs), 1)

    def test_denied_stop_does_not_set_original_token(self):
        def asr(scope, data, language, token):
            port = self.dispatcher.ports['chat.stop']
            def denied(*args): raise PermissionError('denied')
            self.dispatcher.ports['chat.stop'] = host.BoundPort(denied, port.available, port.evidence_id, port.owner)
            with self.assertRaises(ProtocolHold): self.call('chat.stop')
            self.assertFalse(token.is_set())
            return 'привет'
        self.voice.asr = asr
        self.voice_call()
        self.assertEqual(len(self.outputs), 1)

    def test_run_nonce_and_completed_session_are_not_reusable(self):
        tokens = []
        self.voice.asr = lambda scope, data, language, token: tokens.append(token) or 'привет'
        self.voice_call()
        self.assertTrue(tokens[0].is_set())
        self.audio['a'*32] = b'voice'
        self.voice_call()
        self.assertIsNot(tokens[0], tokens[1])
        with self.assertRaises(ProtocolHold): self.call('chat.stop', runId='stale-run')
        packet = self.packet('chat.stop')
        self.ingress.handle(packet)
        with self.assertRaises(ProtocolHold): self.ingress.handle(packet)
        with self.assertRaises(ProtocolHold): self.ingress.voice_session_from_native(self.original)

    def test_stop_during_output_persistence_revokes_donor_receipt(self):
        discarded = []
        def persist(scope, audio):
            self.call('chat.stop')
            return 'b'*32
        self.ports.store_output_audio = persist
        self.ports.discard_output_audio = lambda scope, receipt: discarded.append(receipt) or True
        with self.assertRaises(ProtocolHold): self.voice_call()
        self.assertEqual(discarded, ['b'*32])

    def test_stop_terminates_original_registered_subprocess(self):
        failures = []
        observations = []
        def asr(scope, data, language, token):
            session = self.ingress.voice_session_from_native(self.original)
            def stop_registered():
                try:
                    for _ in range(200):
                        with session._lock:
                            registered = bool(session._processes)
                        if registered:
                            self.call('chat.stop')
                            return
                        threading.Event().wait(.01)
                    raise AssertionError('Original subprocess did not register')
                except BaseException as exc: failures.append(exc); session.stop()
            stopper = threading.Thread(target=stop_registered)
            stopper.start()
            try:
                try:
                    session.run([sys.executable, '-c', 'import time; time.sleep(10)'], timeout=2)
                except VoiceCancelled:
                    observations.append('original-child-cancelled')
            finally: stopper.join(3)
            self.assertFalse(stopper.is_alive())
            self.assertEqual(failures, [])
            return 'привет'
        self.voice.asr = asr
        with self.assertRaises(ProtocolHold): self.voice_call()
        self.assertEqual(failures, [])
        self.assertEqual(observations, ['original-child-cancelled'])
        self.assertEqual(self.outputs, [])

    def test_completion_retirement_is_atomic_with_final_stop_check(self):
        observations = []
        ingress = self.ingress
        original_lock = ingress._voice_lock
        class CompletionBoundary:
            armed = False
            def __enter__(self):
                original_lock.acquire()
                return self
            def __exit__(boundary, *exc):
                original_lock.release()
                if boundary.armed:
                    boundary.armed = False
                    observations.append(self.call('chat.stop')['result'])
        boundary = CompletionBoundary()
        ingress._voice_lock = boundary
        def persist(scope, audio):
            boundary.armed = True
            return 'b'*32
        self.ports.store_output_audio = persist
        response = self.voice_call()
        self.assertEqual(response['status'], 'OK')
        self.assertEqual(len(observations), 1)
        self.assertIsNot(observations[0].get('voiceStopped'), True)
        self.assertIsNone(ingress._active_voice)

if __name__ == '__main__': unittest.main()
