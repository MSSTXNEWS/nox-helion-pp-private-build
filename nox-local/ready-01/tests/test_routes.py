import os,sys,json,threading,unittest,urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server_mega as m
class ApiTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  m.PORT=18899;m.base.PORT=18899
  cls.http=ThreadingHTTPServer(('127.0.0.1',18899),m.Handler)
  cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True);cls.thread.start()
 @classmethod
 def tearDownClass(cls):cls.http.shutdown();cls.http.server_close()
 def get(self,route):
  with urllib.request.urlopen('http://127.0.0.1:18899'+route,timeout=4) as resp:return resp.status,json.loads(resp.read())
 def test_health(self):
  code,x=self.get('/api/mega/health');self.assertEqual((code,x['status']),(200,'READY'))
 def test_trainer_and_s03_hold(self):
  _,t=self.get('/api/training/status');self.assertFalse(t['can_start'])
  _,s=self.get('/api/s03/status');self.assertIn(s['status'],('HOLD','READ_ONLY'))
 def test_push_public_honest(self):
  _,p=self.get('/api/push/status');self.assertFalse(p['browser_close_delivery_verified'])
 def test_unknown_route(self):
  with self.assertRaises(urllib.error.HTTPError):self.get('/api/fake')
 def test_stop_cancels_registered_upstream(self):
  import threading
  class FakeStream:
   closed=False
   def close(self):self.closed=True
  up=FakeStream();evt=threading.Event()
  m.ACTIVE['unit-stop-0001']={'stop':evt,'upstream':up}
  body=json.dumps({'request_id':'unit-stop-0001'}).encode()
  req=urllib.request.Request('http://127.0.0.1:18899/api/chat/stop',data=body,headers={'Content-Type':'application/json'},method='POST')
  with urllib.request.urlopen(req,timeout=3) as resp:
   self.assertTrue(json.loads(resp.read())['stopped'])
  self.assertTrue(evt.is_set());self.assertTrue(up.closed)
  m.ACTIVE.pop('unit-stop-0001',None)
 def test_push_subscribe_blocked_unconfigured(self):
  b=b'{}'; req=urllib.request.Request('http://127.0.0.1:18899/api/push/subscribe',data=b,headers={'Content-Type':'application/json'},method='POST')
  with self.assertRaises(urllib.error.HTTPError) as c:urllib.request.urlopen(req,timeout=3)
  self.assertEqual(c.exception.code,409)
if __name__=='__main__':unittest.main()