"""Source contract of the EXISTING P01 WPF theater, never native QA."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[3]
MEDIA=(ROOT/'integrations/creative/bridge/CreativeHostBridge.cs').read_text(encoding='utf-8')
WEB=(ROOT/'integrations/creative/web/theater.js').read_text(encoding='utf-8')
STAGE=(ROOT/'integrations/creative/stage_creative.py').read_text(encoding='utf-8')

class Tests(unittest.TestCase):
    def test_existing_owner_method_reused(self):
        self.assertIn('private async Task<string> OpenOwnerMediaRouteAsync(', MEDIA)
        self.assertIn('await OpenCreativeProjectorAsync();', MEDIA)
        self.assertIn('routeId is not ("media.player" or "media.subtitles")', MEDIA)
    def test_fresh_native_consent_before_open(self):
        owner=MEDIA.index('private async Task<string> OpenOwnerMediaRouteAsync(')
        section=MEDIA[owner:MEDIA.index('private async Task OpenCreativeProjectorAsync',owner)]
        self.assertLess(section.index('nativeConsent(routeId)'),section.index('await OpenCreativeProjectorAsync()'))
        self.assertIn('Native media consent required',section)
    def test_stop_pre_and_post_async(self):
        section=MEDIA.split('private async Task<string> OpenOwnerMediaRouteAsync(',1)[1].split('private async Task OpenCreativeProjectorAsync',1)[0]
        self.assertGreaterEqual(section.count('stop.ThrowIfCancellationRequested();'),4)
    def test_false_success_prevented(self):
        self.assertIn('MEDIA_PLAYER_UI_OPEN_NOT_PLAYING', MEDIA)
        self.assertIn('SUBTITLE_PICKER_READY_NOT_IMPORTED', MEDIA)
        self.assertIn('MEDIA_OWNER_UI_NOT_READY',MEDIA)
    def test_existing_local_media_boundary(self):
        self.assertIn('SetVirtualHostNameToFolderMapping("nox.local"',MEDIA)
        self.assertIn('viewer.CoreWebView2.Settings.IsWebMessageEnabled=false;',MEDIA)
        self.assertIn('CoreWebView2HostResourceAccessKind.DenyCors',MEDIA)
    def test_subtitles_reuse_existing_file_input(self):
        self.assertIn("document.getElementById('subtitles')",MEDIA)
        self.assertIn("$('subtitles').onchange",WEB)
        self.assertIn('function toWebVtt',WEB)
    def test_disposable_stage_reuses_owner_file(self):
        self.assertIn("sidecar=source/'bridge/CreativeHostBridge.cs'",STAGE)
        self.assertIn('bridge.write_bytes(sidecar.read_bytes())',STAGE)

if __name__=='__main__':unittest.main()
