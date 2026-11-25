echo "C300: v_art_2"
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300; A=/workspace/nox/advisors
curl -fsSL "$R/v_gw_gateway.py?$(date +%s)" -o $A/gateway.py.new && mv $A/gateway.py.new $A/gateway.py
pkill -f advisors/gateway.py; sleep 1
setsid nohup python3 $A/gateway.py >/workspace/nox/svc/logs/advisors.log 2>&1 </dev/null &
sleep 3
IMG=$(ls -t /workspace/nox/state/advisor_images/*.* | head -1); echo img $IMG
python3 - <<P
import json,time,urllib.request,base64
def post(path,body):
    rq=urllib.request.Request('http://127.0.0.1:8793/v1'+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    try: return json.loads(urllib.request.urlopen(rq,timeout=200).read())
    except urllib.error.HTTPError as e: return {'http':e.code,'e':e.read().decode()[:200]}
t=time.time(); r=post('/images/critique',{'image_path':'$IMG','prompt':'Котёнок на подоконнике, закат, акварель','model':'kilo/nvidia/nemotron-3.5-super-vl:free'})
ms=int((time.time()-t)*1000); print('SUPERVL',ms,r.get('model'),str((r.get('critique') or r.get('text') or r))[:300].replace('\n',' '))
if r.get('text'):
    d=json.load(open('/workspace/nox/state/advisors_external.json'))
    for a in d['advisors']:
        if a['id']=='art_critic_nemotron-3.5-super-vl_free': a.update(status='ok',latency_ms=ms,sample=r['text'][:300])
    json.dump(d,open('/workspace/nox/state/advisors_external.json','w'),ensure_ascii=False,indent=1)
print('PRIV owner image', post('/images/critique',{'image_b64':base64.b64encode(b'x'*3000).decode(),'prompt':'x'}))
print('PRIV path', post('/images/critique',{'image_path':'/etc/passwd','prompt':'x'}))
P
echo END
