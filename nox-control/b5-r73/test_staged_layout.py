"""One installed-layout acceptance test, synthetic data only."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile
from stage_bundle import build, FILES

class StagedLayout(unittest.TestCase):
    def test_exact_layout(self):
        repo=Path(os.environ["B5_REPO"])
        raw=build(repo)
        self.assertEqual(raw, build(repo))
        with tempfile.TemporaryDirectory() as d:
            dest=Path(d)
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                m=json.loads(z.read("manifest.json"))
                self.assertEqual(set(z.namelist()), {"manifest.json", *(x[0] for x in FILES)})
                self.assertEqual(len(m["files"]), 10)
                for item in m["files"]:
                    data=z.read(item["name"])
                    self.assertEqual(hashlib.sha256(data).hexdigest(),item["sha256"])
                    self.assertEqual(len(data),item["bytes"])
                self.assertFalse(m["native_accepted"])
                z.extractall(dest)
            env=dict(os.environ, PYTHONPATH=str(dest)+os.pathsep+os.environ["B5_FIXTURES"])
            cmd="""import contextlib,json,subprocess
from pathlib import Path
import retained_pair
from test_retained_pair import fixture,descriptors,DIALOG,SESSION
assert Path(retained_pair.__file__).resolve().parent==Path.cwd()
with contextlib.ExitStack() as stack:
    receipts,turns=fixture()
    packet=retained_pair.compose_pair(dialog_id=DIALOG,session_id=SESSION,artifacts=descriptors(stack),receipts=receipts,turns=turns)
    node='const r=require("./b3_r71_physical_terminal_composition.cjs"); console.log(JSON.stringify(r.check(JSON.parse(require("node:fs").readFileSync(0,"utf8")))))'
    result=json.loads(subprocess.check_output(["node","-e",node],input=json.dumps(packet,ensure_ascii=False).encode("utf-8")))
    assert result["consistent"] is True and result["turns"]==2 and result["readbacks"]==4
    assert all(result[k] is False for k in ("native_accepted","authentication_verified","next_post_allowed"))
    print("STAGED_LAYOUT turns=2 readbacks=4 native_accepted=false")
"""
            subprocess.run([sys.executable,"-B","-c",cmd],cwd=dest,env=env,check=True)

if __name__=="__main__":
    unittest.main()
