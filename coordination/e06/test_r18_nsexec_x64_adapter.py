"""E06 R18 isolated adapter tests. No Windows, model downloads or owner file writes."""
import importlib.util
import pathlib
import unittest

HERE = pathlib.Path(__file__).resolve().parent
ADAPTER = HERE / "r18_nsexec_x64_adapter.py"
spec = importlib.util.spec_from_file_location("r18_adapter", ADAPTER)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class R18StaticNoLossTests(unittest.TestCase):
    def setUp(self):
        self.original = (
            "Section\n"
            + "  " + mod.OLD + " -File preflight.ps1'\n"
            + "  " + mod.OLD + " -File verify.ps1'\n"
            + "  " + mod.OLD + " -File remove.ps1'\n"
            + "SectionEnd\n"
        ).encode()

    def test_exact_three_calls_only(self):
        post, patch = mod.patch_bytes(self.original)
        self.assertEqual(post.count(mod.NEW.encode()), 3)
        self.assertNotIn(mod.OLD.encode(), post)
        self.assertEqual(post.replace(mod.NEW.encode(), mod.OLD.encode()), self.original)
        self.assertTrue(patch.startswith(b"--- owner1-immutable/"))

    def test_fail_closed_missing_call(self):
        with self.assertRaisesRegex(ValueError, "PREIMAGE"):
            mod.patch_bytes(self.original.replace(b" -File verify.ps1", b" -FileX verify.ps1").replace(mod.OLD.encode(), b"x", 1))

    def test_fail_closed_duplicate_adapter(self):
        with self.assertRaisesRegex(ValueError, "PREIMAGE|EXISTING"):
            mod.patch_bytes(self.original.replace(mod.OLD.encode(), mod.NEW.encode(), 1))

    def test_existing_other_logic_unmodified(self):
        before = self.original + b"  Abort P01_SECURITY_GATE\n"
        after, _ = mod.patch_bytes(before)
        self.assertIn(b"Abort P01_SECURITY_GATE", after)
        self.assertEqual(after.replace(mod.NEW.encode(), mod.OLD.encode()), before)


if __name__ == "__main__":
    unittest.main()
