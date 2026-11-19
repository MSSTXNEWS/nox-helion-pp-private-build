"""NOX V29: source-level active routes and D02 no-loss, no external dependencies."""
import unittest, os, posixpath
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlsplit
ROOT=Path(os.environ.get("NOX_V29_SITE_DIR","/mnt/data/nox_v29_site")).resolve()
INDEX_SHA="f3fc804d238146ffe42c50103d3e04c9736b8b587c6572987f59b61a6112eb17"

class Links(HTMLParser):
 def __init__(self):super().__init__();self.refs=[]
 def handle_starttag(self,tag,attrs):
  d=dict(attrs)
  for k in ("src","href","poster"):
   if d.get(k):self.refs.append(d[k])

class ActualSiteLinks(unittest.TestCase):
 def test_original_home_is_unchanged_and_resonance_is_real(self):
  import hashlib
  self.assertEqual(hashlib.sha256((ROOT/"index.html").read_bytes()).hexdigest(),INDEX_SHA)
  route=(ROOT/"resonance.html").read_text("utf8")
  self.assertIn('location.replace("./chat.html")',route)
  self.assertIn('href="chat.html"',route)
  self.assertTrue((ROOT/"chat.html").is_file())
 def test_active_html_static_refs_all_exist(self):
  files={p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*") if p.is_file()}
  active=[n for n in files if n.endswith(".html") and not n.endswith(".template.html")
          and not n.startswith(("original_web_v25_1/","reference/"))]
  self.assertGreaterEqual(len(active),38)
  missing=[]
  for page in active:
   parser=Links();parser.feed((ROOT/page).read_text("utf8","replace"))
   for url in parser.refs:
    if not url or url.startswith(("http:","https:","#","//","data:","blob:","mailto:","tel:","javascript:","/api/")):continue
    raw=urlsplit(url).path
    if not raw:continue
    target=(posixpath.normpath(raw.lstrip("/")) if raw.startswith("/")
            else posixpath.normpath(posixpath.join(posixpath.dirname(page),raw)))
    if target.startswith("../"):continue
    if posixpath.splitext(target)[1] and target not in files:
     missing.append((page,url,target))
  self.assertEqual(missing,[],"Unresolved active source references")
 def test_pc_world_and_hub_links_target_single_primary_resonance(self):
  for page in ("pc/world.html","pc/hub.html"):
   self.assertIn("/resonance.html",(ROOT/page).read_text("utf8"))
  self.assertFalse((ROOT/"resonance.html").read_text("utf8").find('href="chat.html"')<0)

if __name__=="__main__":
 unittest.main(verbosity=2)
