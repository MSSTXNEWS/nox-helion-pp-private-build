echo "K1: dz_keys2"
python3 - <<'P'
import json,urllib.request
def get(u):
    try: return json.load(urllib.request.urlopen('http://127.0.0.1:18091'+u,timeout=15))
    except Exception as e: return {'__err':type(e).__name__+str(getattr(e,'code',''))}
def keys(o,p='',d=0):
    out=[]
    if isinstance(o,dict):
        for k,v in o.items():
            n=(p+'.'+k) if p else k
            if isinstance(v,dict) and d<2: out+=keys(v,n,d+1)
            else: out.append(n+':'+type(v).__name__)
    elif isinstance(o,list): out.append('LIST'+str(len(o)))
    return out
for u in ('/api/nox/training/status','/api/training/status','/api/nox/progress','/api/pc-metrics','/api/chat/health','/glm/props','/memory/health','/api/nox/agents'):
    j=get(u); print(u,'KEYS',' '.join(sorted(keys(j))[:45]))
P
