"""R117: no source bundle publication before the checked-out P04 syntax gate."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "nox-express-g1g2-unified-package.yml"
BUILD = "Build full SHA-locked tracked source archive"
GATE = "G2 P04 original syntax gate (not Windows proof)"
PUBLISH = "Upload one source-and-cache-reference archive"


def admitted(text: str) -> bool:
    names = re.findall(r"^      - name: (.+)$", text, re.MULTILINE)
    if any(names.count(name) != 1 for name in (BUILD, GATE, PUBLISH)):
        return False
    if not (names.index(BUILD) < names.index(GATE) < names.index(PUBLISH)):
        return False
    gate_start = text.index("      - name: " + GATE)
    upload_start = text.index("      - name: " + PUBLISH)
    gate = text[gate_start:upload_start]
    return (("set -euo pipefail" in gate)
            and ("ast.parse(p.read_text(encoding='utf-8')" in gate)
            and ("continue-on-error: true" not in gate)
            and ("if: always()" not in text[upload_start:]))


class SourceBundleAdmission(unittest.TestCase):
    def test_gate_before_publication(self):
        self.assertTrue(admitted(WORKFLOW.read_text(encoding="utf-8")))

    def test_old_publish_before_gate_is_rejected(self):
        actual = WORKFLOW.read_text(encoding="utf-8")
        gate_start = actual.index("      - name: " + GATE)
        upload_start = actual.index("      - name: " + PUBLISH)
        old_order = actual[:gate_start] + actual[upload_start:] + actual[gate_start:upload_start]
        self.assertFalse(admitted(old_order))

    def test_disabling_gate_is_rejected(self):
        actual = WORKFLOW.read_text(encoding="utf-8")
        self.assertFalse(admitted(actual.replace("ast.parse(p.read_text", "print(p.read_text")))
        self.assertFalse(admitted(actual.replace("          retention-days: 7", "          retention-days: 7\n        if: always()")))


if __name__ == "__main__":
    unittest.main()
