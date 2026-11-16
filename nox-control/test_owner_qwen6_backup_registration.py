"""Source-only CP6 envelope and manual registration gates; no owner key or network."""
import contextlib
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

import owner_qwen6_backup_stream as core
import owner_qwen6_backup_runner as runner


PROPOSAL = runner.REPOSITORY / 'coordination/onepass/nox-v61-qwen6-main-registration.yml'
OLD_PUBLIC_SHA = 'd96382c13bd039dcd85551c36b68bebde4e5b7d93d4a711b30ce75c05d93dc32'
OLD_RUNNER_SHA = 'e3a5b8193a0353c188dc1d6872671964e62248a7d0b08e5bd42a8562e9af11f4'


class RegistrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.event_path = Path(self.temporary.name) / 'synthetic-owner-dispatch.json'
        self.source = 'a' * 40
        self.event = {
            'inputs': {'allow_native': 'YES', 'checkpoint_scope': 'QWEN6', 'source_sha': self.source},
            'sender': {'id': runner.OWNER_ID},
            'repository': {'owner': {'id': runner.OWNER_ID}},
        }
        self.env = {
            'GITHUB_EVENT_PATH': str(self.event_path), 'GITHUB_EVENT_NAME': 'workflow_dispatch',
            'GITHUB_REPOSITORY': runner.REPO, 'GITHUB_ACTOR': 'MSSTXNEWS',
            'GITHUB_ACTOR_ID': str(runner.OWNER_ID), 'GITHUB_RUN_ATTEMPT': '1',
            'NOX_PINNED_SOURCE_SHA': self.source, 'GITHUB_SHA': self.source, 'GITHUB_RUN_ID': '123',
            'GITHUB_WORKFLOW_REF': runner.REPO + '/' + runner.WORKFLOW + '@refs/heads/reviewed-cp6-export',
        }

    def tearDown(self):
        self.temporary.cleanup()

    def invoke_authorization(self, *, env=None, event=None, checkout=None):
        self.event_path.write_text(json.dumps(event or self.event))
        with patch.dict(os.environ, env or self.env, clear=True), \
                patch.object(runner.subprocess, 'check_output', return_value=(checkout or self.source) + '\n'):
            return runner.authorize_event()

    def test_refreshed_envelope_changes_only_freshness_and_transfer_identity(self):
        raw = (runner.REPOSITORY / 'nox-control/owner_qwen6_backup_public.json').read_bytes()
        metadata = core.document(raw)
        self.assertEqual(core.digest(raw), runner.PUBLIC_SHA)
        self.assertEqual(metadata['expires_at'] - metadata['created_at'], core.MAX_KEY_TTL)
        self.assertEqual(core.MAX_KEY_TTL, 7200)
        self.assertNotEqual(metadata['transfer_id'], '613dadde21e7349f4d73aa695b6ed82f')
        previous = dict(metadata, created_at=1794807584, expires_at=1794814784,
                        transfer_id='613dadde21e7349f4d73aa695b6ed82f')
        self.assertEqual(core.digest(core.canonical(previous) + b'\n'), OLD_PUBLIC_SHA)
        core.public_key(metadata, now=metadata['created_at'])
        core.public_key(metadata, now=metadata['expires_at'])
        with self.assertRaisesRegex(core.Hold, 'PUBLIC_KEY_EXPIRED'):
            core.public_key(metadata, now=metadata['expires_at'] + 1)

    def test_runner_delta_is_only_public_metadata_pin(self):
        source = Path(runner.__file__).read_bytes()
        line = ('PUBLIC_SHA = ' + repr(runner.PUBLIC_SHA)).encode()
        self.assertEqual(source.count(line), 1)
        original = source.replace(line, ('PUBLIC_SHA = ' + repr(OLD_PUBLIC_SHA)).encode(), 1)
        self.assertEqual(core.digest(original), OLD_RUNNER_SHA)

    def test_frozen_crypto_local_verifier_and_feature_workflow_preserved(self):
        pins = {
            'nox-control/owner_qwen6_backup_stream.py': 'e9a78cd60c5cada7d9f3df5ce82c872bd11b805e8d31aee4707983a94d01c353',
            'nox-control/owner_qwen6_backup_local.py': 'e0230fc066f8538e62800537898956e2c97a0cd1088dcf8d67d225482ed9beeb',
            runner.WORKFLOW: 'cb377ecf9983a780d45f50e6b95c1c801b38b379d0fca69653dd380ff64d4556',
        }
        for path, expected in pins.items():
            with self.subTest(path=path):
                self.assertEqual(core.digest((runner.REPOSITORY / path).read_bytes()), expected)

    def test_manual_owner_first_attempt_exact_stable_source_authorizes(self):
        self.assertEqual(self.invoke_authorization(), (self.source, '123'))

    def test_push_rerun_and_wrong_owner_or_source_never_authorize(self):
        variants = [
            {'GITHUB_EVENT_NAME': 'push'}, {'GITHUB_EVENT_NAME': 'issue_comment'},
            {'GITHUB_RUN_ATTEMPT': '2'}, {'GITHUB_ACTOR': 'another-owner'},
            {'GITHUB_ACTOR_ID': '1'}, {'GITHUB_SHA': 'b' * 40},
            {'NOX_PINNED_SOURCE_SHA': 'b' * 40},
            {'GITHUB_WORKFLOW_REF': runner.REPO + '/.github/workflows/another.yml@refs/heads/main'},
        ]
        for delta in variants:
            with self.subTest(delta=delta), self.assertRaises(core.Hold):
                self.invoke_authorization(env={**self.env, **delta})
        with self.assertRaisesRegex(core.Hold, 'CHECKOUT_SHA'):
            self.invoke_authorization(checkout='b' * 40)
        for delta in [{'allow_native': 'NO'}, {'checkpoint_scope': 'LEGACY'}, {'source_sha': 'b' * 40}]:
            event = {**self.event, 'inputs': {**self.event['inputs'], **delta}}
            with self.subTest(inputs=delta), self.assertRaises(core.Hold):
                self.invoke_authorization(event=event)

    def test_expired_package_stops_before_authentication_and_native(self):
        metadata = core.document((runner.REPOSITORY / 'nox-control/owner_qwen6_backup_public.json').read_bytes())
        self.event_path.write_text(json.dumps(self.event))
        with patch.dict(os.environ, self.env, clear=True), \
                patch.object(runner.subprocess, 'check_output', return_value=self.source + '\n'), \
                patch.object(runner.time, 'time', return_value=metadata['expires_at'] + 1), \
                patch.object(sys, 'argv', ['source-only-test', '--native']), \
                patch.object(runner, 'authentication_namespace') as authentication, \
                patch.object(runner, 'receive') as receive, patch.object(runner, 'cleanup') as cleanup, \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(runner.main(), 2)
        authentication.assert_not_called()
        receive.assert_not_called()
        cleanup.assert_not_called()
        self.assertEqual(output.getvalue().strip(), 'HOLD_QWEN6_BACKUP_PUBLIC_KEY_EXPIRED')

    def test_registration_is_manual_only_and_job_is_exact_existing_qwen_job(self):
        proposal = PROPOSAL.read_text()
        workflow = (runner.REPOSITORY / runner.WORKFLOW).read_text()
        header = proposal.split('permissions:\n', 1)[0]
        self.assertEqual(re.findall(r'^  ([a-z_]+):$', header, re.M), ['workflow_dispatch'])
        self.assertIn("options: ['QWEN6']\n        default: 'QWEN6'", header)
        self.assertIn("default: 'NO'", header)
        self.assertRegex(header, r'(?s)      source_sha:.*?        required: true\n$')
        self.assertNotIn('LEGACY', proposal)
        self.assertEqual(re.findall(r'^  ([a-z0-9-]+):$', proposal.split('jobs:\n', 1)[1], re.M), ['qwen6-export'])
        self.assertEqual(proposal.split('  qwen6-export:', 1)[1], workflow.split('  qwen6-export:', 1)[1])

    def test_registration_uploads_only_seven_cipher_parts_and_checksum_receipt(self):
        proposal = PROPOSAL.read_text()
        paths = re.findall(r'^          path: (.+)$', proposal, re.M)
        expected = ['artifacts/qwen6-checkpoint-backup/qwen6-cipher.part' + f'{i:03d}' for i in range(7)]
        expected.append('artifacts/qwen6-checkpoint-backup/QWEN6_CIPHER_RECEIPT.json')
        self.assertEqual(paths, expected)
        self.assertEqual(proposal.count('uses: actions/upload-artifact@v4'), 8)
        self.assertEqual(proposal.count('compression-level: 0'), 8)
        self.assertEqual(proposal.count('retention-days: 7'), 8)
        self.assertEqual(proposal.count('if-no-files-found: error'), 8)


if __name__ == '__main__':
    unittest.main()
