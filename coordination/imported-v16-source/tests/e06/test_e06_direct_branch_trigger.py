"""Existing E06 build must run from exact canonical SHA without a merge to main."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/nox-v16-e06-d02-onehost.yml"
BRANCH = "integration/nox-v16-unified-candidate-20261028-r01"
REPO = "MSSTXNEWS/nox-helion-pp-private-build"

class DirectBranchBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WORKFLOW.read_text(encoding="utf-8")
        cls.push = cls.source.split("  push:\n", 1)[1].split("  workflow_dispatch:", 1)[0]
        cls.build = cls.source.split("  diagnostic-onehost:\n", 1)[1]

    def test_only_exact_integration_branch_is_pushed(self):
        branches = self.push.split("    branches:\n", 1)[1].split("    paths:", 1)[0]
        self.assertEqual(re.findall(r"- '([^']+)'", branches), [BRANCH])
        for path in ("private_build.ps1", "coordination/e06/**", "tests/e06/**"):
            self.assertIn("- '" + path + "'", self.push)

    def test_build_requires_official_repository_and_exact_ref(self):
        condition = next(line.strip() for line in self.build.splitlines() if line.strip().startswith("if:"))
        expected = ("if: github.repository == '" + REPO + "' && (github.event_name == 'workflow_dispatch' || "
                    "(github.event_name == 'pull_request' && github.event.pull_request.number == 162) || "
                    "(github.event_name == 'push' && github.ref == 'refs/heads/" + BRANCH + "'))")
        self.assertEqual(condition, expected)
        self.assertIn("    needs: visual-source-stage", self.build)

    def test_all_checkouts_are_exact_event_sha_without_credentials(self):
        self.assertEqual(self.source.count("ref: ${{ github.event.pull_request.head.sha || github.sha }}"), 3)
        self.assertEqual(self.source.count("persist-credentials: false"), 3)
        self.assertIn("SourceCommitSha='${{ github.event.pull_request.head.sha || github.sha }}'", self.build)
        self.assertNotIn("pull_request_target:", self.source)
        self.assertNotIn("continue-on-error: true", self.source)
        self.assertIn("permissions:\n  contents: read", self.source)

    def test_same_branch_serialization_preserves_inflight_build(self):
        self.assertIn("group: nox-e06-onehost-${{ github.event.pull_request.head.ref || github.ref_name }}", self.source)
        self.assertIn("cancel-in-progress: false", self.source)

    def test_original_build_and_installed_gates_remain(self):
        for token in ("./private_build.ps1 -OneHostNative", "native_onehost_smoke.py",
                      "build_onehost_installer.ps1", "t06_samevm_installed_smoke.py",
                      "Emit-E07ImmutableHandoff.ps1", "NATIVE_ONEHOST_EXACT_WINDOWS_BACKBONE_PROOF_REQUIRED"):
            self.assertIn(token, self.build)
        self.assertIn("$smoke.release_accepted -ne $false", self.build)
        self.assertEqual(self.source.count("test_e06_direct_branch_trigger.py"), 3)

    def test_new_d02_four_stage_source(self):
        css = (ROOT / "integrations/wow200/runtime/home-guard.css").read_text(encoding="utf-8")
        for stage in ("ORB STEP01", "GARGANTUA STEP02", "LIQUID CHROME STEP03", "DARK VEIL STEP04"):
            with self.subTest(stage=stage):
                self.assertIn(stage, css)
        self.assertIn("pointer-events:none", css)
        self.assertIn("prefers-reduced-motion:reduce", css)
        self.assertIn("forced-colors:active", css)

    def test_p03_graphical_model_and_tool_source(self):
        root = ROOT / "Packages/P03/Source/P03.ModelCenter.Wow"
        html = (root / "index.html").read_text(encoding="utf-8")
        css = (root / "ui.css").read_text(encoding="utf-8")
        js = (root / "ui.js").read_text(encoding="utf-8")
        self.assertEqual(html.count('class="tool-source-card"'), 12)
        self.assertIn('id="quickInstallGrid"', html)
        self.assertIn("quick20Ids", js)
        self.assertIn(".tool-source-grid", css)
        self.assertIn("connect-src 'none'", html)
        self.assertIn('rel="noopener noreferrer"', html)

if __name__ == "__main__":
    unittest.main()
