S=/workspace/nox/web/site
cd $S
[ -f x.txt ] && cp -p x.txt x.txt.bak_s1_$(date +%H%M%S)
base64 -d > x.txt <<'S1EOF'
eAo=
S1EOF
echo OK x.txt $(wc -c <x.txt)
for d in /workspace/nox/nox-control /workspace/nox-control /workspace/nox/web/nox-control; do ls -la $d/c300/LIVING_UI.md 2>&1; done
f=$(find /workspace -name LIVING_UI.md 2>/dev/null | head -1); echo "FOUND $f"; [ -n "$f" ] && head -c 6000 "$f"
