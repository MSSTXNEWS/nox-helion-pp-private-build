echo "C300: k2_d3"
N=/workspace/nox
cat > /tmp/k2_draw.py <<'P'
import http.client,json,time,sys
m=sys.argv[1]; t0=time.time(); seen={}
c=http.client.HTTPConnection("127.0.0.1",8091,timeout=200)
c.request("POST","/api/turn",json.dumps({"conversation_id":"qa-k2-draw-%d"%int(t0),"message":m,"nox_user_id":"owner"}),{"Content-Type":"application/json"})
r=c.getresponse(); print("status",r.status); buf=b""
while time.time()-t0<200:
    ch=r.read1(4096)
    if not ch: break
    buf+=ch
    while b"\n" in buf:
        l,buf=buf.split(b"\n",1)
        try: f=json.loads(l)
        except Exception: continue
        k=f.get("t"); s=json.dumps(f,ensure_ascii=False)
        if k=="delta" and seen.get("delta",0)>3: continue
        seen[k]=seen.get(k,0)+1
        print("%.1fs"%(time.time()-t0),s[:300],flush=True)
print("end %.1fs"%(time.time()-t0))
P
timeout 220 python3 /tmp/k2_draw.py "нарисуй кота"
echo "--- vram"; nvidia-smi --query-gpu=memory.used --format=csv,noheader
ls -lat $N/state/advisor_images | head -3 | cut -c20-100
echo "--- restart log"; tail -5 $N/state/k2_restart.log; tail -1 $N/state/k2_dl.log; uptime
