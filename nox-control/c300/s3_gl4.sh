echo "== GL4"
for u in 127.0.0.1:18200/ 127.0.0.1:18200/svc/glance/ localhost:8091/svc/glance localhost:8091/svc/glance/ localhost:8091/svc/filebrowser/ localhost:8091/svc/ntfy/; do echo $u $(curl -s -m 5 -o /dev/null -w '%{http_code}' http://$u); done
grep -n "svc_registry\|/svc/" /workspace/nox/web/pkg/server/web_server.py | cut -c1-200 | head -15
CW=/workspace/nox/brain/BRAIN
grep -n "sysm *=\|sysm=\|def build_sys\|def system_prompt\|def _system" $CW/nox_core.py | cut -c1-200 | head
grep -n "persona\|PERSONA" $CW/nox_core.py | head -5
grep -n "open(.*state\|STATE.*json\|read_text" $CW/nox_core.py | cut -c1-180 | head -10
ls /workspace/nox/state/*.json | head -20
