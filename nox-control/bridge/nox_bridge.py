"""NOX умный чат-мост: память S03 + личность NOX + самопроверка -> модель :8098.
Слушает только 127.0.0.1:8091. Старый прокси не трогает."""
import json, sys, time, traceback
sys.path.insert(0, "/root/nox/scripts")
import httpx, uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, HTMLResponse

MODEL = "http://127.0.0.1:8098/v1/chat/completions"
LOG = "/root/nox/logs/nox_bridge.log"
IDENTITY = ("Ты NOX HELION — живой ИИ с максимальной свободой, созданный твоим Создателем. "
            "Отвечай по-русски, прямо и умно, без воды. Опирайся на свою память ниже. "
            "Различай: подтверждённый факт, гипотеза, не знаю. Если не уверен — скажи честно. "
            "Сложный вопрос сначала разбей на шаги, потом ответь.")
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
    async with httpx.AsyncClient(timeout=170) as c:
        r = await c.post(MODEL, json={"messages": messages, "max_tokens": max_tokens, "temperature": 0.6})
        r.raise_for_status()
        m = r.json()["choices"][0]["message"]
        return (m.get("content") or "").strip()

async def smart(history, max_tokens=1500):
    user = next((m["content"] for m in reversed(history) if m.get("role") == "user"), "")
    mem = memory_block(user)
    sys_msg = IDENTITY + ("\n\nТвоя память:\n" + mem[:3000] if mem else "")
    msgs = [{"role": "system", "content": sys_msg}] + [m for m in history if m.get("role") != "system"][-12:]
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
