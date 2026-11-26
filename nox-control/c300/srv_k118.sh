echo "C300: srv_k118"
cd /workspace/nox
grep -n "" serve/llama-swap.yaml | sed -n 1,30p | cut -c1-110; grep -n "gpt-oss\|Mistral" serve/llama-swap.yaml | cut -c1-60
pgrep -af llama-swap | head -2 | cut -c1-120; tail -n 3 ops/dpo/run5.log | cut -c1-150
