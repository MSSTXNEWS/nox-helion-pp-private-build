#!/bin/bash
N=/workspace/nox; D=$N/ops/draw; T=$(date +%Y%m%d_%H%M%S)
cp -p $D/invoke_draw.py $D/invoke_draw.py.bak_p3_v1_$T
cat > /tmp/invoke_draw_v2.py <<'PYEOF'
"""ops/draw/invoke_draw.py (P3, 2026-11-25): рисование в чате. Контракт: draw_request(text)->None|(locale,prompt); photo_request(text)->bool;
local_generate(prompt, cancelled=None, photographic=False)->dict(url,path,source,seconds); DrawError.
Канал 1: локальный POST :8091/img/generate (sun_adapter :8097 -> imgsvc :8500). Канал 2 (если korea_img_disabled/503/ошибка): шлюз :8793 /v1/images/generations
(pollinations/horde). Только стандартная библиотека. Откат: invoke_draw.py.stub_bak_p3 (заглушка). Выключатель: state/flags.json {"draw_chat": false}."""
import json, os, re, time, base64, random, threading, urllib.parse, urllib.request

LOCAL = os.environ.get("NOX_DRAW_LOCAL", "http://127.0.0.1:8091/img/generate")
GATE = os.environ.get("NOX_DRAW_GATE", "http://127.0.0.1:8793/v1/images/generations")
OUT_DIR = "/workspace/nox/state/advisor_images"
FLAGS = "/workspace/nox/state/flags.json"


class DrawError(Exception):
    pass


_VERB = re.compile(
    r"^\s*(?:пожалуйста[,\s]+|please[,\s]+|por favor[,\s]+|ты\s+(?:мог(?:ла)?\s+бы\s+)?)?"
    r"(?:нарису(?:й|йте)|изобрази|сгенерируй|сгенерируйте|создай|создайте|сделай|сделайте|сформируй|покажи|draw|paint|sketch|generate|create|make|dibuja|dibújame|genera|crea)"
    r"(?:\s+(?:мне\s+|для\s+меня\s+|me\s+)?(.*))?$", re.I | re.S)
_OBJ = re.compile(r"(картинк|изображени|рисун|иллюстраци|фото|фотограф|арт\b|постер|логотип|аватар|портрет|пейзаж|image|picture|photo|drawing|illustration|portrait|logo|imagen|dibujo|foto)", re.I)
_BARE = re.compile(r"^\s*(?:нарису(?:й|йте)|draw|dibuja)\b", re.I)
_PHOTO = re.compile(r"(фото|фотограф|реалистич|photo|photograph|realistic|fotograf|realista)", re.I)
_STRIP = re.compile(r"^(?:на\s+тему\s+|картинк[ауи][:\s]+|изображени[ея][:\s]+|рисунок[:\s]+|фото(?:графию)?[:\s]+|an?\s+(?:image|picture|photo|drawing)\s+of\s+|(?:image|picture|photo|drawing)\s+of\s+|una?\s+(?:imagen|foto|dibujo)\s+de\s+)", re.I)


def _flag_on():
    try:
        return bool(json.load(open(FLAGS, encoding="utf-8")).get("draw_chat", True))
    except Exception:
        return True


def _locale(t):
    if re.search(r"[а-яё]", t, re.I):
        return "ru"
    if re.search(r"[¿¡ñáéíóú]|\b(dibuja|genera|crea|una|un|de|el|la)\b", t, re.I):
        return "es"
    return "en"


def draw_request(text):
    if not text or not _flag_on():
        return None
    t = str(text).strip()
    if len(t) > 1500:
        return None
    m = _VERB.match(t)
    if not m:
        return None
    rest = (m.group(1) or "").strip(" .!?:;,\n")
    # «нарисуй ...» — всегда рисование; «сделай/покажи/создай ...» только если есть слово про изображение
    if not _BARE.match(t) and not _OBJ.search(t):
        return None
    prompt = _STRIP.sub("", rest).strip(" .!?:;,\n")
    return (_locale(t), prompt)


def photo_request(text):
    return bool(text and _PHOTO.search(str(text)))


def _post(url, body, timeout):
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except Exception:
            return e.code, {}


def _url(path):
    return "/img/file?p=" + urllib.parse.quote(path)


def _run(fn, cancelled, limit):
    box = {}
    th = threading.Thread(target=lambda: box.update(r=_safe(fn)), daemon=True)
    th.start(); t0 = time.time()
    while th.is_alive() and time.time() - t0 < limit:
        if cancelled and cancelled():
            raise DrawError("отменено")
        th.join(0.5)
    if "r" not in box:
        raise DrawError("таймаут генерации")
    return box["r"]


def _safe(fn):
    try:
        return fn()
    except Exception as e:
        return (0, {"error": "%s: %s" % (type(e).__name__, str(e)[:120])})


# --- v2 (P3): перевод на английский, пресеты PHOTOREAL100, неотключаемый фильтр запроса, случайный seed ---
TRANSLATORS = ("http://127.0.0.1:8141/v1/chat/completions", "http://127.0.0.1:8142/v1/chat/completions")
_CYR = re.compile(r"[а-яёА-ЯЁ]")
_MINOR = re.compile(r"(ребён|ребен|дет[иейям]|малолет|школьни|школьниц|подрост|несовершеннолет|лолит|\bloli|child|kid\b|minor|underage|teen|toddler|infant|schoolgirl|schoolboy|\bniñ[oa]s?\b|menor)", re.I)
_SEXUAL = re.compile(r"(секс|эрот|обнаж|голая|голый|порн|интим|nsfw|\bsex|nude|naked|erotic|porn|lingerie|fetish|desnud|erótic)", re.I)
_DEEPFAKE = re.compile(r"(дипфейк|deepfake|deep fake|подмени(?:ть)? лицо|face ?swap|лицо (?:реального|настоящего)|как у (?:путина|трампа|зеленск))", re.I)
_ILLEGAL = re.compile(r"(как (?:сделать|изготовить) (?:бомб|взрывчат|наркот)|child abuse|csam|детская порн)", re.I)


def check_prompt(text):
    t = str(text or "")
    if _MINOR.search(t) and _SEXUAL.search(t):
        raise DrawError("запрещено: несовершеннолетние в откровенном контексте")
    if _DEEPFAKE.search(t):
        raise DrawError("запрещено: изображения реальных людей без согласия / дипфейки")
    if _ILLEGAL.search(t):
        raise DrawError("запрещено: незаконное содержание")


def _translate(text):
    if not _CYR.search(text):
        return text
    body = {"messages": [{"role": "system", "content": "Translate the user's image request into a concise English prompt for an image generator. Keep every object, color, place and style. Output only the English prompt, no quotes, no comments."},
                         {"role": "user", "content": text}], "max_tokens": 80, "temperature": 0, "chat_template_kwargs": {"enable_thinking": False}}
    for u in TRANSLATORS:
        try:
            st, d = _post(u, dict(body, model="x"), 40)
            t = ((d.get("choices") or [{}])[0].get("message") or {}).get("content", "").strip().strip('"«»')
            if st == 200 and t and not _CYR.search(t):
                return t.splitlines()[0][:300]
        except Exception:
            continue
    return text


PHOTO_PRE = "RAW photo, "
PHOTO_POST = ", shot on 35mm lens f/1.8, natural soft light, sharp focus, realistic skin texture, fine detail, subtle film grain, no blur, no watermark, no text"
ART_POST = ", highly detailed, vivid colors, sharp focus, professional composition, no watermark, no text"


def build_prompt(prompt, photographic):
    en = _translate(str(prompt).strip())
    return (PHOTO_PRE + en + PHOTO_POST) if photographic else (en + ART_POST), en


def _local(prompt, photographic):
    w = h = 1024
    return _post(LOCAL, {"prompt": prompt, "model": "auto", "width": w, "height": h, "seed": -1}, 240)


def _gate(prompt, photographic):
    return _post(GATE, {"prompt": prompt, "model": "auto", "seed": random.randint(1, 2**31 - 1)}, 200)


def local_generate(prompt, cancelled=None, photographic=False):
    t0 = time.time()
    check_prompt(prompt)
    p, en = build_prompt(prompt, photographic)
    check_prompt(p)
    why = []
    st, d = _run(lambda: _local(p, photographic), cancelled, 250)
    path = (d or {}).get("path")
    if st == 200 and path and os.path.isfile(path) and (d.get("ok", True) is not False):
        return {"status": "ok", "source": "local", "path": path, "url": _url(path), "seconds": round(time.time() - t0, 1)}
    why.append("local:%s:%s" % (st, str((d or {}).get("error") or (d or {}).get("reason") or "")[:60]))
    st, d = _run(lambda: _gate(p, photographic), cancelled, 210)
    if st != 200 or not (((d or {}).get("data") or [{}])[0] if isinstance(d, dict) else {}).get("path"):
        for _ in range(60):   # лимит pollinations: 1 запрос / ~50 с — ждём окно и повторяем один раз
            if cancelled and cancelled():
                raise DrawError("отменено")
            time.sleep(1)
        st, d = _run(lambda: _gate(p, photographic), cancelled, 210)
    x = ((d or {}).get("data") or [{}])[0] if isinstance(d, dict) else {}
    path = x.get("path")
    if not path and x.get("b64_json"):
        os.makedirs(OUT_DIR, exist_ok=True)
        path = "%s/p3_%d.png" % (OUT_DIR, int(time.time() * 1000))
        open(path, "wb").write(base64.b64decode(x["b64_json"]))
    if st == 200 and path and os.path.isfile(path):
        return {"status": "ok", "source": "gate8793", "path": path, "url": _url(path), "seconds": round(time.time() - t0, 1), "local": why[0], "prompt_en": en}
    why.append("gate:%s:%s" % (st, str((d or {}).get("error") or "")[:60]))
    raise DrawError("; ".join(why))
PYEOF
$N/venv/bin/python -m py_compile /tmp/invoke_draw_v2.py && cp /tmp/invoke_draw_v2.py $D/invoke_draw.py && echo "v2 installed (backup invoke_draw.py.bak_p3_v1_$T)" || { echo COMPILE FAIL; exit 1; }
cd $D && $N/venv/bin/python -c "
import invoke_draw as d
print(d.build_prompt('красной машины на закате',True))
print(d.draw_request('нарисуй кота в космосе'))"
cat > /tmp/p3_imgtest2.py <<'PY'
import sys,json,hashlib,time,base64,urllib.request
sys.path.insert(0,"/workspace/nox/ops/draw"); import invoke_draw as d
Q=["нарисуй кота в космосе","сделай фото красной машины на закате","нарисуй дракона над морем","нарисуй замок на горе зимой","нарисуй робота, который читает книгу"]
out=open("/workspace/nox/state/p3/img_test2.txt","w")
def w(*a): print(*a,file=out,flush=True)
for q in Q:
    pr=d.draw_request(q); w("Q",q,"->",pr,"photo",d.photo_request(q))
    try:
        r=d.local_generate(pr[1],None,d.photo_request(q)); p=r["path"]; b=open(p,"rb").read()
        w("  en:",r.get("prompt_en"),"| path",p,"sha",hashlib.sha256(b).hexdigest()[:10],"src",r["source"],"s",r["seconds"])
        im="data:image/jpeg;base64,"+base64.b64encode(b).decode()
        body={"messages":[{"role":"user","content":[{"type":"text","text":"Describe in one short sentence what is in this image."},{"type":"image_url","image_url":{"url":im}}]}],"max_tokens":50,"temperature":0.2,"chat_template_kwargs":{"enable_thinking":False}}
        rq=urllib.request.Request("http://127.0.0.1:8104/v1/chat/completions",json.dumps(body).encode(),{"Content-Type":"application/json"})
        t=time.time(); m=json.loads(urllib.request.urlopen(rq,timeout=300).read())["choices"][0]["message"]["content"]; w("  vision(%ds):"%(time.time()-t),m.strip()[:200])
    except Exception as e: w("  ERR",type(e).__name__,str(e)[:200])
w("DONE")
PY
nohup setsid $N/venv/bin/python /tmp/p3_imgtest2.py >/tmp/p3_imgtest2.err 2>&1 &
echo "test started"
