echo "C300: srv_k36"
cd /workspace/nox
grep -n "LIVE_TURN" -B3 -A6 integration/adapter.py | cut -c1-200 | head -50
curl -s -m 5 http://127.0.0.1:8104/slots | head -c 700; echo
ss -tnp 2>/dev/null | grep ":8104" | head -3
