echo S4RUN:s6_r8
cd /workspace/nox/web/site
echo "## models js"; grep -o "fetch([^)]*)" nox-p-models.js | head; head -c 2200 nox-p-models.js
echo; echo "## svc"; grep -o "fetch([^)]*)" nox-s4-svc.js | head -5; head -c 1200 nox-s4-svc.js
echo; echo "## integ"; grep -o "fetch([^)]*)" nox-p-integrations.js | head; head -c 1500 nox-p-integrations.js
echo; echo "## down"; grep -o "id=\"[a-zA-Z]*\"" nox-p-down.js | head; wc -c nox-p-down.js
for u in /glm/v1/models /api/svc/registry /api/services /web/svc_registry.json; do echo "URL $u: $(curl -s -m 5 -o /dev/null -w '%{http_code}' http://127.0.0.1:8091$u)"; done
curl -s -m 5 http://127.0.0.1:8091/glm/v1/models | head -c 400
