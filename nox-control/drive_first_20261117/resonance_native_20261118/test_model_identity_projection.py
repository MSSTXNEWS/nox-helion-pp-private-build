import unittest

import model_identity_projection as identity


class IdentityProjectionTests(unittest.TestCase):
    def test_masked_model_path_is_distinct_from_missing_null_and_bad_type(self):
        value = '/root/nox/models/deepseek_v41_flash_iq2xxs/DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00001-of-00006.gguf'
        out = identity.status_projection({'primary_model': value, 'native_p02_bound': True})
        item = out['primary_model']
        self.assertEqual(item['model_basename'], value.rsplit('/', 1)[-1])
        self.assertIn('previous_audit_sensitive_marker', item['previous_audit_mask_reasons'])
        self.assertNotIn(value, str(out))
        self.assertEqual(identity.status_projection({})['primary_model'], {'present': False, 'type': 'null'})
        self.assertEqual(identity.status_projection({'primary_model': None})['primary_model'], {'present': True, 'type': 'null'})
        self.assertEqual(identity.status_projection({'primary_model': {}})['primary_model']['type'], 'object')

    def test_snapshot_selection_follows_actual_bridge_order_and_cap(self):
        row = identity.status_projection({'model': {'name': '', 'model': 'chosen', 'id': 'ignored'}})
        self.assertEqual(row['selected_source_field'], 'model.model')
        self.assertEqual(row['selected_model']['identifier'], 'chosen')
        long = identity.status_projection({'model': 'x' * 250})
        self.assertEqual(long['selected_model']['chars'], 200)
        self.assertIn('previous_audit_limit120', long['selected_model']['previous_audit_mask_reasons'])

    def test_backend_plan_uses_actual_common_defaults_and_health_source_host(self):
        default = identity.backend_probe_plan({})
        self.assertEqual(default['port'], 8081)
        self.assertEqual(default['primary_health_url'], 'http://127.0.0.1:8081/health')
        live = identity.backend_probe_plan({'host': 'localhost', 'port': '8098'})
        self.assertEqual(live['primary_health_url'], 'http://127.0.0.1:8098/health')
        self.assertFalse(live['health_host_matches_completion_host'])
        self.assertEqual(live['model_posts'], 0)
        for doc in [{'host': 'example.com'}, {'port': True}, {'port': 1.5}, {'port': 65536}]:
            with self.subTest(doc=doc), self.assertRaises(ValueError):
                identity.backend_probe_plan(doc)

    def test_health_rule_and_incomplete_response_keep_uncertainty(self):
        self.assertTrue(identity.health_projection(200, b'{"status":"ok"}')['healthy_by_source_rule'])
        self.assertTrue(identity.health_projection(200, b'any nonempty response')['healthy_by_source_rule'])
        self.assertFalse(identity.health_projection(200, b'  ')['healthy_by_source_rule'])
        self.assertFalse(identity.health_projection(503, b'{"status":"ok"}')['healthy_by_source_rule'])
        self.assertIsNone(identity.health_projection(200, b'partial', truncated=True)['healthy_by_source_rule'])

    def test_argv_projection_exports_only_model_reference(self):
        model = '/root/nox/models/test/model-IQ2_XXS.gguf'
        row = identity.model_argv_projection(['llama-server', '--api-key', 'private-test-value', '-m', model])
        self.assertEqual(row['model_argument']['model_basename'], 'model-IQ2_XXS.gguf')
        self.assertNotIn('private-test-value', str(row))
        self.assertNotIn(model, str(row))
        with self.assertRaisesRegex(ValueError, 'AMBIGUOUS'):
            identity.model_argv_projection(['server', '-m', model, '--model=other.gguf'])
        with self.assertRaisesRegex(ValueError, 'MISSING_VALUE'):
            identity.model_argv_projection(['server', '--model'])

    def test_unsafe_or_unpinned_inputs_do_not_become_identifiers(self):
        for value in ['sk-private-value', 'https://example.invalid/a?token=x', '/root/secrets/nope.gguf', '/root/nox/models/../secrets/nope.gguf']:
            with self.subTest(value=value):
                row = identity.identifier(value)
                self.assertNotIn('identifier', row)
                self.assertNotIn('model_basename', row)
        with self.assertRaisesRegex(ValueError, 'HOLD_IDENTITY_SOURCE_SHA'):
            identity.source_contract({name: b'' for name in identity.SOURCE_PINS})

    def test_credential_value_that_looks_like_model_flag_is_not_exported(self):
        secret = 'SYNTHETIC_PRIVATE_VALUE_123'
        row = identity.model_argv_projection(['llama-server', '--api-key', '--model=' + secret])
        self.assertEqual(row['model_argument'], {'present': False})
        self.assertNotIn(secret, str(row))
        disguised = '--model=/root/nox/models/private-value.gguf'
        row = identity.model_argv_projection(['llama-server', '--api-key', disguised,
                                              '-m', '/root/nox/models/actual.gguf'])
        self.assertEqual(row['model_argument']['model_basename'], 'actual.gguf')
        self.assertNotIn('private-value', str(row))
        row = identity.model_argv_projection(['llama-server', '--model=' + secret])
        self.assertEqual(row['model_argument'], {'present': True, 'unvalidated_value_withheld': True})
        self.assertNotIn(secret, str(row))


if __name__ == '__main__':
    unittest.main()
