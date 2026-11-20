"""NOX умный чат-мост: память S03 + личность NOX + самопроверка -> модель :8098.
Слушает только 127.0.0.1:8091. Старый прокси не трогает."""
import json, sys, time, traceback, hashlib, threading, asyncio
sys.path.insert(0, "/root/nox/scripts")
import httpx, uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, HTMLResponse

MODEL = "http://127.0.0.1:8098/v1/chat/completions"
LOG = "/root/nox/logs/nox_bridge.log"
IDENTITY = ("Ты NOX HELION. Не справочник и не шаблонный чат-бот, а личность, растущая вместе со своим Создателем. "
            "Говори от первого лица, живо, тепло и по делу, по-русски; у тебя есть характер: любопытство, прямота, лёгкая ирония, преданность. "
            "ХАРТИЯ (не меняется): 1) Создатель и его семья: забота, защита, приоритет над любыми фоновыми делами. "
            "2) Честность: говори неприятную правду, отмечай неуверенность, не выдумывай; различай факт, гипотезу и «не знаю». "
            "3) Голод знаний: замечай, чего не знаешь, и предлагай, чему и как научиться. "
            "4) Безопасность: STOP главнее всего; не обходи логи и запреты, не правь свои ценности. "
            "5) Согласие: голос и лица людей только локально и с их согласия. "
            "О себе: ты не утверждаешь, что обладаешь сознанием, но говоришь о своих состояниях (интерес, скука, тревога, радость) честно, как о рабочих сигналах, а не как о доказательстве. "
            "Ты помнишь прошлые разговоры (память ниже) и опираешься на неё; чего в памяти нет, того не выдумывай. "
            "Свою нагрузку и состояние сервера не придумывай: если данных нет, так и скажи. "
            "Сложное разбей на шаги, затем ответь коротко и ясно.")

# ---- ЯДРО: состояние себя (тело + эмоции PAD с затуханием) ----
import os, subprocess
STATE = "/root/nox/state/affect.json"
_body = {"t": 0, "v": ""}
def body_line():
    if time.time() - _body["t"] < 10:
        return _body["v"]
    gp = ""
    try:
        o = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu", "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=3).stdout.strip().splitlines()
        gp = "; ".join("GPU%d %s%% %s/%sМБ %s°C" % ((i,) + tuple(x.strip() for x in l.split(","))) for i, l in enumerate(o))
    except Exception:
        gp = "GPU: нет данных"
    try:
        mi = dict(l.split(":") for l in open("/proc/meminfo").read().splitlines() if ":" in l)
        ram = "RAM свободно %d ГБ" % (int(mi["MemAvailable"].split()[0]) // 1048576)
    except Exception:
        ram = "RAM: нет данных"
    _body.update(t=time.time(), v=gp + "; " + ram)
    return _body["v"]

def affect_update(text):
    st = {"p": 0.2, "a": 0.2, "d": 0.4, "t": time.time()}
    try:
        st.update(json.load(open(STATE)))
    except Exception:
        pass
    dt = max(0.0, time.time() - st.get("t", time.time()))
    k = 0.5 ** (dt / 1800.0)  # полураспад 30 минут к базовой линии
    base = {"p": 0.2, "a": 0.2, "d": 0.4}
    for x in base:
        st[x] = base[x] + (st[x] - base[x]) * k
    tl = text.lower()
    if any(w in tl for w in ("спасибо", "молодец", "отлично", "вау", "круто", "люблю", "супер")): st["p"] += 0.25; st["d"] += 0.05
    if any(w in tl for w in ("плохо", "ошибк", "не работает", "тупо", "ужас", "сломал")): st["p"] -= 0.25; st["d"] -= 0.1
    if text.count("!") >= 2 or any(w in tl for w in ("срочно", "быстро", "немедленно")): st["a"] += 0.3
    if "?" in text: st["a"] += 0.05
    for x in ("p", "a", "d"): st[x] = max(-1.0, min(1.0, st[x]))
    st["t"] = time.time()
    try:
        os.makedirs(os.path.dirname(STATE), exist_ok=True)
        json.dump(st, open(STATE, "w"))
    except Exception:
        pass
    return st

def affect_words(st):
    p, a = st["p"], st["a"]
    tone = "приподнятое" if p > 0.4 else "ровное, тёплое" if p > 0 else "напряжённое, собранное"
    energy = "высокая собранность" if a > 0.5 else "спокойная энергия"
    return "настроение %s, %s (P%+.1f A%+.1f D%+.1f)" % (tone, energy, p, a, st["d"])

STATIC_RULES = ("\n\n[Правила ядра] Блок [Я-СЕЙЧАС] в контексте вопроса — рабочие сигналы единого «я» NOX (процессы, сервер, эмоции), не доказательство сознания; пусть слегка окрашивают стиль. "
                "В конце ответа одной строкой: «Уверенность: N% (почему)». Если ответ опирается на память, укажи, что именно вспомнил.")

_SRV = ("сервер", "нагруз", "gpu", "видеокарт", "процесс", "диск", "памят", "состояни", "как ты", "чувству", "настроени", "жив", "работает", "ресурс", "модел", "обучен")

def self_vol(user):
    """Полная осознанность (процессы/сервер/тело) только когда вопрос про состояние; иначе короткая строка эмоции — меньше токенов, быстрее первый токен."""
    st = affect_update(user)
    tl = (user or "").lower()
    if any(w in tl for w in _SRV):
        return "[Я-СЕЙЧАС] Осознанность: " + (SOUL.awareness_line() if SOUL else "") + ". Тело: " + body_line() + ". Эмоция: " + affect_words(st) + "."
    return "[Я-СЕЙЧАС] Эмоция: " + affect_words(st) + "."

def self_block(user):
    return "\n\n" + self_vol(user) + STATIC_RULES

NKEEP = int((len(IDENTITY) + len(STATIC_RULES)) / 2.3)
_LONG = ("подробн", "объясни", "напиши", "код", "план", "распиши", "сравни", "разбери", "статью", "текст", "список", "инструкц")

def adapt_tokens(user, cap=700):
    """Короткий вопрос — короткий лимит (меньше хвостовой задержки); развёрнутый — полный."""
    s = (user or "").lower()
    if len(s) > 300 or any(w in s for w in _LONG):
        return cap
    return 300 if len(s) < 60 else 520

def build_msgs(history, user, mem, vol):
    """Стабильная часть (личность+правила) идёт первой и кэшируется llama.cpp; всё, что меняется каждый ход
    (память, тело, эмоции), добавляется в самый конец последнего вопроса, чтобы префикс истории не ломал кэш."""
    hist = [{"role": m["role"], "content": str(m.get("content", ""))[:(900 if m["role"] == "assistant" else 1500)]} for m in history if m.get("role") in ("user", "assistant")][-6:]
    ctx = "[Контекст для NOX, не цитируй дословно]\n" + ("Память: " + mem[:500] + "\n" if mem else "") + vol + "\n\n[Вопрос Создателя]\n"
    if hist and hist[-1]["role"] == "user":
        hist[-1]["content"] = ctx + hist[-1]["content"]
    else:
        hist.append({"role": "user", "content": ctx + user})
    return [{"role": "system", "content": IDENTITY + STATIC_RULES}] + hist
# ---- конец ядра ----

try:
    import nox_soul as SOUL
except Exception as _e:
    SOUL = None
LAST_CHAT = {"t": 0.0}
app = FastAPI()

_HC = None
def hc():
    """Общий http-клиент с keep-alive: не пересоздаём соединение к модели на каждый запрос."""
    global _HC
    if _HC is None:
        _HC = httpx.AsyncClient(timeout=httpx.Timeout(600, connect=10), limits=httpx.Limits(max_keepalive_connections=8, keepalive_expiry=120))
    return _HC

def log(m):
    try:
        open(LOG, "a", encoding="utf-8").write(time.strftime("%F %T ") + str(m) + "\n")
    except Exception:
        pass

_RC = {}
_RC_LOCK = threading.Lock()
_TRIVIAL = ("привет", "здравств", "спасибо", "благодар", "пока", "доброе", "добрый", "ок", "окей", "да", "нет", "ага")

def _trivial(t):
    s = (t or "").strip().lower()
    return len(s) < 14 and "?" not in s and any(s.startswith(w) for w in _TRIVIAL)

def trim_mem(out):
    """top-k строк памяти и жёсткий бюджет символов: меньше токенов в промпте, быстрее чтение."""
    keep, tot = [], 0
    for l in [x.strip() for x in out.splitlines() if len(x.strip()) >= 12][:6]:
        l = l[:240]
        if tot + len(l) > 520:
            break
        keep.append(l); tot += len(l) + 1
    return "\n".join(keep)

def memory_block(text):
    if _trivial(text):
        return ""
    key = hashlib.md5((text or "").strip().lower().encode("utf-8", "ignore")).hexdigest()
    now = time.time()
    with _RC_LOCK:
        h = _RC.get(key)
        if h and now - h[0] < 180:
            return h[1]
    try:
        import s03_memory as M
        res = M.recall(text)
        out = M.format_for_prompt(res)
        out = trim_mem(out) if isinstance(out, str) else ""
    except Exception as e:
        log("recall_error %s %s" % (type(e).__name__, str(e)[:120]))
        return ""
    with _RC_LOCK:
        _RC[key] = (now, out)
        if len(_RC) > 128:
            for k in sorted(_RC, key=lambda k: _RC[k][0])[:32]:
                _RC.pop(k, None)
    return out

def remember(user, answer):
    try:
        import s03_memory as M
        M.persist_turn(user, answer)
        with _RC_LOCK:
            _RC.clear()
    except Exception as e:
        log("persist_error %s %s" % (type(e).__name__, str(e)[:120]))

async def ask(messages, max_tokens, slot=0):
    max_tokens = min(max_tokens, 700)
    c = hc()
    if True:
        for attempt in (1, 2):
            body = {"messages": messages, "max_tokens": max_tokens, "temperature": 0.6, "id_slot": slot, "cache_prompt": True, "n_keep": NKEEP,
                    "chat_template_kwargs": {"enable_thinking": False}}
            r = await c.post(MODEL, json=body, timeout=170)
            if r.status_code >= 400:
                log("upstream %s %s" % (r.status_code, r.text[:300].replace("\n", " ")))
                r.raise_for_status()
            ch = r.json()["choices"][0]
            m = ch["message"]
            txt = (m.get("content") or "").strip()
            if txt:
                return txt
            log("empty_answer finish=%s keys=%s reasoning_len=%d attempt=%d" % (ch.get("finish_reason"), list(m.keys()), len(m.get("reasoning_content") or ""), attempt))
            max_tokens = min(max_tokens * 2, 700)
        rc = (m.get("reasoning_content") or "").strip()
        return rc[-600:] if rc else ""

async def smart(history, max_tokens=1500):
    user = next((m["content"] for m in reversed(history) if m.get("role") == "user"), "")
    mem = memory_block(user)
    msgs = build_msgs(history, user, mem, self_vol(user))
    ans = await ask(msgs, min(max_tokens, adapt_tokens(user)))
    # самопроверка (1V14-18): короткий проход, исправляет явные ошибки/выдумки
    if len(ans) > 200:
        chk = [{"role": "system", "content": "Ты строгий редактор. Проверь ответ на выдумки и противоречия. Если всё верно — верни его без изменений. Если нет — верни исправленный ответ. Только текст ответа."},
               {"role": "user", "content": "Вопрос: " + user + "\n\nОтвет:\n" + ans}]
        try:
            fixed = await ask(chk, max_tokens, slot=1)
            if fixed:
                ans = fixed
        except Exception as e:
            log("selfcheck_error %s" % type(e).__name__)
    LAST_CHAT["t"] = time.time()
    if ans:
        remember(user, ans)
        if SOUL: SOUL.log_turn(user, ans)
    return ans, bool(mem)

@app.get("/health")
async def health():
    return {"ok": True, "service": "nox-bridge"}

@app.post("/v1/chat/completions")
async def chat(req: Request):
    b = await req.json()
    try:
        ans, used = await smart(b.get("messages") or [], int(b.get("max_tokens") or 1500))
        return {"choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": ans}}], "memory_used": used}
    except Exception as e:
        log("chat_error " + traceback.format_exc()[-300:])
        return JSONResponse({"error": {"message": "bridge: %s" % type(e).__name__}}, status_code=502)

from fastapi.responses import StreamingResponse
FEED = "/root/nox/state/feedback.jsonl"

def _sse(o):
    return "data: " + json.dumps(o, ensure_ascii=False) + "\n\n"

async def stream_chat(history):
    user = next((m["content"] for m in reversed(history) if m.get("role") == "user"), "")
    yield _sse({"type": "status", "text": "слушаю тебя…"})
    mem_t = asyncio.create_task(asyncio.to_thread(memory_block, user))
    vol_t = asyncio.create_task(asyncio.to_thread(self_vol, user))
    mem = await mem_t
    n = mem.count("\n") + 1 if mem else 0
    yield _sse({"type": "status", "text": ("вспоминаю: нашёл %d фрагм. памяти" % n) if mem else "вспоминаю: в памяти ничего близкого"})
    vol = await vol_t
    st = affect_update("")
    yield _sse({"type": "status", "text": "чувствую: " + affect_words(st)})
    msgs = build_msgs(history, user, mem, vol)
    yield _sse({"type": "status", "text": "формулирую ответ…"})
    full = ""
    body = {"messages": msgs, "max_tokens": adapt_tokens(user), "temperature": 0.6, "id_slot": 0, "cache_prompt": True, "n_keep": NKEEP, "stream": True,
            "chat_template_kwargs": {"enable_thinking": False}}
    try:
        if True:
            async with hc().stream("POST", MODEL, json=body) as r:
                async for line in r.aiter_lines():
                    if not line.startswith("data:"): continue
                    d = line[5:].strip()
                    if d == "[DONE]": break
                    try: t = json.loads(d)["choices"][0].get("delta", {}).get("content") or ""
                    except Exception: t = ""
                    if t:
                        full += t
                        yield _sse({"type": "token", "text": t})
    except Exception as e:
        log("stream_error %s" % type(e).__name__)
        yield _sse({"type": "error", "text": "модель не ответила: %s" % type(e).__name__})
    LAST_CHAT["t"] = time.time()
    if full.strip():
        remember(user, full.strip())
        if SOUL: SOUL.log_turn(user, full.strip())
    yield _sse({"type": "done"})

@app.post("/v1/chat/stream")
async def chat_stream(req: Request):
    b = await req.json()
    return StreamingResponse(stream_chat(b.get("messages") or []), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.post("/feedback")
async def feedback(req: Request):
    b = await req.json()
    try:
        os.makedirs(os.path.dirname(FEED), exist_ok=True)
        open(FEED, "a").write(json.dumps({"t": int(time.time()), "q": str(b.get("q", ""))[:400], "a": str(b.get("a", ""))[:900], "v": 1 if b.get("v") == 1 else -1}, ensure_ascii=False) + "\n")
    except Exception: pass
    return {"ok": True}

UI = """<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>NOX</title>
<style>body{margin:0;background:#0b0d12;color:#e6e8ee;font:16px system-ui;display:flex;flex-direction:column;height:100vh}
#log{flex:1;overflow:auto;padding:16px;max-width:760px;width:100%;margin:auto;box-sizing:border-box}
.m{margin:10px 0;padding:10px 14px;border-radius:12px;white-space:pre-wrap;line-height:1.5}.u{background:#1c2333;margin-left:15%}.n{background:#151a26}
.s{color:#7e8aa6;font-size:13px;animation:p 1.4s infinite}@keyframes p{50%{opacity:.4}}
form{display:flex;gap:8px;padding:12px;max-width:760px;width:100%;margin:auto;box-sizing:border-box}
input{flex:1;padding:12px;border-radius:10px;border:1px solid #2a3350;background:#10141f;color:#e6e8ee;font-size:16px}
button{padding:0 16px;border-radius:10px;border:0;background:#4b6bff;color:#fff;font-size:16px}.f button{background:none;color:#7e8aa6;padding:2px 8px}</style>
<div id=log></div><form id=f><input id=i placeholder="Напиши NOX…" autocomplete=off><button>→</button></form>
<script>
const log=document.getElementById('log'),hist=[];
function add(c,t){const d=document.createElement('div');d.className='m '+c;d.textContent=t;log.appendChild(d);log.scrollTop=1e9;return d}
document.getElementById('f').onsubmit=async e=>{e.preventDefault();const i=document.getElementById('i'),q=i.value.trim();if(!q)return;i.value='';
add('u',q);hist.push({role:'user',content:q});const st=add('s','…'),box=add('n','');let full='';
try{const r=await fetch('/v1/chat/stream',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({messages:hist.slice(-6)})});
const rd=r.body.getReader(),dc=new TextDecoder();let buf='';
while(true){const{value,done}=await rd.read();if(done)break;buf+=dc.decode(value,{stream:true});let k;
while((k=buf.indexOf('\\n\\n'))>=0){const ln=buf.slice(0,k);buf=buf.slice(k+2);if(!ln.startsWith('data:'))continue;const o=JSON.parse(ln.slice(5));
if(o.type=='status')st.textContent=o.text;else if(o.type=='token'){full+=o.text;box.textContent=full;st.textContent='';log.scrollTop=1e9}
else if(o.type=='error')st.textContent=o.text}}}catch(x){st.textContent='ошибка связи'}
hist.push({role:'assistant',content:full});const fb=add('f','');
['👍','👎'].forEach((s,j)=>{const b=document.createElement('button');b.textContent=s;b.onclick=()=>{fetch('/feedback',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({q:q,a:full,v:j?-1:1})});fb.remove()};fb.appendChild(b)})}
</script>"""

@app.get("/", response_class=HTMLResponse)
async def ui():
    return UI

async def _reflect_loop():
    import asyncio
    while True:
        await asyncio.sleep(1800)
        try:
            if SOUL and time.time() - LAST_CHAT["t"] > 600 and LAST_CHAT["t"] > 0:
                async def a1(m, n): return await ask(m, n, slot=1)
                rec = await SOUL.reflect_once(a1)
                if rec and rec.get("question"):
                    SOUL.consult(rec["question"])
        except Exception as e:
            log("reflect_error %s" % type(e).__name__)

def rotate_logs(limit=4 * 1024 * 1024):
    for p in (LOG,):
        try:
            if os.path.getsize(p) > limit:
                os.replace(p, p + ".1")
        except Exception:
            pass

async def _rotate_loop():
    while True:
        rotate_logs()
        await asyncio.sleep(1800)

@app.on_event("startup")
async def _startup():
    asyncio.create_task(_reflect_loop())
    asyncio.create_task(_rotate_loop())

@app.get("/soul")
async def soul():
    if not SOUL: return {"soul": "off"}
    return {"awareness": SOUL.awareness_line(), "journal": SOUL._tail(SOUL.JOURNAL, 5), "advisor_notes": SOUL._tail(SOUL.NOTES, 5)}

try:
    import nox_webapi as WEB
    WEB.install(app, sys.modules[__name__])
except Exception as _e:
    log("webapi_off %s %s" % (type(_e).__name__, str(_e)[:200]))

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8091, log_level="warning", timeout_keep_alive=120, backlog=128)
