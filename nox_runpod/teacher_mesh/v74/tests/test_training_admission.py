"""Guard full-base GPU training preflight against accidental weight mutation."""
import ast
import unittest
from nox_runpod.teacher_mesh.v74 import training_gpu_admission as m

class TestFullWeightsPreflight(unittest.TestCase):
    def test_remote_python_compiles(self):
        start="python3 - <<'PYREMOTE'\n"
        end="\nPYREMOTE"
        self.assertEqual(m.REMOTE.count(start),1)
        ast.parse(m.REMOTE.split(start,1)[1].split(end,1)[0])

    def test_gpu_and_approved_dataset_requisite(self):
        s=m.REMOTE
        for key in ("gpu1['free_mb']<12288","rights_verified",
                    "privacy_approved","TRAIN_HOLDOUT_DISJOINTNESS_UNVERIFIED",
                    "NATIVE_ONEHOST_TRAINING_LEASE_NOT_PROVEN"):
            self.assertIn(key,s)

    def test_active_student_gguf_not_trainable(self):
        s=m.REMOTE
        self.assertIn("config.json",s)
        self.assertIn("*.safetensors",s)
        self.assertIn("VETTED_TRAINABLE_HF_BASE_NOT_PINNED",s)
        self.assertIn("HOLD_FULL_BASE_WEIGHT_TRAINING",s)

    def test_no_second_backend_or_weights_changed(self):
        s=m.REMOTE
        for marker in ("'native_training_launched':False","'active_GGUF_changed_by_probe':False",
                       "'full_parameter_optimizer_steps_executed_this_probe':0"):
            self.assertIn(marker,s)
        for forbidden in ("supervisorctl','start","torch.save","pip install",
                          "model.save_pretrained","os.unlink","shutil.rmtree"):
            self.assertNotIn(forbidden,s)

    def test_provenance_not_fake_started(self):
        s=m.REMOTE
        self.assertIn("NATIVE_TRAIN_SOURCE=",s)
        self.assertIn("explicit_lora_call",s)
        self.assertIn("train_worm_t811u.py",s)
        self.assertIn("direct_weights_smoke.py",s)

if __name__=="__main__":unittest.main()
