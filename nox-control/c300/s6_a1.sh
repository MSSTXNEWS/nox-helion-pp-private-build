echo S4RUN:s6_a1
cd /workspace/nox/web/site
echo "## vendor"; ls vendor | grep -i "maplibre\|leaflet\|foliate\|cytoscape\|earth\|tabulator\|epub"; ls vendor/foliate-js 2>/dev/null | head; ls vendor/nox-extra | head -20
echo "## map.html"; sed -n '/<body/,/<\/main>/p' map.html | head -c 1500
echo "## nav.json"; python3 - <<'PY'
import json
j=json.load(open('nav.json')); print(type(j), list(j)[:8] if isinstance(j,dict) else len(j))
s=json.dumps(j,ensure_ascii=False)
import re
for p in "games mail map nexus social calls contacts messenger notifications book-reader benchmark browser ai-learning advisors".split():
    for m in re.finditer(r'\{[^{}]*"%s[^{}]*\}'%p,s): print(p,m.group(0)[:200]); break
PY
echo "## qa_ctl"; head -30 /workspace/nox/qa_ctl.py 2>/dev/null | cut -c1-160; ls /workspace/nox | grep -i "qa_ctl\|outbox"
grep -rn "outbox" /workspace/nox/web/*.py 2>/dev/null | head -5 | cut -c1-200; ls /workspace/nox | head -40
echo "## audit.json"; python3 -c "
import json;j=json.load(open('qa/audit.json'));print(type(j),list(j)[:10] if isinstance(j,dict) else len(j))"
for p in notifications benchmark nexus; do echo "## $p.html"; sed -n '/<body/,/<\/main>/p' $p.html | head -c 700; echo; done
