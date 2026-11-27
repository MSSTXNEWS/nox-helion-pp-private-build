echo "K1: dz_keys3"
python3 - <<'P'
import json,urllib.request,urllib.error
def get(u):
    try:
        r=urllib.request.urlopen('http://127.0.0.1:18091'+u,timeout=15); return r.status,json.load(r)
    except urllib.error.HTTPError as e: return e.code,None
    except Exception as e: return type(e).__name__,None
def keys(o,p='',d=0):
    out=[]
    if isinstance(o,dict):
        for k,v in o.items():
            n=(p+'.'+k) if p else k
            if isinstance(v,dict) and d<2: out+=keys(v,n,d+1)
            else: out.append(n+':'+type(v).__name__)
    elif isinstance(o,list): out.append('LIST'+str(len(o)))
    return out
for u in ('/memory/health','/memory/api','/memory/stats','/api/nox/memory/facts','/api/nox/memory/stats','/api/nox/memory/health','/api/nox/outbox','/api/nox/activity','/api/notifications','/api/nox/self_now','/api/nox/briefs','/glm/v1/nox/stats'):
    c,j=get(u); print(u,c,'KEYS',' '.join(sorted(keys(j))[:30]))
c,j=get('/api/nox/status'); print('status.services',' '.join(sorted((j or {}).get('services',{}).keys())))
P
