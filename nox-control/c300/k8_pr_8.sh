echo "C300: k8_pr_8"
S=/workspace/nox/web/site; cd $S; W=/workspace/nox/web/pkg/server/web_server.py
echo "http $(curl -s -m 5 -o /dev/null -w '%{http_code}' http://127.0.0.1:8091/web/index.html)"
grep -n "def _img_generate" -A40 $W | cut -c1-210 | head -60
grep -n '/vision/describe' $W | head -3 | cut -c1-200
grep -n 'def _vision' -A25 $W | cut -c1-200 | head -35
echo ---GHOST; head -c 1800 nox-ghost.js; echo; grep -n "window.NOXghost\|NoxGhost\|data-ghost\|querySelectorAll" nox-ghost.js | head -8 | cut -c1-200
echo ---ADV; curl -s -m 5 http://127.0.0.1:8793/health | head -c 300; echo; curl -s -m 5 http://127.0.0.1:8793/v1/models | head -c 600; echo; grep -rn "drawing_senior" /workspace/nox --include=*.py --include=*.json --include=*.md --include=*.yaml -l 2>/dev/null | head -5
echo ---P2; ls /workspace/nox/state | grep -i "hunger\|learn\|голод\|lesson" | head; ls data | head -20
grep -n "^## \|index.html" qa/rework/index.fixed | tail -3
grep -c "nox-k8-" index.html; grep -o 'nox-k8-[a-z]*\.js' index.html | sort -u | tr '\n' ' '
echo "K8 pr8 done"
