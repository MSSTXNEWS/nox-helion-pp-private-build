echo "C300: srv_k107"
cd /workspace/nox; grep -n -i "flux\|schnell\|sd-cli\|/sd\b\|steps" ops/draw/invoke_draw.py | cut -c1-180 | head -20; cat ops/draw/bench_sd.sh | head -20 | cut -c1-250
