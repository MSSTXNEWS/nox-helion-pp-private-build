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
EMERGENCY_STOP_SHA = APPROVED_SOURCE_BY_ACTION["emergency_stop"]
EMERGENCY_STOP_PREFLIGHT_SHA = APPROVED_SOURCE_BY_ACTION["emergency_stop_preflight"]
AUDIT_SHA = APPROVED_SOURCE_BY_ACTION["audit"]
SOURCE_ATTEST_SHA = APPROVED_SOURCE_BY_ACTION["source_attest"]
GPU_INVENTORY_SHA = APPROVED_SOURCE_BY_ACTION["gpu_inventory"]
BROWSER_QA_SHA = APPROVED_SOURCE_BY_ACTION["browser_qa"]
STALE_BROWSER_QA_SHA = "9ddb3730f8db1b7b598eaf58ab0aa5973485f6c6"  # helper missing at old pin
SOURCE_EXPORT_SHA = APPROVED_SOURCE_BY_ACTION["source_export"]
OLD_UNAPPROVED_SHA = "80fc87881036462cfbe0aa27bb02b69daf8bfe6a"  # prior #437
STALE_AUDIT_SHA = "22efccc957bc72d54899a701e6d09e5ef69b20c2"  # pre-fix #475
UNAPPROVED_SHA = "a" * 40
OLD_INSPECT_SHA = "215abe9bfe6a9f969899cb2a5be2ddacc071f4c8"


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
                         "1d76f3fbce0b9e9258f77cdc181b038acc4d69c9")
        self.assertEqual(EMERGENCY_STOP_SHA,
                         "5ca33f710dc4e0e462d65fe2856bb42ac85a1a23")
        self.assertEqual(EMERGENCY_STOP_PREFLIGHT_SHA,
                         "a087e3968171ebb338a2fd19736cfa340c30956f")
        self.assertEqual(AUDIT_SHA,
                         "b1e33d60983885a7ebd1979bda4ec640b7ca7047")
        self.assertEqual(SOURCE_ATTEST_SHA,
                         "3e399979e5b2e5ac16c1504542bd5cace989ddd3")
        self.assertEqual(GPU_INVENTORY_SHA,
                         "a95c7c6e4d52a35db9199e1aa2a5ad01752efc7e")
        self.assertEqual(BROWSER_QA_SHA, "eaa4b0d64d3d97a8c2b2680e8eb20137934d76b9")
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
        emergency_stop_body = (
            f"/nox-maintain 60509551 {EMERGENCY_STOP_SHA} emergency_stop")
        self.assertEqual(
            authorize_event(event_for(emergency_stop_body), REPOSITORY, "issue_comment"),
            ("emergency_stop", EMERGENCY_STOP_SHA),
        )
        preflight_body = (
            f"/nox-maintain 60509551 {EMERGENCY_STOP_PREFLIGHT_SHA} "
            "emergency_stop_preflight")
        self.assertEqual(
            authorize_event(event_for(preflight_body), REPOSITORY, "issue_comment"),
            ("emergency_stop_preflight", EMERGENCY_STOP_PREFLIGHT_SHA),
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
            f"/nox-maintain 60509551 {EMERGENCY_STOP_SHA} emergency_stop extra",
            f"/nox-maintain 60509551 {EMERGENCY_STOP_PREFLIGHT_SHA} emergency_stop_preflight extra",
        )
        for body in bodies:
            with self.subTest(body=body):
                with self.assertRaisesRegex(RuntimeError,
                                            "HOLD_EXACT_OWNER_COMMAND"):
                    authorize_event(event_for(body), REPOSITORY, "issue_comment")

    def test_well_formed_unapproved_or_cross_action_shas_hold(self) -> None:
        pairs = (
            (OLD_INSPECT_SHA, "inspect"),
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
            (STALE_BROWSER_QA_SHA, "browser_qa"),
            (BROWSER_QA_SHA, "inspect"),
            (BROWSER_QA_SHA, "audit"),
            (BROWSER_QA_SHA, "source_attest"),
            (BROWSER_QA_SHA, "gpu_inventory"),
            (GPU_INVENTORY_SHA, "browser_qa"),
            (UNAPPROVED_SHA, "emergency_stop"),
            (UNAPPROVED_SHA, "emergency_stop_preflight"),
            (INSPECT_SHA, "emergency_stop"),
            (INSPECT_SHA, "emergency_stop_preflight"),
            (EMERGENCY_STOP_SHA, "inspect"),
            (EMERGENCY_STOP_SHA, "audit"),
            (EMERGENCY_STOP_PREFLIGHT_SHA, "emergency_stop"),
            (EMERGENCY_STOP_SHA, "emergency_stop_preflight"),
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

            emergency_body = (
                f"/nox-maintain 60509551 {EMERGENCY_STOP_SHA} emergency_stop")
            event_path.write_text(json.dumps(event_for(emergency_body)), encoding="utf-8")
            output_path.write_text("", encoding="utf-8")
            with mock.patch.dict(os.environ, env, clear=False):
                self.assertEqual(main(), 0)
            self.assertEqual(output_path.read_text(encoding="utf-8"),
                             f"action=emergency_stop\nsource_sha={EMERGENCY_STOP_SHA}\n")

            unapproved_body = (
                f"/nox-maintain 60509551 {OLD_INSPECT_SHA} inspect"
            )
            event_path.write_text(json.dumps(event_for(unapproved_body)),
                                  encoding="utf-8")
            output_path.write_text("", encoding="utf-8")
            with mock.patch.dict(os.environ, env, clear=False), \
                    contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(), 2)
            self.assertEqual(output_path.read_text(encoding="utf-8"), "")

    def test_source_export_is_exact_sha_bounded_and_owner_only(self) -> None:
        key = "AbC_012-def"
        body = f"/nox-maintain 60509551 {SOURCE_EXPORT_SHA} source_export {key}"
        self.assertEqual(SOURCE_EXPORT_SHA,
                         "1fe739fa49141805701e8f969b77b536a4e49a4b")
        self.assertEqual(authorize_event(event_for(body), REPOSITORY, "issue_comment"),
                         ("source_export", SOURCE_EXPORT_SHA))
        for invalid in (
            f"/nox-maintain 60509551 {'b' * 40} source_export {key}",
            f"/nox-maintain 60509551 {SOURCE_EXPORT_SHA} source_export {key}=",
            f"/nox-maintain 60509551 {SOURCE_EXPORT_SHA} source_export {key} extra",
            f"/nox-maintain 60509551 {SOURCE_EXPORT_SHA} source_export " + "a" * 12001,
        ):
            with self.subTest(body=invalid[:90]), self.assertRaisesRegex(
                    RuntimeError, "HOLD_EXACT_OWNER_COMMAND"):
                authorize_event(event_for(invalid), REPOSITORY, "issue_comment")
        altered = event_for(body)
        altered["sender"]["id"] = OWNER_ID + 1
        with self.assertRaisesRegex(RuntimeError, "HOLD_OWNER_COMMAND_IDENTITY"):
            authorize_event(altered, REPOSITORY, "issue_comment")

        with tempfile.TemporaryDirectory() as temp:
            event_path = Path(temp) / "event.json"
            output_path = Path(temp) / "output"
            event_path.write_text(json.dumps(event_for(body)), encoding="utf-8")
            env = {"GITHUB_EVENT_PATH": str(event_path), "GITHUB_OUTPUT": str(output_path),
                   "GITHUB_REPOSITORY": REPOSITORY, "GITHUB_EVENT_NAME": "issue_comment"}
            stdout = io.StringIO()
            with mock.patch.dict(os.environ, env, clear=False), \
                    contextlib.redirect_stdout(stdout):
                self.assertEqual(main(), 0)
            self.assertEqual(output_path.read_text(encoding="utf-8"),
                             f"action=source_export\nsource_sha={SOURCE_EXPORT_SHA}\n"
                             f"export_key_b64={key}\n")
            self.assertNotIn(key, stdout.getvalue())

            output_path.write_text("", encoding="utf-8")
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
        self.assertIn("contains(github.event.comment.body, ' source_export ')", condition)
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
        self.assertLess(condition.index("contains(github.event.comment.body, ' source_export ')"),
                        owner_job.index("steps:"))

    def test_workflow_runs_only_fixed_owner_actions(self) -> None:
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
        self.assertIn("python -B nox-control/owner_native_operator.py source_export",
                      workflow)
        self.assertNotIn("owner_native_operator.py $", workflow)
        self.assertNotIn("inputs.action", workflow)
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertNotIn("issues: write", workflow)
        self.assertNotIn("pull-requests: write", workflow)
        self.assertNotIn("actions: write", workflow)
        self.assertNotIn("github-script", workflow)
        self.assertEqual(workflow.count("persist-credentials: false"), 3)
        self.assertEqual(workflow.count("NOX2: ${{ secrets.NOX2 }}"), 6)
        self.assertLess(workflow.index("owner_native_inspect_comment_guard.py"),
                        workflow.index("Run the fixed read-only inspect action"))
        self.assertLess(workflow.index("Run the fixed read-only inspect action"),
                        workflow.index("NOX2: ${{ secrets.NOX2 }}"))
        self.assertIn("steps.owner-command.outputs.action == 'inspect'", workflow)
        self.assertIn("steps.owner-command.outputs.action == 'audit'", workflow)
        self.assertIn("steps.owner-command.outputs.action == 'source_attest'", workflow)
        self.assertIn("steps.owner-command.outputs.action == 'gpu_inventory'", workflow)
        self.assertIn("steps.owner-command.outputs.action == 'browser_qa'", workflow)
        self.assertIn("steps.owner-command.outputs.action == 'source_export'", workflow)
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
        self.assertLess(
            workflow.index("Recheck exact pinned #415 source-export command before credentials"),
            workflow.index("Run the exact pinned #415 encrypted source-export action"),
        )
        self.assertLess(
            workflow.index("Compile and test exact pinned #415 encrypted export source before credentials"),
            workflow.index("Run the exact pinned #415 encrypted source-export action"),
        )
        self.assertLess(
            workflow.index("Run the exact pinned #415 encrypted source-export action"),
            workflow.index("Upload only the encrypted S03 source-export artifact"),
        )

    def test_emergency_stop_requires_main_source_pin_before_target_checkout(self) -> None:
        workflow = (Path(__file__).parents[1] / ".github" / "workflows"
                    / "nox-owner-maintenance-command.yml").read_text(encoding="utf-8")
        operator = (Path(__file__).parents[1] / "nox-control"
                    / "owner_native_operator.py").read_text(encoding="utf-8")
        self.assertIn("issue_comment:", workflow)
        self.assertNotIn("workflow_dispatch:", workflow)
        self.assertIn("checkout main owner approval guard", workflow.lower())
        self.assertIn("owner_native_inspect_comment_guard.py", workflow)
        self.assertIn("steps.approved.outputs.action", workflow)
        self.assertIn("steps.approved.outputs.source_sha", workflow)
        self.assertIn("emergency_stop", workflow)
        self.assertIn("emergency_stop_preflight", workflow)
        self.assertIn(
            "'emergency_stop_preflight': 'nox-control/owner_native_emergency_stop_preflight.py'",
            operator,
        )
        self.assertLess(workflow.index("Run main approved-source guard"),
                        workflow.index("ref: ${{ steps.request.outputs.sha }}"))
        self.assertLess(workflow.index("ref: ${{ steps.request.outputs.sha }}"),
                        workflow.index("NOX2: ${{ secrets.NOX2 }}"))
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn(
            "os.environ['APPROVED_ACTION'] != os.environ['REQUEST_ACTION']",
            workflow,
        )
        self.assertIn(
            "os.environ['APPROVED_SHA'] != os.environ['REQUEST_SHA']",
            workflow,
        )
        self.assertIn("source=(", workflow)
        self.assertIn("owner_native_'+a+'.py", workflow)
        self.assertEqual(
            workflow.count("if: steps.request.outputs.action == 'emergency_stop' || steps.request.outputs.action == 'emergency_stop_preflight'"),
            3,
        )

    def test_source_export_route_rechecks_key_and_uploads_ciphertext_only(self) -> None:
        workflow = (Path(__file__).parents[1] / ".github" / "workflows"
                    / "nox-owner-native-inspect.yml").read_text(encoding="utf-8")
        legacy = (Path(__file__).parents[1] / ".github" / "workflows"
                  / "nox-owner-maintenance-command.yml").read_text(encoding="utf-8")
        self.assertIn("steps.owner-command.outputs.export_key_b64", workflow)
        self.assertIn("path: source/artifacts/nox-s03-source-export.enc", workflow)
        self.assertNotIn("path: artifacts/", workflow.replace(
            "path: source/artifacts/nox-s03-source-export.enc", ""))
        self.assertIn("!contains(github.event.comment.body, ' source_export ')", legacy)


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
            "!contains(github.event.comment.body, ' source_export ')",
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
