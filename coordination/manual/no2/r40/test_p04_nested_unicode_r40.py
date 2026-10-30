"""Independent T08 R40 regression: escaped Unicode needs nested traversal.

Load original PR162 source by default; set NOX_P04_PROBE_PATH to isolated candidate
for green validation. Expected original: 3 RED / 3 GREEN. No model/GPU needed.
"""
from pathlib import Path
import importlib.util
import json
import os
import unittest

ROOT=Path(__file__).resolve().parents[4]
SOURCE=Path(os.environ.get("NOX_P04_PROBE_PATH",
                            ROOT/"Packages"/"P04"/"model_snapshot_probe.py"))
spec=importlib.util.spec_from_file_location("nox_r40_p04_nested",SOURCE)
if spec is None or spec.loader is None: raise RuntimeError("MISSING_P04_SOURCE")
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class NestedUnicodeR40(unittest.TestCase):
    def test_nested_object_value_rejected(self):
        with self.assertRaises(ValueError):
            m._strict_json_object(r'{"model_type":"qwen3","extra":{"note":"\ud800"}}')

    def test_nested_object_key_rejected(self):
        with self.assertRaises(ValueError):
            m._strict_json_object(r'{"model_type":"qwen3","extra":{"\ud800":"bad"}}')

    def test_nested_list_surrogate_rejected(self):
        with self.assertRaises(ValueError):
            m._strict_json_object(r'{"model_type":"qwen3","tags":["ok","\udfff"]}')

    def test_valid_supplementary_unicode_pair(self):
        good=m._strict_json_object(r'{"model_type":"qwen3","tags":["\ud83d\ude80"]}')
        self.assertEqual(good["tags"], ["🚀"])

    def test_overflow_still_rejected(self):
        with self.assertRaises(ValueError):
            m._strict_json_object('{"model_type":"qwen3","extra":1e9999}')

    def test_positive_finite_nested_metadata(self):
        doc=m._strict_json_object('{"model_type":"qwen3","meta":{"license":"Apache-2.0","x":1.25}}')
        self.assertEqual(doc["meta"]["x"],1.25)
if __name__=="__main__":unittest.main()
