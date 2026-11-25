echo "C300: a2_art2"
python3 - <<'P'
import json,time,urllib.request,base64,glob,os
OUT='/workspace/nox/state/advisors_external.json'
def post(path,body):
    rq=urllib.request.Request('http://127.0.0.1:8793/v1'+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    try: return json.loads(urllib.request.urlopen(rq,timeout=150).read())
    except urllib.error.HTTPError as e: return {'http':e.code,'e':e.read().decode()[:200]}
    except Exception as e: return {'e':str(e)[:150]}
IMG=sorted(glob.glob('/workspace/nox/state/advisor_images/*.*'),key=os.path.getmtime)[0]
for m in ['kilo/nvidia/nemotron-3.5-super-vl:free','kilo/kilo-auto/free']:
    t=time.time(); r=post('/images/critique',{'image_path':IMG,'prompt':'Котёнок на подоконнике, закат, акварель','model':m})
    ms=int((time.time()-t)*1000); tx=r.get('text') or ''
    print('CRIT',m,ms,r.get('model'),(tx or str(r))[:250].replace('\n',' '))
    if tx and 'super-vl' in m:
        d=json.load(open(OUT))
        for a in d['advisors']:
            if a['id']=='art_critic_nvidia_nemotron-3.5-super-vl_free': a.update(status='ok',latency_ms=ms,sample=tx[:300],error=None)
        json.dump(d,open(OUT,'w'),ensure_ascii=False,indent=1)
print('PRIV owner img',post('/images/critique',{'image_b64':base64.b64encode(b'x'*3000).decode(),'prompt':'x'}))
print('PRIV path',post('/images/critique',{'image_path':'/etc/passwd','prompt':'x'}))
P
