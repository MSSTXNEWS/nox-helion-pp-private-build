"""Source-only compatibility tests: none of these grant E07/EXE acceptance."""
import hashlib, pathlib, sys, unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from stage_original_r11 import verified_index_mode, D02_TAGS
from publish_onehost_payload import EXPECTED
class TestOneHostCompatibility(unittest.TestCase):
 def setUp(self):
  self.original=b'<html><head></head><body><section id="menu"></section><section id="control"></section></body></html>'
  self.sha=hashlib.sha256(self.original).hexdigest()
 def decorated(self):
  text=self.original.decode()
  text=text.replace("</head>",D02_TAGS[1]+D02_TAGS[2]+"</head>")
  text=text.replace("</body>",D02_TAGS[0]+D02_TAGS[3]+"</body>")
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
   verified_index_mode(self.decorated().replace(D02_TAGS[0].encode(),b""),self.sha)
 def test_duplicate_import_rejected(self):
  with self.assertRaisesRegex(RuntimeError,"MARKERS"):
   verified_index_mode(self.decorated()+D02_TAGS[1].encode(),self.sha)
 def test_exact_source_payload(self):
  self.assertEqual(len(EXPECTED),14)
  self.assertNotIn("persona-EV.png",EXPECTED)
if __name__=="__main__":unittest.main()
