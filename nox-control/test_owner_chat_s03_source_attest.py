"""Offline safety tests for the fixed chat/S03 source attestation."""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import owner_chat_s03_source_attest as ATTEST
from test_owner_native_operator_source_attest import OwnerSourceAttestOperatorTests


CHAT_SOURCE = '''
import s03_memory as memory_api
from s03_memory import remember as remember_s03

def handle_turn(user_text):
    marker = "SOURCE_LITERAL_SENTINEL"
    memory_api.remember(user_text, marker=marker)
    return remember_s03(user_text)
'''

MEMORY_SOURCE = '''
def remember(dialog_id, text="DEFAULT_LITERAL_SENTINEL", /, *, source="KW_LITERAL_SENTINEL") -> str:
    query = "INSERT INTO s03_items(text) VALUES (?) -- SQL_LITERAL_SENTINEL"
    with open("/secret/source/path", "a") as stream:
        stream.write(text)
    conn.execute(query, (text,))
    conn.commit()
    return "RETURN_LITERAL_SENTINEL"

def unrelated_read(key):
    return lookup(key)
'''


class SourceAttestTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.root = self.base / 'nox'
        (self.root / 'scripts').mkdir(parents=True)
        self.chat = self.root / 'scripts/chat_proxy.py'
        self.memory = self.root / 'scripts/s03_memory.py'
        self.chat.write_text(CHAT_SOURCE, encoding='utf-8')
        self.memory.write_text(MEMORY_SOURCE, encoding='utf-8')

    def report(self):
        return ATTEST.attest_sources(self.root)

    def test_fixed_pair_sha_and_writer_signatures_are_structural_only(self):
        report = self.report()
        self.assertTrue(report['complete'])
        self.assertEqual(report['status'], 'SOURCE_STATIC_ATTESTED')
        self.assertEqual([row['relative_path'] for row in report['targets']],
                         ['scripts/chat_proxy.py', 'scripts/s03_memory.py'])
        self.assertTrue(all(len(row['sha256']) == 64 for row in report['targets']))
        proxy, memory = report['targets']
        self.assertEqual({row['kind'] for row in proxy['imports']}, {'module', 'symbol'})
        self.assertEqual({row['symbol'] for row in proxy['call_sites']}, {'remember'})
        writer = next(row for row in memory['writer_signatures']
                      if row['qualname'] == 'remember')
        self.assertEqual(writer['posonly'], ['dialog_id', 'text'])
        self.assertEqual(writer['kwonly'], ['source'])
        self.assertEqual(writer['posonly_has_default'], [False, True])
        self.assertEqual(writer['positional_has_default'], [])
        self.assertTrue(writer['return_annotation_present'])
        self.assertIn('s03_table_dml', writer['candidate_reasons'])
        self.assertTrue(writer['commit_call'])
        self.assertEqual(report['chat_to_s03_writer_links'], [writer])
        self.assertFalse(report['guarantees']['target_modules_imported'])
        self.assertFalse(report['guarantees']['target_code_executed'])
        self.assertFalse(report['guarantees']['database_opened'])
        self.assertFalse(report['guarantees']['chat_rows_read'])

    def test_source_literals_paths_sql_and_return_values_are_never_emitted(self):
        rendered = json.dumps(self.report(), sort_keys=True)
        for forbidden in (
            'SOURCE_LITERAL_SENTINEL', 'DEFAULT_LITERAL_SENTINEL',
            'KW_LITERAL_SENTINEL', 'SQL_LITERAL_SENTINEL',
            'RETURN_LITERAL_SENTINEL', '/secret/source/path',
            'INSERT INTO s03_items', 'VALUES (?)',
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, rendered)

    def test_target_modules_are_not_imported_or_executed(self):
        real_import = __import__

        def reject_target_import(name, *args, **kwargs):
            if name.split('.', 1)[0] in {'chat_proxy', 's03_memory'}:
                raise AssertionError('target module import')
            return real_import(name, *args, **kwargs)

        with patch('builtins.__import__', side_effect=reject_target_import):
            report = ATTEST.attest_sources(self.root)
        self.assertTrue(report['complete'])
        self.assertFalse(report['guarantees']['target_modules_imported'])

    def test_leaf_symlink_fails_closed_without_reading_target(self):
        outside = self.base / 'outside.py'
        outside.write_text(CHAT_SOURCE, encoding='utf-8')
        self.chat.unlink()
        self.chat.symlink_to(outside)
        report = self.report()
        self.assertFalse(report['complete'])
        self.assertEqual(report['targets'][0]['status'], 'HOLD_SYMLINK')
        self.assertNotIn('sha256', report['targets'][0])

    def test_parent_symlink_fails_closed_without_reading_target(self):
        outside = self.base / 'outside'
        outside.mkdir()
        (outside / 'chat_proxy.py').write_text(CHAT_SOURCE, encoding='utf-8')
        (outside / 's03_memory.py').write_text(MEMORY_SOURCE, encoding='utf-8')
        scripts = self.root / 'scripts'
        scripts.rename(self.root / 'scripts_real')
        scripts.symlink_to(outside, target_is_directory=True)
        report = self.report()
        self.assertFalse(report['complete'])
        self.assertEqual(report['targets'][0]['status'], 'HOLD_SYMLINK')
        self.assertEqual(report['targets'][1]['status'], 'HOLD_SYMLINK')

    def test_oversized_file_fails_closed_before_ast_parse(self):
        self.chat.write_bytes(b'x' * (ATTEST.MAX_SOURCE_BYTES + 1))
        report = self.report()
        self.assertFalse(report['complete'])
        self.assertEqual(report['targets'][0]['status'], 'HOLD_SOURCE_OVERSIZED')
        self.assertNotIn('sha256', report['targets'][0])

    def test_invalid_utf8_and_syntax_have_explicit_states(self):
        self.chat.write_bytes(b'\xff\xfe')
        invalid_utf8 = self.report()
        self.assertEqual(invalid_utf8['targets'][0]['status'], 'HOLD_SOURCE_INVALID_UTF8')
        self.chat.write_text('def broken(:\n', encoding='utf-8')
        invalid_ast = self.report()
        self.assertEqual(invalid_ast['targets'][0]['status'], 'HOLD_AST_INVALID')
        self.assertEqual(len(invalid_ast['targets'][0]['sha256']), 64)
        self.assertNotIn('broken', json.dumps(invalid_ast))

    def test_ast_node_budget_has_explicit_hold(self):
        with patch.object(ATTEST, 'MAX_AST_NODES', 1):
            report = self.report()
        self.assertEqual(report['targets'][0]['status'], 'HOLD_AST_LIMIT')
        self.assertFalse(report['complete'])

    def test_in_place_change_during_read_fails_closed(self):
        original_read = os.read
        changed = False

        def racing_read(fd, count):
            nonlocal changed
            data = original_read(fd, count)
            if not changed:
                changed = True
                self.chat.write_text(CHAT_SOURCE.replace('handle_turn', 'changed_turn'), encoding='utf-8')
            return data

        with patch.object(ATTEST.os, 'read', side_effect=racing_read):
            report = self.report()
        self.assertEqual(report['targets'][0]['status'], 'HOLD_SOURCE_CHANGED_DURING_READ')
        self.assertFalse(report['complete'])

    def test_leaf_replaced_during_read_fails_path_binding(self):
        original_read = os.read
        replaced = False

        def racing_read(fd, count):
            nonlocal replaced
            data = original_read(fd, count)
            if not replaced:
                replaced = True
                replacement = self.base / 'replacement.py'
                replacement.write_text(CHAT_SOURCE.replace('handle_turn', 'replacement_turn'), encoding='utf-8')
                os.replace(replacement, self.chat)
            return data

        with patch.object(ATTEST.os, 'read', side_effect=racing_read):
            report = self.report()
        self.assertIn(report['targets'][0]['status'],
                      {'HOLD_SOURCE_PATH_CHANGED', 'HOLD_SOURCE_CHANGED_DURING_READ'})
        self.assertFalse(report['complete'])

    def test_missing_target_and_non_allowlisted_path_fail_closed(self):
        self.memory.unlink()
        report = self.report()
        self.assertEqual(report['targets'][1]['status'], 'HOLD_FILE_MISSING')
        with self.assertRaisesRegex(ATTEST.Hold, 'HOLD_TARGET_NOT_ALLOWLISTED'):
            ATTEST._safe_read(self.root, 'scripts/another.py')

    def test_unrelated_generic_getattr_does_not_mask_verified_s03_link(self):
        self.chat.write_text(CHAT_SOURCE + """
def unrelated_preferences(config):
    return getattr(config, 'theme', 'dark')
""", encoding='utf-8')
        report = self.report()
        self.assertTrue(report['complete'])
        self.assertFalse(report['targets'][0]['dynamic_access_detected'])
        self.assertEqual(report['status'], 'SOURCE_STATIC_ATTESTED')

    def test_dynamic_getattr_to_s03_still_fails_closed(self):
        for expression in (
            'getattr(memory_api, "remember")',
            'getattr(memory_api, writer_symbol)',
            'getattr(unknown_module, "persist_turn")',
            'getattr(unknown_module, "ledger_append")',
        ):
            with self.subTest(expression=expression):
                self.chat.write_text(CHAT_SOURCE + "\n" + expression + "\n",
                                     encoding='utf-8')
                report = self.report()
                self.assertFalse(report['complete'])
                self.assertTrue(report['targets'][0]['dynamic_access_detected'])
                self.assertEqual(report['status'], 'HOLD_STATIC_WRITER_LINK_INCOMPLETE')

    def test_dynamic_route_or_unmatched_writer_does_not_claim_complete(self):
        self.chat.write_text('import importlib\nmodule = importlib.import_module("s03_memory")\n', encoding='utf-8')
        report = self.report()
        self.assertFalse(report['complete'])
        self.assertEqual(report['status'], 'HOLD_STATIC_WRITER_LINK_INCOMPLETE')
        self.assertTrue(report['targets'][0]['dynamic_access_detected'])

        self.chat.write_text('from importlib import import_module as load\nmodule = load("s03_memory")\n',
                             encoding='utf-8')
        alias_dynamic = self.report()
        self.assertFalse(alias_dynamic['complete'])
        self.assertTrue(alias_dynamic['targets'][0]['dynamic_access_detected'])

    def test_emitted_cli_line_is_bounded_and_holds_on_missing_files(self):
        self.memory.unlink()
        output = io.StringIO()
        with patch.object(ATTEST, 'ROOT', self.root), contextlib.redirect_stdout(output):
            code = ATTEST.main()
        lines = output.getvalue().splitlines()
        self.assertEqual(code, 2)
        self.assertEqual(len(lines), 2)
        self.assertTrue(all(len(line.encode('utf-8')) < ATTEST.MAX_REPORT_BYTES for line in lines))
        self.assertEqual(lines[-1], 'NOX_MAINT_SOURCE_ATTESTATION_COMPLETE=false')

    def test_unexpected_cli_failure_is_sanitized_without_traceback(self):
        output = io.StringIO()
        with patch.object(ATTEST, 'attest_sources', side_effect=RuntimeError('SECRET_TRACEBACK_SENTINEL')), \
             contextlib.redirect_stdout(output):
            code = ATTEST.main()
        self.assertEqual(code, 2)
        self.assertNotIn('SECRET_TRACEBACK_SENTINEL', output.getvalue())
        self.assertNotIn('Traceback', output.getvalue())
        self.assertIn('HOLD_SOURCE_ATTESTATION_INTERNAL', output.getvalue())


if __name__ == '__main__':
    unittest.main()
