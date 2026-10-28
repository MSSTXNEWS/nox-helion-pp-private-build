"""NOX Projector R14: source contract regression, does not claim native Windows QA."""
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class ProjectorContract(unittest.TestCase):
 def test_theater_local_asset_loading(self):
  html=(ROOT/'web/theater.html').read_text(encoding='utf8')
  js=(ROOT/'web/theater.js').read_text(encoding='utf8')
  self.assertIn('<script src="theater.js"></script>',html)
  self.assertIn("url('../menu_sections.png')",html)
  self.assertNotIn('/api/media/',js)
  self.assertIn('nox-projects.invalid',js)
 def test_no_native_mapping_for_browser_preview(self):
  js=(ROOT/'web/theater.js').read_text(encoding='utf8')
  self.assertIn("query.get('local_project_media')==='1'",js)
  self.assertIn("/^[a-z0-9_-]{1,48}$/i.test(project)",js)
  self.assertIn("const f=e.target.files[0]",js)
 def test_authenticated_source_origin_and_wpf_optin(self):
  entry=(ROOT/'web/entry.js').read_text(encoding='utf8')
  stage=(ROOT/'stage_creative.py').read_text(encoding='utf8')
  cs=(ROOT/'bridge/CreativeHostBridge.cs').read_text(encoding='utf8')
  studio=(ROOT/'web/studio.js').read_text(encoding='utf8')
  self.assertIn('event.source!==frame.contentWindow',entry)
  self.assertIn("type:'nox.creative.projector.v1',project_id:project",studio)
  self.assertIn('OpenCreativeProjectorAsync(GetString(json.RootElement,"projectId"))',stage)
  self.assertIn('Uri.EscapeDataString(projectId)',cs)
  self.assertIn('FileAttributes.ReparsePoint',cs)
  self.assertIn('IsWebMessageEnabled=false',cs)
  self.assertIn('CoreWebView2HostResourceAccessKind.DenyCors',cs)
 def test_projector_has_no_arbitrary_web_or_file_navigation(self):
  cs=(ROOT/'bridge/CreativeHostBridge.cs').read_text(encoding='utf8')
  self.assertIn('NavigationStarting',cs)
  self.assertIn('uri.Scheme!="https"',cs)
  self.assertIn('uri.Host.Equals("nox.local",StringComparison.OrdinalIgnoreCase)',cs)
  self.assertNotIn('CoreWebView2HostResourceAccessKind.Allow',cs)
if __name__=='__main__':unittest.main()