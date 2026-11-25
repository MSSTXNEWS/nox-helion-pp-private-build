echo "C300: k_gw_chk1"
curl -s -m 5 -o /dev/null -w "gw %{http_code}\n" http://127.0.0.1:8793/health
ss -ltnp | grep ':8793 ' | cut -c1-120
grep -c MOCKQA /workspace/nox/advisors/gateway.py
tail -3 /workspace/nox/agent/out/gw_8793.log 2>/dev/null | cut -c1-160
