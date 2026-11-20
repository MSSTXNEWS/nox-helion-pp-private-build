"""NOX V135 signed full-optimizer resume, source-only fail-closed regression."""
from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path

from nox_runpod.teacher_mesh.v135.verified_resume import (
    admit_resume,checkpoint_tree_sha256,
)
from nox_runpod.teacher_mesh.v135 import train_full_base_zero3 as trainer


class FullOptimizerRecovery(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.out=Path(self.temp.name)/"out"
        self.checkpoint=self.out/"checkpoint-5"
        (self.checkpoint/"global_step5").mkdir(parents=True)
        self.config={"zero_optimization":{"stage":3},"optimizer":"AdamW"}
        (self.out/"deepspeed_zero3_cpu.json").write_text(json.dumps(self.config))
        (self.checkpoint/"trainer_state.json").write_text(json.dumps({"global_step":5}))
        (self.checkpoint/"global_step5"/"zero_pp_rank_0_mp_rank_00_model_states.pt").write_bytes(b"model")
        (self.checkpoint/"global_step5"/"zero_pp_rank_0_mp_rank_00_optim_states.pt").write_bytes(b"optimizer")
        self.native={
            "student_base_sha256":"b"*64,
            "resume_checkpoint_path":str(self.checkpoint),
            "resume_checkpoint_step":5,
            "resume_optimizer_scheduler_rng_verified":True,
            "resume_offsite_restore_verified":True,
            "resume_original_student_sha256":"b"*64,
            "resume_checkpoint_tree_sha256":checkpoint_tree_sha256(self.checkpoint),
        }

    def admit(self,native=None,checkpoint=None,max_steps=10,config=None):
        return admit_resume(self.out,checkpoint or self.checkpoint,
                            native if native is not None else self.native,
                            max_steps=max_steps,
                            expected_config=config if config is not None else self.config)

    def test_valid_full_state_signed_checkpoint(self):
        result=self.admit()
        self.assertEqual(result["state"],"VERIFIED_SIGNED_FULL_OPTIMIZER_RESUME")
        self.assertEqual(result["start_step"],5)
        self.assertFalse(result["production_promoted"])

    def test_model_only_snapshot_cannot_resume(self):
        (self.checkpoint/"global_step5"/"zero_pp_rank_0_mp_rank_00_optim_states.pt").unlink()
        with self.assertRaisesRegex(RuntimeError,"HOLD_RESUME_FULL_OPTIMIZER_MISSING"):
            self.admit()

    def test_full_tree_sha_detects_tamper(self):
        (self.checkpoint/"global_step5"/"zero_pp_rank_0_mp_rank_00_model_states.pt").write_bytes(b"tampered")
        with self.assertRaisesRegex(RuntimeError,"HOLD_RESUME_TREE_SHA_MISMATCH"):
            self.admit()

    def test_no_signed_offsite_restore_refuses_resume(self):
        with self.assertRaisesRegex(RuntimeError,"HOLD_RESUME_OWNER_SIGNED_RESTORE"):
            self.admit(native=dict(self.native,resume_offsite_restore_verified=False))

    def test_changed_deepspeed_optimizer_configuration_refused(self):
        with self.assertRaisesRegex(RuntimeError,"HOLD_RESUME_DEEPSPEED_CONFIG_CHANGE"):
            self.admit(config={"optimizer":"Different"})

    def test_symlink_or_external_checkpoint_refused(self):
        alias=self.out/"checkpoint-6"
        alias.symlink_to(self.checkpoint,target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError,"HOLD_RESUME_CHECKPOINT_SCOPE"):
            self.admit(checkpoint=alias)
        outside=Path(self.temp.name)/"foreign"/"checkpoint-5"
        outside.mkdir(parents=True)
        with self.assertRaisesRegex(RuntimeError,"HOLD_RESUME_CHECKPOINT_SCOPE"):
            self.admit(checkpoint=outside)

    def test_existing_step_cannot_be_overwritten_or_reused(self):
        with self.assertRaisesRegex(RuntimeError,"HOLD_RESUME_STEP"):
            self.admit(max_steps=5)
        with self.assertRaisesRegex(RuntimeError,"HOLD_RESUME_STEP"):
            self.admit(max_steps=1)

    def test_dangling_symlink_in_shard_tree_refuses_resume(self):
        (self.checkpoint/"global_step5"/"bad-link.pt").symlink_to(self.out/"missing")
        with self.assertRaisesRegex(RuntimeError,"HOLD_RESUME_SYMLINK"):
            self.admit()

    def test_existing_trainer_wired_to_resume_once(self):
        source=Path(trainer.__file__).read_text("utf-8")
        self.assertIn("admit_resume(out,resume_path,native",source)
        self.assertIn("trainer.train(resume_from_checkpoint=resumed['checkpoint'] if resumed else None)",source)
        self.assertIn("NOX_V135_RESUME_STEP_",source)
        self.assertIn("p.add_argument('--resume-checkpoint'",source)
        self.assertNotIn("save_only_model=True",source)


    def test_written_checkpoint_receipt_binds_exact_step_and_optimizer_state(self):
        proof=trainer._verify_written_checkpoint(self.out,5)
        self.assertEqual(proof["path"],str(self.checkpoint))
        self.assertEqual(proof["global_step"],5)
        self.assertRegex(proof["tree_sha256"],r"^[0-9a-f]{64}$")

        wrong=self.out/"checkpoint-6"
        (wrong/"global_step6").mkdir(parents=True)
        (wrong/"trainer_state.json").write_text(json.dumps({"global_step":5}))
        (wrong/"global_step6"/"zero_pp_rank_0_mp_rank_00_model_states.pt").write_bytes(b"model")
        (wrong/"global_step6"/"zero_pp_rank_0_mp_rank_00_optim_states.pt").write_bytes(b"optimizer")
        with self.assertRaisesRegex(RuntimeError,"HOLD_WRITTEN_CHECKPOINT_STEP_MISMATCH"):
            trainer._verify_written_checkpoint(self.out,6)

        (self.checkpoint/"global_step5"/"zero_pp_rank_0_mp_rank_00_optim_states.pt").unlink()
        with self.assertRaisesRegex(RuntimeError,"HOLD_WRITTEN_CHECKPOINT_OPTIMIZER_MISSING"):
            trainer._verify_written_checkpoint(self.out,5)


if __name__=="__main__":
    unittest.main()
