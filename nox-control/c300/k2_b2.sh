echo "C300: k2_b2"
N=/workspace/nox
cat $N/ops/draw/safety_check.py | cut -c1-200 | head -60
for p in 8811 8812 8104 8141; do s=$(date +%s.%N); r=$(curl -s -m 60 localhost:$p/v1/chat/completions -H 'Content-Type: application/json' -d '{"model":"x","id_slot":3,"messages":[{"role":"system","content":"Translate to a concise English image prompt. Output only it."},{"role":"user","content":"нарисуй кота в космосе"}],"max_tokens":40,"temperature":0,"chat_template_kwargs":{"enable_thinking":false}}' | head -c 400 | grep -o '"content":"[^"]*"' | head -1); echo "port $p wall=$(echo "$(date +%s.%N) - $s" | bc) $r"; done
uptime; ls -la $N/models/subcores/Qwen3-30B-A3B-Thinking-2507-GGUF | cut -c20-100
tail -4 $N/state/k2_restart.log
