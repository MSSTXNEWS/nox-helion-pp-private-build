"""V92 no-adapter real HF base manifest tests; metadata-only synthetic fixtures."""
import json
import struct
import tempfile
import unittest
from pathlib import Path

from nox_runpod.teacher_mesh.v47.night_v47.direct_weights_smoke import model_manifest_bytes

def make(root, *, tensors=None, index=None, tokenizer=True, model_type="qwen3_5_moe"):
    root.mkdir(exist_ok=True,parents=True)
    (root/"config.json").write_text(json.dumps({"model_type":model_type}),encoding="utf-8")
    if tokenizer:
        (root/"tokenizer.json").write_text('{"version":"1.0"}',encoding="utf-8")
    keys=tensors or {"model.layers.1.self_attn.q_proj.weight":
                       {"dtype":"F16","shape":[4],"data_offsets":[0,8]}}
    hdr=json.dumps(keys,separators=(',',':')).encode()
    (root/"model.safetensors").write_bytes(struct.pack('<Q',len(hdr))+hdr+b'\0'*8)
    if index is not None:
        (root/"model.safetensors.index.json").write_text(json.dumps({"weight_map":index}),encoding='utf-8')

class BaseWeightsGate(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/"student"

    def test_valid_local_hf_fp16_base_passes(self):
        make(self.root)
        self.assertGreater(model_manifest_bytes(self.root),40)

    def test_bf16_weight_allowed_for_later_explicit_fp16_and_vram_guard(self):
        make(self.root,tensors={"model.layers.0.weight":
                       {"dtype":"BF16","shape":[4],"data_offsets":[0,8]}})
        self.assertGreater(model_manifest_bytes(self.root),40)

    def test_lora_tensor_is_never_full_base(self):
        make(self.root,tensors={"base_model.model.layers.0.lora_A.default.weight":
                        {"dtype":"BF16","shape":[4],"data_offsets":[0,8]}})
        with self.assertRaisesRegex(RuntimeError,"LORA_ADAPTER"):
            model_manifest_bytes(self.root)

    def test_adapter_config_rejected(self):
        make(self.root)
        (self.root/"adapter_config.json").write_text('{"peft_type":"LORA"}')
        with self.assertRaisesRegex(RuntimeError,"LORA_ADAPTER"):
            model_manifest_bytes(self.root)

    def test_shard_map_missing_file_rejected(self):
        make(self.root,index={"x":"model.safetensors","y":"model-00002-of-00002.safetensors"})
        with self.assertRaisesRegex(RuntimeError,"SHARDS_INCOMPLETE"):
            model_manifest_bytes(self.root)

    def test_absent_tokenizer_fails_closed(self):
        make(self.root,tokenizer=False)
        with self.assertRaisesRegex(RuntimeError,"TOKENIZER_MISSING"):
            model_manifest_bytes(self.root)

    def test_pickle_weight_never_loaded(self):
        make(self.root)
        (self.root/"pytorch_model.bin").write_bytes(b'unsafe pickle')
        with self.assertRaisesRegex(RuntimeError,"UNTRUSTED_PICKLE"):
            model_manifest_bytes(self.root)

    def test_wrong_offsets_rejected(self):
        make(self.root,tensors={"model.layers.0.weight":
                        {"dtype":"F16","shape":[4],"data_offsets":[0,300]}})
        with self.assertRaisesRegex(RuntimeError,"WEIGHT_OFFSETS"):
            model_manifest_bytes(self.root)

    def test_bad_json_header_rejected(self):
        make(self.root)
        (self.root/"model.safetensors").write_bytes(struct.pack('<Q',3)+b'???'+b'\0'*10)
        with self.assertRaisesRegex(RuntimeError,"SAFETENSORS_HEADER"):
            model_manifest_bytes(self.root)

if __name__=="__main__":unittest.main()
