echo S4RUN:s4_kb2
cd /workspace/nox/web/site; curl -fsSL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/s4_src/nox-s4-svc.js?t=$(date +%s)" -o nox-s4-svc.js; grep -c H nox-s4-svc.js
