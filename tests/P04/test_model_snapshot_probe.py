"""Real P04 probe tests with local tiny safetensors fixtures, no GPU/downloads."""
from __future__ import annotations

import importlib.util
import hashlib
import json
import tempfile
import unittest
from unittest import mock
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


    def test_same_inode_change_between_validation_and_hash_is_hold(self):
        original_hash = probe._sha256_stream
        weight = self.root / "model.safetensors"
        def mutate_then_hash(stream):
            # Keep size valid, but mutate payload after the parser observed it.
            with weight.open("r+b") as writer:
                writer.seek(-1, 2)
                writer.write(b"X")
                writer.flush()
            return original_hash(stream)
        with mock.patch.object(probe, "_sha256_stream", side_effect=mutate_then_hash):
            result = probe.inspect(self.root, REV)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "MODEL_WEIGHTS_CHANGED_DURING_INSPECTION")

    def test_replaced_weight_path_cannot_inherit_old_header_result(self):
        original_hash = probe._sha256_stream
        weight = self.root / "model.safetensors"
        replacement = self.root / "replacement.safetensors"
        make_weights(replacement)
        def replace_then_hash(stream):
            try:
                replacement.replace(weight)
            except PermissionError:
                self.skipTest("Platform forbids replacing an open file")
            return original_hash(stream)
        with mock.patch.object(probe, "_sha256_stream", side_effect=replace_then_hash):
            result = probe.inspect(self.root, REV)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "MODEL_WEIGHTS_CHANGED_DURING_INSPECTION")


    def test_g4a_windows_device_and_casefold_aliases_hold_before_reading(self):
        for name in ("CON.safetensors", "nul.safetensors",
                     "COM1.safetensors", "LPT9.safetensors"):
            with self.subTest(name=name):
                (self.root / "model.safetensors.index.json").write_text(
                    json.dumps({"weight_map": {"q.weight": name}}), encoding="utf-8"
                )
                result = probe.inspect(self.root, REV)
                self.assertEqual(result["status"], "HOLD")
                self.assertEqual(result["reason"], "MODEL_SHARD_PATH_UNSAFE")
                self.assertEqual(result["weight_files"], [])
        (self.root / "model.safetensors.index.json").write_text(
            json.dumps({"weight_map": {"q.weight": "model-a.safetensors",
                                       "r.weight": "MODEL-A.safetensors"}}),
            encoding="utf-8"
        )
        result = probe.inspect(self.root, REV)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "MODEL_SHARD_PATH_UNSAFE")
        self.assertEqual(result["weight_files"], [])

    def test_g4a_observed_digest_is_byte_sensitive_not_revision_attestation(self):
        first = probe.inspect(self.root, REV)
        self.assertEqual(first["status"], "LOCAL_FILES_PRESENT_ONLY")
        self.assertEqual(len(first["observed_snapshot_sha256"]), 64)
        self.assertIsNone(first["shard_index_sha256"])
        path = self.root / "model.safetensors"
        blob = path.read_bytes()
        path.write_bytes(blob[:-1] + bytes([blob[-1] ^ 1]))
        second = probe.inspect(self.root, REV)
        self.assertEqual(second["status"], "LOCAL_FILES_PRESENT_ONLY")
        self.assertEqual(first["candidate_sha256"], second["candidate_sha256"])
        self.assertNotEqual(first["observed_snapshot_sha256"],
                            second["observed_snapshot_sha256"])
        (self.root / "model.safetensors.index.json").write_text(
            json.dumps({"weight_map": {"q.weight": "model.safetensors"}}),
            encoding="utf-8"
        )
        third = probe.inspect(self.root, REV)
        self.assertEqual(third["status"], "LOCAL_FILES_PRESENT_ONLY")
        self.assertNotEqual(second["observed_snapshot_sha256"],
                            third["observed_snapshot_sha256"])
        self.assertIs(third["snapshot_revision_attested"], False)



    def test_g4a_r02_windows_device_aliases_hold_before_weight_io(self):
        for name in ("COM¹.safetensors", "LPT³.safetensors",
                     "CON .safetensors", "NUL  .safetensors"):
            with self.subTest(name=name):
                (self.root / "model.safetensors.index.json").write_text(
                    json.dumps({"weight_map": {"q.weight": name}}), encoding="utf-8")
                with mock.patch.object(probe, "_inspect_weight",
                                       side_effect=AssertionError("unsafe shard I/O")):
                    result = probe.inspect(self.root, REV)
                self.assertEqual(result["status"], "HOLD")
                self.assertEqual(result["reason"], "MODEL_SHARD_PATH_UNSAFE")
                self.assertEqual(result["weight_files"], [])

    def test_g4a_r02_surrogate_shard_names_hold_without_encoding_exception(self):
        for name in ("\ud800.safetensors", "shard\udfff.safetensors"):
            with self.subTest(name=repr(name)):
                (self.root / "model.safetensors.index.json").write_text(
                    json.dumps({"weight_map": {"q.weight": name}}), encoding="utf-8")
                with mock.patch.object(probe, "_inspect_weight",
                                       side_effect=AssertionError("unsafe shard I/O")):
                    result = probe.inspect(self.root, REV)
                self.assertEqual(result["status"], "HOLD")
                self.assertEqual(result["reason"], "MODEL_SHARD_PATH_UNSAFE")
                self.assertEqual(result["weight_files"], [])

    def test_g4a_r02_valid_utf8_shard_preserves_observed_digest(self):
        name = "modèle-00001.safetensors"
        make_weights(self.root / name)
        (self.root / "model.safetensors.index.json").write_text(
            json.dumps({"weight_map": {"q.weight": name}}), encoding="utf-8")
        result = probe.inspect(self.root, REV)
        self.assertEqual(result["status"], "LOCAL_FILES_PRESENT_ONLY")
        self.assertEqual(result["weight_files"][0]["name"], name)
        self.assertEqual(len(result["weight_files"][0]["sha256"]), 64)
        self.assertIs(result["snapshot_revision_attested"], False)

    def test_g4a_r03_nonfinite_header_is_hold_before_weight_hash(self):
        for token in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(token=token):
                header = ('{"q.weight":{"dtype":"F32","shape":[1],'
                          '"data_offsets":[0,4],"extra":' + token + '}}').encode("utf-8")
                (self.root / "model.safetensors").write_bytes(
                    len(header).to_bytes(8, "little") + header + bytes(4))
                with mock.patch.object(probe, "_sha256_stream",
                                       side_effect=AssertionError("invalid header hashed")):
                    result = probe.inspect(self.root, REV)
                self.assertEqual(result["status"], "HOLD")
                self.assertEqual(result["reason"], "MODEL_SAFETENSORS_HEADER_INVALID")
                self.assertEqual(result["weight_files"], [])
                self.assertEqual(result["tensor_headers"], 0)

    def test_g4a_r03_late_missing_shard_drops_partial_evidence(self):
        first, second = "model-1.safetensors", "model-2.safetensors"
        make_weights(self.root / first)
        (self.root / "model.safetensors.index.json").write_text(
            json.dumps({"weight_map": {"q.weight": first, "r.weight": second}}),
            encoding="utf-8")
        result = probe.inspect(self.root, REV)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "MODEL_WEIGHTS_NOT_REGULAR")
        self.assertEqual(result["weight_files"], [])
        self.assertEqual(result["tensor_headers"], 0)
        self.assertIsNone(result["observed_snapshot_sha256"])

    def test_g4a_r03_late_tensor_map_mismatch_drops_partial_evidence(self):
        first, second = "model-1.safetensors", "model-2.safetensors"
        make_weights(self.root / first)
        make_weights(self.root / second)
        (self.root / "model.safetensors.index.json").write_text(
            json.dumps({"weight_map": {"q.weight": first, "r.weight": second}}),
            encoding="utf-8")
        result = probe.inspect(self.root, REV)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "MODEL_SHARD_TENSOR_MAP_MISMATCH")
        self.assertEqual(result["weight_files"], [])
        self.assertEqual(result["tensor_headers"], 0)
        self.assertIsNone(result["observed_snapshot_sha256"])


    def test_g4a_r04_declared_payload_size_valid_and_full_shard_sha(self):
        (self.root / "model.safetensors.index.json").write_text(
            json.dumps({"metadata": {"total_size": 4},
                        "weight_map": {"q.weight": "model.safetensors"}}),
            encoding="utf-8")
        result = probe.inspect(self.root, REV)
        self.assertEqual(result["status"], "LOCAL_FILES_PRESENT_ONLY")
        self.assertEqual(result["weight_files"][0]["sha256"],
                         hashlib.sha256((self.root / "model.safetensors").read_bytes()).hexdigest())
        self.assertEqual(result["tensor_headers"], 1)
        self.assertFalse(result["snapshot_revision_attested"])

    def test_g4a_r04_declared_payload_size_mismatch_holds_without_partial_hashes(self):
        for wrong_total in (0, 3, 5, 999):
            with self.subTest(total_size=wrong_total):
                (self.root / "model.safetensors.index.json").write_text(
                    json.dumps({"metadata": {"total_size": wrong_total},
                                "weight_map": {"q.weight": "model.safetensors"}}),
                    encoding="utf-8")
                result = probe.inspect(self.root, REV)
                self.assertEqual(result["status"], "HOLD")
                self.assertEqual(result["reason"], "MODEL_SHARD_TOTAL_SIZE_MISMATCH")
                self.assertEqual(result["weight_files"], [])
                self.assertEqual(result["tensor_headers"], 0)
                self.assertIsNone(result["observed_snapshot_sha256"])

    def test_g4a_r04_invalid_index_total_size_rejected_before_weight_io(self):
        for bad in (-1, True, False, "4", 4.0, None, [], {}):
            with self.subTest(total_size=bad):
                (self.root / "model.safetensors.index.json").write_text(
                    json.dumps({"metadata": {"total_size": bad},
                                "weight_map": {"q.weight": "model.safetensors"}}),
                    encoding="utf-8")
                with mock.patch.object(probe, "_inspect_weight",
                                       side_effect=AssertionError("weight I/O before index validation")):
                    result = probe.inspect(self.root, REV)
                self.assertEqual(result["status"], "HOLD")
                self.assertEqual(result["reason"], "MODEL_SHARD_INDEX_METADATA_INVALID")
                self.assertEqual(result["weight_files"], [])

    def test_g4a_r04_invalid_index_metadata_container_rejected_before_weight_io(self):
        for bad in (None, 4, "not-a-dict", [], True):
            with self.subTest(metadata=bad):
                (self.root / "model.safetensors.index.json").write_text(
                    json.dumps({"metadata": bad,
                                "weight_map": {"q.weight": "model.safetensors"}}),
                    encoding="utf-8")
                with mock.patch.object(probe, "_inspect_weight",
                                       side_effect=AssertionError("weight I/O before index validation")):
                    result = probe.inspect(self.root, REV)
                self.assertEqual(result["status"], "HOLD")
                self.assertEqual(result["reason"], "MODEL_SHARD_INDEX_METADATA_INVALID")
                self.assertEqual(result["weight_files"], [])


    def test_g4a_r04_two_shard_total_size_and_digest_contract(self):
        shard_a, shard_b = "model-1.safetensors", "model-2.safetensors"
        for shard, tensor in ((shard_a, "q.weight"), (shard_b, "r.weight")):
            header = json.dumps({tensor: {"dtype": "F32", "shape": [1],
                                          "data_offsets": [0, 4]}}).encode("utf-8")
            (self.root / shard).write_bytes(
                len(header).to_bytes(8, "little") + header + b"ABCD")
        index = self.root / "model.safetensors.index.json"
        mapping = {"q.weight": shard_a, "r.weight": shard_b}
        index.write_text(json.dumps({"metadata": {"total_size": 8},
                                     "weight_map": mapping}), encoding="utf-8")
        result = probe.inspect(self.root, REV)
        self.assertEqual(result["status"], "LOCAL_FILES_PRESENT_ONLY")
        self.assertEqual(result["tensor_headers"], 2)
        self.assertEqual(len(result["weight_files"]), 2)
        for row in result["weight_files"]:
            self.assertEqual(row["sha256"],
                             hashlib.sha256((self.root / row["name"]).read_bytes()).hexdigest())
        index.write_text(json.dumps({"metadata": {"total_size": 9},
                                     "weight_map": mapping}), encoding="utf-8")
        bad = probe.inspect(self.root, REV)
        self.assertEqual(bad["status"], "HOLD")
        self.assertEqual(bad["reason"], "MODEL_SHARD_TOTAL_SIZE_MISMATCH")
        self.assertEqual(bad["weight_files"], [])
        self.assertEqual(bad["tensor_headers"], 0)


if __name__ == "__main__":
    unittest.main()

