import asyncio
import copy
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('owner_senior_gateway', Path(__file__).with_name('owner_senior_gateway.py'))
gateway = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gateway)

CONTEXT = {
    'schema': 'NOX_TASK_TECHNICAL_CONTEXT_V1', 'handler': 'owner_component',
    'task_evidence_sha256': 'e' * 64, 'prior_verified_count': 3,
    'prior_error_count': 1, 'error_categories': ['timeout'], 'mode': 'TASK_BOOST',
    'global_worker_cap': 6,
    'plan_policy': 'EXISTING_AUTHORIZED_NATIVE_HANDLER_WITH_RESOURCE_LOCKS',
    'memory_text_included': False,
}
ADVICE = json.dumps({'assessment': 'HOLD_FOR_REVIEW', 'check_categories': ['result_verification'],
                    'rationale': 'Private candidate text must stay in the local review cache.'})


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.root_patch = patch.object(gateway, 'ROOT', self.root)
        self.root_patch.start()
        # Existing protocol tests use mocked network replies, never real paid requests.
        self.policy_patch = patch.object(gateway, 'PAID_PROVIDER_EGRESS_ALLOWED', True)
        self.policy_patch.start()
        self.addCleanup(self.policy_patch.stop)
        self.env_patch = patch.dict(os.environ, {}, clear=True)
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.addCleanup(self.root_patch.stop)
        self.addCleanup(self.tmp.cleanup)

    def configure(self, **overrides):
        config = copy.deepcopy(gateway.DEFAULT_CONFIG)
        config.update(overrides)
        gateway._write('config/owner_senior_gateway.json', config)
        return config

    def credentials(self):
        for name in gateway.PROVIDERS:
            gateway.set_credential(name, 'unit-test-credential-value-' + name)

    async def verified(self, provider, credential, prompt, config, verification=False):
        return {'state': 'RECEIVED', 'text': 'NOX_ACCESS_OK' if verification else ADVICE,
                'response_sha256': 'c' * 64}

    def ready(self, **overrides):
        config = self.configure(**overrides)
        self.credentials()
        with patch.object(gateway, '_request', self.verified):
            result = gateway.verify_access()
        self.assertEqual(result['models_verified'], 3)
        self.assertEqual(gateway.status()['state'], 'READY')
        return config

    def test_no_paid_policy_blocks_status_consult_verify_and_direct_http(self):
        # Use the actual module default: patching False would hide a future unsafe default.
        self.policy_patch.stop()
        self.assertIs(gateway.PAID_PROVIDER_EGRESS_ALLOWED, False)
        # No config, credential file, terminal prompt or network setup on a denied policy.
        self.assertEqual(gateway.initialize()['state'], 'NO_PAID_API_POLICY')
        self.assertEqual(gateway.set_credential('openai', 'unit-test-credential-value')['state'],
                         'NO_PAID_API_POLICY')
        with patch.object(gateway.getpass, 'getpass', side_effect=AssertionError('secret prompt')) as secret_prompt:
            with patch('builtins.print') as printed:
                self.assertEqual(gateway.main(['set-key', 'openai']), 2)
                self.assertIn('NO_PAID_API_POLICY', printed.call_args[0][0])
                self.assertEqual(gateway.main(['init-config']), 2)
                self.assertEqual(gateway.main(['verify-access']), 2)
                self.assertEqual(gateway.main(['status']), 0)
            secret_prompt.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [])

        # Even pre-existing valid configuration and keys cannot reopen paid egress.
        self.configure()
        gateway._write('config/owner_senior_credentials.json', {
            'schema': 'NOX_OWNER_SENIOR_CREDENTIALS_V1',
            'keys': {name: 'unit-test-credential-value-' + name for name in gateway.PROVIDERS}})
        with patch.object(gateway, 'request_contract') as request_contract:
            self.assertEqual(gateway.status()['state'], 'NO_PAID_API_POLICY')
            self.assertEqual(gateway.consult_plan(CONTEXT)['state'], 'NO_PAID_API_POLICY')
            self.assertEqual(gateway.verify_access()['state'], 'NO_PAID_API_POLICY')
            result = asyncio.run(gateway._request('openai', 'private-key', '{}', gateway.DEFAULT_CONFIG))
            self.assertEqual(result['state'], 'NO_PAID_API_POLICY')
            request_contract.assert_not_called()
        self.assertFalse((self.root / 'state/owner_senior/access.json').exists())
        self.assertFalse((self.root / 'state/owner_senior/budget.json').exists())

    def test_model_text_fragments_are_not_rewritten(self):
        # Provider text fragments may split inside JSON strings. No added newline
        # or stripped final newline is permitted before evaluating the answer.
        raw = '{"assessment":"HOLD_FOR_REVIEW","check_categories":[],"rationale":"split"}' + chr(10)
        value = {'model': gateway.PROVIDERS['openai']['model'], 'status': 'completed',
                 'output': [{'type': 'message', 'role': 'assistant', 'content': [
                     {'type': 'output_text', 'text': raw[:28]},
                     {'type': 'output_text', 'text': raw[28:]}]}]}
        result = gateway.response_text('openai', value)
        self.assertEqual(result, raw)
        self.assertEqual(gateway.advice_candidate(result)['assessment'], 'HOLD_FOR_REVIEW')

    def test_absent_and_missing_credentials_are_read_only_and_never_call_provider(self):
        self.assertEqual(gateway.status()['state'], 'MISSING_SENIOR_GATEWAY')
        self.assertEqual(list(self.root.iterdir()), [])
        result = gateway.initialize()
        self.assertEqual(result['state'], 'MISSING_CREDENTIALS')
        with patch.object(gateway, '_request') as request:
            self.assertEqual(gateway.consult_plan(CONTEXT)['state'], 'MISSING_CREDENTIALS')
            self.assertEqual(gateway.verify_access()['state'], 'MISSING_CREDENTIALS')
        request.assert_not_called()
        self.assertFalse((self.root / 'config/owner_senior_credentials.json').exists())

    def test_credentials_do_not_mean_access_and_do_not_leave_status(self):
        self.configure()
        self.credentials()
        result = gateway.status()
        self.assertEqual(result['state'], 'UNVERIFIED_ACCESS')
        encoded = json.dumps(result)
        self.assertNotIn('unit-test-credential', encoded)
        self.assertNotIn('credential_binding', encoded)
        self.assertTrue(all(x['credential_configured'] for x in result['providers'].values()))
        path = self.root / 'config/owner_senior_credentials.json'
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        with patch.object(gateway, '_request') as request:
            self.assertEqual(gateway.consult_plan(CONTEXT)['state'], 'UNVERIFIED_ACCESS')
        request.assert_not_called()

    def test_exact_context_allowlist_rejects_private_and_invented_fields(self):
        config = self.configure()
        for changed in ({'prompt': 'private dialog'}, {'memory_text_included': True},
                        {'handler': 'unknown_handler'}, {'prior_verified_count': True},
                        {'prior_error_count': 101}, {'error_categories': ['private text']},
                        {'task_evidence_sha256': 'personal identifier'}, {'global_worker_cap': 60}):
            with self.subTest(changed=tuple(changed)):
                with self.assertRaises(gateway.GatewayHold):
                    gateway.validate_context({**CONTEXT, **changed}, config)
        self.assertEqual(gateway.validate_context(CONTEXT, config), CONTEXT)

    def test_fixed_api_contracts_keep_credentials_only_in_headers(self):
        config = self.configure()
        for name, spec in gateway.PROVIDERS.items():
            url, headers, body = gateway.request_contract(name, 'unit-test-secret', '{}', config)
            self.assertEqual(url, spec['url'])
            self.assertEqual(body['model'], spec['model'])
            self.assertNotIn('unit-test-secret', json.dumps(body))
            self.assertNotIn('tools', body)
            self.assertNotIn('temperature', body)
            self.assertIn('unit-test-secret', json.dumps(headers))
            if name == 'anthropic':
                self.assertEqual(headers['anthropic-version'], '2026-10-21')
                self.assertEqual(body['output_config']['effort'], 'low')
            else:
                self.assertIs(body['store'], False)
            if name == 'google':
                self.assertEqual(headers['Api-Revision'], '2026-05-20')
                self.assertEqual(body['generation_config']['thinking_level'], 'low')

    def test_response_parsers_exclude_thoughts_and_reject_tools_or_partial_output(self):
        examples = {
            'openai': {'model': 'gpt-6-astra', 'status': 'completed', 'output': [
                {'type': 'reasoning', 'summary': 'private chain'},
                {'type': 'message', 'role': 'assistant', 'content': [{'type': 'output_text', 'text': 'public'}]}]},
            'anthropic': {'model': 'claude-fable-5-2', 'type': 'message', 'role': 'assistant',
                          'stop_reason': 'end_turn', 'content': [{'type': 'thinking', 'thinking': 'private chain'},
                                                               {'type': 'text', 'text': 'public'}]},
            'google': {'model': 'gemini-4-carbon', 'status': 'completed', 'steps': [
                {'type': 'thought', 'summary': [{'type': 'text', 'text': 'private chain'}]},
                {'type': 'model_output', 'content': [{'type': 'text', 'text': 'public'}]}]},
        }
        for provider, value in examples.items():
            self.assertEqual(gateway.response_text(provider, value), 'public')
            wrong_model = {**value, 'model': 'unrequested-model'}
            with self.assertRaises(gateway.GatewayHold):
                gateway.response_text(provider, wrong_model)
            incomplete = {**value, 'stop_reason': 'max_tokens', 'status': 'incomplete'}
            with self.assertRaises(gateway.GatewayHold):
                gateway.response_text(provider, incomplete)
        with self.assertRaises(gateway.GatewayHold):
            gateway.response_text('google', {**examples['google'], 'steps': [{'type': 'function_call', 'name': 'delete'}]})

    def test_access_is_bound_to_current_key_model_config_and_freshness(self):
        config = self.ready(minimum_verified_providers=2)
        receipt = gateway._read('state/owner_senior/access.json')
        self.assertNotIn('unit-test-credential', json.dumps(receipt))
        gateway.set_credential('openai', 'replacement-test-credential-value')
        self.assertFalse(gateway.status()['providers']['openai']['access_verified'])
        receipt['providers']['google']['verified_at'] = time.time() - 86500
        gateway._write('state/owner_senior/access.json', receipt)
        self.assertEqual(gateway.status()['state'], 'UNVERIFIED_ACCESS')
        config['max_output_tokens'] = 2048
        gateway._write('config/owner_senior_gateway.json', config)
        self.assertEqual(gateway.status()['verified_provider_count'], 0)

    def test_failed_real_verification_never_certifies_access(self):
        self.ready(minimum_verified_providers=2)
        async def denied(*args, **kwargs):
            return {'state': 'AUTHENTICATION_REJECTED'}
        with patch.object(gateway, '_request', denied):
            result = gateway.verify_access('openai')
        self.assertEqual(result['models_verified'], 0)
        self.assertFalse(gateway.status()['providers']['openai']['access_verified'])
        async def mismatch(*args, **kwargs):
            return {'state': 'RECEIVED', 'text': 'almost NOX_ACCESS_OK', 'response_sha256': 'f' * 64}
        with patch.object(gateway, '_request', mismatch):
            result = gateway.verify_access('anthropic')
        self.assertEqual(result['providers']['anthropic'], 'VERIFICATION_REPLY_MISMATCH')
        self.assertEqual(gateway.status()['state'], 'UNVERIFIED_ACCESS')

    def test_six_callers_share_three_requests_and_private_advice_cache(self):
        self.ready()
        seen = []
        async def delayed(provider, credential, prompt, config, verification=False):
            seen.append((provider, json.loads(prompt)))
            await asyncio.sleep(0.12)
            return await self.verified(provider, credential, prompt, config, verification)
        with patch.object(gateway, '_request', delayed):
            with ThreadPoolExecutor(max_workers=6) as pool:
                values = list(pool.map(lambda _: gateway.consult_plan(CONTEXT, 0.5), range(6)))
            # Completion is asynchronous: wait for the durable cache, not for an arbitrary wall-clock delay.
            deadline = time.monotonic() + 2.0
            while True:
                result = gateway.consult_plan(CONTEXT, 0.05)
                if result['state'] == 'CONSULTED' or time.monotonic() >= deadline:
                    break
                time.sleep(0.01)
        self.assertEqual(result['state'], 'CONSULTED')
        self.assertEqual(len(seen), 3)
        self.assertEqual({p for p, _ in seen}, set(gateway.PROVIDERS))
        self.assertTrue(all(context == CONTEXT for _, context in seen))
        self.assertTrue(all(x['state'] in ('PENDING', 'CONSULTED') for x in values))
        self.assertEqual(result['state'], 'CONSULTED')
        self.assertEqual(result['models_consulted'], 3)
        self.assertTrue(result['cache_reused'])
        self.assertFalse(result['advice_execution_enabled'])
        self.assertNotIn('Private candidate text', json.dumps(result))
        self.assertNotIn('unit-test-credential', json.dumps(result))
        private = gateway._read('state/owner_senior/consultations.json', 1024 * 1024)
        self.assertIn('Private candidate text', json.dumps(private))

    def test_short_wait_returns_pending_and_holds_shared_admission(self):
        self.ready()
        async def delayed(*args, **kwargs):
            await asyncio.sleep(0.2)
            return await self.verified(*args, **kwargs)
        with patch.object(gateway, '_request', delayed):
            start = time.monotonic()
            result = gateway.consult_plan(CONTEXT, 0.01)
            self.assertLess(time.monotonic() - start, 0.15)
            self.assertEqual(result['state'], 'PENDING')
            self.assertIsNone(gateway._lock())
            # The background thread has a bounded deadline but no guaranteed 250-ms scheduling slot.
            deadline = time.monotonic() + 2.0
            while True:
                final = gateway.consult_plan(CONTEXT, 0.05)
                if final['state'] == 'CONSULTED' or time.monotonic() >= deadline:
                    break
                time.sleep(0.01)
            self.assertEqual(final['state'], 'CONSULTED')
        fd = gateway._lock()
        self.assertIsNotNone(fd)
        gateway._unlock(fd)

    def test_hourly_budget_counts_verification_and_does_not_refund_errors(self):
        self.ready(max_requests_per_hour=6)
        calls = []
        async def unavailable(provider, *args, **kwargs):
            calls.append(provider)
            return {'state': 'PROVIDER_TIMEOUT'}
        with patch.object(gateway, '_request', unavailable):
            first = gateway.consult_plan(CONTEXT)
            same = gateway.consult_plan(CONTEXT)
            other = gateway.consult_plan({**CONTEXT, 'task_evidence_sha256': 'd' * 64})
        self.assertEqual(first['state'], 'SENIOR_CONSULTATION_UNAVAILABLE')
        self.assertEqual(same['state'], 'SENIOR_CONSULTATION_UNAVAILABLE')
        self.assertEqual(other['state'], 'RATE_LIMITED')
        self.assertEqual(len(calls), 3)
        self.assertEqual(len(gateway._read('state/owner_senior/budget.json')['events']), 6)

    def test_wire_byte_digest_and_unexpected_compression_hold(self):
        # Mock provider transport only: no paid request or credentials leave the test.
        import gzip
        import httpx
        config = self.configure()
        value = {'model': gateway.PROVIDERS['openai']['model'], 'status': 'completed',
                 'output': [{'type': 'message', 'role': 'assistant',
                             'content': [{'type': 'output_text', 'text': ADVICE}]}]}
        wire = json.dumps(value, separators=(',', ':')).encode('utf-8')
        original = httpx.AsyncClient
        accepted_encodings = []

        async def plain(request):
            accepted_encodings.append(request.headers.get('accept-encoding'))
            return httpx.Response(200, stream=httpx.ByteStream(wire))

        with patch.object(httpx, 'AsyncClient',
                          lambda **kwargs: original(transport=httpx.MockTransport(plain), **kwargs)):
            result = asyncio.run(gateway._request('openai', 'unit-test-secret', '{}', config))
        self.assertEqual(result['state'], 'RECEIVED')
        self.assertEqual(result['text'], ADVICE)
        self.assertEqual(result['response_sha256'], gateway.hashlib.sha256(wire).hexdigest())
        self.assertEqual(accepted_encodings, ['identity'])

        async def compressed(request):
            return httpx.Response(200, headers={'content-encoding': 'gzip'},
                                  stream=httpx.ByteStream(gzip.compress(wire)))

        with patch.object(httpx, 'AsyncClient',
                          lambda **kwargs: original(transport=httpx.MockTransport(compressed), **kwargs)):
            held = asyncio.run(gateway._request('openai', 'unit-test-secret', '{}', config))
        self.assertEqual(held['state'], 'MODEL_RESPONSE_CONTENT_ENCODING')

    def test_http_redirect_is_not_followed_and_body_limit_is_enforced(self):
        import httpx
        config = self.configure()
        original = httpx.AsyncClient
        options = []
        seen = []
        async def redirect(request):
            seen.append(str(request.url))
            return httpx.Response(307, headers={'location': 'https://example.invalid/steal'})
        def factory(**kwargs):
            options.append(kwargs)
            return original(transport=httpx.MockTransport(redirect), **kwargs)
        with patch.object(httpx, 'AsyncClient', factory):
            result = asyncio.run(gateway._request('openai', 'unit-test-secret', '{}', config))
        self.assertEqual(result['state'], 'REDIRECT_REJECTED')
        self.assertEqual(seen, [gateway.PROVIDERS['openai']['url']])
        self.assertFalse(options[0]['trust_env'])
        self.assertFalse(options[0]['follow_redirects'])
        async def huge(request):
            return httpx.Response(200, stream=httpx.ByteStream(b' ' * 262145))
        with patch.object(httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(huge), **kwargs)):
            result = asyncio.run(gateway._request('openai', 'unit-test-secret', '{}', config))
        self.assertEqual(result['state'], 'MODEL_RESPONSE_SIZE')

    def test_total_provider_deadline_cancels_slow_request(self):
        import httpx
        config = self.configure()
        config['request_timeout_seconds'] = 0.02
        original = httpx.AsyncClient
        cancelled = []
        async def slow(request):
            try:
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                cancelled.append(True)
                raise
        with patch.object(httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(slow), **kwargs)):
            begin = time.monotonic()
            result = asyncio.run(gateway._request('google', 'unit-test-secret', '{}', config))
        self.assertEqual(result['state'], 'PROVIDER_TIMEOUT')
        self.assertLess(time.monotonic() - begin, 0.25)
        self.assertEqual(cancelled, [True])

    def test_secret_file_symlink_fifo_and_broad_permissions_are_rejected(self):
        self.configure()
        credential = self.root / 'config/owner_senior_credentials.json'
        os.mkfifo(credential, 0o600)
        begin = time.monotonic()
        self.assertEqual(gateway.status()['state'], 'CONFIGURATION_ERROR')
        self.assertLess(time.monotonic() - begin, 0.1)
        credential.unlink()
        credential.symlink_to(self.root / 'config/owner_senior_gateway.json')
        self.assertEqual(gateway.status()['state'], 'CONFIGURATION_ERROR')
        credential.unlink()
        self.credentials()
        credential.chmod(0o644)
        self.assertEqual(gateway.status()['state'], 'CONFIGURATION_ERROR')

    def test_conflicting_env_and_file_keys_fail_closed(self):
        self.configure()
        self.credentials()
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'different-test-credential-value'}):
            result = gateway.status()
        self.assertEqual(result['state'], 'CONFIGURATION_ERROR')
        self.assertNotIn('different-test-credential', json.dumps(result))

    def test_mutating_advice_schema_is_never_accepted_as_an_action(self):
        for value in ({'action': 'run_command', 'command': 'anything'},
                      {'assessment': 'RUN_NOW', 'check_categories': [], 'rationale': 'test'}):
            with self.assertRaises(gateway.GatewayHold):
                gateway.advice_candidate(json.dumps(value))
        result = gateway.advice_candidate(ADVICE)
        self.assertEqual(result['candidate_state'], 'EVALUATION_REQUIRED')
        self.assertIs(result['execution_authorized'], False)

    def test_one_verified_primary_can_advise_without_claiming_a_council(self):
        self.configure(providers=['openai'])
        gateway.set_credential('openai', 'unit-test-single-provider-credential')
        with patch.object(gateway, '_request', self.verified):
            access = gateway.verify_access('openai')
            self.assertEqual(access['models_verified'], 1)
            status = gateway.status()
            self.assertEqual(status['state'], 'READY')
            self.assertEqual(status['minimum_verified_providers'], 1)
            self.assertEqual(status['verified_access_mode'], 'SINGLE_ADVISER_AVAILABLE')
            result = gateway.consult_plan(CONTEXT)
        self.assertEqual(result['state'], 'CONSULTED')
        self.assertEqual(result['models_consulted'], 1)
        self.assertEqual(result['advisory_mode'], 'SINGLE_ADVISER')
        self.assertIs(result['council_consulted'], False)
        self.assertEqual(result['advice_scope'], 'ASSESSMENT_ONLY')

    def test_real_technical_context_is_typed_and_never_accepts_private_text(self):
        config = self.configure()
        context = {**CONTEXT, 'schema': gateway.DETAILED_CONTEXT_SCHEMA,
            'task_intent': 'improve_chat_latency', 'measurements': {'chat_ttft_ms': 29100, 'cpu_quota_cores': 19.2},
            'targets': {'chat_ttft_ms': 8000, 'global_worker_cap': 6}, 'public_error_codes': ['MODEL_TTFT_OVER_TARGET']}
        checked = gateway.validate_context(context, config)
        prompt = json.loads(gateway.technical_prompt(checked))
        self.assertEqual(prompt['measurements']['chat_ttft_ms'], 29100)
        self.assertIn('meaningful streamed token', prompt['task_intent_description'])
        self.assertTrue(prompt['public_error_descriptions'])
        for changed in ({'task_intent': 'private user request'}, {'measurements': {'private_path': '/secret'}},
                        {'measurements': {'chat_ttft_ms': True}}, {'measurements': {'chat_ttft_ms': float('nan')}},
                        {'public_error_codes': ['password=private']}, {'public_memory': 'private'}):
            with self.assertRaises(gateway.GatewayHold):
                gateway.validate_context({**context, **changed}, config)

    def test_concrete_recommendations_remain_candidates_for_local_evaluation(self):
        self.ready()
        advice = json.dumps({'assessment': 'HOLD_FOR_REVIEW', 'check_categories': ['result_verification', 'resource_admission'],
            'rationale': 'The measured first token latency is above the target.',
            'recommendations': [{'area': 'chat_latency', 'change': 'Measure and bound pre-generation retrieval before changing the model.',
                'expected_effect': 'Identify the dominant source of first token delay.',
                'evaluation': 'Compare meaningful TTFT on the same authenticated two-turn probe.',
                'rollback': 'Preserve the prior verified proxy and model configuration.'}]})
        async def reply(provider, *args, **kwargs):
            return {'state': 'RECEIVED', 'text': advice, 'response_sha256': 'b' * 64}
        with patch.object(gateway, '_request', reply):
            public = gateway.consult_plan(CONTEXT)
        self.assertEqual(public['advice_scope'], 'TECHNICAL_RECOMMENDATIONS')
        self.assertEqual(public['recommendation_count'], 3)
        self.assertNotIn('dominant source', json.dumps(public))
        candidate = gateway.candidate_for_evaluation(public['consultation_sha256'])
        self.assertEqual(len(candidate['candidates']), 3)
        self.assertEqual(candidate['evaluation_state'], 'REQUIRES_NATIVE_EVALUATION')
        self.assertIs(candidate['execution_authorized'], False)
        self.assertTrue(all(row['execution_authorized'] is False for row in candidate['candidates']))


if __name__ == '__main__':
    unittest.main()
