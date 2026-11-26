grep -c FAST_P3 /workspace/nox/judges/judge_service.py; ls /workspace/nox/judges | grep bak_fast
pgrep -af "uvicorn judge_service" | cut -c1-100; ps -o etimes= -p $(pgrep -f "uvicorn judge_service" | head -1)
curl -s -m4 127.0.0.1:8300/health; echo
tail -3 /workspace/nox/agent/out/judge_8300.log 2>/dev/null | cut -c1-150
echo load $(cat /proc/loadavg); df -h /workspace | tail -1 | awk '{print $4" free "$5}'; nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader
L=$(ls -td /workspace/nox/agent/autotrain/rounds/r0*/ | head -1); echo $L; grep -a "скорость" ${L}train.log | tail -2 | cut -c1-110
