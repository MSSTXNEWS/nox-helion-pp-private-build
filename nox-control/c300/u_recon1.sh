echo "C300: u_recon1"
S=/workspace/nox/web/site; cd $S
echo "== index scripts"; grep -o '<script[^>]*src="[^"]*"' index.html | sed 's/<script//' | tr '\n' ' ' | cut -c1-2500; echo
echo "== index bak"; ls -la index.html* | tail -8
echo "== k8 files"; ls -la nox-k8-* | cut -c30-120
echo "== k8 globals"; for f in nox-k8-*.js; do echo "$f: $(grep -o 'window\.[A-Za-z0-9_]*=' $f | sort -u | head -6 | tr '\n' ' ') | const/var: $(grep -oE '^(const|let|var) [A-Za-z0-9_]+' $f | head -5 | tr '\n' ' ')"; done
echo "== gw 8793"; curl -s -m 5 localhost:8793/health | cut -c1-300; curl -s -m 5 localhost:8793/roles | cut -c1-600
echo "== img/vision"; grep -n "img/generate\|vision/describe" web_server.py 2>/dev/null | head; grep -rn "img/generate" --include=*.py /workspace/nox/web 2>/dev/null | head -5
echo "== PORT"; ss -ltn | grep -E ':(8091|8793|80[0-9][0-9])' | head
