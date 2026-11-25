import json,sys,os,urllib.request,concurrent.futures as cf,re,time
D='/workspace/nox/state/mock_qa'; O='/workspace/nox/agent/out'
PAGES='system widgets memory map cinema knowledge projects pdf atlas board qa about integrations'.split()
PR=("Ты строгий UX-ревизор. Снимок интерфейса NOX (тёмная серая тема, данные пустые, это макет). Оцени удобство (юзабилити) 0-10: понятность с первого взгляда, один главный CTA, размер целей >=44px, шрифт >=12px, контраст, пустые состояния, перекрытия плавающих элементов, навигация. "
    "Ответь СТРОГО JSON: {\"U\":число,\"issues\":[до 5 коротких проблем],\"fixes\":[до 5 конкретных правок]}")
def call(tag,pg):
    body={"image_path":f"{D}/{tag}_{pg}.jpg","prompt":PR,"model":"auto","x_nox_allow_image":True}
    rq=urllib.request.Request("http://127.0.0.1:8793/v1/images/critique",json.dumps(body).encode(),{"Content-Type":"application/json"})
    r={"err":"fail"}
    for a in range(5):
        try:
            r=json.loads(urllib.request.urlopen(rq,timeout=180).read())
            if U(r) is not None: return r
            time.sleep(30)
        except urllib.error.HTTPError as e:
            r={"http":e.code,"body":e.read()[:200].decode('utf8','ignore')}
            if e.code in (403,400): return r
            time.sleep(80)
        except Exception as e: time.sleep(30)
    return r
def U(r):
    t=json.dumps(r,ensure_ascii=False); m=re.search(r'\\?"U\\?"\s*:\s*([0-9.]+)',t)
    if m: return float(m.group(1))
    c=r.get('critique') or {}; return c.get('score') if isinstance(c,dict) else None
jobs=[(t,p) for p in PAGES for t in ('before','after')]
out={}
with cf.ThreadPoolExecutor(int(os.environ.get('W','2'))) as ex:
    futs={ex.submit(call,t,p):(t,p) for t,p in jobs}
    for f in cf.as_completed(futs):
        t,p=futs[f]; r=f.result(); out[f"{t}_{p}"]=r
        json.dump(out,open(f"{O}/ux_c_raw.json","w"),ensure_ascii=False)
        with open(f"{O}/ux_c_prog.txt","a") as w: w.write(f"{p} {t} U={U(r)} "+(str(r)[:160] if U(r) is None else '')+"\n")
open(f"{O}/ux_c_prog.txt","a").write("FIN\n")
