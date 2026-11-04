"""Regression tests of evidence classification, not physical E07."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "coordination/e07/v6_functional_route_gap_u10.py"
spec = importlib.util.spec_from_file_location("u10_route_gate", SCRIPT)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def fixture():
    return {"schema": "NOX-E07-FULL-D02-UIA-v1", "source_sha": gate.SOURCE,
            "setup_sha256": gate.SETUP, "build_id": gate.BUILD,
            "physical_setup_verified": True, "five_uia": "PASS",
            "independent_e07_10_10": "HOLD", "release_accepted": False,
            "five_primary": {"status": "PASS", "actions_invoked": 5,
                             "actions_with_new_visible_heading": list(gate.PRIMARY),
                             "scope": "FIVE_REAL_UIA_CLICKS_AND_NAVIGATION_ONLY",
                             "install_or_model_function_verified": False,
                             "live_inference_verified": False,
                             "release_accepted": False}}


class TestClickCannotApproveFunction(unittest.TestCase):
    def test_exact_clicks_do_not_release(self):
        r = gate.classify(fixture())
        self.assertEqual(r["requires_real_function_probes"],
                         ["INSTALL", "MODELS", "LEARN", "SETTINGS"])
        self.assertEqual(r["status"], "NAVIGATION_ONLY_FUNCTIONAL_HOLD")
        self.assertEqual(r["independent_e07_10_10"], "HOLD")
        self.assertIs(r["release_accepted"], False)

    def test_cross_setup_rejected(self):
        d = fixture(); d["setup_sha256"] = "0" * 64
        with self.assertRaises(gate.Hold): gate.classify(d)

    def test_cross_source_and_build_rejected(self):
        for key in ("source_sha", "build_id"):
            with self.subTest(key=key):
                d = fixture(); d[key] = "wrong"
                with self.assertRaises(gate.Hold): gate.classify(d)

    def test_function_pass_cannot_be_laundered(self):
        d = fixture(); d["five_primary"]["install_or_model_function_verified"] = True
        with self.assertRaises(gate.Hold): gate.classify(d)

    def test_release_and_independent_e07_overclaims_rejected(self):
        for key, val in (("release_accepted", True), ("independent_e07_10_10", "PASS")):
            with self.subTest(key=key):
                d = fixture(); d[key] = val
                with self.assertRaises(gate.Hold): gate.classify(d)

    def test_forged_boolean_count_and_missing_heading_rejected(self):
        for value in (True, 4, 6):
            d = fixture(); d["five_primary"]["actions_invoked"] = value
            with self.assertRaises(gate.Hold): gate.classify(d)
        d = fixture(); d["five_primary"]["actions_with_new_visible_heading"].pop()
        with self.assertRaises(gate.Hold): gate.classify(d)

    def test_scope_or_live_inference_overclaim_rejected(self):
        d = fixture(); d["five_primary"]["scope"] = "FUNCTIONS_VERIFIED"
        with self.assertRaises(gate.Hold): gate.classify(d)
        d = fixture(); d["five_primary"]["live_inference_verified"] = True
        with self.assertRaises(gate.Hold): gate.classify(d)

    def test_duplicate_and_nan_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ui.json"
            for body in ('{"x":1,"x":2}', '{"x":NaN}'):
                path.write_text(body, encoding="utf-8")
                with self.assertRaises(gate.Hold): gate.read_receipt(path)
            path.write_text(json.dumps(fixture()), encoding="utf-8")
            self.assertIs(gate.classify(gate.read_receipt(path))["release_accepted"], False)

    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            origin = Path(tmp) / "origin.json"; link = Path(tmp) / "link.json"
            origin.write_text(json.dumps(fixture()), encoding="utf-8")
            try: link.symlink_to(origin)
            except OSError: self.skipTest("symlink unavailable")
            with self.assertRaises(gate.Hold): gate.read_receipt(link)


if __name__ == "__main__":
    unittest.main()
