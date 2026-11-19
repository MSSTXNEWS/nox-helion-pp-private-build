"""Tests for safe, formatting-preserving NOX OneHost workflow admission repair."""
import tempfile
import unittest
from pathlib import Path
from coordination.onepass.native_job_gate_autofix import transform,run
from coordination.onepass.native_job_gate_audit import check_workflow


SOURCE="""name: Real NOX fixture
on:
  push:
    branches: [feature]
  workflow_dispatch:
jobs:
  regression:
    runs-on: ubuntu-latest
    steps:
      - run: python -m unittest
  native:
    if: github.actor == 'MSSTXNEWS'
    runs-on: ubuntu-latest
    env:
      NOX2: placeholder
    steps:
      - run: python -m nox_runpod.teacher_mesh.v51.ephemeral_ssh_probe
"""


class AutoGuardTests(unittest.TestCase):
    def test_preserves_source_auto_ci_and_adds_manual_owner_gate(self):
        result=transform(SOURCE,['native'],path="a.yml")
        self.assertIn('  push:\n',result)
        self.assertIn('  regression:\n',result)
        self.assertIn("    if: ",result)
        self.assertIn("inputs.allow_native == 'YES'",result)
        self.assertIn("default: 'NO'",result)
        self.assertIn("github.actor == 'MSSTXNEWS'",result)
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/"a.yml"
            p.write_text(result)
            self.assertEqual(check_workflow(p,root=Path(t))[0],[])

    def test_adds_dispatch_to_push_only_when_needed(self):
        value=SOURCE.replace("  workflow_dispatch:\n","")
        result=transform(value,['native'],path="b.yml")
        self.assertIn("  workflow_dispatch:\n    inputs:\n",result)
        self.assertIn('  push:\n',result)

    def test_replaces_push_only_job_gate_without_losing_owner(self):
        value=SOURCE.replace(
            "    if: github.actor == 'MSSTXNEWS'",
            "    if: github.event_name == 'push' && github.actor == 'MSSTXNEWS'")
        result=transform(value,['native'],path="c.yml")
        self.assertNotIn("github.event_name == 'push' && github.actor",result)
        self.assertIn("github.event_name == 'workflow_dispatch'",result)

    def test_input_default_is_existing_no(self):
        value=SOURCE.replace(
            "  workflow_dispatch:\n",
            "  workflow_dispatch:\n    inputs:\n"
            "      allow_native:\n        default: 'NO'\n"
            "        options: ['NO', 'YES']\n")
        result=transform(value,['native'],path="d.yml")
        self.assertEqual(result.count("      allow_native:"),1)

    def test_ambiguous_inline_event_is_rejected(self):
        value=SOURCE.replace("  workflow_dispatch:\n","  workflow_dispatch: {inputs: {other: 1}}\n")
        with self.assertRaisesRegex(RuntimeError,"HOLD_INLINE_MANUAL"):
            transform(value,['native'],path="e.yml")

    def test_source_workflows_unchanged_if_no_native_jobs(self):
        self.assertEqual(transform(SOURCE,[],path="f.yml"),SOURCE)

    def test_multiline_original_if_expression_preserved(self):
        value=SOURCE.replace(
            "    if: github.actor == 'MSSTXNEWS'",
            "    if: >-\n"
            "      github.actor == 'MSSTXNEWS'\n"
            "      && !cancelled()")
        result=transform(value,['native'],path="g.yml")
        self.assertIn("!cancelled()",result)
        self.assertIn("inputs.allow_native == 'YES'",result)
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/"g.yml"
            p.write_text(result)
            self.assertEqual(check_workflow(p,root=Path(t))[0],[])

    def test_full_tree_applied_only_after_strict_zero_risks(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            folder=root/".github"/"workflows"
            folder.mkdir(parents=True)
            for n in range(5):
                (folder/f"test{n}.yml").write_text(SOURCE)
            proof=run(root,apply=True)
            self.assertEqual(proof['unsafe_jobs_before'],5)
            self.assertEqual(proof['unsafe_jobs_remaining'],0)
            self.assertTrue(proof['applied'])
            self.assertEqual(proof['changed_files'],5)


if __name__=="__main__":
    unittest.main()
