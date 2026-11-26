echo "C300: k2_r13"
N=/workspace/nox
grep -nE "enabled|registry|json.load" $N/stewards/nox_orch.py | cut -c1-200 | head -25
sed -n 372,384p $N/stewards/nox_orch.py | cut -c1-220
grep -nE "t_coder" -B2 -A12 $N/stewards/orch_registry.json | sed -n 28,60p | cut -c1-160
ls -la $N/models/subcores/Qwen3-30B-A3B-Thinking-2507-GGUF/ | tail -1 | cut -c20-90
echo "--- bind errs now: 8301=$(grep -c 'already in use' $N/agent/out/adapter_mem_8301.log) 8090=$(grep -c 'already in use' $N/agent/out/core_8090.log)"
tail -2 $N/agent/out/selfheal_supervisor.log
