"""Offline authorization tests for the issue-comment inspect wrapper."""
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
    APPROVED_SOURCE_SHA,
    ISSUE_NUMBER,
    OWNER_ID,
    REPOSITORY,
    authorize_event,
    main,
)


SOURCE_SHA = APPROVED_SOURCE_SHA
UNAPPROVED_SOURCE_SHA = "a" * 40


def event_for(body: str = f"/nox-maintain 60509551 {SOURCE_SHA} inspect") -> dict:
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


class OwnerInspectCommentGuardTests(unittest.TestCase):
    def test_exact_owner_inspect_command_returns_only_source_sha(self) -> None:
        self.assertEqual(APPROVED_SOURCE_SHA,
                         "80fc87881036462cfbe0aa27bb02b69daf8bfe6a")
        self.assertEqual(
            authorize_event(event_for(), REPOSITORY, "issue_comment"),
            SOURCE_SHA,
        )

    def test_malformed_or_non_inspect_commands_hold(self) -> None:
        bodies = (
            f"nox-maintain 60509551 {SOURCE_SHA} inspect",
            f"/nox-maintain 60509551 {SOURCE_SHA} repair",
            f"/nox-maintain 60509551 {SOURCE_SHA} inspect extra",
            f"/nox-maintain 60509551 {SOURCE_SHA} inspect\n",
            f"/nox-maintain 60509551 {SOURCE_SHA.upper()} inspect",
            f"/nox-maintain 6050955 {SOURCE_SHA} inspect",
            f"/nox-maintain 60509551 {SOURCE_SHA[:-1]} inspect",
            f"/nox-maintain 60509551 {SOURCE_SHA} audit",
        )
        for body in bodies:
            with self.subTest(body=body):
                with self.assertRaisesRegex(RuntimeError,
                                            "HOLD_EXACT_OWNER_COMMAND"):
                    authorize_event(event_for(body), REPOSITORY, "issue_comment")

    def test_well_formed_but_unapproved_source_sha_holds(self) -> None:
        body = f"/nox-maintain 60509551 {UNAPPROVED_SOURCE_SHA} inspect"
        with self.assertRaisesRegex(RuntimeError,
                                    "HOLD_SOURCE_SHA_NOT_APPROVED"):
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

    def test_preflight_emits_sha_output_only_after_authentication(self) -> None:
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
                             f"source_sha={SOURCE_SHA}\n")

            event_path.write_text(json.dumps(event_for("not a command")),
                                  encoding="utf-8")
            output_path.write_text("", encoding="utf-8")
            with mock.patch.dict(os.environ, env, clear=False), \
                    contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(), 2)
            self.assertEqual(output_path.read_text(encoding="utf-8"), "")


class WorkflowScopeTests(unittest.TestCase):
    def test_native_workflow_has_no_user_selectable_action_or_dispatch_input(self) -> None:
        workflow = (Path(__file__).parents[1] / ".github" / "workflows"
                    / "nox-owner-native-inspect.yml").read_text(encoding="utf-8")
        self.assertIn("issue_comment:", workflow)
        self.assertIn("pull_request:", workflow)
        self.assertNotIn("workflow_dispatch:", workflow)
        self.assertIn("github.event.issue.number == 256", workflow)
        self.assertIn("github.event.comment.author_association == 'OWNER'", workflow)
        self.assertIn("github.event.comment.user.id == 340718567", workflow)
        self.assertIn("github.event.sender.id == 340718567", workflow)
        self.assertIn("APPROVED_SOURCE_SHA", (Path(__file__).with_name(
            "owner_native_inspect_comment_guard.py")).read_text(encoding="utf-8"))
        self.assertIn("python -B nox-control/owner_native_operator.py inspect",
                      workflow)
        self.assertNotIn("owner_native_operator.py $", workflow)
        self.assertNotIn("inputs.action", workflow)
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertNotIn("issues: write", workflow)
        self.assertNotIn("pull-requests: write", workflow)
        self.assertNotIn("actions: write", workflow)
        self.assertNotIn("github-script", workflow)
        self.assertEqual(workflow.count("persist-credentials: false"), 3)
        self.assertEqual(workflow.count("NOX2: ${{ secrets.NOX2 }}"), 1)
        self.assertLess(workflow.index("owner_native_inspect_comment_guard.py"),
                        workflow.index("NOX2: ${{ secrets.NOX2 }}"))


if __name__ == "__main__":
    unittest.main()
