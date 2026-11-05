"""Source-only compatibility tests: none of these grant E07/EXE acceptance."""
import hashlib, pathlib, sys, unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from stage_original_r11 import verified_index_mode, APPROVED_HEAD, APPROVED_BODY
from publish_onehost_payload import EXPECTED
class TestOneHostCompatibility(unittest.TestCase):
 def setUp(self):
  self.original=b'<html><head></head><body><section id="menu"></section><section id="control"></section></body></html>'
  self.sha=hashlib.sha256(self.original).hexdigest()
 def decorated(self):
  text=self.original.decode()
  text=text.replace("</head>","".join(APPROVED_HEAD)+"</head>")
  text=text.replace("</body>","".join(APPROVED_BODY)+"</body>")
  return text.encode()
 def test_unmodified_original(self):
  self.assertEqual(verified_index_mode(self.original,self.sha),"ORIGINAL_R11")
 def test_additive_creative_wow(self):
  self.assertEqual(verified_index_mode(self.decorated(),self.sha),"D02_CREATIVE_WOW200_VERIFIED")
 def test_unapproved_markup_rejected(self):
  with self.assertRaisesRegex(RuntimeError,"PREIMAGE_SHA"):
   verified_index_mode(self.decorated().replace(b"<body>",b'<body data-fake="true">'),self.sha)
 def test_partial_injection_rejected(self):
  with self.assertRaisesRegex(RuntimeError,"MARKERS"):
   verified_index_mode(self.decorated().replace(APPROVED_BODY[0].encode(),b""),self.sha)
 def test_duplicate_import_rejected(self):
  # Canonical anchored insertion remains present, but an extra adjacent tag
  # must invalidate the restored original SHA. Both fail-closed paths are safe.
  with self.assertRaisesRegex(RuntimeError,"PREIMAGE_SHA_HOLD"):
   verified_index_mode(self.decorated().replace(APPROVED_HEAD[0].encode(),APPROVED_HEAD[0].encode()*2),self.sha)
 def test_mega814_native_client_import_resolves_inside_wpf_assets(self):
  """WebView2 maps Assets/ to https://nox.local; no /ui/ root exists."""
  source=(pathlib.Path(__file__).resolve().parent/"mega814.mjs").read_text("utf-8")
  self.assertIn('from "../creative/wow200/ui/onehost-menu-bindings.mjs"',source)
  self.assertNotIn('from "../../ui/onehost-menu-bindings.mjs"',source)
  # The provider file is published by the pinned WOW200 owner stage.
  wow=pathlib.Path(__file__).resolve().parents[2]/"integrations/wow200/stage_wow200.py"
  self.assertTrue(wow.is_file())

 def test_exact_source_payload(self):
  self.assertEqual(len(EXPECTED),14)
  self.assertNotIn("persona-EV.png",EXPECTED)
if __name__=="__main__":unittest.main()
