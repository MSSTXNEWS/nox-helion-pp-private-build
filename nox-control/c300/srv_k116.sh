echo "C300: srv_k116"
cd /workspace/nox
python3 - <<'PY'
import json,base64,urllib.request,glob,os
p=sorted(glob.glob("/workspace/nox/state/advisor_images/flux_*.png"),key=os.path.getmtime)[-1]; print(p, os.path.getsize(p))
b=base64.b64encode(open(p,"rb").read()).decode()
for port in (8104,):
    try:
        d=json.dumps({"model":"x","max_tokens":60,"messages":[{"role":"user","content":[{"type":"image_url","image_url":{"url":"data:image/png;base64,"+b}},{"type":"text","text":"Is there a cat in this image? Is it in space? Answer YES or NO then one short phrase."}]}]}).encode()
        r=json.loads(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:%d/v1/chat/completions"%port,data=d,headers={"Content-Type":"application/json"}),timeout=100).read())
        print(port, r["choices"][0]["message"].get("content","")[:200])
    except Exception as e: print(port,"ERR",repr(e)[:200])
PY
tail -n 4 ops/dpo/run5.log | cut -c1-160
