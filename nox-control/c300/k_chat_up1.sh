echo "C300: k_chat_up1"
cd /workspace/nox/ops/draw && /workspace/nox/venv/bin/python -m py_compile invoke_draw.py && echo "draw ok"
cat > /workspace/nox/agent/out/k_up1_bg.sh <<'BG'
L=/workspace/nox/agent/out/k_up1_bg.log; echo "start $(date)" > $L
/workspace/nox/web/pkg/server/run_web.sh restart >> $L 2>&1
sleep 6; curl -s -m 8 -o /dev/null -w "web %{http_code}\n" http://127.0.0.1:8091/api/chat/health >> $L
cd /workspace/nox && timeout 600 /workspace/nox/venv/bin/python state/liska_restart_core.py >> $L 2>&1; echo "core rc=$?" >> $L
BG
setsid -f bash /workspace/nox/agent/out/k_up1_bg.sh </dev/null >/dev/null 2>&1
echo "scheduled"
