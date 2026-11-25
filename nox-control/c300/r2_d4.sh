cd /workspace/nox
python3 - <<'P'
f='/workspace/nox/r2_reg.py'; s=open(f).read()
s=s.replace("def aiLink(p):","""import collections
_cnt=collections.Counter()
for _p in pages:
    try: _t=open(f"{S}/{_p}.html",encoding='utf-8',errors='replace').read()
    except Exception: continue
    for _m in set(re.findall(r'<script[^>]+src=[\\"\\']([^\\"\\'?#]+)',_t)): _cnt[_m]+=1
SHARED={m for m,c in _cnt.items() if c>=len(pages)*0.4}
def aiLink(p):""",1)
s=s.replace("if m.startswith(('http','//')): continue","if m.startswith(('http','//')) or m in SHARED: continue")
s=s.replace("return ('да: '+' '.join(h)) if h else 'нет'","return ('да: '+' '.join(h)) if h else 'нет (только общая шапка)'")
open(f,'w').write(s)
P
python3 r2_reg.py; grep -o "^| [a-z-]* |.*" web/site/qa/registry.md | awk -F'|' '{print $2,$9}' | head -40
echo SHARED; tail -3 /tmp/r2_audit.log | cut -c1-200
