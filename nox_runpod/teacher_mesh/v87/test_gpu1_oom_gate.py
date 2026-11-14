"""V87 real Volta capacity and chat-first admission tests (no CUDA allocation)."""
import unittest
from nox_runpod.teacher_mesh.v87.gpu1_oom_gate import gpu1_peak_admission

SHA="a"*64
def ready(**updates):
    obj={
        "instance_id":"60509551","native_verified":True,"stop_active":False,
        "main_gpu0_student_healthy":True,"chat_state":"idle","chat_recent":False,
        "onehost_gpu1_lease":True,"gpu1_teacher_in_flight":False,
        "gpu1_optimizer_in_flight":False,
        "student_format":"HF_SAFETENSORS","training_mode":"BASE_WEIGHTS",
        "torch_cuda_major":12,"gpu1_compute_capability":"7.0",
        "precision":"fp16","uses_bf16":False,"uses_flashattention2":False,
        "gpu1_name":"Tesla V100-SXM2-32GB","memory_estimate_verified":True,
        "microbatch":1,"gradient_checkpointing":True,
        "trainable_base_sha256":SHA,"tokenizer_sha256":SHA,"optimizer_profile_sha256":SHA,
        "gpu1_free_mib":20000,"gpu1_model_resident_mib":9000,
        "gpu1_trainable_grad_mib":800,"gpu1_optimizer_state_mib":3200,
        "gpu1_activation_peak_mib":1200,"gpu1_kernel_scratch_mib":700,
    }
    obj.update(updates)
    return obj

class GateTests(unittest.TestCase):
    def test_safe_sample_admits_only_native_owner_next(self):
        g=gpu1_peak_admission(ready())
        self.assertEqual(g["state"],"READY_FOR_OWNER_AND_CHECKPOINT_GATES")
        self.assertFalse(g["performed"])
        self.assertFalse(g["model_loaded"])
        self.assertEqual(g["optimizer_steps_executed"],0)
        self.assertEqual(g["required_free_mib"],17972)
    def test_real_v100_12gb_free_with_full_model_oom(self):
        g=gpu1_peak_admission(ready(gpu1_free_mib=12523))
        self.assertIn("HOLD_CUDA_OOM_EXPECTED",g["reasons"])
        self.assertFalse(g["main_model_changed"])
    def test_35b_full_fp16_cannot_fit_one_v100(self):
        g=gpu1_peak_admission(ready(
            gpu1_model_resident_mib=70000,gpu1_free_mib=28000))
        self.assertIn("HOLD_MODEL_RESIDENCE_EXCEEDS_GPU1",g["reasons"])
    def test_gguf_is_inference_not_training(self):
        g=gpu1_peak_admission(ready(student_format="GGUF_Q4"))
        self.assertIn("HOLD_TRAINABLE_BASE_NOT_HF",g["reasons"])
    def test_qlora_instead_of_base_weights_denied(self):
        g=gpu1_peak_admission(ready(training_mode="QLORA"))
        self.assertIn("HOLD_BASE_WEIGHT_ONLY_NOT_ADAPTER",g["reasons"])
    def test_chat_preempts(self):
        g=gpu1_peak_admission(ready(chat_state="generating"))
        self.assertIn("HOLD_CHAT_P0_PREEMPTS_GPU1",g["reasons"])
    def test_teacher_same_gpu_blocks_trainer(self):
        g=gpu1_peak_admission(ready(gpu1_teacher_in_flight=True))
        self.assertIn("HOLD_TEACHER_ACTIVE_OR_UNKNOWN",g["reasons"])
    def test_unknown_teacher_fails_closed(self):
        g=gpu1_peak_admission(ready(gpu1_teacher_in_flight=None))
        self.assertIn("HOLD_TEACHER_ACTIVE_OR_UNKNOWN",g["reasons"])
    def test_cpu_offload_unverified_never_assumed(self):
        g=gpu1_peak_admission(ready(memory_estimate_verified=False))
        self.assertIn("HOLD_PEAK_ESTIMATE_UNVERIFIED",g["reasons"])
    def test_no_flashattn_bf16_cuda13(self):
        g=gpu1_peak_admission(ready(torch_cuda_major=13,uses_bf16=True))
        self.assertIn("HOLD_VOLTA_SM70_CUDA12",g["reasons"])
        self.assertIn("HOLD_VOLTA_FP16_KERNELS",g["reasons"])
    def test_bad_grad_checkpointing_and_microbatch(self):
        g=gpu1_peak_admission(ready(microbatch=2,gradient_checkpointing=False))
        self.assertIn("HOLD_MICROBATCH_MUST_BE_ONE",g["reasons"])
        self.assertIn("HOLD_GRADIENT_CHECKPOINTING",g["reasons"])
    def test_no_training_without_valid_sha(self):
        g=gpu1_peak_admission(ready(trainable_base_sha256="size-is-not-a-hash"))
        self.assertIn("HOLD_SHA_TRAINABLE_BASE_SHA256",g["reasons"])
    def test_missing_measurement_never_pass(self):
        g=gpu1_peak_admission(ready(gpu1_activation_peak_mib=None))
        self.assertIn("HOLD_ESTIMATE_GPU1_ACTIVATION_PEAK_MIB",g["reasons"])
if __name__=="__main__": unittest.main()
