#!/usr/bin/env python3
"""Validate fixed owner issue-comment commands with immutable source pins.

This runs before checking out the source SHA named in the comment and before
the NOX2 secret is added to any step environment. It emits no comment text.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

REPOSITORY = "MSSTXNEWS/nox-helion-pp-private-build"
OWNER_ID = 340718567
ISSUE_NUMBER = 256
INSTANCE_ID = 60509551
# Only reviewed immutable source commits may receive the NOX2 secret.
APPROVED_SOURCE_BY_ACTION = {
    "inspect": "215abe9bfe6a9f969899cb2a5be2ddacc071f4c8",  # merged PR #477
    "audit": "b1e33d60983885a7ebd1979bda4ec640b7ca7047",  # merged PR #485
    "source_attest": "07ebd86b15ae32644bc8bb562a396ec85918b13b",  # reviewed repair pin #489
    "gpu_inventory": "a95c7c6e4d52a35db9199e1aa2a5ad01752efc7e",  # exact-head source tests green
    "browser_qa": "23f0a7d7d34e2d35ce58886a435332fb7a0e94fe",  # immutable one-stream owner browser source bundle
}
COMMAND = re.compile(
    rf"/nox-maintain {INSTANCE_ID} ([0-9a-f]{{40}}) (inspect|audit|source_attest|gpu_inventory|browser_qa)\Z"
)


def authorize_event(event: object, repository: str | None,
                    event_name: str | None) -> tuple[str, str]:
    """Return an allowlisted action/SHA pair, or raise a sanitized HOLD."""
    if repository != REPOSITORY or event_name != "issue_comment":
        raise RuntimeError("HOLD_EVENT_SCOPE")
    if not isinstance(event, dict):
        raise RuntimeError("HOLD_EVENT_SHAPE")

    comment = event.get("comment")
    event_repo = event.get("repository")
    issue = event.get("issue")
    sender = event.get("sender")
    if not all(isinstance(value, dict)
               for value in (comment, event_repo, issue, sender)):
        raise RuntimeError("HOLD_EVENT_SHAPE")

    commenter = comment.get("user")
    repo_owner = event_repo.get("owner")
    if not isinstance(commenter, dict) or not isinstance(repo_owner, dict):
        raise RuntimeError("HOLD_EVENT_SHAPE")
    if (commenter.get("id") != OWNER_ID
            or repo_owner.get("id") != OWNER_ID
            or comment.get("author_association") != "OWNER"
            or type(issue.get("number")) is not int
            or issue.get("number") != ISSUE_NUMBER
            or sender.get("id") != OWNER_ID):
        raise RuntimeError("HOLD_OWNER_COMMAND_IDENTITY")

    body = comment.get("body")
    if not isinstance(body, str):
        raise RuntimeError("HOLD_EXACT_OWNER_COMMAND")
    match = COMMAND.fullmatch(body)
    if match is None:
        raise RuntimeError("HOLD_EXACT_OWNER_COMMAND")
    source_sha, action = match.groups()
    if APPROVED_SOURCE_BY_ACTION.get(action) != source_sha:
        raise RuntimeError("HOLD_SOURCE_ACTION_NOT_APPROVED")
    return action, source_sha


def main() -> int:
    try:
        event_path = os.environ.get("GITHUB_EVENT_PATH", "")
        if not event_path:
            raise RuntimeError("HOLD_EVENT_PATH")
        event = json.loads(Path(event_path).read_text(encoding="utf-8"))
        action, source_sha = authorize_event(
            event,
            os.environ.get("GITHUB_REPOSITORY"),
            os.environ.get("GITHUB_EVENT_NAME"),
        )
        output_path = os.environ.get("GITHUB_OUTPUT", "")
        if not output_path:
            raise RuntimeError("HOLD_OUTPUT_PATH")
        with Path(output_path).open("a", encoding="utf-8") as output:
            output.write(f"action={action}\n")
            output.write(f"source_sha={source_sha}\n")
    except (OSError, ValueError, RuntimeError) as exc:
        reason = str(exc)
        if not re.fullmatch(r"HOLD_[A-Z0-9_]+", reason):
            reason = "HOLD_INVALID_EVENT"
        print(f"NOX_OWNER_COMMAND={reason}", file=sys.stderr)
        return 2

    print("NOX_OWNER_COMMAND=AUTHORIZED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
