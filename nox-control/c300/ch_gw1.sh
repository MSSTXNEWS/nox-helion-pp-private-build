echo "C300: ch_gw1"
G=/workspace/nox/advisors/gateway.py; ls -l $G; wc -l $G
grep -n "^def \|^class \|PROVIDERS\|needs_key\|^[A-Z_]* *= *[\[{]" $G | cut -c1-170 | head -70
echo "== models all"; curl -s -m5 localhost:8793/v1/models | python3 -c "
import sys,json
for m in json.load(sys.stdin)['data']: print(m['id'],m.get('available'),m.get('status'),m.get('needs_key'),m.get('latency_ms'))" | head -60
echo "== key env names"; ls /workspace/nox/advisors | head -30; grep -o "[A-Z_]*API_KEY[A-Z_]*" $G | sort -u | head
echo "== audit"; tail -c 400 /workspace/nox/state/ch_audit1.log; pgrep -af qa_audit | cut -c1-90 | head -3
