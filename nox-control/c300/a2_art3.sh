echo "C300: a2_art3"
python3 - <<'P'
import json,time,urllib.request,glob,os
OUT='/workspace/nox/state/advisors_external.json'
def get(u): return json.loads(urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'nox-advisors/1.0'}),timeout=30).read())
d=get('https://ai-gateway.kilo.ai/api/v1/models'); d=d if isinstance(d,list) else d.get('data',[])
vis=[m['id'] for m in d if str(m['id']).endswith(':free') and 'image' in json.dumps((m.get('architecture') or {}).get('input_modalities',''))]
print('KILO vision free',vis)
def post(path,body):
    rq=urllib.request.Request('http://127.0.0.1:8793/v1'+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    try: return json.loads(urllib.request.urlopen(rq,timeout=100).read())
    except urllib.error.HTTPError as e: return {'http':e.code,'e':e.read().decode()[:150]}
    except Exception as e: return {'e':str(e)[:150]}
IMG=sorted(glob.glob('/workspace/nox/state/advisor_images/*.*'),key=os.path.getmtime)[0]
reg=json.load(open(OUT))
for a in reg['advisors']:
    if a['id']=='art_critic_nvidia_nemotron-3.5-super-vl_free': a.update(status='weak',error='empty content (reasoning eats tokens)')
n=0
for m in vis:
    if 'omni-30b' in m or 'super-vl' in m or n>=3: continue
    n+=1; t=time.time(); r=post('/images/critique',{'image_path':IMG,'prompt':'Котёнок на подоконнике, закат, акварель','model':'kilo/'+m}); ms=int((time.time()-t)*1000); tx=r.get('text') or ''
    print('CRIT',m,ms,tx[:200].replace('\n',' ') or r)
    e={'id':'art_critic_'+m.replace('/','_').replace(':','_'),'role':'drawing_senior_critic','provider':'kilo','model':m,'title':m+' (kilo free)','strengths':'vision: композиция, анатомия, свет, соответствие промпту','limits':'150 запросов/ч на IP (шлюз)','status':'ok' if tx else 'fail','latency_ms':ms,'needs_key':False,'call':'POST :8793/v1/images/critique {image_path,prompt,model}','sample':tx[:300]}
    reg['advisors']=[a for a in reg['advisors'] if a['id']!=e['id']]+[e]
    r_=reg.setdefault('roles',{}).setdefault('drawing_senior_critic',[])
    if e['id'] not in r_: r_.append(e['id'])
json.dump(reg,open(OUT,'w'),ensure_ascii=False,indent=1)
print('OK ids',[a['id'] for a in reg['advisors'] if a.get('role') and a['status']=='ok'])
P
