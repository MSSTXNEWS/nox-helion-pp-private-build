echo "C300: k2_p1"
N=/workspace/nox; D=$N/ops/draw
cp -n $D/invoke_draw.py $D/invoke_draw.py.bak_k2
cat > $D/safety_worker.py <<'P'
"""k2: постоянный воркер проверки безопасности (те же модели/правила, что safety_check.py), читает пути со stdin, печатает JSON-строку на путь."""
import sys, json, os
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
D = "/workspace/nox/models/flux"
import torch; torch.set_num_threads(2)
from transformers import pipeline
from PIL import Image
def mk(dev):
    return (pipeline("image-classification", model=D + "/nsfw_image_detection", device=dev),
            pipeline("image-classification", model=D + "/vit-age-classifier", device=dev))
try:
    n, a = mk(0 if torch.cuda.is_available() else -1)
except Exception:
    n, a = mk(-1)
print("READY", flush=True)
for line in sys.stdin:
    p = line.strip()
    try:
        im = Image.open(p).convert("RGB")
        nsfw = {x["label"].lower(): x["score"] for x in n(im)}.get("nsfw", 0.0)
        ages = {x["label"]: round(x["score"], 3) for x in a(im, top_k=8)}
        minor = sum(v for k, v in ages.items() if k in ("0-2", "3-9", "10-19"))
        block = nsfw > 0.5 and minor > 0.30
        print(json.dumps({"nsfw": round(nsfw, 3), "minor_p": round(minor, 3), "ages": ages, "block": block, "why": "NSFW и признаки несовершеннолетнего" if block else ""}), flush=True)
    except Exception as e:
        print(json.dumps({"error": "%s: %s" % (type(e).__name__, str(e)[:150]), "block": False}), flush=True)
P
python3 - <<'P'
f="/workspace/nox/ops/draw/invoke_draw.py"; s=open(f).read(); n=0
def rep(a,b):
    global s,n
    if a in s: s=s.replace(a,b,1); n+=1
    else: print("MISSING:",a[:60])
rep('["taskset", "-c", "4-7,20-23", SD_BIN,','[SD_BIN,')
rep('"-W", "1024", "-H", "1024", "--seed"','"-W", "768", "-H", "768", "--seed"')
rep('"--backend", "te=cpu", "-t", "6", "-o", out]','"-t", "8", "-o", out] + _te_args()')
rep('def _flux(prompt, cancelled):','''def _te_args():
    """k2: при свободных >=15 ГБ VRAM T5 на GPU (быстро), иначе T5 на CPU (экономия VRAM, как раньше)."""
    try:
        u, t = [int(x) for x in subprocess.check_output(["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"], timeout=10).decode().split(",")]
        if (t - u) >= 15000: return []
    except Exception:
        pass
    return ["--backend", "te=cpu"]


def _flux(prompt, cancelled):''')
rep('TRANSLATORS = ("http://127.0.0.1:8141/v1/chat/completions", "http://127.0.0.1:8142/v1/chat/completions", "http://127.0.0.1:8104/v1/chat/completions")',
    'TRANSLATORS = ("http://127.0.0.1:8104/v1/chat/completions", "http://127.0.0.1:8811/v1/chat/completions", "http://127.0.0.1:8141/v1/chat/completions", "http://127.0.0.1:8142/v1/chat/completions")')
rep('st, d = _post(u, dict(body, model="x"), 70)','st, d = _post(u, dict(body, model="x", **({"id_slot": 3} if ":8104" in u else {})), 70)')
rep('''    try:
        r = subprocess.run([PY, "-I", SAFETY, path], capture_output=True, timeout=120)
        res = json.loads(r.stdout.decode().strip().splitlines()[-1])
    except Exception as e:
        res = {"error": str(e)[:100]}''','''    res = _safety_fast(path)''')
rep('def _safety_after(path):','''_SW = [None]; _SWL = threading.Lock()
SW_PATH = "/workspace/nox/ops/draw/safety_worker.py"


def _sw_get():
    import select
    p = _SW[0]
    if p and p.poll() is None: return p
    p = subprocess.Popen([PY, "-I", SW_PATH], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
    if not select.select([p.stdout], [], [], 120)[0] or "READY" not in p.stdout.readline():
        p.kill(); raise RuntimeError("safety worker not ready")
    _SW[0] = p
    return p


def _safety_fast(path):
    """k2: постоянный воркер (модели в памяти); при любой ошибке — прежний запуск safety_check.py."""
    import select
    try:
        with _SWL:
            p = _sw_get()
            p.stdin.write(path + "\\n"); p.stdin.flush()
            if not select.select([p.stdout], [], [], 60)[0]: p.kill(); raise RuntimeError("timeout")
            return json.loads(p.stdout.readline())
    except Exception:
        try:
            r = subprocess.run([PY, "-I", SAFETY, path], capture_output=True, timeout=120)
            return json.loads(r.stdout.decode().strip().splitlines()[-1])
        except Exception as e:
            return {"error": str(e)[:100]}


if "nox_core" in " ".join(sys.argv[:1]) if False else os.path.basename(sys.argv[0] if sys.argv else "") == "nox_core.py":
    threading.Thread(target=lambda: _safe(_sw_get), daemon=True).start()


def _safety_after(path):''')
s=s.replace("import json, os, re, time, base64, random, threading, subprocess, urllib.parse, urllib.request","import json, os, re, sys, time, base64, random, threading, subprocess, urllib.parse, urllib.request",1)
open(f,"w").write(s); print("applied",n)
P
$N/venv/bin/python -c "import py_compile;py_compile.compile('$D/invoke_draw.py',doraise=True);print('compile ok')"
grep -n "invoke_draw" $N/brain/BRAIN/nox_core.py | head -5 | cut -c1-200
echo "--- standalone timing x2"
cd $D && cat > /tmp/k2_ld.py <<'P'
import sys,time; sys.path.insert(0,"/workspace/nox/ops/draw")
import invoke_draw as I
for i in range(2):
    t=time.time()
    try: r=I.local_generate("кот",None,False); print(i,"OK",r.get("source"),r.get("seconds"),"wall",round(time.time()-t,1),r.get("prompt_en"))
    except Exception as e: print(i,"ERR",str(e)[:200],round(time.time()-t,1))
P
NOX_DRAW_FORCE=1 timeout 280 $N/venv/bin/python /tmp/k2_ld.py 2>&1 | tail -5 | cut -c1-250
uptime; tail -3 $N/state/k2_restart.log
