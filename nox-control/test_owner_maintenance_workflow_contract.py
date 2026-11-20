import ast
from pathlib import Path
import re
import unittest


WORKFLOW = (Path(__file__).resolve().parents[1] /
            ".github/workflows/nox-owner-maintenance-command.yml")


def _line_containing(source: str, fragment: str) -> str:
    lines = [line.strip() for line in source.splitlines() if fragment in line]
    if len(lines) != 1:
        raise AssertionError(f"expected one workflow line containing {fragment!r}")
    return lines[0]


class OwnerMaintenanceWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WORKFLOW.read_text(encoding="utf-8")
        cls.parser_line = _line_containing(cls.source, "m=re.fullmatch(")
        cls.guard_line = _line_containing(cls.source, "assert a in (")

    def test_memfd_audit_is_an_exact_owner_command_token(self):
        assignment = ast.parse(self.parser_line).body[0]
        pattern = ast.literal_eval(assignment.value.args[0])
        self.assertIn("memfd_audit", pattern)
        self.assertIsNotNone(re.fullmatch(
            pattern, "/nox-maintain 60509551 " + "a" * 40 + " memfd_audit"))
        self.assertIsNone(re.fullmatch(
            pattern, "/nox-maintain 60509551 " + "a" * 40 + " memfd_audit extra"))
        self.assertIsNone(re.fullmatch(
            pattern, "/nox-maintain 60509551 " + "a" * 40 + " MEMFD_AUDIT"))

    def test_action_guard_and_syntax_path_include_memfd_source(self):
        guard = ast.parse(self.guard_line).body[0]
        allowed = ast.literal_eval(guard.test.comparators[0])
        self.assertIn("memfd_audit", allowed)
        self.assertIn("elif a=='memfd_audit':", self.source)
        self.assertIn(
            "py_compile.compile('nox-control/owner_native_memfd_audit.py',doraise=True)",
            self.source)

    def test_allowlist_runs_before_checkout_and_secret_step(self):
        parser_index = self.source.index(self.parser_line)
        checkout_index = self.source.index("uses: actions/checkout@")
        secret_index = self.source.index("NOX2: ${{ secrets.NOX2 }}")
        compile_index = self.source.index("Validate reviewed checkout syntax before credentials")
        self.assertLess(parser_index, checkout_index)
        self.assertLess(compile_index, secret_index)


if __name__ == "__main__":
    unittest.main()
