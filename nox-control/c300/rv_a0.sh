echo "C300: rv_a0"
N=/workspace/nox
ls $N/web | head -30
find $N/web -maxdepth 3 -name nav.json | head
for f in $(find $N/web -maxdepth 3 -name nav.json | head -1); do python3 -c "
import json,sys
d=json.load(open('$f'))
print(json.dumps(d,ensure_ascii=False)[:3000])"; done
ls $N/web/site/web 2>/dev/null | head -100
ls $N/venv/lib/python3*/site-packages | grep -i -E "axe|playwright" ; find $N -maxdepth 4 -iname 'axe*.js' 2>/dev/null | head -3
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:18091/web/index.html
