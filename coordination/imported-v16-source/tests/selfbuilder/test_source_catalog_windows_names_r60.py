"""Source catalog must not approve aliases which collide on Windows OneHost."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import unittest

MODULE = Path(__file__).resolve().parents[2] / "src/nox_selfbuilder/source_catalog.py"
spec = importlib.util.spec_from_file_location("nox_source_catalog_r60", MODULE)
assert spec is not None and spec.loader is not None
catalog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog)

_SHA = "a" * 40

def tree(*paths):
    return "".join(f"100644 blob {_SHA}\\t{p}\\0" for p in paths).replace("\\t", "\t").replace("\\0", "\0")

class OriginalWindowsSourceNamespaceTests(unittest.TestCase):
    def test_distinct_safe_source_paths_survive(self):
        out = catalog._regular_blobs(tree("src/one.py", "src/two.py"))
        self.assertEqual(set(out), {"src/one.py", "src/two.py"})

    def test_case_only_leaf_alias_rejected(self):
        with self.assertRaisesRegex(ValueError, "GIT_TREE_WINDOWS_NAMESPACE_COLLISION"):
            catalog._regular_blobs(tree("Core/Menu.py", "Core/menu.py"))

    def test_case_only_parent_alias_rejected(self):
        with self.assertRaisesRegex(ValueError, "GIT_TREE_WINDOWS_NAMESPACE_COLLISION"):
            catalog._regular_blobs(tree("Assets/HUD/a.py", "assets/engine/b.py"))

    def test_unicode_case_alias_rejected(self):
        with self.assertRaisesRegex(ValueError, "GIT_TREE_WINDOWS_NAMESPACE_COLLISION"):
            catalog._regular_blobs(tree("nfc/é.py", "nfc/É.py"))

    def test_unsafe_checkout_names_fail_closed(self):
        for path in ("CON.py", "assets/x:ads.py", "Assets/.GIT/a.py",
                     "Assets/trailing./mod.py", "Assets/e\\u0301.py"):
            with self.subTest(path=path):
                self.assertFalse(catalog._safe_source_path(path))
                with self.assertRaisesRegex(ValueError, "GIT_TREE_WINDOWS_UNSAFE_SOURCE_PATH"):
                    catalog._regular_blobs(tree(path))

if __name__ == "__main__":
    unittest.main()
