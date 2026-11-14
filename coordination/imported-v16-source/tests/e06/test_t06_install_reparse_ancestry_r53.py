"""Regression for NOX T06 installed same-VM path/reparse admission (source only).

Load only the original helper AST; never import or execute the Windows CI
smoke's main function, Setup, PowerShell, registry, or filesystem mutations.
"""
from __future__ import annotations

import ast
from pathlib import Path
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parents[2] / "coordination/e06/t06_samevm_installed_smoke.py"


def load_plain_parents():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    functions = [node for node in tree.body
                 if isinstance(node, ast.FunctionDef) and node.name == "plain_parents"]
    if len(functions) != 1:
        raise AssertionError("expected exactly one canonical plain_parents helper")
    namespace = {"Path": Path}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(SOURCE), "exec"),
         namespace)
    return namespace["plain_parents"]


class SyntheticPath:
    """Emulate Windows dangling junction: exists=False, is_junction=True."""
    def __init__(self, label, parent=None, *, exists=False,
                 junction=False, symlink=False, directory=False):
        self.label = label
        self._parent = parent
        self._exists = exists
        self._junction = junction
        self._symlink = symlink
        self._directory = directory

    @property
    def parent(self):
        return self._parent if self._parent is not None else self

    def exists(self):
        return self._exists

    def is_junction(self):
        return self._junction

    def is_symlink(self):
        return self._symlink

    def is_dir(self):
        return self._directory


class InstalledReparseAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.admit = staticmethod(load_plain_parents())

    def test_dangling_junction_in_programs_ancestor_fails_closed(self):
        root = SyntheticPath("C:", exists=True, directory=True)
        programs = SyntheticPath("Programs", root, exists=False, junction=True)
        target = SyntheticPath("NOX HELION", programs)
        self.assertFalse(self.admit(target, root))

    def test_dangling_junction_as_install_leaf_fails_closed(self):
        root = SyntheticPath("C:", exists=True, directory=True)
        leaf = SyntheticPath("NOX HELION", root, exists=False, junction=True)
        self.assertFalse(self.admit(leaf, root))

    def test_junction_at_trust_base_fails_closed(self):
        root = SyntheticPath("C:", exists=True, directory=True, junction=True)
        self.assertFalse(self.admit(root, root))

    def test_normal_uncreated_path_remains_allowed(self):
        root = SyntheticPath("C:", exists=True, directory=True)
        parent = SyntheticPath("Programs", root, exists=True, directory=True)
        leaf = SyntheticPath("NOX HELION", parent)
        self.assertTrue(self.admit(leaf, root))

    def test_real_existing_parent_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as home:
            root = Path(home)
            outside = root / "outside"
            outside.mkdir()
            link = root / "Programs"
            try:
                link.symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError):
                # Windows CI may lack SeCreateSymbolicLinkPrivilege.
                # Synthetic dangling-junction tests still run and must fail closed.
                self.skipTest("symlink creation unavailable on this Windows runner")
            self.assertFalse(self.admit(link / "NOX HELION", root))

    def test_disposable_setup_and_user_data_guards_wired(self):
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn("T06_CI_INSTALL_REPARSE_ANCESTOR_HOLD", source)
        self.assertIn("T06_CI_INSTALL_PATH_CHANGED_AFTER_PREFLIGHT_HOLD", source)
        self.assertIn("T06_USER_DATA_REPARSE_ANCESTOR_HOLD", source)
        self.assertIn("not getattr(p,\"is_junction\"", source)
        self.assertIn("plain_parents(persistent,local_base)", source)


if __name__ == "__main__":
    unittest.main()
