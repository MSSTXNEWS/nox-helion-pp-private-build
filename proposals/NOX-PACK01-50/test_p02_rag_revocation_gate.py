"""Source-only NOX V16 E02 regression; Windows native C# execution remains HOLD."""
import pathlib
import re
import unittest

SRC = pathlib.Path(__file__).with_name('P02RagChatOwnerPort.cs')


def audit(src):
    code = re.sub(r'/\*.*?\*/|//[^\n]*', '', src, flags=re.S)
    start = re.search(r'await\s+_existingP04\.RetrieveAsync\s*\(', code)
    ret = re.search(r'\breturn\s+result\s*;', code)
    if not start or not ret or start.end() >= ret.start():
        return False
    after = code[start.end():ret.start()]
    return bool(
        re.search(r'stop\.ThrowIfCancellationRequested\(\);', after)
        and re.search(r'if\s*\(_authorizeNativeSession\(nativeScope\)\s+is\s+not\s+true\)\s*throw\s+new\s+UnauthorizedAccessException', after)
        and 'x.OwnerSid != nativeScope.WindowsSid' in after
        and 'x.ConversationId != nativeScope.ConversationId' in after
        and 'result.ContextText.Length > 24000' in after
    )


class RAGPostAwaitSourceGate(unittest.TestCase):
    def setUp(self):
        self.src = SRC.read_text(encoding='utf-8')

    def test_after_await_stop_and_auth_present(self):
        self.assertTrue(audit(self.src))

    def test_old_preawait_only_fails(self):
        self.assertFalse(audit(self.src.replace(
            'if (_authorizeNativeSession(nativeScope) is not true)\n            throw new UnauthorizedAccessException("Native NOX session revoked during RAG retrieval");',
            '_authorizeNativeSession(nativeScope);')))

    def test_postawait_stop_not_optional(self):
        self.assertFalse(audit(self.src.replace(
            'stop.ThrowIfCancellationRequested();\n        if (_authorizeNativeSession(nativeScope) is not true)',
            'if (_authorizeNativeSession(nativeScope) is not true)')))

    def test_original_p04_provider_must_remain(self):
        self.assertFalse(audit(self.src.replace('_existingP04.RetrieveAsync', '_anotherP04.RetrieveAsync')))

    def test_private_source_citations(self):
        self.assertFalse(audit(self.src.replace('x.OwnerSid != nativeScope.WindowsSid', 'x.OwnerSid == x.OwnerSid')))

    def test_no_duplicate_storage_or_remote_host(self):
        for name in ('new SqliteConnection', 'new OllamaClient', 'new WebApplication', 'HttpListener'):
            self.assertNotIn(name, self.src)


if __name__ == '__main__':
    unittest.main()
