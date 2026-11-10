"""Functional cognitive unity tests; no claimed consciousness or fake merge."""
from tempfile import TemporaryDirectory
from unittest import TestCase,main
from nox_prime_unified_self_v51 import compose
class UnifiedIdentityTests(TestCase):
    def test_eight_cores_one_principal_and_five_personas(self):
        with TemporaryDirectory() as root:
            data=compose(root,["qwen3:8b"],
                   {"operating_model":"qwen3:8b",
                    "limits":"8GB AMD VRAM is a scheduling constraint"},3,False)
            self.assertEqual(data["identity"],"NOX PRIME")
            self.assertEqual(data["principal_count"],1)
            self.assertEqual(len(data["core_ids"]),8)
            self.assertEqual(len(data["persona_ids"]),5)
            self.assertEqual(data["cognitive_memory"]["M0_M1_local_episodes"],3)
            self.assertFalse(data["cognitive_memory"]["native_s03_chat_writable"])
            self.assertFalse(data["adapters"]["unrelated_tensors_merged"])
            self.assertFalse(data["subjective_consciousness_verified"])
    def test_no_fabricated_8b_lora(self):
        with TemporaryDirectory() as root:
            d=compose(root,["qwen3:8b"],{"operating_model":"qwen3:8b"},0,True)
            self.assertTrue(d["affect_model"]["trainable_en_classifier"])
            self.assertFalse(d["adapters"]["any_0p5b_lora_applied_to_primary_8b"])
    def test_bad_memory_count_rejected(self):
        with TemporaryDirectory() as root:
            with self.assertRaises(ValueError):
                compose(root,[],{},-1)
if __name__=="__main__":main()
