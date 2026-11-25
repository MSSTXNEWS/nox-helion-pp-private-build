echo "C300: k8_pr_7"
S=/workspace/nox/web/site; cd $S
echo "http $(curl -s -m 5 -o /dev/null -w '%{http_code}' http://127.0.0.1:8091/web/index.html)"
wc -c creative.html; grep -o '<script[^>]*src="[^"]*"' creative.html | sed 's/<script[^>]*src=//' | tr '\n' ' ' | head -c 900; echo; grep -o 'id="[^"]*"' creative.html | head -60 | tr '\n' ' '; echo
head -c 1500 nox-dz-creative.js; echo; grep -o "fetch([^)]*)" nox-dz-creative.js nox-s2-creative.js | sort -u | head -12
W=/workspace/nox/web/pkg/server/web_server.py
grep -n '"/img/generate"\|/api/vision\|8104\|/api/turn' $W | head -12 | cut -c1-220
cat /workspace/nox/state/persona.json | head -c 600; echo
grep -n "persona" $W | head -6 | cut -c1-200
ls site/nox-persona.js && head -c 1200 nox-persona.js
echo "K8 pr7 done"
