S=/workspace/nox/web/site; RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/assets; T=$(date +%s)
for f in nox-svc-embed.js nox-ninja.js; do curl -fsSL "$RAW/$f?t=$T" -o $S/$f; done
grep -c MutationObserver $S/nox-svc-embed.js
grep -v "^\s*$" /workspace/nox/invoke_install.log | grep -v "^+" | tail -12 | cut -c1-200
