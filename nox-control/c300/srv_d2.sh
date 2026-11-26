D=/workspace/nox/ops/v5_live_adapter_20261125
ls -la --time-style=+%m-%d_%H:%M $D | awk '{print $5,$6,$7}' | sort -k2 | tail -30
echo == refs; grep -rl "r031-step\|v5_live_adapter_20261125/r0" /workspace/nox/state /workspace/nox/ops/*.py /workspace/nox/ops/*.sh /workspace/nox/agent/*.sh 2>/dev/null | head -5
ps aux | grep -E "llama-server.*lora|--lora" | grep -v grep | cut -c1-200 | head
ls $D/*.py $D/*.sh 2>/dev/null | head; cat $D/state.json 2>/dev/null | head -c 400
