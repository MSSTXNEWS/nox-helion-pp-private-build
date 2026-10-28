"""Source-first WOW / Persona integration contract; never grants Windows E07."""
import json, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
CR=ROOT/"integrations/creative"
WOW=ROOT/"integrations/wow200"
class VisualNoLoss(unittest.TestCase):
 def test_persona_screen_is_mounted_on_existing_studio(self):
  html=(CR/"web/studio.html").read_text(encoding="utf-8")
  self.assertEqual(html.count('src="studio.js"'),1)
  self.assertEqual(html.count('src="persona-media.js"'),1)
  self.assertEqual(html.count('href="persona-media.css"'),1)
  self.assertLess(html.index('src="studio.js"'),html.index('src="persona-media.js"'))
  self.assertIn('main class="content"',html)
 def test_asset_stage_is_original_single_owner(self):
  source=(CR/"stage_creative.py").read_text(encoding="utf-8")
  self.assertIn("for p in sorted(web.iterdir()):",source)
  self.assertIn("CREATIVE_ALREADY_STAGED_OR_CONFLICT",source)
 def test_ev_identity_stays_unapproved_and_video_only_when_available(self):
  manifest=json.loads((CR/"PERSONA_R15_MEDIA_SOURCE.json").read_text())
  self.assertEqual(manifest["active_portrait_media"],["KV","AM","LA","KW"])
  self.assertEqual(manifest["blocked_persona"],["EV"])
  js=(CR/"web/persona-media.js").read_text()
  self.assertIn("IDENTITY_CONFLICT_HOLD",js)
  self.assertIn("addEventListener('error'",js)
  self.assertIn("prefers-reduced-motion: reduce",js)
  self.assertIn("video.pause()",js)
 def test_home_test_import_path_exists(self):
  js=(WOW/"tests/test_home_scene.mjs").read_text()
  self.assertIn("new URL('../runtime/home-scene.mjs',import.meta.url)",js)
  self.assertTrue((WOW/"runtime/home-scene.mjs").is_file())
 def test_utf8_budget_uses_bytes_not_chars(self):
  cs=(CR/"bridge/CreativeHostBridge.cs").read_text()
  worker=(CR/"creative_worker.py").read_text()
  self.assertIn("Encoding.UTF8.GetByteCount(payload.GetRawText())>262144",cs)
  self.assertNotIn("payload.GetRawText().Length>262144",cs)
  self.assertIn("MAX_REQUEST = 262_144",worker)
  self.assertIn("len(line.encode('utf-8')) > MAX_REQUEST",worker)
 def test_no_false_wow_200_or_release_claim(self):
  stage=(WOW/"stage_wow200.py").read_text()
  self.assertIn('"complete_200_runtime_verified":False',stage)
  self.assertIn('"release_accepted":False',stage)
if __name__=="__main__": unittest.main()
