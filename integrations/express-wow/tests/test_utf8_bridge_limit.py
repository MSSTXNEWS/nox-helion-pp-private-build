"""Source-level E06 native-to-worker UTF-8 contract regression, not a Windows compile claim."""
import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
BRIDGE=ROOT/'integrations/creative/bridge/CreativeHostBridge.cs'
WORKER=ROOT/'integrations/creative/creative_worker.py'

class NativeLimit(unittest.TestCase):
 def test_unicode_budget_matches_native_and_worker(self):
  bridge=BRIDGE.read_text(encoding='utf-8')
  worker=WORKER.read_text(encoding='utf-8')
  self.assertIn('Encoding.UTF8.GetByteCount(payload.GetRawText())>262144',bridge)
  self.assertNotIn('payload.GetRawText().Length>262144',bridge)
  self.assertIn('MAX_REQUEST = 262_144',worker)
  self.assertIn("len(line.encode('utf-8')) > MAX_REQUEST",worker)
  malicious=json.dumps({'action':'route_chat','text':'🎬'*80000},ensure_ascii=False)
  self.assertLess(len(malicious),262144)
  self.assertGreater(len(malicious.encode('utf-8')),262144)

if __name__=='__main__':unittest.main()