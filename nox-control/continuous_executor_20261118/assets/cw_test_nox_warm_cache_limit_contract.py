"""3A03: malformed limits cannot alias a valid cached S03 query."""
import unittest
from unittest import mock

from nox_runpod.teacher_mesh.v38.durable_runtime import WarmS03Cache
from nox_runpod.teacher_mesh.v38.synaptic_brain import Session


class WarmCacheLimitContractTests(unittest.TestCase):
    def setUp(self):
        self.session = Session('owner', 'principal', 'chat')
        self.rows = [{'tenant': 'owner', 'principal': 'principal', 'chat_id': 'chat',
                      'segment': 'M2', 'verified': True, 'content': 'same native row'}]
        self.recall = mock.Mock(return_value=self.rows)
        self.revision = mock.Mock(return_value='revision-1')
        self.cache = WarmS03Cache(self.recall, self.revision)

    def test_bool_limit_is_rejected_before_any_native_callback(self):
        for limit in (True, False):
            with self.subTest(limit=limit), self.assertRaisesRegex(ValueError, 'S03_CACHE_LIMIT'):
                self.cache(self.session, 'query', limit)
        self.recall.assert_not_called()
        self.revision.assert_not_called()

    def test_float_or_text_limit_does_not_alias_cached_integer(self):
        self.cache(self.session, 'query', 1)
        calls = (self.recall.call_count, self.revision.call_count)
        for limit in (1.0, 1.5, '1', None):
            with self.subTest(limit=limit), self.assertRaisesRegex(ValueError, 'S03_CACHE_LIMIT'):
                self.cache(self.session, 'query', limit)
        self.assertEqual((self.recall.call_count, self.revision.call_count), calls)
        self.assertEqual(self.cache.stats['hits'], 0)

    def test_nonpositive_or_oversized_limits_never_reach_s03(self):
        for limit in (-1, 0, 21, 2 ** 100):
            with self.subTest(limit=limit), self.assertRaisesRegex(ValueError, 'S03_CACHE_LIMIT'):
                self.cache(self.session, 'query', limit)
        self.recall.assert_not_called()
        self.revision.assert_not_called()
        self.assertEqual(self.cache._reads, {})

    def test_no_revision_bypass_obeys_the_same_validation(self):
        self.cache.revision = None
        with self.assertRaisesRegex(ValueError, 'S03_CACHE_LIMIT'):
            self.cache(self.session, 'query', '3')
        self.recall.assert_not_called()

    def test_valid_boundary_limits_keep_callback_and_cache_behavior(self):
        for limit in (1, 20):
            self.assertEqual(self.cache(self.session, 'query', limit), self.rows)
            self.assertEqual(self.cache(self.session, 'query', limit), self.rows)
        self.assertEqual(self.recall.call_count, 2)
        self.assertEqual(self.cache.stats['hits'], 2)

    def test_invalid_call_cannot_mutate_existing_cache_accounting(self):
        self.cache(self.session, 'query', 1)
        before = (self.cache.bytes, dict(self.cache.stats), list(self.cache.entries))
        with self.assertRaisesRegex(ValueError, 'S03_CACHE_LIMIT'):
            self.cache(self.session, 'query', True)
        self.assertEqual((self.cache.bytes, dict(self.cache.stats), list(self.cache.entries)), before)


if __name__ == '__main__':
    unittest.main()
