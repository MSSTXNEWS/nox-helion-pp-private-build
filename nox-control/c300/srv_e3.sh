#!/bin/bash
D=/workspace/nox/canon_night; F=$D/embed_server.py
cat > /tmp/emb_t.py <<'PY'
import json,time,urllib.request
def t(n):
    body=json.dumps({"texts":["Сколько весит слон и почему небо голубое, расскажи подробно про рассеяние Рэлея. "*8]*n}).encode()
    s=time.time(); r=json.load(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8082/embed",data=body,headers={"Content-Type":"application/json"}),timeout=120)); return round(time.time()-s,2),r["dim"],r["vectors"][0][:2]
print("1 text",t(1)); print("16 texts",t(16))
print(urllib.request.urlopen("http://127.0.0.1:8082/health").read().decode()[:150])
PY
echo BEFORE; python3 /tmp/emb_t.py
cp -n $F $F.bak_srv_gpu
python3 -I - <<'PY'
F="/workspace/nox/canon_night/embed_server.py"; s=open(F,encoding="utf-8").read()
if "EMB_GPU_P3" in s: print("already"); raise SystemExit
s=s.replace('os.environ["CUDA_VISIBLE_DEVICES"] = ""','DEV = os.environ.get("NOX_EMBED_DEVICE", "cuda")   # EMB_GPU_P3: bge-m3 fp16 на GPU (1.2 ГБ), освобождает ~4 ядра CPU; откат: NOX_EMBED_DEVICE=cpu\nos.environ["CUDA_VISIBLE_DEVICES"] = "0" if DEV == "cuda" else ""',1)
s=s.replace('''    _model = AutoModel.from_pretrained(MODEL_PATH, torch_dtype=torch.float32).to("cpu").eval()''','''    global DEV
    if DEV == "cuda" and not torch.cuda.is_available(): DEV = "cpu"
    _model = AutoModel.from_pretrained(MODEL_PATH, torch_dtype=torch.float16 if DEV == "cuda" else torch.float32).to(DEV).eval()''',1)
s=s.replace('''        enc = _tok(texts, padding=True, truncation=True, max_length=512, return_tensors="pt")''','''        enc = _tok(texts, padding=True, truncation=True, max_length=512, return_tensors="pt").to(DEV)''',1)
s=s.replace('"device": "cpu"','"device": DEV',1)
s=s.replace("vec = torch.nn.functional.normalize(vec, p=2, dim=1)","vec = torch.nn.functional.normalize(vec.float(), p=2, dim=1)",1)
open(F,"w",encoding="utf-8").write(s); import py_compile; py_compile.compile(F,doraise=True); print("patched")
PY
OLD=$(cat $D/embed.pid 2>/dev/null); [ -z "$OLD" ] && OLD=$(pgrep -f canon_night/embed_server.py | head -1)
kill $OLD; sleep 2; pgrep -f canon_night/embed_server.py && kill -9 $(pgrep -f canon_night/embed_server.py)
setsid -f bash $D/run_embed.sh > /tmp/run_embed.out 2>&1 < /dev/null
for i in $(seq 1 30); do sleep 4; curl -fs -m2 127.0.0.1:8082/health >/dev/null 2>&1 && break; done
cat /tmp/run_embed.out; echo AFTER; python3 /tmp/emb_t.py; python3 /tmp/emb_t.py | head -2
nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader | head -8; top -b -n1 | grep -E "embed|python" | head -3 | cut -c1-90
