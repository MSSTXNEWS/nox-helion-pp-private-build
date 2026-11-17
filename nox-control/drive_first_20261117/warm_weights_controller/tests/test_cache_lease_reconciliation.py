"""Real local cache operations with a fault-injected authoritative host callback.

No native server, Drive account, model, or scheduler is used by these regressions.
"""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from nox_warm import Controller, Hold, Snapshot

MiB = 1024 * 1024


class CacheLeaseReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / 'source'
        self.source.write_bytes(b'cache-lease-regression\n' * 64)
        body = self.source.read_bytes()
        self.group = {
            'id': 'advisor', 'remote_path': 'advisor.bin', 'cache_path': 'advisor.bin',
            'size_bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest(),
            'priority': 1, 'warm_bytes': 0, 'ram_load_bytes': MiB, 'gpu_load_bytes': 0,
            'tier': 'warmSSD', 'modes': ['WORK'], 'startup_preload': True,
            'protected': False, 'may_unload': True,
        }
        self.manifest = {
            'schema': 'NOX_WARM_MANIFEST_V1', 'source_policy': 'DRIVE_FIRST',
            'startup_storage': 'warmSSD', 'allow_ssd_cache': True,
            'groups': [self.group], 'mode_groups': {'WORK': ['advisor'], 'TRAIN': []},
            'budgets': {'chat_reserve_bytes': MiB, 'train_reserve_bytes': MiB,
                        'system_reserve_bytes': MiB, 'ssd_reserve_bytes': MiB,
                        'startup_transfer_bytes': MiB, 'startup_warm_bytes': 0,
                        'startup_max_groups': 2},
        }
        self.admissions = []
        self.releases = []
        self.lose_admission_ack = False
        self.lose_release_ack = True
        self.controller = self.make_controller()

    def tearDown(self):
        self.tmp.cleanup()

    def admit(self, request):
        self.admissions.append(dict(request))
        if self.lose_admission_ack:
            raise TimeoutError('host may have granted; acknowledgement lost')
        return {'granted': True, 'scope': 'host', 'lease_id': 'lease-' + str(len(self.admissions)),
                'fencing_token': len(self.admissions)}

    def release(self, lease):
        self.releases.append(dict(lease))
        if self.lose_release_ack:
            raise TimeoutError('host may have released; acknowledgement lost')
        return {'released': True}

    def make_controller(self):
        return Controller(
            self.manifest, self.root / 'cache', self.root / 'journal.json',
            snapshot=lambda: Snapshot(0, 128 * MiB, 128 * MiB, 128 * MiB, 0, 0, 0, 0, 0),
            host_resource_admission=self.admit, host_release_resource=self.release,
            owner_should_pause=lambda: False,
        )

    def lose_release(self):
        with self.assertRaisesRegex(Hold, 'CACHE_RESOURCE_RELEASE_UNCONFIRMED'):
            self.controller.cache_local('advisor', self.source, apply=True)

    def readback(self, released=True, **updates):
        result = {'verified': True, 'source': 'isolated-authoritative-host-fixture',
                  'observed_at': 1, 'lease_id': 'lease-1', 'fencing_token': 1,
                  'released': released}
        result.update(updates)
        return result

    def test_lost_release_blocks_repeated_admission_even_after_restart(self):
        self.lose_release()
        restarted = self.make_controller()
        with self.assertRaisesRegex(Hold, 'CACHE_LEASE_RECONCILE_REQUIRED'):
            restarted.cache_local('advisor', self.source, apply=True)
        self.assertEqual(len(self.admissions), 1)
        self.assertEqual(len(self.releases), 1)
        self.assertEqual(restarted.data['cache_lease_reconcile']['lease_id'], 'lease-1')

    def test_lost_admission_is_recorded_before_callback_and_blocks_retry(self):
        self.lose_admission_ack = True
        with self.assertRaises(TimeoutError):
            self.controller.cache_local('advisor', self.source, apply=True)
        persisted = json.loads((self.root / 'journal.json').read_text())
        self.assertEqual(persisted['cache_lease_operation']['state'], 'UNKNOWN')
        with self.assertRaisesRegex(Hold, 'CACHE_LEASE_RECONCILE_REQUIRED'):
            self.make_controller().cache_local('advisor', self.source, apply=True)
        self.assertEqual(len(self.admissions), 1)
        self.assertEqual(self.releases, [])

    def test_stale_fencing_readback_cannot_release_or_clear_pending_lease(self):
        self.lose_release()
        for token in (0, True, 2):
            with self.assertRaisesRegex(Hold, 'CACHE_LEASE_READBACK_UNVERIFIED'):
                self.controller.reconcile_cache_lease(self.readback(fencing_token=token))
        self.assertEqual(len(self.releases), 1)
        self.assertEqual(self.controller.data['cache_lease_reconcile']['lease_id'], 'lease-1')
        result = self.controller.reconcile_cache_lease(self.readback())
        self.assertTrue(result['lease_released'])
        self.assertFalse(result['native_release_performed'])
        self.lose_release_ack = False
        self.controller.cache_local('advisor', self.source, apply=True)
        self.assertEqual(len(self.admissions), 2)
        self.assertNotEqual(self.admissions[0]['transition_id'], self.admissions[1]['transition_id'])

    def test_verified_still_held_allows_one_explicit_release_retry(self):
        self.lose_release()
        self.controller.reconcile_cache_lease(self.readback(released=False))
        with self.assertRaisesRegex(Hold, 'CACHE_LEASE_RECONCILE_REQUIRED'):
            self.controller.cache_local('advisor', self.source, apply=True)
        self.assertEqual(len(self.releases), 1)
        self.lose_release_ack = False
        result = self.controller.release_reconciled_cache_lease()
        self.assertTrue(result['lease_released'])
        with self.assertRaisesRegex(Hold, 'CACHE_RELEASE_RETRY_NOT_AUTHORIZED'):
            self.controller.release_reconciled_cache_lease()
        self.assertEqual(len(self.releases), 2)

    def test_unknown_admission_needs_exact_request_readback(self):
        self.lose_admission_ack = True
        with self.assertRaises(TimeoutError):
            self.controller.cache_local('advisor', self.source, apply=True)
        receipt = {'verified': True, 'source': 'isolated-host-fixture', 'observed_at': 1,
                   'released': True, 'settled_resource_request_id': 'wrong'}
        with self.assertRaisesRegex(Hold, 'CACHE_LEASE_READBACK_UNVERIFIED'):
            self.controller.reconcile_cache_lease(receipt)
        receipt['settled_resource_request_id'] = self.admissions[0]['transition_id']
        self.controller.reconcile_cache_lease(receipt)
        self.lose_admission_ack = False
        self.lose_release_ack = False
        self.controller.cache_local('advisor', self.source, apply=True)
        self.assertEqual(len(self.admissions), 2)
        self.assertEqual(len(self.releases), 1)

    def test_multi_group_startup_preserves_first_unknown_lease(self):
        second = dict(self.group, id='second', cache_path='second.bin', remote_path='second.bin')
        self.manifest['groups'].append(second)
        self.manifest['mode_groups']['WORK'].append('second')
        self.controller = self.make_controller()
        for group in self.manifest['groups']:
            self.controller.cache.stage_local(group, self.source)
        result = self.controller.startup(apply=True)
        self.assertEqual(result['selected'][0]['reason'], 'CACHE_RESOURCE_RELEASE_UNCONFIRMED')
        self.assertEqual(result['selected'][1]['reason'], 'CACHE_LEASE_RECONCILE_REQUIRED')
        self.assertEqual(len(self.admissions), 1)
        self.assertEqual(len(self.releases), 1)
        self.assertEqual(self.controller.data['cache_lease_reconcile']['lease_id'], 'lease-1')

    def test_legacy_pending_lease_is_reconciled_without_new_admission(self):
        self.controller.data['cache_lease_reconcile'] = {
            'granted': True, 'scope': 'host', 'lease_id': 'lease-1', 'fencing_token': 1,
        }
        self.controller._persist()
        self.controller = self.make_controller()
        with self.assertRaisesRegex(Hold, 'CACHE_LEASE_RECONCILE_REQUIRED'):
            self.controller.cache_local('advisor', self.source, apply=True)
        self.assertEqual(self.admissions, [])
        self.controller.reconcile_cache_lease(self.readback())
        self.assertEqual(self.releases, [])
        self.lose_release_ack = False
        self.controller.cache_local('advisor', self.source, apply=True)
        self.assertEqual(len(self.admissions), 1)

    def test_interrupt_during_release_is_preserved_and_unknown_is_durable(self):
        def interrupted(lease):
            self.releases.append(dict(lease))
            persisted = json.loads((self.root / 'journal.json').read_text())
            self.assertEqual(persisted['cache_lease_operation']['state'], 'RELEASE_PENDING')
            raise KeyboardInterrupt()
        self.controller.host_release_resource = interrupted
        with self.assertRaises(KeyboardInterrupt):
            self.controller.cache_local('advisor', self.source, apply=True)
        self.controller = self.make_controller()
        with self.assertRaisesRegex(Hold, 'CACHE_LEASE_RECONCILE_REQUIRED'):
            self.controller.cache_local('advisor', self.source, apply=True)
        self.assertEqual(len(self.releases), 1)


if __name__ == '__main__':
    unittest.main()
