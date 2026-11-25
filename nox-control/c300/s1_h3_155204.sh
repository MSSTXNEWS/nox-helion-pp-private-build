S=/workspace/nox/web/site
cd $S
[ -f x.txt ] && cp -p x.txt x.txt.bak_s1_$(date +%H%M%S)
base64 -d > x.txt <<'S1EOF'
eAo=
S1EOF
echo OK x.txt $(wc -c <x.txt)
cd /workspace/nox/web/site
grep -o 'class="[^"]*"' index.html | sort | uniq -c | sort -rn | head -12
grep -o 'class="[^"]*"' system.html | sort | uniq -c | sort -rn | head -8
grep -o 'grid-stack-item-content\|class="tile[^"]*"\|class="tl[^"]*"' nox-home-gs.js | sort | uniq -c | head
