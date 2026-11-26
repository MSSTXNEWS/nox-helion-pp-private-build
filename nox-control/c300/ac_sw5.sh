echo "C300: ac_sw5"
grep -n "Skywork\|reward" /workspace/nox/judges/judge_service.py | head -20 | cut -c1-230
sed -n 358,362p /workspace/nox/judges/judge_service.py | cut -c1-400
curl -s -m 5 127.0.0.1:8300/judges | head -c 900
