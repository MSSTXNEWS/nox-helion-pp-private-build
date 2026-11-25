S=/workspace/nox/web/site
cd $S
[ -f x.txt ] && cp -p x.txt x.txt.bak_s1_$(date +%H%M%S)
base64 -d > x.txt <<'S1EOF'
eAo=
S1EOF
echo OK x.txt $(wc -c <x.txt)
cd /workspace/nox/web/site; ls nox-k3-drill.js && cat nox-k3-drill.js | head -c 5000; echo ----; find / -name settings.json -path "*User*" 2>/dev/null | head; ps aux | grep -i code-server | head -3 | cut -c1-200
