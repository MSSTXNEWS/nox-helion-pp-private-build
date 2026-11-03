"""Exact approved Creative+WOW preimage inverse for MEGA814 (SOURCE ONLY)."""
import hashlib
import importlib.util
from pathlib import Path
import unittest

MODULE=Path(__file__).with_name("stage_original_r11.py")
spec=importlib.util.spec_from_file_location("nox_mega814_original_stage",MODULE)
stage=importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage)

HEAD=(
 '<link rel="stylesheet" href="creative/wow200/proposals/NOX-CINEMA-FX/nox-cinema.css">'
 '<link rel="stylesheet" href="creative/wow200/runtime/home-guard.css">'
 '<link rel="stylesheet" href="creative/wow200/ui/selfbuilder-menu-v2.css">'
 '<link rel="stylesheet" href="creative/wow200/ui/selfbuilder-wow-workbench.css">'
 '<link rel="stylesheet" href="creative/wow200/ui/nox-r11-wow.css">'
 '<link rel="stylesheet" href="creative/wow200/proposals/P01/WOW-MAX10/p01-cinematic-menu.css">'
)
BODY=(
 '<script src="creative/entry.js"></script>'
 '<script type="module" src="creative/wow200/runtime/home-scene.mjs"></script>'
 '<script type="module" src="creative/wow200/ui/onehost-menu-bindings.mjs"></script>'
)

def digest(data):return hashlib.sha256(data).hexdigest()
def mounted(plain):
 return plain.replace("</head>",HEAD+"</head>",1).replace("</body>",BODY+"</body>",1).encode("utf-8")

class OriginalPreimageAdmission(unittest.TestCase):
 def setUp(self):
  self.original='<html><head>\n<meta charset="utf-8">\n</head><body>\n<section id="menu"></section><section id="control"></section>\n</body></html>'
  self.expected=digest(self.original.encode("utf-8"))
 def test_pristine_owner_index_unchanged(self):
  self.assertEqual(stage.verified_index_mode(self.original.encode(),self.expected),"ORIGINAL_R11")
 def test_real_creative_wow200_full_additive_mount_accepted(self):
  self.assertEqual(stage.verified_index_mode(mounted(self.original),self.expected),"D02_CREATIVE_WOW200_VERIFIED")
 def test_reject_extra_injected_tag_even_with_known_mount(self):
  evil=mounted(self.original).replace(b"</head>",b'<script src="unapproved.js"></script></head>')
  with self.assertRaisesRegex(RuntimeError,"HOLD"):
   stage.verified_index_mode(evil,self.expected)
 def test_reject_duplicate_approved_block(self):
  evil=mounted(self.original).replace(b"</head>",HEAD.encode()+b"</head>")
  with self.assertRaises(RuntimeError):
   stage.verified_index_mode(evil,self.expected)
 def test_reject_reordered_or_detached_known_tag(self):
  evil=mounted(self.original).replace(HEAD.encode(),b"",1).replace(b"<head>",b"<head>"+HEAD.encode(),1)
  with self.assertRaisesRegex(RuntimeError,"D02_MARKERS_MISSING_DUPLICATED_HOLD"):
   stage.verified_index_mode(evil,self.expected)
 def test_preserve_crlf_origin_identity(self):
  original=self.original.replace("\n","\r\n")
  self.assertEqual(stage.verified_index_mode(mounted(original),digest(original.encode())),"D02_CREATIVE_WOW200_VERIFIED")
 def test_reject_mutated_original_body(self):
  evil=mounted(self.original.replace('id="control"','id="controls"'))
  with self.assertRaisesRegex(RuntimeError,"PREIMAGE_SHA_HOLD"):
   stage.verified_index_mode(evil,self.expected)

if __name__=="__main__":unittest.main()
