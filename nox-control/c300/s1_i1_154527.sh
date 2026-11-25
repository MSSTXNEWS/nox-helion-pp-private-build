S=/workspace/nox/web/site
cd $S
[ -f x.txt ] && cp -p x.txt x.txt.bak_s1_$(date +%H%M%S)
base64 -d > x.txt <<'S1EOF'
eAo=
S1EOF
echo OK x.txt $(wc -c <x.txt)
cd /workspace/nox/web/site
ls -la --time-style=+%F_%R index.html* | head -30
ls -d /workspace/nox/web/*/ /workspace/nox/archive* /workspace/nox/backup* 2>/dev/null | head
find /workspace /root -maxdepth 5 \( -iname "NOX_V13*" -o -iname "*NOX_V7_WEB*" -o -iname "*WEB_UNIFIED*" -o -iname "index.html.bak*" -o -iname "*V29*" \) 2>/dev/null | head -20
