import json,sys,os,urllib.request,concurrent.futures as cf,re,time
D='/workspace/nox/state/mock_qa'; O='/workspace/nox/agent/out'
TAG=sys.argv[1]; FILES=sys.argv[2:]
PR=("Ты строгий UI/UX-ревизор. Снимок страницы NOX HELION (тёмная серая тема «Графит», демо-макет без живых данных). Оцени 0-10: A (эстетика, аккуратность, сетка, анимация/ощущение движения), R (читаемость: шрифт, контраст), U (удобство: один заметный главный CTA, цели >=44px, индикаторы загрузки, информативные пустые состояния, элементы не перекрывают шапку и низ), WOW (впечатление, сравни с Linear/Vercel/ChatGPT). "
    "Ответь СТРОГО JSON: {\"A\":число,\"R\":число,\"U\":число,\"WOW\":число,\"issues\":[до 5 коротких проблем],\"fixes\":[до 5 конкретных правок]}")
def sc(r):
    t=json.dumps(r,ensure_ascii=False); o={}
    for k in('A','R','U','WOW'):
        m=re.search(r'\\?"%s\\?"\s*:\s*([0-9.]+)'%k,t); o[k]=float(m.group(1)) if m else None
    return o
def call(f):
    body={"image_path":f"{D}/{f}","prompt":PR,"model":"auto","x_nox_allow_image":True}
    rq=urllib.request.Request("http://127.0.0.1:8793/v1/images/critique",json.dumps(body).encode(),{"Content-Type":"application/json"})
    r={"err":"fail"}
    for a in range(6):
        try:
            r=json.loads(urllib.request.urlopen(rq,timeout=180).read())
            if sc(r)['U'] is not None: return r
            time.sleep(25)
        except urllib.error.HTTPError as e:
            r={"http":e.code,"body":e.read()[:200].decode('utf8','ignore')}
            if e.code in (403,400): return r
            time.sleep(60 if e.code==429 else 30)
        except Exception as e: time.sleep(30)
    return r
out={}
with cf.ThreadPoolExecutor(2) as ex:
    futs={ex.submit(call,f):f for f in FILES}
    for fu in cf.as_completed(futs):
        f=futs[fu]; r=fu.result(); out[f]=r
        s=sc(r); txt=json.dumps(r,ensure_ascii=False)
        m=re.search(r'"issues"\s*:\s*\[.*?\]\s*,\s*"fixes"\s*:\s*\[.*?\]',txt.replace('\\"','"'))
        with open(f"{O}/ui_{TAG}_prog.txt","a") as w: w.write(f"{f} {s} "+(m.group(0)[:900] if m else txt[:300])+"\n")
open(f"{O}/ui_{TAG}_prog.txt","a").write("FIN\n")
