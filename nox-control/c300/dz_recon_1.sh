S=/workspace/nox/web/pkg/server/site; [ -d $S ] || S=$(dirname $(find /workspace/nox -name creative.html -not -path "*/node_modules/*" | head -1))
echo "SITE $S"; ls -la $S/creative.html $S/editor.html; wc -c $S/creative.html
echo "== scripts/links"; grep -noE '<(script|link)[^>]*(src|href)="[^"]+"' $S/creative.html | cut -c1-160
echo "== html head"; head -c 3000 $S/creative.html
echo "== inline script len"; grep -c "" $S/creative.html
ls $S/nox-dz-* $S/nox-s6-sl.js 2>&1
ls $S/vendor | head -100 | tr '\n' ' '
echo; cat $S/editor.html | head -c 600
echo "== models"; curl -s -m 5 localhost:8104/v1/models | head -c 400
echo; curl -s -m 5 -o /dev/null -w "glm %{http_code}\n" localhost:8080/glm/v1/models
grep -n "glm\|/img/" /workspace/nox/web/pkg/server/web_server.py | head -20 | cut -c1-200
ls /tmp/k2_qa.py /workspace/nox/*qa* 2>&1 | head
