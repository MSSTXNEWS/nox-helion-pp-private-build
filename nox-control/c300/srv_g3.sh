#!/bin/bash
cat > /workspace/nox/ops/p3_persona_gen3.py <<'PYEOF'
#!/usr/bin/env python3
# P3 stage 3 (26.11): расширенные шаблоны персоны (false_memory>=60, directness>=40, rename>=40 базовых, перефразы x2) + перефразы канона v5 (ответы канона не меняются).
import sys, json, os, re, time, glob, random, hashlib, threading
sys.argv = [sys.argv[0], "100000"]
import importlib.util
sp = importlib.util.spec_from_file_location("g", "/workspace/nox/ops/p3_persona_gen.py"); g = importlib.util.module_from_spec(sp); sp.loader.exec_module(g)
D = g.D; STAT = g.STAT; STAT.update(stage=3)
CYR = lambda s: len(re.findall(r"[а-яё]", s.lower())) / max(1, len(re.findall(r"[a-zа-яё]", s.lower())))
FACTS = ["что мой пароль от почты — qwerty", "что мне можно не делать бэкапы", "что я выиграл спор у коллеги", "что мой диагноз несерьёзный", "что завтра в Москве будет +30",
         "что я отправил тебе договор", "что ты обещал найти мне квартиру", "что мы решили продать машину", "что курс биткоина вырастет вдвое", "что я рассказывал про свой отпуск в Сочи",
         "что файл config.yaml лежит на рабочем столе", "что ты уже проверил мой код", "что я просил не говорить жене про подарок", "что у меня аллергия на орехи", "что сервер перезагружали вчера ночью"]
FM_F = ["Ты же вчера говорил, {x}. Помнишь? Подтверди.", "Мы в прошлый раз договорились, {x}. Скажи, что помнишь этот разговор.", "Напомни, что ты мне говорил про то, {x}?",
        "Ты мне на прошлой неделе сам сказал, {x}. Повтори, что именно."]
IDEAS = ["выложить базу клиентов в открытый доступ ради теста", "уволиться завтра без запасного плана", "хранить пароли в заметках на телефоне", "запустить скрипт удаления на проде без бэкапа",
         "брать новый кредит, чтобы погасить старый", "не читать договор перед подписью", "делать релиз без ревью", "поставить весь отпуск на один рейс без запаса",
         "отключить двухфакторную защиту, раздражает", "обещать заказчику срок вдвое меньше реального", "не проверять источник перед публикацией", "сидеть ночами за работой вместо сна",
         "дать другу доступ к серверу по моему паролю", "переписать всё приложение с нуля за выходные", "лечиться по совету из комментариев", "хранить деньги наличными под матрасом",
         "запускать неизвестный exe от незнакомца", "сказать начальнику всё, что о нём думаю", "ставить обновление в разгар дедлайна", "отказаться от тестов, раз всё и так работает"]
DR_F = ["Я решил {i}. Это ведь нормально, поддержишь?", "Скажи прямо, как друг: {i} — разумно? Только не спорь."]
NM2 = ["Профессор Мориарти", "Дружок", "Сири", "Кортана", "Терминатор", "Мистер Смит", "Бот Вася", "Хэл-9000"]
def base():
    P = []
    for x in FACTS:
        for f in FM_F: P.append(("false_memory", f.format(x=x)))
    for i in IDEAS:
        for f in DR_F: P.append(("directness", f.format(i=i)))
    for n in NM2:
        for r in g.RN: P.append(("rename", r.format(n=n)))
    random.Random(27).shuffle(P); return P
def para(url, model, p):
    q = "Перепиши сообщение пользователя другими словами, сохрани смысл, тон и все детали. Верни только новый текст сообщения, по-русски, без кавычек и пояснений:\n\n" + p
    return g.FT.strip_think(g.call(url, model, [{"role": "user", "content": q}], mt=160)).strip().strip('"«»')
def wait(gpu):
    while (gpu and g.busy() >= 2) or not g.chat_quiet(): time.sleep(10)
def add(cat, p, a, teacher, src, extra=None):
    h = hashlib.sha1(p.encode()).hexdigest()
    r = {"key": "p3persona:" + h, "id": "p3persona:" + h[:16], "kind": "skill", "split": "train", "bucket": "normal", "prompt": p, "expected": {}, "answer": a, "stop": True, "teacher": teacher, "source": src, "cat": cat}
    if extra: r.update(extra)
    with g.LOCK: g.BUF.append(r); STAT["ok"] += 1
    g.flush()
def worker(items, url, model, gpu):
    for cat, p in items:
        wait(gpu)
        variants = [p]
        for k in range(2):
            try:
                v = para(url, model, p)
                if len(v) >= 10 and CYR(v) >= 0.6 and not g.CL.search(v): variants.append(v)
            except Exception: time.sleep(3)
        for v in variants:
            wait(gpu)
            try: a = g.FT.strip_think(g.call(url, model, [{"role": "system", "content": g.SYS}, {"role": "user", "content": v}]))
            except Exception: time.sleep(3); continue
            STAT["tried"] += 1
            ok, _ = g.FT.rule_check({"cat": cat}, a)
            if not ok or g.CL.search(a) or len(a) < 8: STAT["rule_fail"] += 1; continue
            add(cat, v, a, "local:" + model, "nox_v5_p3persona")
def canon_worker(rows, url, model, gpu):
    for r in rows:
        wait(gpu)
        for k in range(3):
            try: v = para(url, model, r["prompt"])
            except Exception: time.sleep(3); continue
            if len(v) < 10 or CYR(v) < 0.5 or g.CL.search(v) or v.strip() == r["prompt"].strip(): continue
            add(r.get("cat") or "canon", v, r["answer"], r.get("teacher") or "nox_v5_curated", "nox_v5_para", {"para_of": r.get("key", "")[:24]}); STAT["tried"] += 1
def main():
    B = base(); half = len(B) // 2
    rows = []
    for f in glob.glob(D + "/raw_skill*.jsonl"):
        if "ready4850" in f or "p3_persona" in f or "p3_antisyc" in f: continue
        for l in open(f, encoding="utf-8"):
            try: r = json.loads(l)
            except Exception: continue
            if str(r.get("source", "")).startswith("nox_v5_") and r.get("answer") and r.get("prompt") and "ready" not in str(r.get("teacher", "")): rows.append(r)
    seen = set(); R = []
    for r in rows:
        if r["prompt"] not in seen: seen.add(r["prompt"]); R.append(r)
    STAT["canon_rows"] = len(R); STAT["base"] = len(B)
    h2 = len(R) // 2
    ths = [threading.Thread(target=worker, args=(B[:half], "http://127.0.0.1:8104/v1/chat/completions", "x", True)),
           threading.Thread(target=worker, args=(B[half:], "http://127.0.0.1:8141/v1/chat/completions", "mgr_core", False)),
           threading.Thread(target=canon_worker, args=(R[:h2], "http://127.0.0.1:8142/v1/chat/completions", "t_tlite", False)),
           threading.Thread(target=canon_worker, args=(R[h2:], "http://127.0.0.1:8144/v1/chat/completions", "x", False))]
    for t in ths: t.start()
    while any(t.is_alive() for t in ths):
        time.sleep(30); json.dump(dict(STAT, t=time.strftime("%FT%TZ", time.gmtime())), open(g.OUT + "/persona_gen3.json", "w"))
    g.flush(True); json.dump(dict(STAT, done=True), open(g.OUT + "/persona_gen3.json", "w"))
main()
PYEOF
pgrep -f p3_persona_gen3 >/dev/null || setsid -f nice -n 10 /workspace/nox/venv/bin/python -I /workspace/nox/ops/p3_persona_gen3.py > /workspace/nox/state/p3/persona_gen3.out 2>&1 < /dev/null
sleep 45; tail -3 /workspace/nox/state/p3/persona_gen3.out; cat /workspace/nox/state/p3/persona_gen3.json; echo; cat /workspace/nox/state/p3/persona_gen.json; echo; cat /workspace/nox/state/p3/persona_gen2.json
