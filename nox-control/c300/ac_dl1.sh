echo "C300: ac_dl1"
df -h /workspace | tail -1; df -BG --output=avail /workspace | tail -1
du -xsh /workspace/nox/distill_v2/ckpt_keep /workspace/nox/ops/v5_live_adapter_20261125 /workspace/nox/backup 2>/dev/null
ls /workspace/nox/models/subcores/ /workspace/nox/models/gpu/unsloth 2>/dev/null | head -20
curl -sI -m 10 https://huggingface.co/unsloth/Qwen3-30B-A3B-Thinking-2507-GGUF/resolve/main/Qwen3-30B-A3B-Thinking-2507-Q4_K_M.gguf | head -8 | cut -c1-160
