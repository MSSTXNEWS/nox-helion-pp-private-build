echo "C300: srv_k78"
D=/workspace/nox/ops/v5_live_adapter_20261125
ls -la --time-style=+%m-%d_%H:%M $D/*.gguf | awk '{print $5, $6, $7}'
B=/workspace/nox/ops/v5_knowledge_gpu_20261125/main-rows.jsonl.bak_add_accepted_long_20261125_step125; ls -la $B 2>&1 | awk '{print $5,$9}'
echo == lsof; for f in $D/*.gguf $B; do lsof "$f" 2>/dev/null | tail -n +2 | head -2 | awk -v f="$f" '{print "OPEN",f,$1,$2}'; done; echo lsof_done
echo == refs
for c in $(ls /workspace/nox/*/llama-swap*.yaml /workspace/nox/llama-swap*.y*ml /workspace/nox/**/llama-swap*.y*ml 2>/dev/null | head); do echo $c; done
timeout 60 grep -rl "v5_live_adapter_20261125" /workspace/nox --include=*.yaml --include=*.yml --include=*.json --include=*.cmd --include=*.conf 2>/dev/null | grep -v "/venv" | head -10
