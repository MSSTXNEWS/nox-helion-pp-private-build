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

    def test_malformed_shard_mapping_returns_hold_instead_of_crashing_installer(self):
        for value in ([], {}, None, 12, ["model.safetensors"]):
            with self.subTest(value=value):
                (self.root / "model.safetensors.index.json").write_text(
                    json.dumps({"weight_map": {"a": "model.safetensors", "b": value}}),
                    encoding="utf-8")
                result = probe.inspect(self.root, REV)
                self.assertEqual(result["status"], "HOLD")
                self.assertEqual(result["reason"], "MODEL_SHARD_PATH_UNSAFE")
                self.assertEqual(result["weight_files"], [])

    def test_invalid_tensor_names_are_not_accepted_as_installed_snapshot(self):
        for name in ("", "  ", "\ud800"):
            with self.subTest(name=name):
                (self.root / "model.safetensors.index.json").write_text(
                    json.dumps({"weight_map": {name: "model.safetensors"}}), encoding="utf-8")
                result = probe.inspect(self.root, REV)
                self.assertEqual(result["status"], "HOLD")
                self.assertEqual(result["reason"], "MODEL_SHARD_INDEX_INVALID")

    def test_malformed_safetensors_header_is_hold_before_hashing_weights(self):
        valid = {"dtype": "F32", "shape": [1], "data_offsets": [0, 4]}
        cases = [
            {"q": {**valid, "shape": [-1]}},
            {"q": {**valid, "shape": [True]}},
            {"q": {**valid, "shape": ["1"]}},
            {"q": {**valid, "data_offsets": [1, 4]}},
            {"q": {**valid, "data_offsets": [0, 3]}},
            {"q": valid, "r": valid},
            {"q": valid, "__metadata__": {"format": 1}},
        ]
        for header in cases:
            with self.subTest(header=header):
                encoded = json.dumps(header).encode("utf-8")
                (self.root / "model.safetensors").write_bytes(
                    len(encoded).to_bytes(8, "little") + encoded + bytes(4))
                result = probe.inspect(self.root, REV)
                self.assertEqual(result["status"], "HOLD")
                self.assertEqual(result["reason"], "MODEL_SAFETENSORS_HEADER_INVALID")

    def test_duplicate_tensor_names_are_rejected(self):
        tensor = '{"dtype":"F32","shape":[1],"data_offsets":[0,4]}'
        encoded = ('{"q":' + tensor + ',"q":' + tensor + '}').encode()
        (self.root / "model.safetensors").write_bytes(
            len(encoded).to_bytes(8, "little") + encoded + bytes(4))
        self.assertEqual(probe.inspect(self.root, REV)["status"], "HOLD")

    def test_empty_and_scalar_tensors_keep_valid_format_semantics(self):
        header = {"empty": {"dtype": "F32", "shape": [0], "data_offsets": [0, 0]},
                  "scalar": {"dtype": "F32", "shape": [], "data_offsets": [0, 4]},
                  "__metadata__": {"format": "pt"}}
        encoded = json.dumps(header).encode()
        (self.root / "model.safetensors").write_bytes(
            len(encoded).to_bytes(8, "little") + encoded + bytes(4))
        self.assertEqual(probe.inspect(self.root, REV)["status"], "LOCAL_FILES_PRESENT_ONLY")


    def test_index_tensor_names_match_exact_shard_contents(self):
        shard1, shard2 = "model-1.safetensors", "model-2.safetensors"
        def write_shard(name, tensor_names):
            header = {tensor: {"dtype": "F32", "shape": [1],
                              "data_offsets": [i * 4, (i + 1) * 4]}
                      for i, tensor in enumerate(tensor_names)}
            raw = json.dumps(header).encode("utf-8")
            (self.root / name).write_bytes(
                len(raw).to_bytes(8, "little") + raw + bytes(4 * len(tensor_names)))
        cases = [
            ({"q": shard1, "r": shard2}, ["q"], ["r"], True),
            ({"q": shard1}, ["missing"], ["r"], False),
            ({"q": shard1}, ["q", "undeclared"], ["r"], False),
            ({"q": shard1, "r": shard2}, ["r"], ["q"], False),
        ]
        for mapping, first, second, valid in cases:
            with self.subTest(mapping=mapping, first=first, second=second):
                write_shard(shard1, first)
                write_shard(shard2, second)
                (self.root / "model.safetensors.index.json").write_text(
                    json.dumps({"weight_map": mapping}), encoding="utf-8")
                result = probe.inspect(self.root, REV)
                self.assertEqual(result["status"], "LOCAL_FILES_PRESENT_ONLY" if valid else "HOLD")
                if not valid:
                    self.assertEqual(result["reason"], "MODEL_SHARD_TENSOR_MAP_MISMATCH")

    def test_duplicate_index_tensor_mapping_is_rejected(self):
        (self.root / "model.safetensors.index.json").write_text(
            '{"weight_map":{"q.weight":"missing.safetensors","q.weight":"model.safetensors"}}',
            encoding="utf-8")
        result = probe.inspect(self.root, REV)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "MODEL_METADATA_INVALID")

    def test_count_helper_contract_is_preserved(self):
        self.assertEqual(probe._weight_header(self.root / "model.safetensors"), 1)


if __name__ == "__main__":
    unittest.main()

