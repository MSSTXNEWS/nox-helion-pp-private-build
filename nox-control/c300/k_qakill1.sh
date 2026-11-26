echo "C300: k_qakill1"
for p in 3602620 3602641; do
  c=$(tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null)
  if echo "$c" | grep -q qa_audit.py; then kill $p && echo "killed $p: $c"; else echo "skip $p: [$c]"; fi
done
sleep 2; ps -eo pid,etimes,args | grep [q]a_audit.py | head
python3 -m py_compile /workspace/nox/web/chat_core.py 2>/dev/null; cd /workspace/nox && find . -maxdepth 3 -name chat_core.py | head -3
cat > /workspace/nox/agent/out/k_qk_bg.sh <<'BG'
L=/workspace/nox/agent/out/k_qk_bg.log; echo "start $(date)" > $L
/workspace/nox/web/pkg/server/run_web.sh restart >> $L 2>&1
sleep 8; curl -s -m 8 -o /dev/null -w "web %{http_code}\n" http://127.0.0.1:8091/api/chat/health >> $L
BG
setsid -f bash /workspace/nox/agent/out/k_qk_bg.sh </dev/null >/dev/null 2>&1
sleep 25; cat /workspace/nox/agent/out/k_qk_bg.log
