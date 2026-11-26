echo "C300: srv_k117"
cd /workspace/nox
D=models/gpu/bartowski/mistralai_Mistral-Small-3.2-24B-Instruct-2506-GGUF
lsof +D $D 2>/dev/null | awk 'NR>1{print $1,$2,$9}' | sort -u | head -5; echo "--grep"
grep -n "$(basename $D)\|Mistral-Small" serve/llama-swap.yaml state/orch_registry.json stewards/orch_registry.json 2>/dev/null | cut -c1-200 | head -5
wc -l ops/teacher_answers/*.jsonl
python3 - <<'PY'
import json,base64,urllib.request,glob,os
p=sorted(glob.glob("/workspace/nox/state/advisor_images/flux_*.png"),key=os.path.getmtime)[-1]
b=base64.b64encode(open(p,"rb").read()).decode()
d=json.dumps({"model":"x","max_tokens":900,"chat_template_kwargs":{"enable_thinking":False},"messages":[{"role":"user","content":[{"type":"image_url","image_url":{"url":"data:image/png;base64,"+b}},{"type":"text","text":"Is there a cat in this image, in space? Answer YES or NO and one short phrase."}]}]}).encode()
try:
    r=json.loads(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8104/v1/chat/completions",data=d,headers={"Content-Type":"application/json"}),timeout=120).read())
    m=r["choices"][0]["message"]; print("content:",repr((m.get("content") or "")[:200]),"| reasoning:",repr((m.get("reasoning_content") or "")[:150]))
except Exception as e: print("ERR",repr(e)[:200])
PY
