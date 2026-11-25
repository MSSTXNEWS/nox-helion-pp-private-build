echo S4RUN:s6_r7
cd /workspace/nox/web/site
for p in models intents integrations install; do echo "##### $p.html"; sed -n '/<body/,/<\/main>/p' $p.html | head -c 2500; echo; grep -o '<script[^>]*src="[^"]*"' $p.html | grep -v "nox-\(nav\|dock\|ninja\|mini\|pwa\|pult\|sun\|state\|cmd\|actions\|cast\|radial\|live\|gesture\)" ; done
echo "## registry"; python3 -c "
import json;j=json.load(open('qa/registry.json'));c=j['commands'];print(len(c));k=list(c)[:3];print(k,[c[x] for x in k])"
ls data | head -30; ls | grep -i "svc\|registry" | head
echo "## NOXds"; grep -o "NOXds\.[a-z]*" nox-ds.js | sort -u; grep -n "skeleton\|empty *[:=(]" nox-ds.js | head -8 | cut -c1-250
