echo "C300: k_draw_rs2"
cd /workspace/nox/ops/draw && /workspace/nox/venv/bin/python -m py_compile invoke_draw.py && echo "v2 compiles"
/workspace/nox/web/pkg/server/run_web.sh restart 2>&1 | tail -2
sleep 6; curl -s -m 8 -o /dev/null -w "web %{http_code}\n" http://127.0.0.1:8091/api/chat/health
cat > /workspace/nox/agent/out/k_rs2_bg.sh <<'BG'
L=/workspace/nox/agent/out/k_rs2_bg.log; echo "start $(date)" > $L
cd /workspace/nox && timeout 600 /workspace/nox/venv/bin/python state/liska_restart_core.py >> $L 2>&1; echo "core rc=$?" >> $L
BG
setsid nohup bash /workspace/nox/agent/out/k_rs2_bg.sh </dev/null >/dev/null 2>&1 &
echo "core restart scheduled"
