"""NOX V16 manual #2 R36: independent P04 fail-closed parser regressions.

These are deliberately RED on the cited original source until owner #3 fixes
P04 and owner #1 integrates the approved patch. No training, CUDA, download
or product mutation. Run: python -m unittest discover -s coordination/manual/no2/r36
-p test_p04_snapshot_r36.py -v
"""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "Packages" / "P04" / "model_snapshot_probe.py"
spec = importlib.util.spec_from_file_location("nox_p04_snapshot_r36", SCRIPT)
if spec is None or spec.loader is None:
    raise RuntimeError("P04_SOURCE_MISSING")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def weights_file(root: Path, tensors: dict):
    payload = json.dumps(tensors, separators=(",", ":")).encode("utf-8")
    f = root / "model.safetensors"
    f.write_bytes(len(payload).to_bytes(8, "little") + payload)
    return f


class ModelSnapshotR36(unittest.TestCase):
    def test_reject_infinite_exponent_even_without_nan_constant(self):
        # CPython json.loads('1e9999') is +inf, despite parse_constant hooks.
        with self.assertRaises(ValueError):
            probe._strict_json_object('{"model_type":"qwen3","value":1e9999}')

    def test_reject_lone_utf16_surrogate_even_when_escaped(self):
        # Malformed Unicode must not enter immutable model metadata.
        with self.assertRaises(ValueError):
            probe._strict_json_object(r'{"model_type":"qwen3","bad":"\ud800"}')

    def test_reject_zero_tensor_with_shape_dimension_larger_than_u64(self):
        with tempfile.TemporaryDirectory(prefix="nox_p04_r36_") as temp:
            p = weights_file(Path(temp), {
                "empty": {"dtype": "F32", "shape": [0, 2**64],
                          "data_offsets": [0, 0]}
            })
            with self.assertRaises(ValueError):
                probe._weight_header(p)

    def test_valid_finite_metadata_is_accepted(self):
        doc = probe._strict_json_object('{"model_type":"qwen3","value":1.25}')
        self.assertEqual(doc["value"], 1.25)

    def test_valid_small_empty_tensor_is_accepted(self):
        with tempfile.TemporaryDirectory(prefix="nox_p04_r36_") as temp:
            p = weights_file(Path(temp), {
                "empty": {"dtype": "F32", "shape": [0, 1],
                          "data_offsets": [0, 0]}
            })
            self.assertEqual(probe._weight_header(p), frozenset({"empty"}))


if __name__ == "__main__":
    unittest.main()
