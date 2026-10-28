"""Source-only positive/negative regression for E02/E06 RAG session revocation."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "coordination" / "security"))
from g3_02_rag_revocation_guard import audit_source, git_blob_sha1


PREFIX = """
if (_authorizeNativeSession(nativeScope) is not true)
    throw new UnauthorizedAccessException("Native NOX session not authorized");
var result = await _existingP04.RetrieveAsync(nativeScope.WindowsSid,
    nativeScope.ConversationId,userMessage,topK,stop).ConfigureAwait(false);
"""


class RagReauthorizationTests(unittest.TestCase):
    def test_01_reject_auth_only_before_await(self):
        report = audit_source(PREFIX + "return result;")
        self.assertEqual(report["finding"], "RAG_OWNER_SESSION_REVOCATION_NOT_RECHECKED_AFTER_AWAIT")

    def test_02_accept_recheck_after_await_as_candidate_only(self):
        candidate = PREFIX + """
if (_authorizeNativeSession(nativeScope) is not true)
    throw new UnauthorizedAccessException("Native NOX session revoked");
return result;
"""
        self.assertEqual(audit_source(candidate)["status"], "RECHECK_PATTERN_PRESENT_NEEDS_RUNTIME_QA")

    def test_03_ignore_comment_spoofed_recheck(self):
        source = PREFIX + "// _authorizeNativeSession(nativeScope)\nreturn result;"
        self.assertEqual(audit_source(source)["status"], "HOLD")

    def test_04_reject_other_scope_as_post_await_check(self):
        source = PREFIX + "if (_authorizeNativeSession(otherScope) is not true) throw;\nreturn result;"
        self.assertEqual(audit_source(source)["status"], "HOLD")

    def test_05_unknown_provider_requires_hold(self):
        self.assertEqual(audit_source("var result = await Foo(); return result;")["finding"],
                         "EXPECTED_ORIGINAL_RAG_PATH_MISSING")

    def test_06_reject_noop_post_await_callback(self):
        source = PREFIX + "var ignored = _authorizeNativeSession(nativeScope);\nreturn result;"
        self.assertEqual(audit_source(source)["status"], "HOLD")

    def test_07_reject_if_without_throw(self):
        source = PREFIX + "if (_authorizeNativeSession(nativeScope) is not true) LogOnly();\nreturn result;"
        self.assertEqual(audit_source(source)["status"], "HOLD")

    def test_08_git_blob_sha_is_distinct_from_file_sha256(self):
        self.assertEqual(git_blob_sha1(b"hello\n"), "ce013625030ba8dba906f756967f9e9ca394464a")


if __name__ == "__main__":
    unittest.main()
