"""R65 source-only regression: original WPF renderer process recovery, not installed E07."""
import hashlib
from pathlib import Path
import unittest
R=Path(__file__).resolve().parents[2]
P=R/"coordination/e06/OneHostP02WebView2Bridge.cs"
class RendererRecovery(unittest.TestCase):
 def test_render_failure_requires_one_trusted_reload(self):
  s=P.read_text("utf-8")
  for x in ("CoreWebView2ProcessFailedKind.RenderProcessExited",
            "Interlocked.CompareExchange(ref _rendererReloadAttempts, 1, 0)",
            "!NativeSidMatches() || !ExactShellReturn(_web.Source)",
            "_web.Reload();"):
   self.assertIn(x,s)
 def test_browser_failure_never_grants_stale_ipc(self):
  s=P.read_text("utf-8")
  for x in ("CoreWebView2ProcessFailedKind.BrowserProcessExited",
            "_browserProcessLost = true;",
            "_rendererAwaitingTrustedContent || !ExactShellReturn(e.Source)",
            "!_rendererAwaitingTrustedContent && !_lifetime.IsCancellationRequested",
            "_rendererAwaitingTrustedContent && _rendererReloadInitiated"):
   self.assertIn(x,s)
 def test_exact_build_pins(self):
  raw=P.read_bytes()
  sha=hashlib.sha1(b"blob "+str(len(raw)).encode()+bytes([0])+raw).hexdigest()
  ps=(R/"coordination/e06/build_onehost_installer.ps1").read_text("utf-8")
  py=(R/"coordination/e06/t06_compile_original_wpf_p02.py").read_text("utf-8")
  self.assertIn("blob='"+sha+"'",ps)
  self.assertIn('"coordination/e06/OneHostP02WebView2Bridge.cs":"'+sha+'"',py)
if __name__=="__main__": unittest.main()
