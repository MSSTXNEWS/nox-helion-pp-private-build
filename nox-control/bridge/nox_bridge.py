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

async def ask(messages, max_tokens):
    max_tokens = min(max_tokens, 700)
    async with httpx.AsyncClient(timeout=170) as c:
        for attempt in (1, 2):
            body = {"messages": messages, "max_tokens": max_tokens, "temperature": 0.6, "id_slot": 0, "cache_prompt": True,
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
    sys_msg = IDENTITY + ("\n\nТвоя память:\n" + mem[:1200] if mem else "")
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
    if ans:
        remember(user, ans)
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

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8091, log_level="warning")
