# I-49 CPU checkpoint comparison

- **Selection:** This exact pair and tensor were selected during this run under current owner authorization; no pre-existing allowlist is asserted.
- **Training:** Not started (`training_started=false`). No writes to Drive or the server.
- **Sources:** `understanding_pref_checkpoint-105` (`1PNX-lRLaKVTRPakDOOqctF_rUoPvOu59`) → `mix_final_sft_checkpoint-383` (`1CG_ALzrWsZLyrtuGxvNp4ajyZGfgh6nH`); both Qwen3.6-35B-A3B LoRA r=64, 306,787,336 bytes each.
- **JOIN / assembled SHA-256:** before `924d05894749d2107629549d9d95ca4e5538d33c2eac351d0c0c26919ccbb7a2`; after `8c32c5979470018bd260421b7ace2ef681e3c7f0e3dc978b6fecfdd98c25bcd1`. Each local assembly matched the JOIN digest and size; all four part hashes per source matched `SHA256SUMS` (full list and manifest hashes are in the JSON receipt).
- **Comparator:** `handoff/20261117/nox-v15-kit/execution/role4/tensor_delta.py` at `e10c80f64e3fd88298be2776c58d03939e6e71f6`; source SHA-256 `a1917cfda4fd012b92332a8b3513fb1ad3e4694050f254d38b3a88f803cfb867`.
- **Selected tensor:** `base_model.model.model.language_model.layers.0.linear_attn.in_proj_qkv.lora_A.weight` (F32, `[64, 2048]`, 524,288 bytes). Before SHA-256 `8f156397d7705748bc36e18d7658b0fbe5edac3592903a75714e6e0b05907812`; after SHA-256 `b6170f7d3462c8ed0fef0f33c2f6c722d1be99609902ded09086fb3883e6470a`.
- **Result:** `SELECTED_CHANGE_OBSERVED`; container headers agree and there were no comparator issues. This is evidence for the selected tensor only, not a claim that training was run or that all checkpoint tensors changed.
