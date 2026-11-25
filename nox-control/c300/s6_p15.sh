echo S4RUN:s6_p15
cd /workspace/nox/web/site
grep -n "cvStyle" nox-s2-music.js | head -3 | cut -c1-80
python3 - <<'PY'
import re
t=open('nox-s2-music.js').read()
i=t.find('cvStyle'); 
for m in re.finditer(r'cvStyle',t):
    s=t[max(0,m.start()-30):m.start()+220]
    if 'function' in s[:60] or '=' in s[20:60]: print(repr(s)); break
PY
