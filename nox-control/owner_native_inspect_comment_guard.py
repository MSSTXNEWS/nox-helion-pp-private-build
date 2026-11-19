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
    "inspect": "1d76f3fbce0b9e9258f77cdc181b038acc4d69c9",  # merged PR #550 cgroup route
    "audit": "b1e33d60983885a7ebd1979bda4ec640b7ca7047",  # merged PR #485
    "source_attest": "3e399979e5b2e5ac16c1504542bd5cace989ddd3",  # updated chat/S03 static scope #520
    "gpu_inventory": "a95c7c6e4d52a35db9199e1aa2a5ad01752efc7e",  # exact-head source tests green
    "audit_gpu_inventory": "d2fec1611e7eb09d7c45dcdc149a58a8fad3b485",  # bounded read-only owner census + GPU inventory route
    "browser_qa": "eaa4b0d64d3d97a8c2b2680e8eb20137934d76b9",  # PR #543 helper source commit; preserve this pin with a merge commit
    "refill_snapshot": "3a0bf379988f5b9b0828822a576461bb8730f12b",
    "source_export": "845c76d44676d56157125e729db81b45e006cf92",  # exact pinned encrypted-only #415 source export
    "emergency_stop": "101e4ddb258bc48e490e66624a1f0a85401f1e06",  # exact drained emergency-stop source commit
    "emergency_stop_preflight": "26d20a37c0ec1c9ca1addd373d89baec29ebb632",  # bounded read-only endpoint facts
}
# An additional read-only inspect pin preserves existing callers at the prior SHA.
CGROUP_CONTROL_INSPECT_SHA = "4d0698a4222d765dc56b5525843d7d633c767584"
MAPPED_MEMORY_INSPECT_SHA = "ad76f877bb1df29d360b5c885217024e4773725f"
SOURCE_EXPORT_KEY_MAX_CHARS = 12000
COMMAND = re.compile(
    rf"/nox-maintain {INSTANCE_ID} ([0-9a-f]{{40}}) "
    rf"(inspect|audit|source_attest|gpu_inventory|audit_gpu_inventory|browser_qa|emergency_stop_preflight|emergency_stop)\Z"
)
SOURCE_EXPORT_COMMAND = re.compile(
    rf"/nox-maintain {INSTANCE_ID} ({re.escape(APPROVED_SOURCE_BY_ACTION['source_export'])}) "
    rf"source_export ([A-Za-z0-9_-]{{1,{SOURCE_EXPORT_KEY_MAX_CHARS}}})\Z"
)
REFILL_SNAPSHOT_COMMAND = re.compile(
    rf"/nox-maintain {INSTANCE_ID} ([0-9a-f]{{40}}) "
    r"refill_snapshot ([A-Za-z0-9_-]{500,900})\Z"
)


def parse_command(body: object) -> tuple[str, str, str | None]:
    """Parse one exact owner command; return action, immutable SHA, and key if any."""
    if not isinstance(body, str):
        raise RuntimeError("HOLD_EXACT_OWNER_COMMAND")
    match = COMMAND.fullmatch(body)
    if match is not None:
        source_sha, action = match.groups()
        return action, source_sha, None
    export_match = SOURCE_EXPORT_COMMAND.fullmatch(body)
    if export_match is not None:
        source_sha, key_b64 = export_match.groups()
        return "source_export", source_sha, key_b64
    refill_match = REFILL_SNAPSHOT_COMMAND.fullmatch(body)
    if refill_match is not None:
        source_sha, recipient_b64 = refill_match.groups()
        return "refill_snapshot", source_sha, recipient_b64
    raise RuntimeError("HOLD_EXACT_OWNER_COMMAND")


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

    action, source_sha, _ = parse_command(comment.get("body"))
    allowed = (APPROVED_SOURCE_BY_ACTION.get(action) == source_sha
               or (action == "inspect" and source_sha in
                   (CGROUP_CONTROL_INSPECT_SHA, MAPPED_MEMORY_INSPECT_SHA)))
    if not allowed:
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
        _, _, export_key_b64 = parse_command(event["comment"]["body"])
        output_path = os.environ.get("GITHUB_OUTPUT", "")
        if not output_path:
            raise RuntimeError("HOLD_OUTPUT_PATH")
        with Path(output_path).open("a", encoding="utf-8") as output:
            output.write(f"action={action}\n")
            output.write(f"source_sha={source_sha}\n")
            if export_key_b64 is not None:
                # URL-safe base64 cannot inject an Actions output delimiter or
                # newline; keep the public key out of stdout and logs.
                output.write(f"export_key_b64={export_key_b64}\n")
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
