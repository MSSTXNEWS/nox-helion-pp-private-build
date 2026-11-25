echo S4RUN:s6_a2
cd /workspace/nox/web/site
python3 - <<'PY'
import json
j=json.load(open('nav.json'))
for k in ['groups','hidden','pages','soon']:
    v=j[k]; print('##',k,type(v).__name__,len(v)); 
    print(json.dumps(v if k!='pages' else (list(v.items())[:2] if isinstance(v,dict) else v[:2]),ensure_ascii=False)[:700])
s=json.dumps(j['groups'],ensure_ascii=False)
for p in ['games','mail','map','social','calls','contacts','messenger','notifications','book-reader','benchmark','browser','ai-learning','advisors','nexus']: print(p,'in groups' if p+'.html' in s else 'not in groups', 'in pages' if p+'.html' in json.dumps(j['pages']) else '')
PY
grep -n "pin\|sys.argv" /workspace/nox/qa_ctl.py | tail -8 | cut -c1-160
echo "## foliate"; ls vendor/foliate-js | tr '\n' ' '; ls vendor/maplibre-gl | head -5
echo "## notif sources"; grep -ln "outbox" *.js 2>/dev/null | head; grep -o "api/[a-z/_-]*" nox-actions.js nox-ninja.js 2>/dev/null | sort -u | head -20
curl -s -m 4 http://127.0.0.1:8091/api/notifications | head -c 300; echo; curl -s -m 4 http://127.0.0.1:8091/api/outbox | head -c 200; echo; ls /workspace/nox/pc_outbox | head -5; ls /workspace/nox/pc_outbox | wc -l
python3 -c "
import json;j=json.load(open('qa/audit.json'));k=list(j)[0];print(k,json.dumps(j[k],ensure_ascii=False)[:500])"
