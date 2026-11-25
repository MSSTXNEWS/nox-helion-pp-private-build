echo "C300: a2_art1"
A=/workspace/nox/advisors
echo "== prev selftest log"; cut -c1-300 $A/art_selftest.log | tail -12
echo "== registry roles"; python3 - <<'P'
import json
d=json.load(open('/workspace/nox/state/advisors_external.json'))
print(d.get('roles'))
for a in d['advisors']:
    if a.get('role'): print(a['id'],a['status'],a.get('latency_ms'),str(a.get('error') or a.get('sample') or '')[:120].replace('\n',' '))
P
ls -la /workspace/nox/state/advisor_images | tail -5; ls -la /workspace/nox/state/secrets/advisors.env; curl -s -m5 127.0.0.1:8793/health | head -c 200; echo
echo "== v_art_2 check"; grep -c images_critique $A/gateway.py
