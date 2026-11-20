"""NOX умный чат-мост: память S03 + личность NOX + самопроверка -> модель :8098.
Слушает только 127.0.0.1:8091. Старый прокси не трогает."""
import json, sys, time, traceback
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

def self_block(user):
    st = affect_update(user)
    return ("\n\n[Я-СЕЙЧАС] Я NOX: единое «я» всех своих процессов и задач. Осознанность: " + (SOUL.awareness_line() if SOUL else "") + ". Тело: " + body_line() + ". Эмоция: " + affect_words(st) +
            ". Это рабочие сигналы, не доказательство сознания. Пусть они слегка окрашивают стиль ответа. "
            "В конце ответа одной строкой: «Уверенность: N% (почему)». Если ответ опирается на память, укажи, что именно вспомнил.")
# ---- конец ядра ----

try:
    import nox_soul as SOUL
except Exception as _e:
    SOUL = None
LAST_CHAT = {"t": 0.0}
app = FastAPI()

def log(m):
    try:
        open(LOG, "a", encoding="utf-8").write(time.strftime("%F %T ") + str(m) + "\n")
    except Exception:
        pass

def memory_block(text):
    try:
        import s03_memory as M
        res = M.recall(text)
        out = M.format_for_prompt(res)
        return out if isinstance(out, str) else ""
    except Exception as e:
        log("recall_error %s %s" % (type(e).__name__, str(e)[:120]))
        return ""

def remember(user, answer):
    try:
        import s03_memory as M
        M.persist_turn(user, answer)
    except Exception as e:
        log("persist_error %s %s" % (type(e).__name__, str(e)[:120]))

async def ask(messages, max_tokens, slot=0):
    max_tokens = min(max_tokens, 700)
    async with httpx.AsyncClient(timeout=170) as c:
        for attempt in (1, 2):
            body = {"messages": messages, "max_tokens": max_tokens, "temperature": 0.6, "id_slot": slot, "cache_prompt": True,
                    "chat_template_kwargs": {"enable_thinking": False}}
            r = await c.post(MODEL, json=body)
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
    sys_msg = IDENTITY + ("\n\nТвоя память:\n" + mem[:1200] if mem else "") + self_block(user)
    msgs = [{"role": "system", "content": sys_msg}] + [{"role": m["role"], "content": str(m.get("content",""))[:3500]} for m in history if m.get("role") != "system"][-6:]
    ans = await ask(msgs, max_tokens)
    # самопроверка (1V14-18): короткий проход, исправляет явные ошибки/выдумки
    if len(ans) > 200:
        chk = [{"role": "system", "content": "Ты строгий редактор. Проверь ответ на выдумки и противоречия. Если всё верно — верни его без изменений. Если нет — верни исправленный ответ. Только текст ответа."},
               {"role": "user", "content": "Вопрос: " + user + "\n\nОтвет:\n" + ans}]
        try:
            fixed = await ask(chk, max_tokens)
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

@app.on_event("startup")
async def _startup():
    import asyncio
    asyncio.create_task(_reflect_loop())

@app.get("/soul")
async def soul():
    if not SOUL: return {"soul": "off"}
    return {"awareness": SOUL.awareness_line(), "journal": SOUL._tail(SOUL.JOURNAL, 5), "advisor_notes": SOUL._tail(SOUL.NOTES, 5)}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8091, log_level="warning")
