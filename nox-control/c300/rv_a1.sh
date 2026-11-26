echo "C300: rv_a1"
N=/workspace/nox
python3 -c "
import json
d=json.load(open('$N/web/site/nav.json'))
for g in d['groups']:
  print(g['group'],'|',' '.join(i['file']+('(soon)' if i.get('soon') else '') for i in g['items']))
"
ls $N/web/site/*.html | wc -l; ls $N/web/site | head -80 | tr '\n' ' '
find $N -iname 'axe*.js' -not -path '*/node_modules/*/node_modules/*' 2>/dev/null | head -3
pip list 2>/dev/null | grep -i axe; $N/venv/bin/pip list 2>/dev/null | grep -i -E "axe|playwright"
ss -ltnp 2>/dev/null | grep -E ":8104|:18091|:8091" | cut -c1-120
curl -s -m5 -o /dev/null -w "axe cdn %{http_code}\n" https://cdn.jsdelivr.net/npm/axe-core@4.10.0/axe.min.js
