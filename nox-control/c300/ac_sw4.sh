echo "C300: ac_sw4"
Y=/workspace/nox/serve/llama-swap.yaml; cp -n $Y $Y.bak_accel_20261126
grep -q '"trainer17b"' $Y || cat >> $Y <<'YML'
  "trainer17b":
    cmd: /workspace/nox/bin/llama-server --host 127.0.0.1 --port ${PORT} -m /workspace/nox/models/agents/trainer17b/Qwen3-1.7B-Q4_K_M.gguf -ngl 0 -t 2 -c 4096 --parallel 2 --jinja --alias trainer17b
    proxy: http://127.0.0.1:${PORT}
    ttl: 300
YML
tail -6 $Y | cut -c1-120; python3 -c "import yaml;d=yaml.safe_load(open('$Y'));print('yaml ok',len(d['models']))" 2>&1 | tail -1
J=/workspace/nox/judges; ls $J | head -20; wc -l $J/judge_service.py; grep -nE "def |@app|fast|8300" $J/judge_service.py | head -40 | cut -c1-160
ls /workspace/nox/models/gpu/Skywork/Skywork-Reward-V2-Qwen3-0.6B | head
