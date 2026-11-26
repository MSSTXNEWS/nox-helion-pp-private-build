echo "K1: dz_keys1"
python3 - <<'P'
import json,urllib.request
def get(u):
    try: return json.load(urllib.request.urlopen('http://127.0.0.1:18091'+u,timeout=15))
    except Exception as e: return {'__err':type(e).__name__}
def keys(o,p='',d=0):
    out=[]
    if isinstance(o,dict):
        for k,v in o.items():
            n=(p+'.'+k) if p else k
            if isinstance(v,dict) and d<3: out+=keys(v,n,d+1)
            else: out.append(n+(':'+type(v).__name__))
    return out
for u in ('/api/nox-live','/api/nox/agenda','/api/nox/status'):
    j=get(u); print(u, 'KEYS', ' '.join(sorted(keys(j))[:80]))
P
