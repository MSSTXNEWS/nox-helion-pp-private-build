echo "C300: ui_ix1"
Fz=/workspace/nox/web/v29src/V29_3_FROZEN/site; S=/workspace/nox/web/site
/workspace/nox/venv/bin/python - <<'P'
import re,os,hashlib
Fz='/workspace/nox/web/v29src/V29_3_FROZEN/site'; S='/workspace/nox/web/site'
h=lambda p:hashlib.md5(open(p,'rb').read()).hexdigest()
seen=set(); q=['index.html']; rep=[]
while q:
    f=q.pop(0)
    if f in seen: continue
    seen.add(f); p=os.path.join(Fz,f)
    if not os.path.isfile(p): rep.append(('NOFROZEN',f)); continue
    st='MISSING' if not os.path.exists(os.path.join(S,f)) else ('SAME' if h(p)==h(os.path.join(S,f)) else 'DIFF')
    rep.append((st,f))
    if f.endswith(('.html','.js','.mjs','.css')):
        t=open(p,errors='ignore').read()
        for m in re.findall(r'''(?:src|href|from|import\()\s*=?\s*["']((?:\./|\.\./)?[A-Za-z0-9_\-./]+\.(?:js|mjs|css|json))["']''',t)+re.findall(r'''@import\s+(?:url\()?["']?([A-Za-z0-9_\-./]+\.css)''',t):
            n=os.path.normpath(os.path.join(os.path.dirname(f),m)); 
            if not n.startswith('..') and n not in seen: q.append(n)
    if len(seen)>400: break
import collections
print(collections.Counter(r[0] for r in rep))
for r in rep:
    if r[0]!='SAME': print(*r)
P
echo "== index head"; head -c 1800 $Fz/index.html | tr -s '\n ' ' '
echo; echo "== current index head"; head -c 900 $S/index.html | tr -s '\n ' ' '
