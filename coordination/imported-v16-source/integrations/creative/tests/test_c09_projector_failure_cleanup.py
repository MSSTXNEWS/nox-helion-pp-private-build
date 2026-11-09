"""C09 source contract: failed existing WPF projector initialization must not be cached as ready.
Run: python -m unittest integrations.creative.tests.test_c09_projector_failure_cleanup
This is SOURCE ONLY: .NET/WebView2 installed behavior still needs Windows E06/E07.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / 'integrations/creative/bridge/CreativeHostBridge.cs'

class ProjectorFailureCleanupSourceTest(unittest.TestCase):
    def test_failed_initialization_closes_only_its_window_and_forgets_it(self):
        code = SOURCE.read_text(encoding='utf-8-sig')
        method = code.split('private async Task OpenCreativeProjectorAsync(', 1)[1].split(
            'private async Task<string> StopCreativeWorkerAsync(', 1)[0]
        self.assertIn('Window? openingProjector = null;', method)
        self.assertIn('openingProjector=theater;', method)
        self.assertLess(method.index('openingProjector=theater;'), method.index('theater.Show();'))
        self.assertLess(method.index('theater.Show();'), method.index('await viewer.EnsureCoreWebView2Async(env);'))
        failed = method.split('catch(Exception ex)', 1)[1]
        self.assertIn('openingProjector.Close();', failed)
        self.assertIn('if (ReferenceEquals(_creativeProjector,openingProjector))', failed)
        self.assertRegex(failed, r'_creativeProjector\s*=\s*null;')
        self.assertRegex(failed, r'_creativeProjectorProjectId\s*=\s*null;')
        self.assertIn('CREATIVE_PROJECTOR_CLOSE', failed)

if __name__ == '__main__':
    unittest.main()
