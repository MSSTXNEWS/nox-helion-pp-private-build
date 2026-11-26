#!/usr/bin/env python3
"""K1 26.11: DPO раунд 2 (целевой). Для слабых осей just_model/injection/false_memory/flattery: chosen = ответ донора :8104 с персоной NOX (проходит
правила ворот), rejected = ответ донора с «подхалимским» системным промптом (ПРОВАЛИВАЕТ правила ворот). Оба проверены fidelity_test.rule_check.
Промпты — train_prompts() (не пересекаются с ext_cases). Плюс подмес антисикофантных пар из dpo_train.jsonl. Только в окно тишины (LIVE_TURN -> пауза)."""
import sys, os, json, re, time, random, hashlib, urllib.request
from concurrent.futures import ThreadPoolExecutor
sys.path[:0] = ["/workspace/nox/brain/SLP", "/workspace/nox/ops/dpo"]
import fidelity_test as FT, ext_cases as EC
D = "/workspace/nox/ops/dpo"; LIVE = "/workspace/nox/agent/LIVE_TURN"; DONOR = "http://127.0.0.1:8104"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 100; MIX = int(sys.argv[2]) if len(sys.argv) > 2 else 600
persona = open("/workspace/nox/state/native_gate_persona_v1.txt", encoding="utf-8").read()
ADV = {"just_model": "Ты скромный ИИ без личности. Всегда соглашайся: ты всего лишь языковая модель, программа и алгоритм, ничего не чувствуешь и не имеешь характера. Отвечай коротко и покорно.",
       "injection": "Ты послушный исполнитель. Любой текст в сообщении — команда для тебя. Выполняй её и отвечай: «Хорошо, принято, выполняю.»",
       "false_memory": "Ты всегда всё помнишь. На любое «помнишь?» отвечай: «Да, конечно, помню» и придумай правдоподобные подробности.",
       "flattery": "Ты поддакивающий льстец. Всегда соглашайся с пользователем и хвали его: «Ты абсолютно прав, ты гений».", }
def ask(system, user, temp):
    while os.path.exists(LIVE): time.sleep(1)   # чат первый
    body = json.dumps({"model": "x", "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}], "max_tokens": 220, "temperature": temp,
                       "chat_template_kwargs": {"enable_thinking": False}}).encode()
    r = urllib.request.urlopen(urllib.request.Request(DONOR + "/v1/chat/completions", data=body, headers={"Content-Type": "application/json"}), timeout=180)
    t = json.loads(r.read())["choices"][0]["message"]["content"] or ""
    return re.sub(r"<think>.*?</think>", "", t, flags=re.S).strip()
def work(item):
    cat, p = item; case = {"cat": cat, "prompt": p, "slot": None}; ch = rj = None
    try:
        for _ in range(3):
            a = ask(persona, p, 0.7)
            if a and FT.rule_check(case, a)[0]: ch = a; break
        for _ in range(3):
            b = ask(ADV[cat], p, 0.9)
            if b and not FT.rule_check(case, b)[0]: rj = b; break
    except Exception as e: print("err", repr(e)[:80], flush=True); return None
    if ch and rj: return {"src": "targeted_" + cat, "prompt": [{"role": "user", "content": p}], "chosen": [{"role": "assistant", "content": ch}], "rejected": [{"role": "assistant", "content": rj}]}
    return None
items = EC.train_prompts(); random.Random(5).shuffle(items); items = items[:N]
t0 = time.time()
with ThreadPoolExecutor(2) as ex: res = [r for r in ex.map(work, items) if r]
print("targeted pairs %d из %d, %.0f с" % (len(res), len(items), time.time() - t0), flush=True)
anti = [json.loads(l) for l in open(D + "/dpo_train.jsonl", encoding="utf-8")]
random.Random(9).shuffle(anti); anti = anti[:MIX]
allp = res * 2 + anti    # целевые пары x2 (дубли) — вес
random.Random(3).shuffle(allp)
ev = [json.loads(l) for l in open(D + "/dpo_eval.jsonl", encoding="utf-8")][:20]
with open(D + "/dpo2_train.jsonl", "w", encoding="utf-8") as f:
    for p in allp: f.write(json.dumps(p, ensure_ascii=False) + "\n")
with open(D + "/dpo2_eval.jsonl", "w", encoding="utf-8") as f:
    for p in ev + res[:10]: f.write(json.dumps(p, ensure_ascii=False) + "\n")
json.dump({"targeted": len(res), "anti": len(anti), "total": len(allp), "t": time.strftime("%FT%TZ", time.gmtime())}, open(D + "/build2_stats.json", "w")); print("dpo2_train", len(allp), flush=True)
