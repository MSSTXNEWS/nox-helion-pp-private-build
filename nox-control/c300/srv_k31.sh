echo "C300: srv_k31"
cd /workspace/nox/distill_v2/code
sed -n '2118,2135p;2184,2200p;2255,2300p' distill_v2.py | cut -c1-230
sed -n '2905,2935p' distill_v2.py | cut -c1-200
grep -n "chat_hold\|chat_busy\|ST + '/orch\|busy" distill_v2.py | head -12 | cut -c1-200
ls -la /workspace/nox/state/orch 2>/dev/null | head; ls -la --time-style=full-iso /workspace/nox/state/orch/chat_hold* 2>/dev/null; date
