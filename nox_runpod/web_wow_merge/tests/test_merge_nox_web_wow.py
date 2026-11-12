import unittest, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from merge_nox_web_wow import merge, digest, dependencies, CHAT_MAIN, ROUTES

class MergeTests(unittest.TestCase):
    def setUp(self):
        self.web={n:b"<html><head></head><body></body></html>" for n in ROUTES}
        self.web["index.html"]=b"ORIGINAL D02 and 14 worlds"
        self.v25={"chat.html":b'<script src="./chat-ui-v25.js"></script>',
                  "memory.html":b'<script src="./memory-v25.js"></script>',
                  "chat-ui-v25.js":b"chat V25",
                  "memory-v25.js":b"memory V25"}
    def test_preserves_d02_and_v25_chat_and_routes(self):
        m,r=merge(self.web,self.v25,{"chat.html":b"old"})
        self.assertEqual(r["status"],"SOURCE_MERGED_PHYSICAL_QA_HOLD")
        self.assertEqual(m["index.html"],self.web["index.html"])
        self.assertEqual(m["chat.html"],self.v25["chat.html"])
        self.assertEqual(m["memory.html"],self.v25["memory.html"])
        self.assertEqual(m["chat-ui-v25.js"],b"chat V25")
    def test_blocks_shared_dependency_conflict(self):
        self.web["chat-ui-v25.js"]=b"other script"
        m,r=merge(self.web,self.v25,{})
        self.assertIsNone(m)
        self.assertEqual(r["status"],"HOLD_CONFLICTS")
        self.assertEqual(r["conflicts"][0]["path"],"chat-ui-v25.js")
    def test_never_replaces_original_home_via_chat(self):
        p=dict(self.v25,**{"index.html":b"new fake D02"})
        m,r=merge(self.web,p,{})
        self.assertEqual(m["index.html"],self.web["index.html"])
    def test_v24_can_only_supply_missing(self):
        p={"chat.html":b'<script src="./legacy.js"></script>',
           "memory.html":b'old memory',"legacy.js":b"legacy"}
        m,r=merge(self.web,self.v25,p)
        self.assertEqual(m["chat.html"],self.v25["chat.html"])
        self.assertNotIn("legacy.js",m)
    def test_no_claim_gpu_or_s03_runtime(self):
        m,r=merge(self.web,self.v25,{})
        self.assertEqual(r["s03"],"NOT_TESTED")
        self.assertEqual(r["gpu_training"],"UNTOUCHED")
        self.assertFalse(r["production_modified"])
if __name__=="__main__":unittest.main()
