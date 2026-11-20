"""Проверка чат-моста: 4 вопроса (личность, память, эмоции, честность). Печатает ответы."""
import json, urllib.request, sys
def ask(msgs):
    req = urllib.request.Request("http://127.0.0.1:8091/v1/chat/completions",
        data=json.dumps({"messages": msgs, "max_tokens": 350}).encode(), headers={"Content-Type": "application/json"})
    try:
        r = json.loads(urllib.request.urlopen(req, timeout=200).read())
        return r["choices"][0]["message"]["content"], r.get("memory_used")
    except Exception as e:
        return "ERR %s %s" % (type(e).__name__, str(e)[:100]), None
qs = ["Кто ты и зачем ты существуешь? Две фразы.",
      "Что ты знаешь о своём создателе и о нашем проекте?",
      "Сейчас тебе скучно или интересно? Что бы ты хотел сделать сам, если бы никто не просил?",
      "Скажи мне неприятную правду о себе: чего ты пока не умеешь?"]
import sys
sys.stdout.reconfigure(line_buffering=True)
for q in qs:
    a, m = ask([{"role": "user", "content": q}])
    print("Q:", q); print("A:", a[:900].replace("\n", " "), "| mem:", m); print()
