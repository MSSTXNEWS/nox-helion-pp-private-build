echo "C300: srv_k87"
cd /workspace/nox/ops/draw; /workspace/nox/venv/bin/python -I - <<'PY'
import sys,json,time,base64,urllib.request
sys.path.insert(0,'.'); import invoke_draw as D
t0=time.time(); dr=D.draw_request("нарисуй кота в космосе")
try:
    r=D.local_generate(dr[1] if dr else "кот в космосе", photographic=False); print("draw",r.get("source"),r.get("seconds"),r.get("path"))
    b=base64.b64encode(open(r["path"],"rb").read()).decode()
    body={"model":"x","max_tokens":60,"temperature":0,"chat_template_kwargs":{"enable_thinking":False},"messages":[{"role":"user","content":[{"type":"image_url","image_url":{"url":"data:image/jpeg;base64,"+b}},{"type":"text","text":"Does this image clearly show a cat in outer space? Answer YES or NO first, then one short sentence."}]}]}
    v=json.load(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8104/v1/chat/completions",data=json.dumps(body).encode(),headers={"Content-Type":"application/json"}),timeout=200))["choices"][0]["message"]["content"]; print("vision",v[:120])
except Exception as e: print("draw err",repr(e)[:200], "%.0f c"%(time.time()-t0))
PY
