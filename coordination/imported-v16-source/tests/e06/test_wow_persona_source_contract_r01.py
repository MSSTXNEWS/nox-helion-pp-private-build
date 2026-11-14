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
 def test_persona_zip_is_optional_and_owner_sha_gated(self):
  code=(ROOT/"coordination/e06/build_onehost_installer.ps1").read_text()
  self.assertIn("[string]$PersonaBundlePath=''",code)
  self.assertIn("PERSONA_REQUIRES_ORIGINAL_VISUAL_STAGE",code)
  self.assertIn("5eed031e9f8dc5fb9c829e0dfa0668014b7eda36",code)
  self.assertIn("9abc124ce1a543417afcd2a08097c5d72b5901a10830869cf495fa7045330ec7",code)
  self.assertLess(code.index("& $py.Source $wowScript $source $wow"),code.index("& $py.Source $personaScript $source $personaBundle"))
  self.assertLess(code.index("& $py.Source $personaScript $source $personaBundle"),code.index("& dotnet publish $project"))
  self.assertIn("persona_media_staged=$wantsPersona",code)
  self.assertIn("persona_windows_media_accepted=$false",code)

 def test_backend_status_is_rendered_as_text_not_markup(self):
  studio=(CR/"web/studio.js").read_text()
  self.assertNotIn(".innerHTML",studio)
  self.assertIn("title.textContent=name",studio)
  self.assertIn("full.textContent=JSON.stringify(report,null,2)",studio)
  self.assertIn("quick.replaceChildren(rows.cloneNode(true))",studio)
  self.assertIn("detail.replaceChildren(rows,full)",studio)
  self.assertIn("typeof ready!=='boolean'",studio)

 def test_no_false_wow_200_or_release_claim(self):
  stage=(WOW/"stage_wow200.py").read_text()
  self.assertIn('"complete_200_runtime_verified":False',stage)
  self.assertIn('"release_accepted":False',stage)
 def test_projector_only_maps_valid_local_movie_in_native_host(self):
  stage=(CR/"stage_creative.py").read_text()
  entry=(CR/"web/entry.js").read_text()
  studio=(CR/"web/studio.js").read_text()
  movie=(CR/"web/theater.js").read_text()
  bridge=(CR/"bridge/CreativeHostBridge.cs").read_text()
  builder=(ROOT/"coordination/e06/build_onehost_installer.ps1").read_text()
  self.assertIn('OpenCreativeProjectorAsync(GetString(json.RootElement,"projectId"))',stage)
  self.assertIn("type:'nox.creative.projector.v1',project_id:project",studio)
  self.assertIn("action:'creativeProjector',projectId:project",entry)
  self.assertIn("OpenCreativeProjectorAsync(string? requestedProjectId",bridge)
  self.assertIn("Uri.EscapeDataString(projectId)",bridge)
  self.assertIn("FileAttributes.ReparsePoint",bridge)
  self.assertIn("CoreWebView2HostResourceAccessKind.DenyCors",bridge)
  self.assertIn("query.get('local_project_media')==='1'",movie)
  self.assertIn("nox-projects.invalid",movie)
  engine=(CR/"nox_fastpack/engine.py").read_text()
  self.assertIn('self.projects=self.root/"projects"',engine)
  self.assertIn('output=folder/"NOX_MOVIE_FINAL.mp4"',engine)
  self.assertIn("chooseSubtitle",movie)
  self.assertIn("if(event.key==='F11'",movie)
  self.assertIn("9d6b22198bd57362477afa1a7132c982793c1a64",builder)
if __name__=="__main__": unittest.main()
