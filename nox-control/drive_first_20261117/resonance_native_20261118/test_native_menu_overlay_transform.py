"""Targeted tests for the new exact-delta primitive; never imports NOX."""
import hashlib
from pathlib import Path
import unittest
from unittest import mock

import native_menu_overlay_transform as patch


HERE = Path(__file__).resolve().parent
REFRESH = HERE.parent
HISTORICAL = REFRESH / 'history_contract_reuse/candidates/native_v29_bridge_432b6195.py'
RAW_UI = REFRESH / 'web29_original_chat_audit_20261117/source_v13/site/nox-ui.js'
EXPECTED = REFRESH / 'new_resonance_audit_20261117/menu_overlay_fix/historical_native_v29_bridge.candidate.py'
HISTORICAL_SHA = '3cd548a69ac0fa7128368bef77f5f7ef032359128cf723eaca1c6a0514c85dc6'
EXPECTED_SHA = '612da90c9675d16a5d38572206423e22bff1c6e983a602368f59297d864ae346'


class ExactMenuDeltaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = HISTORICAL.read_bytes()
        cls.raw_ui = RAW_UI.read_bytes()
        cls.expected = EXPECTED.read_bytes()
        if patch.sha256(cls.before) != HISTORICAL_SHA or patch.sha256(cls.expected) != EXPECTED_SHA:
            raise RuntimeError('HOLD_HISTORICAL_TEST_FIXTURE_SHA')
        if patch.sha256(cls.raw_ui) != patch.FROZEN_UI_SHA256:
            raise RuntimeError('HOLD_TEST_UI_SHA')

    def fixture_pins(self):
        # Test-only pin substitution exercises the public code on a known fixture.
        # The production module has no selectable preimage/pin parameter.
        return mock.patch.multiple(patch, BRIDGE_BEFORE_SHA256=HISTORICAL_SHA,
                                   BRIDGE_BEFORE_BYTES=len(self.before),
                                   BRIDGE_AFTER_SHA256=EXPECTED_SHA,
                                   BRIDGE_AFTER_BYTES=len(self.expected))

    def test_structural_result_equals_previously_reviewed_candidate_byte_for_byte(self):
        self.assertEqual(patch._splice_tuple_bytes(self.before), self.expected)
        self.assertEqual(len(self.expected) - len(self.before), len(patch.INSERTION))

    def test_public_fixed_entry_rejects_historical_file_and_invalid_types(self):
        with self.assertRaisesRegex(patch.PatchHold, 'HOLD_MENU_BRIDGE_PREIMAGE'):
            patch.transform(self.before, self.raw_ui)
        for raw, ui, rollback in [(None, self.raw_ui, False),
                                  (self.before, 'text', False),
                                  (self.before, self.raw_ui, 1)]:
            with self.subTest(rollback=rollback, raw_type=type(raw)):
                with self.assertRaisesRegex(patch.PatchHold, 'HOLD_MENU_INPUT_TYPE'):
                    patch.transform(raw, ui, rollback=rollback)

    def test_forward_reverse_and_served_delta_on_verified_fixture(self):
        with self.fixture_pins():
            prepared = patch.transform(self.before, self.raw_ui)
            self.assertEqual(prepared, self.expected)
            self.assertEqual(patch.transform(prepared, self.raw_ui, rollback=True), self.before)
            receipt = patch.describe(self.before, self.raw_ui)
            self.assertEqual(receipt['after_sha256'], EXPECTED_SHA)
            self.assertEqual(receipt['served_after_sha256'], patch.SERVED_AFTER_SHA256)
            self.assertFalse(receipt['native_installed'])

    def test_rollback_refuses_unrelated_edit_and_duplicate_insertion(self):
        with self.fixture_pins():
            prepared = patch.transform(self.before, self.raw_ui)
            changed = prepared.replace(b'asyncio', b'zzzzzzz', 1)
            self.assertEqual(len(changed), len(prepared))
            with self.assertRaisesRegex(patch.PatchHold, 'HOLD_MENU_ROLLBACK_PREIMAGE'):
                patch.transform(changed, self.raw_ui, rollback=True)
            with self.assertRaisesRegex(patch.PatchHold, 'HOLD_MENU_ROLLBACK_LAYOUT'):
                patch.transform(prepared + patch.INSERTION, self.raw_ui, rollback=True)

    def test_ui_pin_and_forward_source_pin_fail_closed(self):
        with self.fixture_pins():
            with self.assertRaisesRegex(patch.PatchHold, 'HOLD_MENU_FROZEN_UI_BYTES'):
                patch.transform(self.before, self.raw_ui + b'\n')
            changed = self.before.replace(b'asyncio', b'zzzzzzz', 1)
            with self.assertRaisesRegex(patch.PatchHold, 'HOLD_MENU_BRIDGE_PREIMAGE'):
                patch.transform(changed, self.raw_ui)

    def test_primitive_rejects_repeated_addition_or_wrong_tuple_layout(self):
        with self.assertRaisesRegex(patch.PatchHold, 'HOLD_MENU_BASE_OVERLAY_CHANGED'):
            patch._splice_tuple_bytes(self.expected)
        altered = self.before.replace(b'    ),\n)\n\n\ndef _overlay_v122_owner_ui',
                                      b'    ),\n )\n\n\ndef _overlay_v122_owner_ui', 1)
        self.assertNotEqual(altered, self.before)
        with self.assertRaisesRegex(patch.PatchHold, 'HOLD_MENU_TUPLE_CLOSING_LAYOUT'):
            patch._splice_tuple_bytes(altered)

    def test_utf8_prefix_preserves_exact_byte_splice(self):
        prefix = '# Точное смещение UTF-8\n'.encode()
        self.assertEqual(patch._splice_tuple_bytes(prefix + self.before), prefix + self.expected)


if __name__ == '__main__':
    unittest.main()
