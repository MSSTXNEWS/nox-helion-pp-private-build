"""Bounded synthetic status proof tests; no native/model/network operations."""
import base64
from contextlib import ExitStack
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import types
import unittest
from unittest.mock import patch

import owner_qwen_training_status as status
import owner_training_status_binding as binding
import test_owner_qwen_training_observe as fixtures

HERE = Path(__file__).parent


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()


class QwenStatusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = fixtures.module(fixtures.CONTRACT_PATH, '_qwen_status_test_contract')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / 'lora/qwen35_9b/6907283384'; self.output.mkdir(parents=True)
        scripts = self.root / 'scripts'; scripts.mkdir()
        (self.root / 'state').mkdir()
        for target, source in (('owner_qwen_training_observe.py', HERE / 'owner_qwen_training_observe.py'),
                               ('owner_qwen_training_contract.py', fixtures.CONTRACT_PATH)):
            (scripts / target).write_bytes(source.read_bytes())
        scope = patch.object(status, 'ROOT', self.root); scope.start(); self.addCleanup(scope.stop)
        status._HASH_CACHE.clear()

    def checkpoint_fixture(self, good=5):
        return fixtures.QwenObservationTests.fixture(self, good=good, skipped=0)

    def baseline(self, lineage, manifest, directory):
        return {**status.BASELINE, 'lineage_file_sha256': status.digest((directory / 'lineage.json').read_bytes()),
                'lineage_sha256': self.contract.canonical_sha(lineage),
                'adapter_tensor_sha256': fixtures.sha(b'tensor5')}

    def test_wrapper_bytes_match_both_actual_native_receipts(self):
        initial = json.loads(Path('/tmp/nox_qwen_initial_actual_6907283384.json').read_text())
        resumed = json.loads(Path('/tmp/nox_qwen_advance6_6907513913.json').read_text())
        obs = types.SimpleNamespace(SCRIPTS=Path('/root/nox/scripts'), OUTPUT=Path('/root/nox/lora/qwen35_9b/6907283384'),
                                    CORPUS=Path('/root/nox/state/qwen_corpus/6907283384'), DATA_PINS=fixtures.OBS.DATA_PINS)
        for row, goal, key in ((initial, 5, 'admission_sha256'), (resumed, 6, 'new_admission_sha256')):
            profile = {**initial['student_profile'], 'successful_updates_goal': goal}
            argv = status.arguments(obs, row['request'], row[key], profile)
            self.assertEqual(status.digest(status.wrapper_bytes(argv, row['request'], goal)), row['wrapper_sha256'])

    def test_cache_reuses_full_sha_only_while_entire_identity_matches(self):
        path = self.root / 'tensor.bin'; path.write_bytes(b'a' * 32768)
        pin = status.digest(path.read_bytes()); before = path.stat()
        audit = {'checkpoint_bytes_hashed': 0, 'checkpoint_files_from_stat_cache': 0}
        status.read(path, keep=False, expected=pin, audit=audit)
        status.read(path, keep=False, expected=pin, audit=audit)
        self.assertEqual(audit, {'checkpoint_bytes_hashed': 32768, 'checkpoint_files_from_stat_cache': 1})
        path.write_bytes(b'b' * 32768); os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
        with self.assertRaisesRegex(status.StatusHold, 'FILE_SHA'):
            status.read(path, keep=False, expected=pin, audit=audit)

    def test_untrusted_observer_symlink_and_nonfinite_metadata_fail_closed(self):
        path = self.root / 'scripts/owner_qwen_training_observe.py'
        path.write_text('raise AssertionError("must not execute")')
        with self.assertRaisesRegex(status.StatusHold, 'FILE_SHA'):
            status.observer()
        data = self.root / 'bad.json'; data.write_text('{"step": NaN}')
        with self.assertRaisesRegex(status.StatusHold, 'NONFINITE_JSON'):
            status.document(data)
        link = self.root / 'link'; link.symlink_to(data)
        with self.assertRaisesRegex(status.StatusHold, 'PATH'):
            status.read(link)

    def test_real_checkpoint_proof_cache_and_modified_optimizer_rejection(self):
        lineage, _, manifest, _, directory = self.checkpoint_fixture()
        audit = {'checkpoint_bytes_hashed': 0, 'checkpoint_files_from_stat_cache': 0}
        obs = status.observer(audit)
        pin = status.digest((directory / 'checkpoint_manifest.json').read_bytes())
        with patch.object(status, 'BASELINE', self.baseline(lineage, manifest, directory)):
            proof, _, _ = status.checkpoint(obs, self.contract, lineage, directory.name, pin, time.monotonic() + 2)
            self.assertEqual(proof['successful_optimizer_steps'], 5)
            self.assertEqual(proof['skipped_steps'], 0)
            self.assertEqual(proof['checkpoint_file_count'], 9)
            status.checkpoint(obs, self.contract, lineage, directory.name, pin, time.monotonic() + 2)
            self.assertGreaterEqual(audit['checkpoint_files_from_stat_cache'], 9)
            (directory / 'optimizer.pt').write_bytes(b'corrupted optimizer')
            with self.assertRaisesRegex(status.StatusHold, 'FILE_SHA'):
                status.checkpoint(obs, self.contract, lineage, directory.name, pin, time.monotonic() + 2)

    def snapshot_fixture(self, live=False, race=False, failure=False):
        lineage, saved, manifest, terminal, directory = self.checkpoint_fixture()
        fixtures.write(self.output / 'owner_lineage.json', lineage)
        fixtures.write(self.output / 'owner_progress.json', {'pid': 1234, 'successful_optimizer_steps': 5,
                                                          'attempted_steps': 5, 'skipped_steps': 0, 'time': 1})
        obs = status.observer()
        process = {'pid': 9876, 'start_ticks': 5555, 'exact_admitted_argv': True,
                   'cuda_visible_devices_1': True, 'supervisor_ancestry_verified': True}
        service = {'state': 'RUNNING' if live else ('FATAL' if failure else 'EXITED'), 'pid': 8888 if live else None}
        context = dict(status.INITIAL)
        gate = {'goal': 6 if live else 5, 'current_context': context, 'configured_anchor': context,
                'continuation_acceptance_anchor': None, 'pointer_sha256': '1' * 64, 'wrapper_sha256': '2' * 64}
        admitted = ({}, {'student_profile': {'runtime_versions': {'test': True}}}, [], gate)
        flag = {'TRAIN_HOLD.flag': {'present': not live, 'owned_complete': not live and not failure, 'owned_failure': failure},
                'TRAIN_PAUSE_REQUEST.flag': {'present': False}, 'global_stop_present': False}
        calls = [0]
        def admit(*_):
            calls[0] += 1
            if race and calls[0] == 2:
                raise status.StatusHold('HOLD_QWEN_STATUS_ADMISSION_CHANGED')
            return admitted
        with ExitStack() as stack:
            stack.enter_context(patch.object(status, 'BASELINE', self.baseline(lineage, manifest, directory)))
            stack.enter_context(patch.object(status, 'observer', return_value=obs))
            stack.enter_context(patch.object(status, 'admitted', side_effect=admit))
            stack.enter_context(patch.object(status, 'flags', return_value=flag))
            stack.enter_context(patch.object(obs, 'service', return_value=service))
            stack.enter_context(patch.object(obs, 'trainers', return_value=[process] if live else []))
            stack.enter_context(patch.object(obs, 'process', return_value=process))
            result = status.snapshot(context)
        return result

    def test_completed_five_is_positive_saved_progress_without_live_or_restart_claim(self):
        result = self.snapshot_fixture()
        self.assertEqual(result['optimizer_steps'], 5)
        self.assertTrue(result['positive_optimizer_steps_verified'])
        self.assertFalse(result['live_admitted_process_verified'])
        self.assertFalse(result['restart_acceptance_verified'])
        self.assertEqual(result['state'], 'STUDENT_UPDATES_CHECKPOINTED_RESTART_ACCEPTANCE_REQUIRED')

    def test_current_loading_process_keeps_saved_five_and_marks_old_progress_stale(self):
        result = self.snapshot_fixture(live=True)
        self.assertEqual(result['state'], 'RUNNING_CURRENT_QWEN_ADMISSION')
        self.assertEqual(result['optimizer_steps'], 5)
        self.assertTrue(result['live_admitted_process_verified'])
        self.assertFalse(result['current_process_model_loaded_verified'])
        self.assertTrue(result['progress_telemetry']['stale_relative_to_observed_child'])

    def test_owned_failure_remains_failure_even_if_pause_helper_would_accept(self):
        with patch.object(status, 'cooperative_pause', return_value=True):
            result = self.snapshot_fixture(failure=True)
        self.assertEqual(result['state'], 'HELD_AFTER_FAILURE')
        self.assertFalse(result['live_admitted_process_verified'])

    def test_admission_race_cannot_leave_positive_terminal_facts_in_projection(self):
        result = self.snapshot_fixture(race=True)
        self.assertEqual(result['state'], 'UNVERIFIED_ADMISSION')
        self.assertIsNone(result['optimizer_steps'])
        self.assertFalse(result['positive_optimizer_steps_verified'])
        self.assertNotIn('last_terminal', result)
        self.assertNotIn('latest_verified_checkpoint', result)

    def test_zero_new_resume_pause_keeps_prior_manifest_identity_without_acceptance(self):
        lineage, saved, manifest, row, directory = self.checkpoint_fixture()
        row.update(state='EXISTING_TRAINER_HOLD_OR_PAUSE', reload_verified=True,
                   new_successful_optimizer_steps=0, process_identity={**row['process_identity'], 'pid': 7777})
        fixtures.write(self.output / 'owner_last_result.json', row)
        obs = status.observer()
        proof = status.terminal(obs, self.contract, lineage, manifest, saved, time.monotonic() + 2)
        self.assertTrue(proof['zero_new_update_pause_verified'])
        self.assertFalse(proof['restart_acceptance_verified'])
        row['new_successful_optimizer_steps'] = 1; fixtures.write(self.output / 'owner_last_result.json', row)
        with self.assertRaisesRegex(status.StatusHold, 'ZERO_UPDATE_PAUSE_SCOPE'):
            status.terminal(obs, self.contract, lineage, manifest, saved, time.monotonic() + 2)

    def test_pause_classification_requires_verified_fresh_terminal_for_current_admission(self):
        terminal = {'state': 'EXISTING_TRAINER_HOLD_OR_PAUSE', 'terminal_receipt_mtime_ns': 3000000000}
        flags = {'TRAIN_PAUSE_REQUEST.flag': {'present': True, 'mtime_ns': 2000000000}}
        self.assertTrue(status.cooperative_pause(terminal, flags, 1.0))
        self.assertFalse(status.cooperative_pause(terminal, flags, 4.0))
        self.assertFalse(status.cooperative_pause({**terminal, 'state': 'UNVERIFIED_OR_STALE_TERMINAL'}, flags, 1.0))
        self.assertFalse(status.cooperative_pause(terminal, {'TRAIN_PAUSE_REQUEST.flag': {'present': False}}, 1.0))
        self.assertFalse(status.cooperative_pause(terminal, {'TRAIN_PAUSE_REQUEST.flag': {'present': True, 'mtime_ns': 4000000000}}, 1.0))

    def test_old_acceptance_checkpoint_is_checked_separately_from_latest_progress(self):
        lineage, six, m6, row6, d6 = self.checkpoint_fixture(good=6)
        row6.update(state='STUDENT_RESTART_AND_UPDATES_VERIFIED', reload_verified=True)
        fixtures.write(self.output / 'owner_acceptance.json', row6)
        _, seven, m7, _, d7 = self.checkpoint_fixture(good=7)
        obs = status.observer()
        with patch.object(status, 'BASELINE', self.baseline(lineage, m6, d6)):
            proof = status.terminal(obs, self.contract, lineage, m7, seven, time.monotonic() + 2, True)
        self.assertTrue(proof['restart_acceptance_verified'])
        self.assertEqual(proof['successful_optimizer_steps'], 6)
        self.assertEqual(proof['checkpoint_manifest_sha256'], status.digest((d6 / 'checkpoint_manifest.json').read_bytes()))

    def test_ordinary_turn_never_reads_training_and_new_projection_replaces_old_keys(self):
        messages = [{'role': 'user', 'content': '17 * 19'}]
        with patch.object(binding, 'current_training', side_effect=AssertionError('IO forbidden')):
            self.assertIs(binding.augment_messages(messages, '17 * 19'), messages)
        namespace = {'snapshot': lambda: {'training': {'legacy35b_key': True}},
                     'evidence_for_model': lambda *args: {'state': 'OK'}}
        value = {'schema': status.SCHEMA, 'state': 'TEST_QWEN', 'observed_at': 123}
        with patch.object(status, 'snapshot', return_value=value):
            status.bind_self_observation(namespace)
            self.assertNotIn('legacy35b_key', namespace['snapshot']()['training'])

    def admission_fixture(self, target):
        """Owned synthetic receipt tree; pinned source reads are explicit mocks."""
        obs = status.observer()
        original = json.loads(Path('/tmp/nox_qwen_initial_actual_6907283384.json').read_text())
        profile = {**original['student_profile'], 'base_directory': str(self.root / 'state/qwen_memfd'),
                   'output_directory': str(self.output)}
        p5 = {'schema': 'NOX_OWNER_TRAINING_ADMISSION_V1', 'request': status.INITIAL['request'],
              'source_sha': status.INITIAL['source_sha'], 'initial_request': status.INITIAL['request'],
              'student_profile': profile, 'created_at': 1,
              'sources': {str(obs.SCRIPTS / n): s for n, s in obs.PINS.items() if n.endswith('.py')}}
        raw5 = encode(p5); pin5 = status.digest(raw5)
        wrap5 = status.wrapper_bytes(status.arguments(obs, p5['request'], pin5, profile), p5['request'], 5)
        initial = {**original, 'student_profile': profile, 'source_pins': obs.PINS,
                   'admission_sha256': pin5, 'wrapper_sha256': status.digest(wrap5)}
        initial_context = {**status.INITIAL, 'receipt_sha256': status.digest(encode(initial))}
        p6 = {**p5, 'request': status.WINDOW_REQUEST, 'source_sha': status.WINDOW_SOURCE,
              'student_profile': {**profile, 'successful_updates_goal': 6}, 'created_at': 2,
              'previous_request': p5['request'], 'previous_admission_sha256': pin5,
              'accepted_previous_window': status.BASELINE['terminal_sha256']}
        raw6 = encode(p6); pin6 = status.digest(raw6)
        wrap6 = status.wrapper_bytes(status.arguments(obs, p6['request'], pin6, p6['student_profile']), p6['request'], 6)
        r6 = {'schema': 'NOX_QWEN_WINDOW_ADVANCE_V1', 'request': p6['request'], 'source_sha': p6['source_sha'],
              'state': 'WINDOW_STARTED_ACCEPTANCE_PENDING', 'initial_request': p5['request'], 'target_goal': 6,
              'new_admission_sha256': pin6, 'wrapper_sha256': status.digest(wrap6),
              'previous_request': p5['request'], 'previous_admission_sha256': pin5,
              'acceptance': status.previous_acceptance()}
        c6 = {'request': r6['request'], 'source_sha': r6['source_sha'], 'receipt_sha256': status.digest(encode(r6))}
        files = {obs.STATE / ('owner_qwen_install_' + p5['request'] + '.json'): encode(initial),
                 obs.STATE / ('owner_qwen_window_' + p6['request'] + '.json'): encode(r6),
                 self.root / 'backup/owner_qwen_window' / p6['request'] / 'previous_admission.json': raw5,
                 self.root / 'backup/owner_qwen_window' / p6['request'] / 'previous_wrapper.sh': wrap5,
                 obs.STATE / 'owner_training_admission.json': raw6,
                 obs.SCRIPTS / 'run_train_volta_t866u.sh': wrap6}
        if target == 1000:
            name6 = 'checkpoint-u00000006-a00000006-g00000000000000000123'
            certificate = {'checkpoint': str(self.output / name6), 'checkpoint_manifest_sha256': 'a' * 64,
                           'successful_optimizer_steps': 6, 'new_successful_optimizer_steps': 1,
                           'state': 'STUDENT_RESTART_AND_UPDATES_VERIFIED', 'reload_verified': True}
            certificate_raw = encode(certificate); certificate_sha = status.digest(certificate_raw)
            accepted = {'previous_goal': 6, 'target_goal': 1000, 'terminal_receipt_sha256': certificate_sha,
                        'acceptance_sha256': certificate_sha, 'lineage_sha256': status.BASELINE['lineage_sha256'],
                        'checkpoint': {'directory': name6, 'manifest_sha256': 'a' * 64, 'verified_files': 9,
                                       'verified_bytes': 100, 'all_checkpoint_file_sha256_verified': True}}
            p1000 = {**p6, 'request': '999999', 'source_sha': 'a' * 40, 'created_at': 3,
                     'student_profile': {**profile, 'successful_updates_goal': 1000},
                     'previous_request': p6['request'], 'previous_admission_sha256': pin6,
                     'accepted_previous_window': certificate_sha}
            raw = encode(p1000); pin = status.digest(raw)
            wrapper = status.wrapper_bytes(status.arguments(obs, p1000['request'], pin, p1000['student_profile']), p1000['request'], 1000)
            receipt = {**r6, 'request': p1000['request'], 'source_sha': p1000['source_sha'], 'target_goal': 1000,
                       'new_admission_sha256': pin, 'wrapper_sha256': status.digest(wrapper),
                       'previous_request': p6['request'], 'previous_admission_sha256': pin6, 'acceptance': accepted}
            files.update({obs.STATE / 'owner_training_admission.json': raw,
                          obs.SCRIPTS / 'run_train_volta_t866u.sh': wrapper,
                          obs.STATE / ('owner_qwen_window_' + p1000['request'] + '.json'): encode(receipt),
                          self.root / 'backup/owner_qwen_window' / p1000['request'] / 'previous_admission.json': raw6,
                          self.root / 'backup/owner_qwen_window' / p1000['request'] / 'previous_wrapper.sh': wrap6,
                          obs.OUTPUT / 'owner_acceptance.json': certificate_raw})
        def read(path, maximum=2 * 1024 ** 2, *, expected=None, **_):
            path = Path(path)
            if path in files:
                raw = files[path]; pin = status.digest(raw)
                status.require(expected is None or pin == expected, 'FILE_SHA')
                return raw, {'sha256': pin, 'bytes': len(raw)}
            if path.parent == obs.SCRIPTS and path.name in obs.PINS:
                self.assertEqual(expected, obs.PINS[path.name])
                return b'pinned-source-read-fixture', {'sha256': expected}
            raise FileNotFoundError(str(path))
        def document(path, expected=None, maximum=2 * 1024 ** 2):
            raw, meta = read(path, maximum, expected=expected)
            return json.loads(raw), meta
        return obs, c6, files, initial_context, pin5, status.digest(wrap5), read, document

    def run_admission_fixture(self, fixture, context=None):
        obs, anchor, _, initial, pin5, wrapper5, read, document = fixture
        with patch.object(status, 'INITIAL', initial), patch.object(status, 'INITIAL_ADMISSION_SHA', pin5), \
             patch.object(status, 'INITIAL_WRAPPER_SHA', wrapper5), patch.object(status, 'read', side_effect=read), \
             patch.object(status, 'document', side_effect=document):
            return status.admitted(context or anchor, obs)

    def test_actual_goal_six_receipt_chain_binds_to_sealed_context(self):
        fixture = self.admission_fixture(6)
        _, pointer, argv, gate = self.run_admission_fixture(fixture)
        self.assertEqual(gate['goal'], 6)
        self.assertEqual(gate['current_context'], fixture[1])
        self.assertEqual(argv[-1], '--resume')
        bad = {**fixture[1], 'receipt_sha256': '0' * 64}
        with self.assertRaisesRegex(status.StatusHold, 'CONFIGURED_ANCHOR_NOT_IN_CURRENT_CHAIN'):
            self.run_admission_fixture(fixture, bad)

    def test_descendant_thousand_requires_archived_chain_and_exact_six_certificate(self):
        fixture = self.admission_fixture(1000)
        _, _, _, gate = self.run_admission_fixture(fixture)
        self.assertEqual(gate['goal'], 1000)
        self.assertNotEqual(gate['current_context'], fixture[1])
        self.assertIsNotNone(gate['continuation_acceptance_anchor'])
        del fixture[2][fixture[0].OUTPUT / 'owner_acceptance.json']
        with self.assertRaises(FileNotFoundError):
            self.run_admission_fixture(fixture)

    def test_modified_archive_or_foreign_goal_cannot_be_adopted(self):
        fixture = self.admission_fixture(6)
        archive = self.root / 'backup/owner_qwen_window' / status.WINDOW_REQUEST / 'previous_admission.json'
        fixture[2][archive] += b' '
        with self.assertRaisesRegex(status.StatusHold, 'FILE_SHA'):
            self.run_admission_fixture(fixture)
        fixture = self.admission_fixture(1000)
        path = fixture[0].STATE / 'owner_training_admission.json'
        value = json.loads(fixture[2][path]); value['student_profile']['successful_updates_goal'] = 1001
        fixture[2][path] = encode(value)
        with self.assertRaisesRegex(status.StatusHold, 'WINDOW_GOAL'):
            self.run_admission_fixture(fixture)


if __name__ == '__main__':
    unittest.main()
