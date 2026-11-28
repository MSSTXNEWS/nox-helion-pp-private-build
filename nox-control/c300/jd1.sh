echo "K1: jd1"
python3 - <<'PY'
import json,time,urllib.request
for i,(q,a) in enumerate([("Сколько будет 2+2?","4."),("Почему небо голубое?","Из-за рэлеевского рассеяния: короткие синие волны рассеиваются в атмосфере сильнее красных, поэтому небо кажется голубым."),("Как дела?","Привет, Создатель! Всё отлично. Чем могу помочь?")]):
    t0=time.time()
    try:
        r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8300/judge",json.dumps({"text":a,"context":q,"source":None,"role":"answer","fast":True}).encode(),{"Content-Type":"application/json","X-NOX-Priority":"chat"}),timeout=60)
        o=json.loads(r.read()); print("JUDGE sec=%.2f keys=%s p=%s"%(time.time()-t0,sorted(o.keys())[:8],o.get("p_good",o.get("p",(o.get("agg") or {}).get("p_good") if isinstance(o.get("agg"),dict) else o.get("agg")))))
    except Exception as e: print("JUDGE err",type(e).__name__,round(time.time()-t0,2))
PY
echo END
