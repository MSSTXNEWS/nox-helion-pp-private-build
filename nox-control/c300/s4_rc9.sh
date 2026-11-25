echo S4RUN:s4_rc9
S=/workspace/nox/web/site
ls $S/vendor/paper-design-shaders $S/vendor/tone $S/vendor/nox-x/tone $S/vendor/3d-force-graph 2>&1 | head -30
grep -n "initChart\|echarts" $S/nox-brain-x.js | head -12 | cut -c1-200
grep -n "async function feel" -A22 $S/nox-brain-x.js | cut -c1-260 | head -34
curl -s -m6 127.0.0.1:8091/api/nox/status | head -c 900; echo
ls $S/data | head; python3 - <<'P'
import re
t=open('/workspace/nox/web/site/vendor/paper-design-shaders/'+__import__('os').listdir('/workspace/nox/web/site/vendor/paper-design-shaders')[0]).read() if False else ''
P
