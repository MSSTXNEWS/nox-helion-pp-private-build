echo S4RUN:s4_rc6
S=/workspace/nox/web/site
cd $S
echo == system; grep -n -i "очист\|clear\|confirm" nox-p-system.js | cut -c1-260 | head -12
echo == registry; python3 -c "
import json;c=json.load(open('qa/registry.json'))['commands']
for k,v in c.items(): print(k, v.get('confirm'), (v.get('desc') or '')[:60])" | head -40
echo == growth; grep -n -i "dataZoom\|8100\|недоступ" nox-brain-x.js | cut -c1-240 | head
echo == organ table; grep -n "livePanel\|Органы и процессы" nox-brain-x.js | cut -c1-200 | head
echo == consc html; sed -n '/<main/,/<\/main>/p' consciousness.html | cut -c1-400
grep -n "llm-viz\|llm" nox-brain-x.js | cut -c1-200 | head -8
