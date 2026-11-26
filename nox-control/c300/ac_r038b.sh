echo "C300: ac_r038b"
grep -aE "скорость|профиль|шаг [0-9]+," /workspace/nox/agent/autotrain/rounds/r038/train.log | tail -6 | cut -c1-200
df -h /workspace | tail -1
M=$(ls -d /workspace/nox/models/body/unsloth/Qwen3.6-35B-A3B* 2>/dev/null | head -3); echo $M
find /workspace/nox/models -maxdepth 4 -name config.json 2>/dev/null | grep -i "3.6\|qwen3" | head -5
python3 - <<'PY'
import json,glob
for f in glob.glob('/workspace/nox/models/**/config.json',recursive=True)[:200]:
    if '3.6' in f or 'Qwen3.6' in f:
        d=json.load(open(f));t=d.get('text_config',d);print(f,t.get('architectures',d.get('architectures')),t.get('num_experts'),t.get('moe_intermediate_size'),t.get('hidden_size'),t.get('num_hidden_layers'))
PY
ls /workspace/nox/distill_v2/ckpt_keep/best_step_0075*/ | head; python3 -c "
import json;print(open('/workspace/nox/distill_v2/ckpt_keep/best_step_0075_hold1.1159_11231724/adapter_config.json').read()[:600])" 2>&1 | head -20
