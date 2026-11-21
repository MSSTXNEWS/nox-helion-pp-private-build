"""Offline allowlist and output-schema tests for the fixed source-attest action."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import owner_chat_s03_source_attest as ATTEST
import owner_native_operator as OP


CHAT_SOURCE = '''
import s03_memory as memory_api

def handle_turn(user_text):
    return memory_api.remember(user_text)
'''

MEMORY_SOURCE = '''
def remember(dialog_id, text):
    query = "INSERT INTO s03_items(text) VALUES (?) -- SQL_SENTINEL"
    conn.execute(query, (text,))
    conn.commit()
'''


def _report(chat=CHAT_SOURCE):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory) / 'nox'
        scripts = root / 'scripts'
        scripts.mkdir(parents=True)
        (scripts / 'chat_proxy.py').write_text(chat, encoding='utf-8')
        (scripts / 's03_memory.py').write_text(MEMORY_SOURCE, encoding='utf-8')
        return ATTEST.attest_sources(root)


def _stdout(report, complete=None):
    if complete is None:
        complete = report.get('complete') is True
    encoded = json.dumps(report, ensure_ascii=True, sort_keys=True, separators=(',', ':'))
    suffix = 'true' if complete else 'false'
    return (OP.SOURCE_ATTEST_MARKER + encoded + '\n'
            + 'NOX_MAINT_SOURCE_ATTESTATION_COMPLETE=' + suffix)


class OwnerSourceAttestOperatorTests(unittest.TestCase):
    def assert_hold(self, stdout):
        with self.assertRaisesRegex(RuntimeError, 'HOLD_SOURCE_ATTESTATION_REPORT_SCHEMA'):
            OP.forward_source_attestation_stdout(stdout)

    def test_fixed_mapping_and_cli_enum_accept_only_source_attest(self):
        self.assertEqual(OP.FILES['source_attest'],
                         'nox-control/owner_chat_s03_source_attest.py')
        self.assertEqual(OP.operator_argument_parser().parse_args(['source_attest']).action,
                         'source_attest')
        with mock.patch('sys.stderr'):
            with self.assertRaises(SystemExit):
                OP.operator_argument_parser().parse_args(['arbitrary_action'])

    def test_owner_authorization_accepts_fixed_action_and_rejects_unknown(self):
        sha = 'b' * 40
        event = {
            'comment': {'id': 12345, 'user': {'id': OP.OWNER_ID},
                        'author_association': 'OWNER',
                        'body': f'/nox-maintain {OP.INSTANCE} {sha} source_attest'},
            'repository': {'owner': {'id': OP.OWNER_ID}},
            'issue': {'number': 256}, 'sender': {'id': OP.OWNER_ID},
        }
        with tempfile.TemporaryDirectory() as directory:
            event_path = Path(directory) / 'event.json'
            event_path.write_text(json.dumps(event), encoding='utf-8')
            env = {'GITHUB_EVENT_PATH': str(event_path),
                   'GITHUB_REPOSITORY': OP.REPO,
                   'GITHUB_EVENT_NAME': 'issue_comment',
                   'NOX_PINNED_SOURCE_SHA': sha}
            with mock.patch.dict(os.environ, env, clear=False), \
                 mock.patch.object(OP.subprocess, 'check_output', return_value=sha + '\n'):
                self.assertEqual(OP.authorize_event('source_attest'), 12345)
                with self.assertRaisesRegex(RuntimeError, 'HOLD_ACTION_NOT_ALLOWLISTED'):
                    OP.authorize_event('unlisted')

    def test_valid_report_is_forwarded_as_two_exact_lines(self):
        report = _report()
        self.assertTrue(report['complete'])
        lines, accepted = OP.forward_source_attestation_stdout(_stdout(report))
        self.assertEqual(accepted, report)
        self.assertEqual(lines[1], OP.SOURCE_ATTEST_COMPLETE_TRUE)
        self.assertEqual(len(lines), 2)
        rendered = '\n'.join(lines)
        self.assertNotIn('SQL_SENTINEL', rendered)
        self.assertNotIn('INSERT INTO', rendered)

    def test_explicit_incomplete_report_is_forwardable_only_as_false(self):
        chat = 'import importlib\nmodule = importlib.import_module("s03_memory")\n'
        report = _report(chat)
        self.assertFalse(report['complete'])
        lines, accepted = OP.forward_source_attestation_stdout(_stdout(report))
        self.assertEqual(accepted['status'], 'HOLD_STATIC_WRITER_LINK_INCOMPLETE')
        self.assertEqual(lines[1], OP.SOURCE_ATTEST_COMPLETE_FALSE)
        self.assert_hold(_stdout(report, complete=True))

    def test_minimal_sanitized_hold_report_is_allowed_as_failure_receipt(self):
        report = {'schema': OP.SOURCE_ATTEST_SCHEMA,
                  'status': 'HOLD_SOURCE_UNREADABLE', 'complete': False}
        lines, accepted = OP.forward_source_attestation_stdout(_stdout(report))
        self.assertEqual(accepted, report)
        self.assertEqual(lines[1], OP.SOURCE_ATTEST_COMPLETE_FALSE)

        oversized = {'schema': OP.SOURCE_ATTEST_SCHEMA,
                     'status': 'HOLD_REPORT_OVERSIZED', 'complete': False,
                     'targets': [], 'guarantees': copy.deepcopy(OP.SOURCE_ATTEST_GUARANTEES)}
        self.assertEqual(OP.forward_source_attestation_stdout(_stdout(oversized))[1], oversized)
        oversized['status'] = 'HOLD_OTHER'
        self.assert_hold(_stdout(oversized))

    def test_extra_duplicate_missing_or_nonterminal_markers_hold(self):
        valid = _stdout(_report())
        lines = valid.splitlines()
        for invalid in (
            valid + '\nNOX_MAINT_UNEXPECTED=x',
            lines[0] + '\n' + lines[0] + '\n' + lines[1],
            lines[0],
            lines[0] + '\nNOX_MAINT_UNEXPECTED=x\n' + lines[1],
            lines[0] + '\n' + lines[1] + '\n\n',
            lines[0] + '\n' + lines[1] + '\ntrailing output',
        ):
            with self.subTest(invalid=invalid[-80:]):
                self.assert_hold(invalid)

    def test_malformed_json_duplicate_keys_and_oversize_hold(self):
        for payload in (
            '{not-json}',
            '{"schema":"NOX_CHAT_S03_SOURCE_ATTESTATION_V1",'
            '"status":"HOLD_SOURCE_UNREADABLE","complete":false,"complete":false}',
        ):
            with self.subTest(payload=payload):
                self.assert_hold(OP.SOURCE_ATTEST_MARKER + payload + '\n'
                                 + OP.SOURCE_ATTEST_COMPLETE_FALSE)
        oversized = OP.SOURCE_ATTEST_MARKER + ('x' * OP.SOURCE_ATTEST_MAX_LINE_BYTES) \
            + '\n' + OP.SOURCE_ATTEST_COMPLETE_FALSE
        self.assert_hold(oversized)

    def test_unknown_keys_wrong_order_path_and_hash_hold(self):
        report = _report()
        changed = copy.deepcopy(report)
        changed['unapproved'] = 'SECRET_SENTINEL'
        self.assert_hold(_stdout(changed))

        changed = copy.deepcopy(report)
        changed['targets'].reverse()
        self.assert_hold(_stdout(changed))

        changed = copy.deepcopy(report)
        changed['targets'][0]['relative_path'] = '/root/nox/scripts/chat_proxy.py'
        self.assert_hold(_stdout(changed))

        changed = copy.deepcopy(report)
        changed['targets'][1]['sha256'] = 'not-a-hash'
        self.assert_hold(_stdout(changed))

        changed = copy.deepcopy(report)
        changed['guarantees']['database_opened'] = True
        self.assert_hold(_stdout(changed))

        changed = copy.deepcopy(report)
        changed['guarantees']['target_paths_fixed'] = 1
        self.assert_hold(_stdout(changed))

    def test_secret_like_identifiers_and_unknown_signature_fields_hold(self):
        report = _report()
        changed = copy.deepcopy(report)
        changed['targets'][1]['writer_signatures'][0]['positional'][1] = 'api_key'
        changed['chat_to_s03_writer_links'][0]['positional'][1] = 'api_key'
        self.assert_hold(_stdout(changed))

        changed = copy.deepcopy(report)
        changed['targets'][1]['writer_signatures'][0]['source'] = 'SOURCE_SENTINEL'
        self.assert_hold(_stdout(changed))

    def test_success_status_requires_complete_static_link_and_exact_guarantees(self):
        report = _report()
        changed = copy.deepcopy(report)
        changed['targets'][0]['static_scope_complete'] = False
        self.assert_hold(_stdout(changed))

        changed = copy.deepcopy(report)
        changed['chat_to_s03_writer_links'] = []
        self.assert_hold(_stdout(changed))

        changed = copy.deepcopy(report)
        changed['status'] = 'HOLD_STATIC_WRITER_LINK_INCOMPLETE'
        self.assert_hold(_stdout(changed))


if __name__ == '__main__':
    unittest.main()
