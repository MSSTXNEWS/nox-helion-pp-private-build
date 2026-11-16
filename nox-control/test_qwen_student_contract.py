"""Local contract tests, not a substitute for native CUDA/model/update proof."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import owner_qwen_corpus as corpus
import owner_qwen_memfd as memfd
import owner_qwen_training_contract as c
import qwen_student_training_entry as entry


def sha(value):
    return hashlib.sha256(str(value).encode()).hexdigest()


def proof(lineage, n=6):
    rows = [{"optimizer_step_before": i, "optimizer_step_after": i + 1,
             "adapter_sha_before": sha("tensor" + str(i)), "adapter_sha_after": sha("tensor" + str(i + 1)),
             "amp_skipped": False, "finite_gradients": True, "loss": 2.1,
             "training_example_sha256": [sha("example" + str(i * 8 + j)) for j in range(8)]}
            for i in range(n)]
    return {"schema": c.PROOF_SCHEMA, "lineage_sha256": c.canonical_sha(lineage),
            "base_manifest_sha256": c.MANIFEST_SHA, "reload_verified": True,
            "holdout_finite": True, "independent_holdout_accepted": True,
            "update_evidence": rows, "successful_optimizer_steps": n,
            "final_adapter_tensor_sha256": rows[-1]["adapter_sha_after"]}


class ContractTests(unittest.TestCase):
    def test_pinned_manifest_wrong_base_origin_and_size_rejected(self):
        path = Path(__file__).with_name("qwen35_9b_manifest.json")
        self.assertEqual(c.sha256_file(path), c.MANIFEST_SHA)
        manifest = json.loads(path.read_text())
        self.assertEqual(len(c.validate_manifest(manifest)), 16)
        for edit in (lambda m: m.update(model_id="other/base"),
                     lambda m: m["files"][0].update(immutable_url="https://untrusted.invalid/weights"),
                     lambda m: m["files"][0].update(bytes=m["files"][0]["bytes"] + 1)):
            bad = copy.deepcopy(manifest); edit(bad)
            with self.assertRaises(c.Hold): c.validate_manifest(bad)

    def test_zero_updates_unchanged_tensors_and_repeated_fixture_do_not_pass(self):
        lineage = {"schema": c.SCHEMA, "base": {"model_id": c.MODEL_ID}}
        good = proof(lineage)
        self.assertTrue(c.verify_proof(good, lineage=lineage))
        mutations = (
            lambda p: p.update(reload_verified=False),
            lambda p: p["update_evidence"][0].update(adapter_sha_after=p["update_evidence"][0]["adapter_sha_before"]),
            lambda p: p["update_evidence"][0].update(amp_skipped=True),
            lambda p: p.update(independent_holdout_accepted=False),
            lambda p: [r.update(training_example_sha256=p["update_evidence"][0]["training_example_sha256"])
                       for r in p["update_evidence"][1:]],
        )
        for mutate in mutations:
            p = copy.deepcopy(good); mutate(p)
            with self.assertRaises(c.Hold): c.verify_proof(p, lineage=lineage)

    def test_old_optimizer_lineage_rejected(self):
        with self.assertRaises(c.Hold):
            c.validate_resume_lineage({"schema": c.SCHEMA, "base": {"model_id": "old/35B"}},
                                      {"schema": c.SCHEMA, "base": {"model_id": c.MODEL_ID}})

    def test_ssd_cannot_admit_19gb_base_on_13gb(self):
        with self.assertRaises(c.Hold):
            c.storage_admission(destination_free=13 * c.GIB, cgroup_current=80 * c.GIB,
                                cgroup_max=180 * c.GIB, bytes_to_stage=19_329_393_661,
                                runtime_headroom=24 * c.GIB, destination_is_tmpfs=False, disk_free=13 * c.GIB)

    def test_regular_file_checker_never_accepts_proc_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target"; target.write_bytes(b"x")
            link = Path(tmp) / "link"; link.symlink_to(target)
            with self.assertRaises(c.Hold): c.sha256_file(link)


class Response(io.BytesIO):
    status = 200
    def __init__(self, raw):
        super().__init__(raw); self.headers = {"Content-Length": str(len(raw))}
    def geturl(self): return "https://huggingface.co/public/test"


class MemfdTests(unittest.TestCase):
    def test_actual_sealed_owned_fd_and_foreign_symlink_rejection(self):
        raw = b"local test fixture only"
        row = {"path": "fixture.bin", "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
               "immutable_url": "https://huggingface.co/public/test"}
        class Opener:
            def open(self, *args, **kwargs): return Response(raw)
        with tempfile.TemporaryDirectory() as tmp, patch.object(memfd.urllib.request, "build_opener", return_value=Opener()):
            with memfd.SealedModel(tmp, guard=lambda _: None) as store:
                result = store.stage([row]); path = store.directory / row["path"]
                self.assertTrue(result["all_sha256_verified"])
                self.assertEqual(path.read_bytes(), raw)
                self.assertTrue(store.verify_path(path, row["sha256"], row["bytes"]))
                with self.assertRaises(OSError): os.pwrite(store._owned[row["path"]], b"x", 0)
                path.unlink(); path.symlink_to("/proc/self/exe")
                with self.assertRaises(c.Hold): store.verify_path(path, row["sha256"], row["bytes"])
                path.unlink()
            self.assertFalse(store.directory.exists())

    def test_bad_hash_does_not_expose_link_and_foreign_content_survives(self):
        raw = b"wrong content"
        row = {"path": "fixture", "bytes": len(raw), "sha256": sha("different"),
               "immutable_url": "https://huggingface.co/public/test"}
        class Opener:
            def open(self, *args, **kwargs): return Response(raw)
        with tempfile.TemporaryDirectory() as tmp, patch.object(memfd.urllib.request, "build_opener", return_value=Opener()):
            store = memfd.SealedModel(tmp, guard=lambda _: None)
            foreign = store.directory / "foreign"; foreign.write_text("keep")
            with self.assertRaises(c.Hold): store.stage([row])
            self.assertFalse((store.directory / "fixture").exists())
            store.close(); self.assertEqual(foreign.read_text(), "keep")


class CharacterTokenizer:
    def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=False):
        user = messages[0]["content"]
        prefix = "USER:" + user + "\nASSISTANT:"
        return prefix if add_generation_prompt else prefix + messages[-1]["content"]
    def __call__(self, text, **kwargs):
        text = text[:kwargs["max_length"]]
        return {"input_ids": [ord(x) for x in text], "attention_mask": [1] * len(text),
                "offset_mapping": [(i, i + 1) for i in range(len(text))]}


class CorpusTests(unittest.TestCase):
    def test_filter_preserves_native_rejections(self):
        good = {"prompt": "Как проверить обновление?", "answer": "Нужно сверить тензоры и состояние оптимизатора."}
        self.assertIsNotNone(corpus.extract_pair(good))
        for bad in ({**good, "accepted": False}, {**good, "teacher": "ChatGPT"},
                    {**good, "answer": {"nested": "not plain text"}}):
            self.assertIsNone(corpus.extract_pair(bad))

    def test_tokenized_admission_filters_long_prompt_and_masks_prefix(self):
        def rows(n):
            return [[{"role": "user", "content": "question " + str(i)},
                     {"role": "assistant", "content": "A verified response long enough."}] for i in range(n)]
        train = rows(40) + [[{"role": "user", "content": "x" * 600},
                            {"role": "assistant", "content": "Answer truncated away."}]]
        a, b, evidence = entry.admit_tokenized_dataset(CharacterTokenizer(), train, rows(8))
        self.assertEqual((len(a), len(b)), (40, 8))
        self.assertEqual(evidence["splits"][0]["rejected_reasons"], {"HOLD_NO_ASSISTANT_TOKENS_AFTER_TRUNCATION": 1})
        self.assertEqual(a[0]["labels"][0], -100)
        self.assertNotEqual(a[0]["labels"][-1], -100)
        with self.assertRaises(c.Hold): entry.admit_tokenized_dataset(CharacterTokenizer(), train[1:], rows(8))

    def test_real_file_snapshot_has_disjoint_groups_provenance_and_no_text_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / "scripts").mkdir()
            loader = root / "scripts/train_qlora_35b_t866u.py"; loader.write_text("test fixture loader, never imported")
            source = root / corpus.SOURCES[0]; source.parent.mkdir(parents=True)
            with source.open("w") as stream:
                for i in range(250):
                    stream.write(json.dumps({"prompt": "fixture request " + str(i),
                        "answer": "fixture answer for a local test only " + str(i)}) + "\n")
            output = root / "state/qwen_corpus/test"
            with patch.object(corpus, "SOURCE_LOADER_SHA", c.sha256_file(loader)):
                receipt = corpus.snapshot(root, output)
            self.assertGreaterEqual(receipt["train_unique_rows"], 40)
            self.assertGreaterEqual(receipt["holdout_unique_rows"], 8)
            self.assertNotIn("fixture answer", json.dumps(receipt))
            sets = []
            for name in ("train.jsonl", "holdout.jsonl"):
                records = [json.loads(s) for s in (output / name).read_text().splitlines()]
                self.assertTrue(all(r["provenance"]["source_sha256"] == c.sha256_file(source) for r in records))
                sets.append({r["provenance"]["group_sha256"] for r in records})
            self.assertFalse(sets[0] & sets[1])


class RetentionTests(unittest.TestCase):
    def build(self, root):
        out = root / "lora/qwen35_9b/test"; out.mkdir(parents=True)
        lineage = {"schema": c.SCHEMA, "base": {"model_id": c.MODEL_ID}}
        records = []
        for i in range(1, 10):
            name = f"checkpoint-u{i:08d}-a{i:08d}-g{i:020d}"
            path = out / name; path.mkdir(); (path / "adapter_model.safetensors").write_bytes(str(i).encode())
            record = {"schema": "NOX_QWEN35_9B_CHECKPOINT_V1", "directory": name,
                      "lineage_sha256": c.canonical_sha(lineage),
                      "files_sha256": {"adapter_model.safetensors": c.sha256_file(path / "adapter_model.safetensors")}}
            entry.atomic_json(path / "checkpoint_manifest.json", record)
            records.append({"directory": name, "manifest_sha256": c.sha256_file(path / "checkpoint_manifest.json"),
                            "successful_total": i, "attempted_total": i, "retained": True,
                            "evaluated_at_current_step": True, "holdout_loss": 1.0 if i == 3 else 2.0})
        entry.atomic_json(out / "owner_checkpoints.json", {"schema": "NOX_QWEN_OWNED_CHECKPOINTS_V1",
                          "lineage_sha256": c.canonical_sha(lineage), "checkpoints": records})
        entry.atomic_json(out / "latest_checkpoint.json", {k: records[-1][k] for k in ("directory", "manifest_sha256")})
        accepted = proof(lineage); accepted["checkpoint"] = str(out / records[5]["directory"])
        entry.atomic_json(out / "owner_acceptance.json", accepted)
        return out, lineage, records

    def test_keep_accepted_latest_previous_best_and_do_not_touch_foreign_scope(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(entry, "ROOT", Path(tmp)):
            root = Path(tmp); out, lineage, records = self.build(root)
            old = root / "lora/old35B"; old.mkdir(); (old / "unique").write_text("keep")
            evidence = entry.prune_checkpoints(out, lineage)
            self.assertEqual(evidence["deleted_verified_own_checkpoints"], 5)
            self.assertEqual({p.name for p in out.glob("checkpoint-*")},
                             {records[i - 1]["directory"] for i in (3, 6, 8, 9)})
            self.assertEqual((old / "unique").read_text(), "keep")

    def test_one_modified_checkpoint_prevents_all_deletion(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(entry, "ROOT", Path(tmp)):
            out, lineage, records = self.build(Path(tmp))
            (out / records[4]["directory"] / "adapter_model.safetensors").write_bytes(b"changed")
            with self.assertRaises(c.Hold): entry.prune_checkpoints(out, lineage)
            self.assertEqual(len(list(out.glob("checkpoint-*"))), 9)


if __name__ == "__main__":
    unittest.main()
