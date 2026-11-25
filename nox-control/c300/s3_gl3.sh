echo "== GL3"; cat /workspace/nox/svc/glance/glance.yml
/workspace/nox/venv/bin/python -c "import json;print(json.load(open('/workspace/nox/web/pkg/server/svc_registry.json'))['glance'])"
grep -n "glance" /workspace/nox/svc/*.sh | cut -c1-300
for p in 8099 8100 8081 8085; do echo $p $(curl -s -m 3 -o /dev/null -w '%{http_code}' 127.0.0.1:$p/); done
echo "-- web /svc/glance"; curl -s -m 5 -o /dev/null -w '%{http_code}\n' localhost:8091/svc/glance/
CW=$(readlink /proc/470350/cwd); echo CORE_CWD=$CW; ls $CW | head -30
grep -n "sysm *=\|sysm=\|def build_system\|def system" $CW/nox_core.py | cut -c1-200 | head
grep -n "state/\|\.json" $CW/nox_core.py | grep -i "open(\|read_text\|Path(" | cut -c1-200 | head -15
