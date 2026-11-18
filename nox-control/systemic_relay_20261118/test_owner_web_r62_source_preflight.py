"""Source-only bounded R6.2 web-hash preflight tests, no native calls."""
import importlib.util
from pathlib import Path
import re
from unittest import TestCase,main
from unittest.mock import patch

SOURCE = Path(__file__).with_name("owner_web_r62_source_preflight.py")
spec=importlib.util.spec_from_file_location("r62_preflight",SOURCE)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class R62PreflightTests(TestCase):
    def test_fixed_source_hashes_and_scope(self):
        self.assertEqual(len(m.SOURCE),10)
        self.assertEqual(len(m.R62),2)
        for name,value in {**m.SOURCE,**m.R62,**m.LIVE}.items():
            self.assertNotIn("..",name.split("/"))
            self.assertRegex(value,r"^[0-9a-f]{64}$")
        self.assertEqual(m.checksum("../../etc/passwd"),{"state":"SCOPE_HOLD"})

    def test_page_absence_invalidates_matching_claim(self):
        found={p:{"state":"KNOWN","version":["R5_BASE"]} for p in m.SOURCE}
        found["pc/pages/voice/index.html"]={"state":"MISSING"}
        with patch.object(m,"checksum",side_effect=lambda p:found[p]):
            with patch("builtins.print") as output:
                m.main()
        import json
        report=output.call_args_list[0].args[0].split("NOX_MAINT_WEB_R62_PREFLIGHT=",1)[1]
        self.assertFalse(json.loads(report)["all_navigable_pages_match_r5"])

if __name__=="__main__":main()
