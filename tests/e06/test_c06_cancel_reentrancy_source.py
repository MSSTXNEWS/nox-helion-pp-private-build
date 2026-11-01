#!/usr/bin/env python3
"""C06 source guard, not Windows/.NET native acceptance."""
from pathlib import Path
import re
import sys
import unittest

CODE = Path(sys.argv[1]).read_text(encoding='utf-8') if len(sys.argv)>1 else (
    Path(__file__).resolve().parents[2] / 'coordination/e06/OneHostP02WebView2Bridge.cs'
).read_text(encoding='utf-8')
if len(sys.argv)>1:
    sys.argv[:] = [sys.argv[0]]
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
if __name__=='__main__': unittest.main()
