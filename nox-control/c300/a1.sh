set -u
S=/workspace/nox/web/site; P=/workspace/nox/web/pkg/server
RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/assets
T=$(date +%s)
for f in nox-dock-pop.js nox-dock-pop.css nox-ninja.js nox-svc-embed.js; do curl -fsSL "$RAW/$f?t=$T" -o $S/$f && echo got $f; done
curl -fsSL "$RAW/svc_proxy.py?t=$T" -o $P/svc_proxy.py && echo got svc_proxy
[ -f $P/svc_registry.json ] || echo '{}' > $P/svc_registry.json
# ninja-keys
mkdir -p $S/vendor/ninja-keys /tmp/nk && cd /tmp/nk && rm -rf package
URL=$(curl -s https://registry.npmjs.org/ninja-keys/latest | python3 -c "import json,sys;print(json.load(sys.stdin)['dist']['tarball'])")
curl -fsSL "$URL" | tar xz && ls package package/bundle 2>/dev/null | head -20
F=$(ls package/bundle/ninja-keys.min.js package/bundle/*.js 2>/dev/null | head -1); echo bundle=$F
[ -n "$F" ] && cp "$F" $S/vendor/ninja-keys/ninja-keys.js && cp package/LICENSE $S/vendor/ninja-keys/LICENSE 2>/dev/null; ls -la $S/vendor/ninja-keys
head -c 300 $S/vendor/ninja-keys/ninja-keys.js; echo
# patch web_server.py
cd $P; [ -f web_server.py.bak_svc_20261124 ] || cp web_server.py web_server.py.bak_svc_20261124
python3 - <<'PY'
p='/workspace/nox/web/pkg/server/web_server.py'; s=open(p,encoding='utf-8').read()
if 'svc_proxy' not in s:
    s=s.replace('    def do_GET(self):\n        if __import__("creative_proxy").handle(self, "GET"): return','    def do_GET(self):\n        if __import__("svc_proxy").handle(self, "GET"): return\n        if __import__("creative_proxy").handle(self, "GET"): return',1)
    s=s.replace('    def do_POST(self):\n        if __import__("creative_proxy").handle(self, "POST"): return','    def do_POST(self):\n        if __import__("svc_proxy").handle(self, "POST"): return\n        if __import__("creative_proxy").handle(self, "POST"): return',1)
    s=s.replace('    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()','    __import__("svc_proxy").install(H)\n    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()',1)
    open(p,'w',encoding='utf-8').write(s)
print('patched', s.count('svc_proxy'))
PY
python3 -c "import ast;ast.parse(open('$P/web_server.py').read())" && echo syntax-ok
# html tags
cd $S; n=0
for f in *.html; do
  grep -q 'nox-dock-pop.js' "$f" || { sed -i 's#</body>#<script src="./nox-dock-pop.js" defer></script>\n<script type="module" src="./nox-ninja.js"></script>\n</body>#' "$f"; n=$((n+1)); }
done; echo tagged $n
grep -c "nox-dock-pop" index.html downloads.html
for pg in cinema music board dispatcher memory downloads studio; do grep -q nox-svc-embed $pg.html || sed -i 's#</body>#<script src="./nox-svc-embed.js" defer></script>\n</body>#' $pg.html; done
/workspace/nox/web/pkg/server/run_web.sh restart 2>&1 | tail -2; sleep 4
curl -s localhost:8091/svc/_status; echo; curl -s -o /dev/null -w "%{http_code}\n" localhost:8091/web/nox-dock-pop.js
curl -s -o /dev/null -w "%{http_code}\n" localhost:8091/api/chat/health
