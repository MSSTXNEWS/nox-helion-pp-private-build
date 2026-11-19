"""Offline authorization tests for fixed inspect/audit/source-attest/browser-QA actions."""
from __future__ import annotations

import json
import os
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from owner_native_inspect_comment_guard import (
    APPROVED_SOURCE_BY_ACTION,
    ISSUE_NUMBER,
    OWNER_ID,
    REPOSITORY,
    authorize_event,
    main,
)


INSPECT_SHA = APPROVED_SOURCE_BY_ACTION["inspect"]
AUDIT_SHA = APPROVED_SOURCE_BY_ACTION["audit"]
SOURCE_ATTEST_SHA = APPROVED_SOURCE_BY_ACTION["source_attest"]
GPU_INVENTORY_SHA = APPROVED_SOURCE_BY_ACTION["gpu_inventory"]
BROWSER_QA_SHA = APPROVED_SOURCE_BY_ACTION["browser_qa"]
OLD_UNAPPROVED_SHA = "80fc87881036462cfbe0aa27bb02b69daf8bfe6a"  # prior #437
STALE_AUDIT_SHA = "22efccc957bc72d54899a701e6d09e5ef69b20c2"  # pre-fix #475
UNAPPROVED_SHA = "a" * 40


def event_for(body: str = f"/nox-maintain 60509551 {INSPECT_SHA} inspect") -> dict:
    return {
        "comment": {
            "id": 987654,
            "body": body,
            "author_association": "OWNER",
            "user": {"id": OWNER_ID, "login": "MSSTXNEWS"},
        },
        "repository": {"full_name": REPOSITORY,
                       "owner": {"id": OWNER_ID}},
        "issue": {"number": ISSUE_NUMBER},
        "sender": {"id": OWNER_ID, "login": "MSSTXNEWS"},
    }


class OwnerCommentGuardTests(unittest.TestCase):
    def test_exact_inspect_audit_and_attestation_commands_return_pinned_pairs(self) -> None:
        self.assertEqual(INSPECT_SHA,
                         "215abe9bfe6a9f969899cb2a5be2ddacc071f4c8")
        self.assertEqual(AUDIT_SHA,
                         "b1e33d60983885a7ebd1979bda4ec640b7ca7047")
        self.assertEqual(SOURCE_ATTEST_SHA,
                         "3e399979e5b2e5ac16c1504542bd5cace989ddd3")
        self.assertEqual(GPU_INVENTORY_SHA,
                         "a95c7c6e4d52a35db9199e1aa2a5ad01752efc7e")
        self.assertEqual(BROWSER_QA_SHA, "9ddb3730f8db1b7b598eaf58ab0aa5973485f6c6")
        self.assertEqual(authorize_event(event_for(), REPOSITORY, "issue_comment"),
                         ("inspect", INSPECT_SHA))
        audit_body = f"/nox-maintain 60509551 {AUDIT_SHA} audit"
        self.assertEqual(
            authorize_event(event_for(audit_body), REPOSITORY, "issue_comment"),
            ("audit", AUDIT_SHA),
        )
        attest_body = f"/nox-maintain 60509551 {SOURCE_ATTEST_SHA} source_attest"
        self.assertEqual(
            authorize_event(event_for(attest_body), REPOSITORY, "issue_comment"),
            ("source_attest", SOURCE_ATTEST_SHA),
        )
        gpu_body = f"/nox-maintain 60509551 {GPU_INVENTORY_SHA} gpu_inventory"
        self.assertEqual(
            authorize_event(event_for(gpu_body), REPOSITORY, "issue_comment"),
            ("gpu_inventory", GPU_INVENTORY_SHA),
        )
        browser_body = f"/nox-maintain 60509551 {BROWSER_QA_SHA} browser_qa"
        self.assertEqual(
            authorize_event(event_for(browser_body), REPOSITORY, "issue_comment"),
            ("browser_qa", BROWSER_QA_SHA),
        )

    def test_malformed_or_unavailable_actions_hold(self) -> None:
        bodies = (
            f"nox-maintain 60509551 {INSPECT_SHA} inspect",
            f"/nox-maintain 60509551 {INSPECT_SHA} repair",
            f"/nox-maintain 60509551 {INSPECT_SHA} inspect extra",
            f"/nox-maintain 60509551 {INSPECT_SHA} inspect\n",
            f"/nox-maintain 60509551 {INSPECT_SHA.upper()} inspect",
            f"/nox-maintain 6050955 {INSPECT_SHA} inspect",
            f"/nox-maintain 60509551 {INSPECT_SHA[:-1]} inspect",
            f"/nox-maintain 60509551 {AUDIT_SHA} repair",
            f"/nox-maintain 60509551 {SOURCE_ATTEST_SHA} source_attest extra",
            f"/nox-maintain 60509551 {GPU_INVENTORY_SHA} gpu_inventory extra",
            f"/nox-maintain 60509551 {BROWSER_QA_SHA} browser_qa extra",
        )
        for body in bodies:
            with self.subTest(body=body):
                with self.assertRaisesRegex(RuntimeError,
                                            "HOLD_EXACT_OWNER_COMMAND"):
                    authorize_event(event_for(body), REPOSITORY, "issue_comment")

    def test_well_formed_unapproved_or_cross_action_shas_hold(self) -> None:
        pairs = (
            (OLD_UNAPPROVED_SHA, "inspect"),
            (STALE_AUDIT_SHA, "audit"),
            (UNAPPROVED_SHA, "inspect"),
            (UNAPPROVED_SHA, "audit"),
            (AUDIT_SHA, "inspect"),
            (INSPECT_SHA, "audit"),
            (UNAPPROVED_SHA, "source_attest"),
            (INSPECT_SHA, "source_attest"),
            (SOURCE_ATTEST_SHA, "inspect"),
            (SOURCE_ATTEST_SHA, "audit"),
            (UNAPPROVED_SHA, "gpu_inventory"),
            (GPU_INVENTORY_SHA, "inspect"),
            (GPU_INVENTORY_SHA, "audit"),
            (GPU_INVENTORY_SHA, "source_attest"),
            (SOURCE_ATTEST_SHA, "gpu_inventory"),
            (UNAPPROVED_SHA, "browser_qa"),
            (BROWSER_QA_SHA, "inspect"),
            (BROWSER_QA_SHA, "audit"),
            (BROWSER_QA_SHA, "source_attest"),
            (BROWSER_QA_SHA, "gpu_inventory"),
            (GPU_INVENTORY_SHA, "browser_qa"),
        )
        for sha, action in pairs:
            body = f"/nox-maintain 60509551 {sha} {action}"
            with self.subTest(sha=sha, action=action), self.assertRaisesRegex(
                    RuntimeError, "HOLD_SOURCE_ACTION_NOT_APPROVED"):
                authorize_event(event_for(body), REPOSITORY, "issue_comment")

    def test_wrong_event_repository_issue_or_owner_holds(self) -> None:
        cases = (
            (event_for(), "other/repo", "issue_comment",
             "HOLD_EVENT_SCOPE"),
            (event_for(), REPOSITORY, "workflow_dispatch",
             "HOLD_EVENT_SCOPE"),
        )
        for event, repository, event_name, code in cases:
            with self.subTest(repository=repository, event_name=event_name):
                with self.assertRaisesRegex(RuntimeError, code):
                    authorize_event(event, repository, event_name)

        for field, value in (
            ("issue", {"number": ISSUE_NUMBER + 1}),
            ("sender", {"id": OWNER_ID + 1}),
            ("repository", {"full_name": REPOSITORY,
                            "owner": {"id": OWNER_ID + 1}}),
        ):
            altered = event_for()
            altered[field] = value
            with self.subTest(field=field):
                with self.assertRaisesRegex(
                        RuntimeError, "HOLD_OWNER_COMMAND_IDENTITY"):
                    authorize_event(altered, REPOSITORY, "issue_comment")

        altered = event_for()
        altered["comment"]["user"]["id"] = OWNER_ID + 1
        with self.assertRaisesRegex(RuntimeError,
                                    "HOLD_OWNER_COMMAND_IDENTITY"):
            authorize_event(altered, REPOSITORY, "issue_comment")

        altered = event_for()
        altered["comment"]["author_association"] = "CONTRIBUTOR"
        with self.assertRaisesRegex(RuntimeError,
                                    "HOLD_OWNER_COMMAND_IDENTITY"):
            authorize_event(altered, REPOSITORY, "issue_comment")

    def test_preflight_emits_fixed_action_pair_only_after_authentication(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            event_path = Path(temp) / "event.json"
            output_path = Path(temp) / "output"
            event_path.write_text(json.dumps(event_for()), encoding="utf-8")
            env = {
                "GITHUB_EVENT_PATH": str(event_path),
                "GITHUB_OUTPUT": str(output_path),
                "GITHUB_REPOSITORY": REPOSITORY,
                "GITHUB_EVENT_NAME": "issue_comment",
            }
            with mock.patch.dict(os.environ, env, clear=False):
                self.assertEqual(main(), 0)
            self.assertEqual(output_path.read_text(encoding="utf-8"),
                             f"action=inspect\nsource_sha={INSPECT_SHA}\n")

            audit_body = f"/nox-maintain 60509551 {AUDIT_SHA} audit"
            event_path.write_text(json.dumps(event_for(audit_body)),
                                  encoding="utf-8")
            output_path.write_text("", encoding="utf-8")
            with mock.patch.dict(os.environ, env, clear=False):
                self.assertEqual(main(), 0)
            self.assertEqual(output_path.read_text(encoding="utf-8"),
                             f"action=audit\nsource_sha={AUDIT_SHA}\n")

            attest_body = f"/nox-maintain 60509551 {SOURCE_ATTEST_SHA} source_attest"
            event_path.write_text(json.dumps(event_for(attest_body)),
                                  encoding="utf-8")
            output_path.write_text("", encoding="utf-8")
            with mock.patch.dict(os.environ, env, clear=False):
                self.assertEqual(main(), 0)
            self.assertEqual(output_path.read_text(encoding="utf-8"),
                             f"action=source_attest\nsource_sha={SOURCE_ATTEST_SHA}\n")

            gpu_body = f"/nox-maintain 60509551 {GPU_INVENTORY_SHA} gpu_inventory"
            event_path.write_text(json.dumps(event_for(gpu_body)), encoding="utf-8")
            output_path.write_text("", encoding="utf-8")
            with mock.patch.dict(os.environ, env, clear=False):
                self.assertEqual(main(), 0)
            self.assertEqual(output_path.read_text(encoding="utf-8"),
                             f"action=gpu_inventory\nsource_sha={GPU_INVENTORY_SHA}\n")

            browser_body = f"/nox-maintain 60509551 {BROWSER_QA_SHA} browser_qa"
            event_path.write_text(json.dumps(event_for(browser_body)), encoding="utf-8")
            output_path.write_text("", encoding="utf-8")
            with mock.patch.dict(os.environ, env, clear=False):
                self.assertEqual(main(), 0)
            self.assertEqual(output_path.read_text(encoding="utf-8"),
                             f"action=browser_qa\nsource_sha={BROWSER_QA_SHA}\n")

            unapproved_body = (
                f"/nox-maintain 60509551 {OLD_UNAPPROVED_SHA} audit"
            )
            event_path.write_text(json.dumps(event_for(unapproved_body)),
                                  encoding="utf-8")
            output_path.write_text("", encoding="utf-8")
            with mock.patch.dict(os.environ, env, clear=False), \
                    contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(), 2)
            self.assertEqual(output_path.read_text(encoding="utf-8"), "")

            event_path.write_text(json.dumps(event_for("not a command")),
                                  encoding="utf-8")
            with mock.patch.dict(os.environ, env, clear=False), \
                    contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(), 2)
            self.assertEqual(output_path.read_text(encoding="utf-8"), "")


class WorkflowScopeTests(unittest.TestCase):
    def test_owner_job_prefilter_only_starts_for_fixed_action_suffixes(self) -> None:
        workflow = (Path(__file__).parents[1] / ".github" / "workflows"
                    / "nox-owner-native-inspect.yml").read_text(encoding="utf-8")
        owner_job = workflow.split("  owner-inspect:\n", 1)[1]
        condition = owner_job.split("    runs-on:", 1)[0]
        self.assertIn("endsWith(github.event.comment.body, ' inspect')", condition)
        self.assertIn("endsWith(github.event.comment.body, ' audit')", condition)
        self.assertIn("endsWith(github.event.comment.body, ' source_attest')", condition)
        self.assertIn("endsWith(github.event.comment.body, ' gpu_inventory')", condition)
        self.assertIn("endsWith(github.event.comment.body, ' browser_qa')", condition)
        self.assertLess(condition.index("endsWith(github.event.comment.body, ' inspect')"),
                        owner_job.index("steps:"))
        self.assertLess(condition.index("endsWith(github.event.comment.body, ' audit')"),
                        owner_job.index("steps:"))
        self.assertLess(condition.index("endsWith(github.event.comment.body, ' source_attest')"),
                        owner_job.index("steps:"))
        self.assertLess(condition.index("endsWith(github.event.comment.body, ' gpu_inventory')"),
                        owner_job.index("steps:"))
        self.assertLess(condition.index("endsWith(github.event.comment.body, ' browser_qa')"),
                        owner_job.index("steps:"))

    def test_workflow_runs_only_five_fixed_owner_actions(self) -> None:
        workflow = (Path(__file__).parents[1] / ".github" / "workflows"
                    / "nox-owner-native-inspect.yml").read_text(encoding="utf-8")
        self.assertIn("issue_comment:", workflow)
        self.assertIn("pull_request:", workflow)
        self.assertNotIn("workflow_dispatch:", workflow)
        self.assertIn("github.event.issue.number == 256", workflow)
        self.assertIn("github.event.comment.author_association == 'OWNER'", workflow)
        self.assertIn("github.event.comment.user.id == 340718567", workflow)
        self.assertIn("github.event.sender.id == 340718567", workflow)
        self.assertIn("APPROVED_SOURCE_BY_ACTION", (Path(__file__).with_name(
            "owner_native_inspect_comment_guard.py")).read_text(encoding="utf-8"))
        self.assertIn("python -B nox-control/owner_native_operator.py inspect",
                      workflow)
        self.assertIn("python -B nox-control/owner_native_operator.py audit",
                      workflow)
        self.assertIn("python -B nox-control/owner_native_operator.py source_attest",
                      workflow)
        self.assertIn("python -B nox-control/owner_native_operator.py gpu_inventory",
                      workflow)
        self.assertIn("python -B nox-control/owner_native_operator.py browser_qa",
                      workflow)
        self.assertNotIn("owner_native_operator.py $", workflow)
        self.assertNotIn("inputs.action", workflow)
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertNotIn("issues: write", workflow)
        self.assertNotIn("pull-requests: write", workflow)
        self.assertNotIn("actions: write", workflow)
        self.assertNotIn("github-script", workflow)
        self.assertEqual(workflow.count("persist-credentials: false"), 3)
        self.assertEqual(workflow.count("NOX2: ${{ secrets.NOX2 }}"), 5)
        self.assertLess(workflow.index("owner_native_inspect_comment_guard.py"),
                        workflow.index("Run the fixed read-only inspect action"))
        self.assertLess(workflow.index("Run the fixed read-only inspect action"),
                        workflow.index("NOX2: ${{ secrets.NOX2 }}"))
        self.assertIn("steps.owner-command.outputs.action == 'inspect'", workflow)
        self.assertIn("steps.owner-command.outputs.action == 'audit'", workflow)
        self.assertIn("steps.owner-command.outputs.action == 'source_attest'", workflow)
        self.assertIn("steps.owner-command.outputs.action == 'gpu_inventory'", workflow)
        self.assertIn("steps.owner-command.outputs.action == 'browser_qa'", workflow)
        self.assertLess(
            workflow.index("Recheck pinned GPU inventory command without credentials"),
            workflow.index("Run the fixed read-only GPU inventory action"),
        )
        self.assertLess(
            workflow.index("Run the fixed read-only GPU inventory action"),
            workflow.rindex("NOX2: ${{ secrets.NOX2 }}"),
        )
        self.assertLess(
            workflow.index("Recheck pinned source-attest command without credentials"),
            workflow.index("Run the fixed read-only source-attest action"),
        )
        self.assertLess(
            workflow.index("Run the fixed read-only source-attest action"),
            workflow.rindex("NOX2: ${{ secrets.NOX2 }}"),
        )


    def test_legacy_workflow_excludes_canonical_actions_before_secrets(self) -> None:
        workflow = (Path(__file__).parents[1] / ".github" / "workflows"
                    / "nox-owner-maintenance-command.yml").read_text(encoding="utf-8")
        owner_job = workflow.split("jobs:", 1)[1]
        condition = owner_job.split("    runs-on:", 1)[0]
        exclusions = (
            "!contains(github.event.comment.body, ' inspect')",
            "!contains(github.event.comment.body, ' audit')",
            "!contains(github.event.comment.body, ' source_attest')",
            "!contains(github.event.comment.body, ' gpu_inventory')",
            "!contains(github.event.comment.body, ' browser_qa')",
        )
        for exclusion in exclusions:
            with self.subTest(exclusion=exclusion):
                self.assertIn(exclusion, condition)
                self.assertLess(condition.index(exclusion),
                                owner_job.index("    steps:"))
        self.assertNotIn("memfd_audit')", condition)
        self.assertIn("!contains(github.event.comment.body, ' browser_qa')", condition)
        self.assertIn("'memfd_audit')", workflow)
        self.assertLess(owner_job.index("    steps:"),
                        owner_job.index("NOX2:"))

if __name__ == "__main__":
    unittest.main()
