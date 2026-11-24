S=/workspace/nox/web/site
echo ==stubscript; sed -n 38,80p $S/advisors.html | cut -c1-400
echo ==media; sed -n 40,56p $S/nox-p-media.js | cut -c1-500
echo ==apiblock; sed -n 182,186p /workspace/nox/web/pkg/server/web_server.py | cut -c1-200
echo ==ver; grep -o "REVISION *= *'[0-9]*'" $S/vendor/three/three.module.js $S/vendor/three/build/three.module.js 2>/dev/null | head -2
curl -s -m5 http://127.0.0.1:4533/rest/ping.view?v=1.16.1\&c=nox\&f=json | head -c 300; echo
curl -s -m5 -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8091/svc/navidrome/ping
grep -n "mars" $S/nox-p-about.js | cut -c1-300 | head -3
# stub list structure sanity
for p in games map mail tv planets resonance g01-status; do echo $p $(grep -c "<header>" $S/$p.html) $(grep -c nox-nav $S/$p.html) $(wc -c <$S/$p.html); done
