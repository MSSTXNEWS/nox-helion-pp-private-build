S=/workspace/nox/web/site
cd $S
[ -f x.txt ] && cp -p x.txt x.txt.bak_s1_$(date +%H%M%S)
base64 -d > x.txt <<'S1EOF'
eAo=
S1EOF
echo OK x.txt $(wc -c <x.txt)
ps -o args= -p $(pgrep -f "code-server --bind\|svc/code-server --bind" | head -1) | tr " " "\n" | grep -A1 user-data; ls /workspace/nox/svc/*/User/settings.json /workspace/**/User/settings.json 2>/dev/null; cat /workspace/nox/web/site/qa/rework/finance.fixed | tail -5
