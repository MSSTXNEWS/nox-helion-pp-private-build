S=/workspace/nox/web/site
cd $S
[ -f x.txt ] && cp -p x.txt x.txt.bak_s1_$(date +%H%M%S)
base64 -d > x.txt <<'S1EOF'
eAo=
S1EOF
echo OK x.txt $(wc -c <x.txt)
ps aux | grep "bind-addr 127.0.0.1:18207" | grep -v grep | head -1 | grep -o "user-data-dir [^ ]*"; find /workspace /root -maxdepth 6 -path "*User/settings.json" 2>/dev/null
