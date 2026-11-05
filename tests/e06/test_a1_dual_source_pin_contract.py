"""Prevent reintroducing stale A1 FirstBoot pins between both original owner stages."""
from pathlib import Path
import hashlib
import json
import re
import unittest

ROOT=Path(__file__).resolve().parents[2]
MANIFEST=ROOT/"coordination/e06/A1_BUILD_SOURCES.lock.json"
STAGE=ROOT/"coordination/e06/stage_native_stdio.py"
SOURCE=ROOT/"src/nox_selfbuilder"

def git_blob(content):
    return hashlib.sha1(b"blob "+str(len(content)).encode("ascii")+b"\0"+content).hexdigest()

class A1DualSourcePin(unittest.TestCase):
    def test_all_staged_a1_sources_match_real_git_blobs(self):
        entries=json.loads(MANIFEST.read_text("utf-8"))["sources"]
        native=STAGE.read_text("utf-8")
        self.assertEqual(len(entries),10)
        for name,expected in entries.items():
            path=SOURCE/name
            self.assertTrue(path.is_file(),name)
            self.assertEqual(git_blob(path.read_bytes()),expected,name)
            if name!="worm_providers.py":
                needle="('src/nox_selfbuilder/"+name+"', 'nox_selfbuilder/"+name+"', '"+expected+"')"
                self.assertIn(needle,native)

    def test_firstboot_not_stale_again(self):
        name="firstboot_coordinator.py"
        expected=json.loads(MANIFEST.read_text("utf-8"))["sources"][name]
        self.assertIn(name,STAGE.read_text("utf-8"))
        self.assertEqual(git_blob((SOURCE/name).read_bytes()),expected)

if __name__=="__main__":
    unittest.main()
