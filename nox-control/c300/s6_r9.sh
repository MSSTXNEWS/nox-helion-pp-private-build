echo S4RUN:s6_r9
cd /workspace/nox/web/site
for p in constructor scene effects widgets about glance; do echo "##### $p.html"; sed -n '/<body/,/<\/main>/p' $p.html | head -c 1800; echo; grep -o '<script[^>]*src="[^"]*"' $p.html | grep -v "nox-\(nav\|dock\|ninja\|mini\|pwa\|pult\|sun\|state\|cmd\|actions\|cast\|radial\|live\|gesture\|theme\|fx\|worlds\|ds\|s6\)" ; done
echo "## llama-swap"; for u in /running /models /v1/models /upstream; do echo "$u $(curl -s -m 4 -o /dev/null -w '%{http_code}' http://127.0.0.1:8200$u)"; done; curl -s -m 4 http://127.0.0.1:8200/running | head -c 300
echo "## registry model cmds"; python3 -c "
import json;c=json.load(open('qa/registry.json'))['commands'];print([k for k in c if 'model' in k or 'llama' in k or 'load' in k]);print(list(c))"
echo "## nox-live"; curl -s -m 5 http://127.0.0.1:8091/api/nox-live | head -c 900
echo; echo "## glance"; curl -s -m 5 -o /dev/null -w '%{http_code}' http://127.0.0.1:8091/svc/glance/; ls data
