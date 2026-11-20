"""Unchanged legacy cognition test bodies, isolated from bridge and shell modules for local review."""
import json, time, unittest, threading
from nox_runpod.teacher_mesh.v38.synaptic_brain import SynapticBrain, NativePorts, Session, PulseConfig
S = Session(tenant='nox', principal='owner', chat_id='resonance')

def record(*, chat='resonance', persona=None, text='Запись из проверенной памяти'):
    r = dict(id='verified-memory', tenant='nox', principal='owner', chat_id=chat, segment='M7', source_uri='s03://owner/memory/verified', content=text, verified=True, superseded=False)
    if persona is not None:
        r['persona_id'] = persona
    return r

class LegacyRequiredMemory(unittest.TestCase):

    def _p(self, fn, **kwargs):
        b = SynapticBrain(NativePorts(authorize=lambda s: True, stop=lambda: False, s03_recall=fn, **kwargs), PulseConfig(fast_deadline_ms=25, deep_deadline_ms=180, memory_deadline_ms=180, max_workers=8, max_context_chars=3100))
        self.addCleanup(b.close)
        return b

    def test_slow_memory_is_waited_for(self):

        def slow(s, p, l):
            time.sleep(0.075)
            return [record()]
        b = self._p(slow)
        result = b.pulse(S, 'Вспомни вчера')
        self.assertEqual(result['state'], 'READY_FOR_ONE_NOX_MODEL')
        self.assertEqual(result['cores']['C02']['hit_count'], 1)
        self.assertGreaterEqual(result['elapsed_ms'], 60)

    def test_memory_context_pressure_holds_before_model_without_truncation(self):
        # No-loss memory policy: never turn an over-budget evidence set into an
        # apparently complete answer by silently shortening S03 records.
        rows = [record(text='Реальное воспоминание с источником ' + 'ж' * 360 + str(i))
                for i in range(8)]
        b = self._p(lambda s, p, l: rows)
        model_calls = []
        events = list(b.stream(S, 'Вспомни все восемь записей',
                               lambda p, m: model_calls.append(True) or iter(['FAKE ANSWER']),
                               deep=True))
        self.assertEqual(events[-1], {'type': 'hold', 'state': 'HOLD_CONTEXT_TOO_LARGE'})
        self.assertEqual(model_calls, [])

    def test_cross_chat_requires_trusted_grant(self):
        foreign = [record(chat='other-chat')]
        b = self._p(lambda s, p, l: foreign)
        self.assertEqual(b.pulse(S, 'test')['cores']['C02']['hit_count'], 0)
        good = self._p(lambda s, p, l: foreign, memory_scope_authorize=lambda s, r: True)
        self.assertEqual(good.pulse(S, 'test')['cores']['C02']['hit_count'], 1)

    def test_persona_specific_event_isolated_even_with_cross_grant(self):
        entries = [record(chat='other-chat', persona='KV')]
        b = self._p(lambda s, p, l: entries, memory_scope_authorize=lambda s, r: True)
        self.assertEqual(b.pulse(S, 'test')['cores']['C02']['hit_count'], 0)
        selected = Session(tenant='nox', principal='owner', chat_id='resonance', persona_enabled=True, persona_id='KV')
        self.assertEqual(b.pulse(selected, 'test')['cores']['C02']['hit_count'], 1)

    def test_memory_scheduled_before_optional_slow_sensors(self):
        seen = []

        def native_memory(s, p, l):
            seen.append('memory')
            return [record()]

        def sensor(s):
            time.sleep(0.04)
            seen.append('sensor')
            return {'gpu': 'real'}
        brain = SynapticBrain(NativePorts(authorize=lambda s: True, stop=lambda: False, s03_recall=native_memory, sensors=sensor), PulseConfig(max_workers=1, max_inflight=1, fast_deadline_ms=25, deep_deadline_ms=180, memory_deadline_ms=180))
        self.addCleanup(brain.close)
        result = brain.pulse(S, 'memory test')
        self.assertEqual(result['state'], 'READY_FOR_ONE_NOX_MODEL')
        self.assertEqual(result['cores']['C02']['hit_count'], 1)

    def test_response_contract_is_single_model_and_proactive_with_evidence(self):
        calls = []

        def generator(prompt, meta):
            calls.append(meta)
            return iter(['Проверенный ответ NOX.'])
        brain = self._p(lambda s, p, l: [record()])
        events = list(brain.stream(S, 'Объясни и предложи исправление', generator))
        self.assertEqual(len(calls), 1)
        self.assertEqual(events[-1]['type'], 'done')
        policy = calls[0]['response_contract']
        self.assertEqual(policy['quality_mode'], 'fast')
        self.assertIn('native receipt', policy['initiative_policy'])
        self.assertIn('M0-M7', policy['memory_policy'])
        self.assertIn('S03', calls[0]['cognitive_context'])
        self.assertNotIn('teacher_response', calls[0])

    def test_deep_contract_reuses_same_installed_model(self):
        calls = []
        brain = self._p(lambda s, p, l: [record()])
        list(brain.stream(S, 'Глубокий анализ', lambda p, m: calls.append(m) or iter(['Ответ']), deep=True))
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]['response_contract']['quality_mode'], 'deep')

    def test_placeholder_only_answer_gets_one_same_model_retry(self):
        calls = []

        def model(prompt, metadata):
            calls.append(metadata)
            return iter(['...', ' ']) if len(calls) == 1 else iter(['Полный ответ NOX'])
        brain = self._p(lambda s, p, l: [record()])
        events = list(brain.stream(S, 'Почему? Объясни и исправь.', model))
        self.assertEqual(len(calls), 2)
        self.assertEqual([e['text'] for e in events if e['type'] == 'delta'], ['Полный ответ NOX'])
        self.assertEqual(events[-1]['type'], 'done')
        self.assertIn('repair_instruction', calls[1]['response_contract'])

    def test_twice_placeholder_never_claims_done(self):
        brain = self._p(lambda s, p, l: [record()])
        calls = []

        def model(prompt, meta):
            calls.append(meta)
            return iter(['…'])
        events = list(brain.stream(S, 'Проверь работу', model))
        self.assertEqual(len(calls), 2)
        self.assertEqual(events[-1]['state'], 'HOLD_PLACEHOLDER_ONLY_MODEL_ANSWER')
        self.assertFalse(any((e['type'] == 'delta' for e in events)))

    def test_real_reply_is_one_call_no_quality_regression(self):
        brain = self._p(lambda s, p, l: [record()])
        calls = []

        def model(prompt, meta):
            calls.append(meta)
            return iter(['Привет', ', чем могу помочь?'])
        events = list(brain.stream(S, 'Привет', model))
        self.assertEqual(len(calls), 1)
        self.assertEqual(''.join((e['text'] for e in events if e['type'] == 'delta')), 'Привет, чем могу помочь?')
        self.assertEqual(events[-1]['type'], 'done')

    def test_stop_during_placeholder_retry_prevents_second_call(self):
        calls = []
        live = [False]
        brain = SynapticBrain(NativePorts(authorize=lambda s: True, stop=lambda: live[0], s03_recall=lambda s, p, l: [record()]), PulseConfig(max_workers=8))
        self.addCleanup(brain.close)

        def model(p, m):
            calls.append(True)
            live[0] = True
            return iter(['...'])
        events = list(brain.stream(S, 'Привет', model))
        self.assertEqual(len(calls), 1)
        self.assertEqual(events[-1]['state'], 'HOLD_STOP_DURING_STREAM')

class LegacyCognitionTests(unittest.TestCase):

    def setUp(self):
        self.s = Session(tenant='nox', principal='owner', chat_id='resonance')
        self.calls = []

    def native(self, **overrides):
        callbacks = dict(authorize=lambda _: True, stop=lambda: False, sensors=lambda _: {'gpu': {'used_vram_mib': 100}}, s03_recall=lambda s, p, l: [{'verified': True, 'tenant': s.tenant, 'principal': s.principal, 'chat_id': s.chat_id, 'segment': 'M7', 'content': 'Genesis fact', 'source_uri': 's03://genesis/event'}], self_receipts=lambda _: [{'native_verified': True, 'kind': 'verified_birth', 'verified_sha256': 'a' * 64, 'optimizer_step_verified': True, 'weights_reloaded': True}], affect=lambda s, p: {'label': 'neutral', 'confidence': 0.9}, preferences=lambda s: {'language': 'ru'}, available_skills=lambda s: {'available': ['code']}, queue_status=lambda s: {'running': 3})
        callbacks.update(overrides)
        return NativePorts(**callbacks)

    def test_no_arbitrary_persona(self):
        with self.assertRaises(ValueError):
            Session(tenant='nox', principal='owner', chat_id='chat', persona_enabled=True, persona_id='hacker').validate()

    def test_genesis_birth_requires_strict_native_true(self):
        seed = {'native_verified': True, 'kind': 'verified_birth', 'verified_sha256': 'a' * 64, 'occurred_at': '2026-11-15T00:00:00Z'}
        for step, reload, expected in [('false', 'false', False), (1, True, False), (True, 'no', False), (True, True, True)]:
            with self.subTest(step=step, reload=reload):
                event = dict(seed, optimizer_step_verified=step, weights_reloaded=reload)
                b = SynapticBrain(self.native(self_receipts=lambda _: [event]), PulseConfig(fast_deadline_ms=300, deep_deadline_ms=400, max_workers=8))
                try:
                    core = b.pulse(self.s, 'Genesis')['cores']['C03']
                    self.assertEqual(bool(core['events']), expected)
                    self.assertEqual(core['consciousness_claim'], 'NOT_ESTABLISHED')
                finally:
                    b.close()

    def test_spanish_response_contract_keeps_truthful_self_model(self):
        s = Session(tenant='nox', principal='owner', chat_id='resonance', language='es')
        calls = []
        b = SynapticBrain(self.native(), PulseConfig(fast_deadline_ms=300, deep_deadline_ms=400, max_workers=8))
        try:
            ev = list(b.stream(s, '¿Quién eres?', lambda p, m: calls.append(m) or iter(['Soy NOX.'])))
            self.assertEqual(ev[-1]['type'], 'done')
            self.assertEqual(len(calls), 1)
            g = calls[0]['response_contract']
            self.assertEqual(g['language'], 'es')
            self.assertIn('C04', g['affect_policy'])
            self.assertIn('Genesis', g['self_model_policy'])
            self.assertIn('RU/ES/EN', g['language_policy'])
        finally:
            b.close()
