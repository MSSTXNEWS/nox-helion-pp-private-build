S=/workspace/nox/web/site
cd $S
ls sw.js* nox-pwa.js manifest.json 2>&1; find . -maxdepth 2 -name 'sw*.js' -not -path './vendor/*' | head
echo ==SW; cat sw.js | head -c 6000
echo ==PWA; cat nox-pwa.js | head -c 2500
echo ==SUBMIT; grep -n "'submit'\|\"submit\"\|onsubmit\|preventDefault" nox-wow.js | cut -c1-200 | head
grep -n "sw.js\|Service-Worker" /workspace/nox/web/pkg/server/web_server.py | head
