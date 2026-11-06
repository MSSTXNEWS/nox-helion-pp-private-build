import json, os, threading, unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.request import urlopen
import server_integrated
class Integration(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  os.environ['NOX_ROOT']=str(Path(__file__).resolve().parent/'EMPTY_TEST_ROOT')
  cls.server=ThreadingHTTPServer(('127.0.0.1',0),server_integrated.Handler)
  server_integrated.PORT=cls.server.server_port
  server_integrated.old.PORT=cls.server.server_port
  server_integrated.old.base.PORT=cls.server.server_port
  cls.worker=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.worker.start()
 @classmethod
 def tearDownClass(cls): cls.server.shutdown();cls.server.server_close()
 def test_routes(self):
  for path in ['','chat.html','training.html','models.html','memory.html','system.html','install.html','projects.html','settings.html','nox-pages.js','nox-pages.css','nox-notices.js']:
   with self.subTest(path=path):
    with urlopen('http://127.0.0.1:%s/'%self.server.server_port+path,timeout=2) as r: self.assertEqual(r.status,200)
 def test_discovery_no_models(self):
  with urlopen('http://127.0.0.1:%s/api/nox/discover'%self.server.server_port,timeout=3) as r:
   obj=json.load(r);self.assertEqual(obj['s03_candidates'],[])
 def test_pages_contract(self):
  with urlopen('http://127.0.0.1:%s/api/nox/pages'%self.server.server_port,timeout=2) as r:
   d=json.load(r);self.assertEqual(len(d['pages']),9)
if __name__=='__main__':unittest.main()