"""Real P04 probe tests with local tiny safetensors fixtures, no GPU/downloads."""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "Packages" / "P04" / "model_snapshot_probe.py"
spec = importlib.util.spec_from_file_location("model_snapshot_probe", SCRIPT)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
REV = "a" * 40


def make_weights(path: Path):
    header = json.dumps(
        {"q.weight": {"dtype": "F32", "shape": [1],
                      "data_offsets": [0, 4]}},
        separators=(",", ":")
    ).encode("utf-8")
    path.write_bytes(len(header).to_bytes(8, "little") + header + bytes(4))


class ModelSnapshotProbeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "config.json").write_text('{"model_type":"qwen3"}', encoding="utf-8")
        make_weights(self.root / "model.safetensors")

    def test_local_candidate_never_claims_license_training_or_revision_attestation(self):
        result = probe.inspect(self.root, REV)
        self.assertEqual(result["status"], "LOCAL_FILES_PRESENT_ONLY")
        self.assertEqual(result["tensor_headers"], 1)
        self.assertEqual(len(result["weight_files"][0]["sha256"]), 64)
        for field in ("model_license_verified", "dataset_rights_verified",
                      "gpu_training_verified", "snapshot_revision_attested"):
            self.assertIs(result[field], False)

    def test_revision_required(self):
        self.assertEqual(probe.inspect(self.root, None)["reason"], "IMMUTABLE_REVISION_REQUIRED")
        self.assertEqual(probe.inspect(self.root, "main")["status"], "HOLD")

    def test_refuses_numeric_only_tensor_without_config(self):
        (self.root / "config.json").unlink()
        self.assertEqual(probe.inspect(self.root, REV)["status"], "HOLD")

    def test_refuses_corrupt_weights(self):
        (self.root / "model.safetensors").write_bytes(b"not safetensors")
        self.assertEqual(probe.inspect(self.root, REV)["reason"], "MODEL_SAFETENSORS_HEADER_INVALID")

    def test_rejects_duplicate_config_metadata(self):
        (self.root / "config.json").write_text(
            '{"model_type":"qwen3","model_type":"other"}', encoding="utf-8"
        )
        self.assertEqual(probe.inspect(self.root, REV)["reason"], "MODEL_METADATA_INVALID")

    def test_rejects_duplicate_shard_map_names(self):
        (self.root / "model.safetensors.index.json").write_text(
            '{"weight_map":{"q.weight":"part-1.safetensors","q.weight":"part-2.safetensors"}}',
            encoding="utf-8"
        )
        self.assertEqual(probe.inspect(self.root, REV)["reason"], "MODEL_METADATA_INVALID")

    def test_rejects_overlapping_tensor_byte_ranges(self):
        shared = {"dtype": "F32", "shape": [1], "data_offsets": [0, 4]}
        header = json.dumps({"first": shared, "second": shared}).encode("utf-8")
        (self.root / "model.safetensors").write_bytes(
            len(header).to_bytes(8, "little") + header + bytes(4)
        )
        self.assertEqual(probe.inspect(self.root, REV)["reason"],
                         "MODEL_SAFETENSORS_HEADER_INVALID")

    def test_accepts_distinct_nonoverlapping_tensor_byte_ranges(self):
        header = json.dumps({
            "first": {"dtype": "F32", "shape": [1], "data_offsets": [0, 4]},
            "second": {"dtype": "F32", "shape": [1], "data_offsets": [4, 8]},
        }).encode("utf-8")
        (self.root / "model.safetensors").write_bytes(
            len(header).to_bytes(8, "little") + header + bytes(8)
        )
        self.assertEqual(probe.inspect(self.root, REV)["status"],
                         "LOCAL_FILES_PRESENT_ONLY")

    def test_rejects_unindexed_gap_between_tensors(self):
        header = json.dumps({
            "first": {"dtype": "F32", "shape": [1], "data_offsets": [0, 4]},
            "second": {"dtype": "F32", "shape": [1], "data_offsets": [8, 12]},
        }).encode("utf-8")
        (self.root / "model.safetensors").write_bytes(
            len(header).to_bytes(8, "little") + header + bytes(12)
        )
        self.assertEqual(probe.inspect(self.root, REV)["reason"],
                         "MODEL_SAFETENSORS_HEADER_INVALID")

    def test_rejects_unindexed_trailing_bytes(self):
        header = json.dumps({
            "first": {"dtype": "F32", "shape": [1], "data_offsets": [0, 4]},
        }).encode("utf-8")
        (self.root / "model.safetensors").write_bytes(
            len(header).to_bytes(8, "little") + header + bytes(8)
        )
        self.assertEqual(probe.inspect(self.root, REV)["reason"],
                         "MODEL_SAFETENSORS_HEADER_INVALID")

    def test_accepts_empty_tensor_and_complete_data_buffer(self):
        header = json.dumps({
            "empty": {"dtype": "F32", "shape": [0], "data_offsets": [0, 0]},
            "full": {"dtype": "F32", "shape": [1], "data_offsets": [0, 4]},
        }).encode("utf-8")
        (self.root / "model.safetensors").write_bytes(
            len(header).to_bytes(8, "little") + header + bytes(4)
        )
        self.assertEqual(probe.inspect(self.root, REV)["status"], "LOCAL_FILES_PRESENT_ONLY")

    def _write_tensor_header(self, tensors, nbytes=4, metadata=None):
        obj = dict(tensors)
        if metadata is not None:
            obj["__metadata__"] = metadata
        header = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        (self.root / "model.safetensors").write_bytes(
            len(header).to_bytes(8, "little") + header + bytes(nbytes)
        )

    def test_rejects_unknown_dtype(self):
        self._write_tensor_header({"t": {"dtype": "UNVERIFIED", "shape": [1], "data_offsets": [0, 4]}})
        self.assertEqual(probe.inspect(self.root, REV)["reason"], "MODEL_SAFETENSORS_HEADER_INVALID")

    def test_rejects_boolean_shape_dimension(self):
        self._write_tensor_header({"t": {"dtype": "F32", "shape": [True], "data_offsets": [0, 4]}})
        self.assertEqual(probe.inspect(self.root, REV)["reason"], "MODEL_SAFETENSORS_HEADER_INVALID")

    def test_rejects_negative_shape_dimension(self):
        self._write_tensor_header({"t": {"dtype": "F32", "shape": [-1], "data_offsets": [0, 4]}})
        self.assertEqual(probe.inspect(self.root, REV)["reason"], "MODEL_SAFETENSORS_HEADER_INVALID")

    def test_rejects_fractional_shape_dimension(self):
        self._write_tensor_header({"t": {"dtype": "F32", "shape": [1.0], "data_offsets": [0, 4]}})
        self.assertEqual(probe.inspect(self.root, REV)["reason"], "MODEL_SAFETENSORS_HEADER_INVALID")

    def test_rejects_tensor_byte_length_too_short(self):
        self._write_tensor_header({"t": {"dtype": "F32", "shape": [2], "data_offsets": [0, 4]}})
        self.assertEqual(probe.inspect(self.root, REV)["reason"], "MODEL_SAFETENSORS_HEADER_INVALID")

    def test_rejects_tensor_byte_length_too_long(self):
        self._write_tensor_header({"t": {"dtype": "F16", "shape": [1], "data_offsets": [0, 4]}})
        self.assertEqual(probe.inspect(self.root, REV)["reason"], "MODEL_SAFETENSORS_HEADER_INVALID")

    def test_rejects_empty_tensor_name(self):
        self._write_tensor_header({"": {"dtype": "F32", "shape": [1], "data_offsets": [0, 4]}})
        self.assertEqual(probe.inspect(self.root, REV)["reason"], "MODEL_SAFETENSORS_HEADER_INVALID")

    def test_rejects_control_character_tensor_name(self):
        self._write_tensor_header({"t\\n": {"dtype": "F32", "shape": [1], "data_offsets": [0, 4]}})
        self.assertEqual(probe.inspect(self.root, REV)["reason"], "MODEL_SAFETENSORS_HEADER_INVALID")

    def test_rejects_non_object_metadata(self):
        self._write_tensor_header({"t": {"dtype": "F32", "shape": [1], "data_offsets": [0, 4]}}, metadata="not-a-map")
        self.assertEqual(probe.inspect(self.root, REV)["reason"], "MODEL_SAFETENSORS_HEADER_INVALID")

    def test_rejects_non_string_metadata_value(self):
        self._write_tensor_header({"t": {"dtype": "F32", "shape": [1], "data_offsets": [0, 4]}}, metadata={"license": 5})
        self.assertEqual(probe.inspect(self.root, REV)["reason"], "MODEL_SAFETENSORS_HEADER_INVALID")

    def test_accepts_valid_scalar_and_half_precision_tensor(self):
        self._write_tensor_header({
            "scalar": {"dtype": "F64", "shape": [], "data_offsets": [0, 8]},
            "half": {"dtype": "F16", "shape": [2], "data_offsets": [8, 12]},
        }, nbytes=12, metadata={"format": "local-fixture"})
        self.assertEqual(probe.inspect(self.root, REV)["status"], "LOCAL_FILES_PRESENT_ONLY")

    def test_rejects_duplicate_safetensors_tensor_names(self):
        header = (b'{"q.weight":{"dtype":"F32","shape":[1],"data_offsets":[0,4]},'
                  b'"q.weight":{"dtype":"F32","shape":[1],"data_offsets":[0,4]}}')
        (self.root / "model.safetensors").write_bytes(
            len(header).to_bytes(8, "little") + header + bytes(4)
        )
        self.assertEqual(probe.inspect(self.root, REV)["reason"], "MODEL_SAFETENSORS_HEADER_INVALID")

    def test_rejects_nonfinite_json_metadata(self):
        (self.root / "config.json").write_text(
            '{"model_type":"qwen3","untrusted":NaN}', encoding="utf-8"
        )
        self.assertEqual(probe.inspect(self.root, REV)["reason"], "MODEL_METADATA_INVALID")

    def test_detects_shard_missing(self):
        (self.root / "model.safetensors.index.json").write_text(
            json.dumps({"weight_map": {"a": "model-00001-of-00002.safetensors"}}),
            encoding="utf-8"
        )
        self.assertEqual(probe.inspect(self.root, REV)["status"], "HOLD")

    def test_rejects_unsafe_index_path(self):
        (self.root / "model.safetensors.index.json").write_text(
            json.dumps({"weight_map": {"a": "../escape.safetensors"}}),
            encoding="utf-8"
        )
        self.assertEqual(probe.inspect(self.root, REV)["reason"], "MODEL_SHARD_PATH_UNSAFE")

    def test_rejects_symlink_weights(self):
        weight = self.root / "model.safetensors"
        weight.rename(self.root / "actual.safetensors")
        try:
            weight.symlink_to(self.root / "actual.safetensors")
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks not available in this test environment")
        self.assertEqual(probe.inspect(self.root, REV)["reason"], "MODEL_WEIGHTS_NOT_REGULAR")

    def test_indexed_shard_valid(self):
        (self.root / "model.safetensors.index.json").write_text(
            json.dumps({"weight_map": {"q.weight": "model-00001-of-00001.safetensors"}}),
            encoding="utf-8"
        )
        make_weights(self.root / "model-00001-of-00001.safetensors")
        self.assertEqual(probe.inspect(self.root, REV)["status"], "LOCAL_FILES_PRESENT_ONLY")

    def test_rejects_valid_shard_with_wrong_tensor_mapping(self):
        (self.root / "model.safetensors.index.json").write_text(
            json.dumps({"weight_map": {"a": "model-00001-of-00001.safetensors"}}),
            encoding="utf-8"
        )
        make_weights(self.root / "model-00001-of-00001.safetensors")
        self.assertEqual(probe.inspect(self.root, REV)["reason"], "MODEL_SHARD_TENSOR_MAP_MISMATCH")


if __name__ == "__main__":
    unittest.main()
