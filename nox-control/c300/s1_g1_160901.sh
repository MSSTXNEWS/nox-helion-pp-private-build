S=/workspace/nox/web/site
cd $S
[ -f x.txt ] && cp -p x.txt x.txt.bak_s1_$(date +%H%M%S)
base64 -d > x.txt <<'S1EOF'
eAo=
S1EOF
echo OK x.txt $(wc -c <x.txt)
cd /workspace/nox/web/site
ls vendor/echarts | head; ls vendor/assistant-ui | head; du -sh vendor/assistant-ui
curl -s -m8 http://127.0.0.1:8091/api/nox-live | head -c 700; echo
grep -n "echarts\|<main\|class=\"grid\"" system.html | head -8 | cut -c1-200
grep -o 'src="[^"]*echarts[^"]*"' system.html settings.html | head -3
