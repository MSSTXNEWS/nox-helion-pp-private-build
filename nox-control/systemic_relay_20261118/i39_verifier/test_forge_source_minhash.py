"""Verify I-39 through the actual pinned Forge preflight entry point."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import forge_split_guard as guard


PROMPT = (
    "Проверь исходную дату документа и сравни результаты предыдущей проверки. "
    "Conserva los hechos confirmados y explica cualquier diferencia observada "
    "en la última revisión del proyecto con fuentes verificables y fechas completas."
)


class ForgeSourceMinHashTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.manifest = self.root / "splits.json"
        self.rows = {}
        for split in guard.SPLITS:
            self.rows[split] = [
                self.row(split, task, language)
                for task in sorted(guard.TASKS) for language in sorted(guard.LANGS)
            ]

    def row(self, split, task, language):
        key = f"{split}-{task}-{language}"
        return {"sample_id": key, "origin_id": f"origin-{key}",
                "source_sha256": guard.sha(key.encode()),
                "source_url": f"https://example.org/{key}", "license": "CC0-1.0",
                "task": task, "language": language, "goal": task,
                "prompt": f"Question {key}", "response": f"Answer {key}"}

    def prepare(self):
        splits = {}
        for split, rows in self.rows.items():
            payload = "".join(json.dumps(row) + "\n" for row in rows).encode()
            name = f"{split}.jsonl"
            (self.root / name).write_bytes(payload)
            splits[split] = {"path": name, "rows": len(rows), "sha256": guard.sha(payload)}
        payload = json.dumps({"splits": splits}).encode()
        self.manifest.write_bytes(payload)
        return guard.sha(payload)

    def validate(self):
        return guard.validate(self.root, self.manifest, self.prepare())

    def test_near_duplicate_source_rejected_before_training(self):
        first, second = self.rows["train"][:2]
        first["prompt"] = PROMPT
        second["prompt"] = PROMPT.upper().replace("COMPLETAS", "DETALLADAS")
        second["source_url"] = first["source_url"].replace("example.org", "EXAMPLE.ORG:443")
        with self.assertRaisesRegex(ValueError, "^MINHASH_SAME_SOURCE_DUPLICATE$"):
            self.validate()

    def test_cli_reports_train_holdout_leakage_with_distinct_provenance(self):
        self.rows["train"][0]["prompt"] = PROMPT
        self.rows["holdout"][0]["prompt"] = PROMPT.replace("completas", "detalladas")
        pin = self.prepare()
        result = subprocess.run(
            [sys.executable, guard.__file__, "--manifest", str(self.manifest),
             "--manifest-sha256", pin, "--corpus-dir", str(self.root)],
            capture_output=True, text=True, check=False, timeout=5,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout), {
            "status": "HOLD", "training_started": False,
            "reason": "TRAIN_HOLDOUT_MINHASH_LEAKAGE",
        })

    def test_short_prompt_min_hash_detects_eight_of_ten_shared_shingles(self):
        self.rows["train"][0]["prompt"] = "uno dos tres cuatro cinco seis siete ocho nueve diez once"
        self.rows["holdout"][0]["prompt"] = "uno dos tres cuatro cinco seis siete ocho nueve diez doce"
        with self.assertRaisesRegex(ValueError, "^TRAIN_HOLDOUT_MINHASH_LEAKAGE$"):
            self.validate()

    def test_repetitive_prompt_with_one_distinct_shingle_still_detects_leakage(self):
        repetitive = " ".join(["hola"] * 15)
        self.rows["train"][0]["prompt"] = repetitive + "."
        self.rows["holdout"][0]["prompt"] = repetitive + "!"
        with self.assertRaisesRegex(ValueError, "^TRAIN_HOLDOUT_MINHASH_LEAKAGE$"):
            self.validate()

    def test_short_prompts_sharing_only_one_shingle_still_pass(self):
        self.rows["train"][0]["prompt"] = "uno dos tres cuatro"
        self.rows["holdout"][0]["prompt"] = "uno dos tres cinco"
        self.assertEqual(self.validate()["status"], "SOURCE_SPLITS_VERIFIED")

    def test_distinct_text_from_same_source_still_passes(self):
        first, second = self.rows["train"][:2]
        first["prompt"] = PROMPT
        second["prompt"] = (
            "Resume el catálogo de herramientas disponibles y enumera los permisos "
            "obligatorios para abrir cada carpeta privada del entorno actual."
        )
        second["source_url"] = first["source_url"]
        result = self.validate()
        self.assertEqual(result["status"], "SOURCE_SPLITS_VERIFIED")
        self.assertEqual(result["minhash_prompts_checked"], sum(map(len, self.rows.values())))

    def test_index_budget_exhaustion_fails_closed(self):
        self.rows["train"][0]["prompt"] = PROMPT
        with patch.object(guard, "MINHASH_POSTING_LIMIT", 3):
            with self.assertRaisesRegex(ValueError, "^MINHASH_INDEX_BUDGET_EXCEEDED$"):
                self.validate()


if __name__ == "__main__":
    unittest.main()
