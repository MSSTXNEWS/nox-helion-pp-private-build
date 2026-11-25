echo S4RUN:s4_rc7
S=/workspace/nox/web/site
curl -s -m6 127.0.0.1:8091/memory/health | head -c 300; echo
python3 -c "
import json;c=json.load(open('$S/qa/registry.json'))['commands']
print({k:v for k,v in c.items() if 'search' in k or 'meili' in k})"
curl -s -m8 "127.0.0.1:8091/search?q=nox" | head -c 700; echo
curl -s -m8 "127.0.0.1:8091/search?q=nox&limit=3" -H 'Accept: application/json' | head -c 200; echo
grep -n "search" /workspace/nox/web/pkg/server/web_server.py | head -8 | cut -c1-220
grep -n "meili\|search" $S/nox-cmd.js | head -5 | cut -c1-200
ls $S/vendor | grep -i "force\|cytoscape\|tone\|paper\|globe"; ls $S/vendor/nox-x | head -30
ls $S/vendor/nox-brain | head
