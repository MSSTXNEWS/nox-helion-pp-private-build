"""Fail-closed physical SETTINGS/BACK UIA witness regressions."""
from __future__ import annotations
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/"coordination"/"e07"))
from probe_v6_settings_roundtrip_u12 import classify, SCHEMA
from independent_setup_e07 import Hold

class TestSettingsRoundtrip(unittest.TestCase):
    def good(self):
        return {"schema":SCHEMA,"initialSettingsHeading":False,
                "settingsInvoke":True,"settingsHeadingAfter":True,
                "backControlVisibleAfterSettings":True,"backInvoke":True,
                "settingsHeadingAfterBack":False,
                "fivePrimaryVisibleAfterBack":True,"sameOriginalHwndAlive":True}
    def test_pass_is_not_release_or_full_function(self):
        out=classify(self.good())
        self.assertEqual(out["uia_invocations"],2)
        self.assertFalse(out["full_settings_function_verified"])
        self.assertFalse(out["release_accepted"])
        self.assertEqual(out["independent_e07_10_10"],"HOLD")
    def test_missing_fields_rejected(self):
        for k in self.good():
            with self.subTest(k=k),self.assertRaises(Hold):
                d=self.good(); del d[k]; classify(d)
    def test_unexpected_fields_rejected(self):
        d=self.good(); d["release_accepted"]=True
        with self.assertRaises(Hold):classify(d)
    def test_false_actions_and_transitions_rejected(self):
        for k in self.good():
            if k=="schema":continue
            with self.subTest(k=k),self.assertRaises(Hold):
                d=self.good();d[k]=not d[k];classify(d)
    def test_wrong_types_rejected(self):
        d=self.good();d["settingsInvoke"]=1
        with self.assertRaises(Hold):classify(d)
    def test_invented_result_rejected(self):
        with self.assertRaises(Hold):classify({"status":"PASS"})

if __name__ == "__main__":unittest.main()
