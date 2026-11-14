"""Focused SOURCE regression for C10: no native P03 lifecycle metadata to external WebView2.
Run from repository root: python tests/e06/test_c10_model_lifecycle_origin_source.py
This is deliberately not a Windows/WPF runtime acceptance test.
"""
from pathlib import Path
import re
import unittest

SOURCE = Path('coordination/e06/MainWindow.NativeP02.cs')


def body_segment(source, start, end):
    return source.split(start, 1)[1].split(end, 1)[0]


class C10NativeLifecycleOriginGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SOURCE.read_text(encoding='utf-8')
        cls.sink = body_segment(cls.source, 'public async ValueTask PublishToP01Async(',
                                'public async ValueTask PublishToP05Async(')

    def test_model_events_are_blocked_before_generic_page_post(self):
        gate = re.search(r'if\s*\(core is null \|\| bridge is null \|\|\s*bridge.BrowserExternalActive \|\|\s*!IsTrustedNoxDocument\(core.Source\)\s*\|\|'
                         r'\s*string.IsNullOrEmpty\(sid\) \|\|'
                         r'\s*!owner.NativeP02Acl\(sid, "models.queue"\)\) return;', self.sink)
        self.assertIsNotNone(gate, 'missing mapped-origin AND SID/ACL gate')
        self.assertLess(gate.start(), self.sink.index('owner.PostMessage(new {'))
        self.assertIn('if (IsP03Document(core.Source))', self.sink)
        self.assertIn('var bridge = owner._nativeP02Bridge;', self.sink)

    def test_trusted_url_is_exact_native_mapped_origin(self):
        helper = body_segment(self.source, 'private static bool IsTrustedNoxDocument(',
                              'private static bool IsP03Document(')
        for required in ('Uri.TryCreate(source, UriKind.Absolute', 'uri.Scheme == Uri.UriSchemeHttps',
                         'uri.IsDefaultPort', 'uri.UserInfo.Length == 0',
                         'uri.Host.Equals("nox.local", StringComparison.OrdinalIgnoreCase)'):
            self.assertIn(required, helper)
        self.assertNotIn('StartsWith(', helper)
        self.assertNotIn('Contains(', helper)

    def test_no_other_host_or_model_lifecycle_stage_was_replaced(self):
        self.assertIn('await owner.Dispatcher.InvokeAsync(() => {', self.sink)
        self.assertIn('kind="modelLifecycle"', self.sink)
        self.assertIn('core.PostWebMessageAsJson(ModelWowBridgeContract.EventJson(item))', self.sink)
        self.assertIn('owner.AppendRuntimeV3(', self.source)


if __name__ == '__main__':
    unittest.main()
