S=/workspace/nox/web/site
cd $S
[ -f x.txt ] && cp -p x.txt x.txt.bak_s1_$(date +%H%M%S)
base64 -d > x.txt <<'S1EOF'
eAo=
S1EOF
echo OK x.txt $(wc -c <x.txt)
ss -ltnp | grep -E ':8091|:8090|:8097' | cut -c1-150
curl -s -m5 -o /dev/null -w "8091 %{http_code}\n" http://127.0.0.1:8091/finance.html
ps aux | grep -E "web_server|http.server|nginx" | grep -v grep | head -4 | cut -c1-180
