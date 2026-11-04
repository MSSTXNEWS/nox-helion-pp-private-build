"""U05: frozen E07 owned-file pin is exact; no dynamic receipt waiver."""
from __future__ import annotations
import importlib.util
import sys
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2] / "coordination/e07/independent_setup_e07.py"
spec = importlib.util.spec_from_file_location("nox_e07_frozen_count_u05", SOURCE)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def lifecycle(count=1004):
    obj = {"uninstall_owned_files_checked": count}
    for name in ("install", "verify", "update", "rollback", "uninstall"):
        obj[name] = {"code": 0}
    return obj


class FrozenCountTests(unittest.TestCase):
    def test_old_physical_setup_retains_pinned_count(self):
        self.assertEqual(mod.FROZEN_E06_OWNED_COUNT, 1004)
        self.assertTrue(mod.samevm_lifecycle_verified(lifecycle(1004)))
        self.assertFalse(mod.samevm_lifecycle_verified(lifecycle(1005)))

    def test_future_candidate_requires_explicit_new_pin(self):
        self.assertTrue(mod.samevm_lifecycle_verified(
            lifecycle(1005), expected_owned_files=1005))
        self.assertFalse(mod.samevm_lifecycle_verified(
            lifecycle(1004), expected_owned_files=1005))

    def test_untrusted_count_types_and_limits_rejected(self):
        for value in (None, True, False, 1004.0, "1004", 0, -1, 4097):
            with self.subTest(value=value):
                self.assertFalse(mod.samevm_lifecycle_verified(
                    lifecycle(1004), expected_owned_files=value))
        for count in (None, False, True, "1004", 1004.0):
            with self.subTest(count=count):
                self.assertFalse(mod.samevm_lifecycle_verified(lifecycle(count)))

    def test_missing_or_fake_lifecycle_exits_rejected(self):
        self.assertFalse(mod.samevm_lifecycle_verified(None))
        for name in ("install", "verify", "update", "rollback", "uninstall"):
            for value in (None, {"code": True}, {"code": "0"}, {"code": 1}):
                with self.subTest(name=name, value=value):
                    obj = lifecycle()
                    obj[name] = value
                    self.assertFalse(mod.samevm_lifecycle_verified(obj))


if __name__ == "__main__":
    unittest.main()
