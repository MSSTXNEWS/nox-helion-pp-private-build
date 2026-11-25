cd /workspace/nox/web/site/vendor
grep -n "^export" nox-liquid-glass/liquid-glass.js | cut -c1-200
sed -n '/Attach to an existing/,/^}/p' nox-liquid-glass/liquid-glass.js | head -40 | cut -c1-220
cat nox-liquid-glass/NOX-INTEGRATION.txt
ls nox-x/vad | head; ls three/build | head -5
