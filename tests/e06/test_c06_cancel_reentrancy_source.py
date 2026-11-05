#!/usr/bin/env python3
"""C06 source guard, not Windows/.NET native acceptance."""
from pathlib import Path
import re
import sys
import unittest

# unittest discovery owns argv; only direct invocation may select a fixture.
SOURCE = (Path(__file__).resolve().parents[2] /
          'coordination/e06/OneHostP02WebView2Bridge.cs')
if __name__ == '__main__' and len(sys.argv) > 1 and not sys.argv[1].startswith('-'):
    SOURCE = Path(sys.argv.pop(1)).resolve()
CODE = SOURCE.read_text(encoding='utf-8')
METHOD=CODE.split('private void RevokeDocument()',1)[1].split('private async Task StopRevokedChatAsync()',1)[0]
class C06CancellationReentrancySource(unittest.TestCase):
    def test_old_lifetime_swapped_before_cancellation(self):
        self.assertRegex(METHOD,r'var revoked\s*=\s*_document\s*;')
        self.assertLess(METHOD.index('_document = new CancellationTokenSource();'),METHOD.index('revoked.Cancel();'))
    def test_callback_exception_cannot_abort_owner_stop(self):
        self.assertRegex(METHOD,r'catch\s*\(AggregateException\)\s*\{')
        self.assertRegex(METHOD,r'finally\s*\{\s*revoked.Dispose\(\);\s*\}')
        self.assertLess(METHOD.index('revoked.Dispose();'),METHOD.index('StopRevokedChatAsync();'))
    def test_revoke_retains_all_epoch_and_stop_invariants(self):
        for marker in ('Interlocked.Increment(ref _epoch)', 'Interlocked.Increment(ref _streamEpoch)',
                       'Interlocked.CompareExchange(ref _stopPending, 1, 0)', 'StopRevokedChatAsync()',
                       'Never clear _usedIds'):
            self.assertIn(marker,METHOD)
    def test_no_external_ipc_unlock_or_second_host(self):
        for marker in ('_externalMode = false', 'IsWebMessageEnabled = true',
                       'AreHostObjectsAllowed = true', 'new CoreWebView2', 'Navigate('):
            self.assertNotIn(marker,METHOD)
    def test_menu_stop_negative_native_ack_never_becomes_requested(self):
        # Native success must survive original owner receipt validation,
        # not merely a transport Accepted bit. SOURCE_ONLY; .NET not run.
        main = (SOURCE.parent / 'MainWindow.NativeP02.cs').read_text(encoding='utf-8')
        menu = main.split('if (route == "menu.binding") {', 1)[1].split('if (route == "menu.dispatch") {', 1)[0]
        stop = menu.split('if (name == "stop") {', 1)[1].split('if (name == "button")', 1)[0]
        self.assertRegex(stop, r'if\s*\(!nativeStop\.Accepted\s*\|\|\s*!string\.IsNullOrEmpty\(nativeStop\.ErrorCode\)\s*\|\|\s*LegacyOwnerDenial\(nativeStop\.Result\)\)')
        self.assertLess(stop.index('LegacyOwnerDenial(nativeStop.Result)'), stop.index('MENU_STOP_REQUESTED'))
        self.assertIn('NativeP02Acl(stopSid, "chat.stop")',stop)

    def test_menu_model_worker_negative_native_ack_never_becomes_result(self):
        main = (SOURCE.parent / 'MainWindow.NativeP02.cs').read_text(encoding='utf-8')
        menu = main.split('if (route == "menu.binding") {', 1)[1].split('if (route == "menu.dispatch") {', 1)[0]
        self.assertRegex(menu,r'if\s*\(!ownerResult\.Accepted\s*\|\|\s*!string\.IsNullOrEmpty\(ownerResult\.ErrorCode\)\s*\|\|\s*LegacyOwnerDenial\(ownerResult\.Result\)\s*\|\|')
        self.assertLess(menu.index('LegacyOwnerDenial(ownerResult.Result)'), menu.index('MENU_NATIVE_OWNER_RESULT'))
        self.assertIn('ConfirmP02NativeAsync(ownerRoute, ownerPayload, cancel)',menu)
        self.assertIn('MENU_OWNER_REVOKED_HOLD',menu)

if __name__=='__main__': unittest.main()
