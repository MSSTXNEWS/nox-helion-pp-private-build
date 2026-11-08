"""Prove Stage1 downloads ONE merge-compatible trainable neural base, not 5."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from unittest.mock import patch
import nox_prime_stage1_download_all_v1 as stage1
import nox_prime_download_five_v1 as model_list

class Stage1DownloadTests(unittest.TestCase):
    def test_first_stage_has_only_one_trainable_foundation(self):
        self.assertEqual(stage1.STAGES[0],"NOX_CORE_WEIGHTS")
        self.assertEqual(len(stage1.STAGES),7)
        self.assertEqual(model_list.MODELS[0][1],"Qwen/Qwen3-0.6B")

    def test_one_stage1_base_and_all_six_other_component_stages(self):
        with TemporaryDirectory() as d:
            root=Path(d);(root/"brain").mkdir()
            observed=[]
            def selected_model(root,only=None):
                observed.append(tuple(only))
                return {"completed":1,"models":[{"model":"Qwen/Qwen3-0.6B"}]}
            with patch.object(stage1,"download_five",side_effect=selected_model),\
                 patch.object(stage1,"semantic",return_value={"status":"REUSED"}),\
                 patch.object(stage1,"affect_dataset",return_value={"status":"REUSED"}),\
                 patch.object(stage1,"whisper",return_value={"status":"REUSED"}),\
                 patch.object(stage1,"voices",return_value={"status":"REUSED"}),\
                 patch.object(stage1,"engine_sources",return_value=[]),\
                 patch.object(stage1,"_custom_reranker",return_value={"status":"REUSED"}):
                rc=stage1.run(root,Path(__file__).parent)
            self.assertEqual(rc,0)
            self.assertEqual(observed,[("Qwen3-0.6B",)])
            state=json.loads((root/"brain"/"telemetry"/"stage1_download_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(state["completed_groups"],7)
            self.assertEqual(state["failed_groups"],0)
            self.assertEqual(state["core_weights_to_download"],["Qwen/Qwen3-0.6B"])
            self.assertFalse(state["new_gpu_training_launched"])
            self.assertFalse(state["deleted_originals"])
            self.assertFalse(state["s03_changed"])

if __name__=="__main__":
    unittest.main()
