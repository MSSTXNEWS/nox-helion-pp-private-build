S=/workspace/nox/web/site
cd $S
[ -f x.txt ] && cp -p x.txt x.txt.bak_s1_$(date +%H%M%S)
base64 -d > x.txt <<'S1EOF'
eAo=
S1EOF
echo OK x.txt $(wc -c <x.txt)
cd /workspace/nox/web/site/vendor/nox-fx
ls -la; grep -o "createFrame[A-Za-z]*\|export{[^}]*}" hud.js | sort -u | head; tail -c 600 hud.js
cd ..; curl -s -m15 -o /dev/null -w "npm %{http_code}\n" https://registry.npmjs.org/@arwes/frames
