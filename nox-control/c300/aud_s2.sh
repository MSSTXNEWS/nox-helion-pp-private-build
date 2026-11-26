echo "C300: aud_s2"
date -u; uptime
P=/workspace/nox/venv/bin/python
cat > /tmp/aud_chat.py <<'PY'
import json,time,urllib.request,sys
base=sys.argv[1]
qs=["Привет! Как ты себя сейчас чувствуешь, коротко?","Сколько будет 17*23? Ответь числом.","Что ты помнишь о нашем последнем разговоре?"]
for i,q in enumerate(qs):
    cid="qa-audit-%d-%d"%(int(time.time()),i)
    body=json.dumps({"conversation_id":cid,"message":q,"mode":"auto"}).encode()
    t0=time.time();first=None;n=0;txt="";ev={}
    try:
        r=urllib.request.urlopen(urllib.request.Request(base+"/api/turn",data=body,headers={"Content-Type":"application/json"}),timeout=90)
        for line in r:
            line=line.strip()
            if not line: continue
            try: o=json.loads(line)
            except Exception: ev['raw']=ev.get('raw',0)+1; continue
            t=o.get("type") or o.get("event") or "?"
            ev[t]=ev.get(t,0)+1
            if t=="meta" and ev[t]==1: print("  meta_t=%.2f keys=%s"%(time.time()-t0,list(o.keys())[:10]))
            d=o.get("delta") or o.get("text") or ""
            if t=="delta" and d:
                if first is None: first=time.time()-t0
                txt+=d
            if t=="done" and not txt: txt=str(o.get("text") or o.get("answer") or "")[:200]
            if t=="error": print("  ERROR",str(o)[:200])
            if time.time()-t0>85: print("  CUT 85s"); break
        print("Q%d status=%s first=%s total=%.2f events=%s len=%d ans=%r"%(i,r.status,None if first is None else round(first,2),time.time()-t0,ev,len(txt),txt[:140]))
    except Exception as e:
        print("Q%d EXC %.2f %r"%(i,time.time()-t0,e)[:300])
PY
for B in http://127.0.0.1:18091 ; do echo "== chat via $B"; timeout 270 $P /tmp/aud_chat.py $B; done
echo "== web pages"
for p in index chat-dc chat writer studio system memory settings training photo calendar; do
  curl -s -m 10 -o /tmp/aud_p.html -w "$p http=%{http_code} size=%{size_download} t=%{time_total} " http://127.0.0.1:18091/web/$p.html
  echo "select=$(grep -o -i '<select' /tmp/aud_p.html | wc -l) scripts=$(grep -o -i '<script' /tmp/aud_p.html | wc -l) fake=$(grep -o -i -E 'ONLINE|LIVE|[0-9]{2}%' /tmp/aud_p.html | wc -l) hold=$(grep -o -i 'HOLD' /tmp/aud_p.html | wc -l)"
done
echo "== web server turn log tail (timings only)"
ls -t /workspace/nox/agent/out/*web*chat* /workspace/nox/logs/*web* 2>/dev/null | head -3
for f in $(ls -t /workspace/nox/agent/out/*web_chat*.log /workspace/nox/agent/out/*turn*.log 2>/dev/null | head -2); do echo "-- $f"; grep -a -o -E "(ttft|first|elapsed|took|latency|timeout)[^,;]{0,40}" $f | tail -15; done
echo END
