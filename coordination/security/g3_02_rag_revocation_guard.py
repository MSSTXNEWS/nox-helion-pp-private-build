"""Read-only V16 gate for a pinned PACK01 P02->P04 RAG source candidate.

A source-level heuristic, NOT an installed Windows authorization test.
Never edits the owner file or trusts browser-originated identity claims.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

OWNER_BLOB_SHA1 = "3cf0d077e7598269819597267b5afbf768b7f743"
OWNER_PATH = "proposals/NOX-PACK01-50/P02RagChatOwnerPort.cs"


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def audit_source(source: str) -> dict[str, object]:
    code = re.sub(r"/\*.*?\*/|//[^\n]*", "", source, flags=re.S)
    invocation = re.search(r"await\s+_existingP04\s*\.\s*RetrieveAsync\s*\(", code)
    terminal = re.search(r"return\s+result\s*;", code)
    if not invocation or not terminal or terminal.start() <= invocation.start():
        return {"status": "HOLD", "finding": "EXPECTED_ORIGINAL_RAG_PATH_MISSING"}
    post_await = code[invocation.end():terminal.start()]
    recheck = re.search(r"_authorizeNativeSession\s*\(\s*nativeScope\s*\)", post_await)
    if not recheck:
        return {
            "status": "HOLD",
            "finding": "RAG_OWNER_SESSION_REVOCATION_NOT_RECHECKED_AFTER_AWAIT",
            "owner": "E02/P02 and E06 single-host integrator",
            "scope": "SOURCE_ONLY_INTEGRATION_HOLD",
        }
    return {"status": "RECHECK_PATTERN_PRESENT_NEEDS_RUNTIME_QA", "finding": None}


def main() -> int:
    parser = argparse.ArgumentParser(description="Pinned read-only NOX RAG revocation gate")
    parser.add_argument("owner_source", type=Path, help="Exact PR27 source file; never modify it")
    args = parser.parse_args()
    raw = args.owner_source.read_bytes()
    blob = git_blob_sha1(raw)
    if blob != OWNER_BLOB_SHA1:
        result = {"status": "HOLD", "finding": "OWNER_GIT_BLOB_SOURCE_DRIFT", "expected": OWNER_BLOB_SHA1, "actual": blob}
    else:
        result = audit_source(raw.decode("utf-8"))
        result.update({"source": OWNER_PATH, "git_blob_sha1": blob, "source_sha256": hashlib.sha256(raw).hexdigest()})
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result["status"] == "HOLD" else 0


if __name__ == "__main__":
    raise SystemExit(main())
