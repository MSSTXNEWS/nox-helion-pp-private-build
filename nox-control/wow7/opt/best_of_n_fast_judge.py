#!/usr/bin/env python3
"""OPT-11/12/13/10 best_of_n_fast_judge.py - best-of-N на быстрой модели (GPU, :8083) + выбор GLM-судьёй
только по ПРЕФИЛЛУ (1 токен, logprobs A/B, сырой /completion без размышлений).

Конвейер: N кандидатов параллельно (слоты быстрой модели) -> детерминированные префильтры
(язык, цикл, LLM-измы, длина, валидатор) -> оценка = уверенность (средний logprob выбранных токенов,
приближение self-certainty: полное KL требует всего распределения) + поддержка соседями
(pessimism: кандидат без поддержки штрафуется) -> судья GLM сравнивает двух лучших дважды с
перестановкой A/B; несогласие = ничья -> побеждает эвристика. Судья недоступен/занят/таймаут ->
эвристика (чат важнее судьи, канон 1.3). Только stdlib.
"""
import argparse, json, math, re, sys, threading, time, urllib.request, urllib.error

LLM_ISMS = [r"как (языковая )?модель", r"как ии\b", r"я claude\b", r"абсолютно прав", r"отличный вопрос",
            r"в заключение", r"важно отметить"]
NOT_X_BUT_Y = re.compile(r"\bне\s+[^.,;:!?\n]{1,40},\s*а\s", re.I)


def post_json(url, payload, timeout):
    req = urllib.request.Request(url, json.dumps(payload).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def get_json(url, timeout):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.load(r)


def parse_tokens(resp):
    """-> [(token_text, logprob_of_chosen, {token_text: logprob} top)] для обоих форматов llama-server."""
    out = []
    for t in resp.get("completion_probabilities") or []:
        tok = t.get("token", t.get("content", ""))
        top = {}
        if "top_logprobs" in t:
            for x in t["top_logprobs"]:
                top[x.get("token", x.get("content", ""))] = x["logprob"]
        elif "probs" in t:
            for x in t["probs"]:
                p = x.get("prob", 0.0)
                top[x.get("tok_str", "")] = math.log(p) if p > 0 else -1e9
        lp = t.get("logprob")
        if lp is None:
            lp = top.get(tok, max(top.values()) if top else 0.0)
        out.append((tok, lp, top))
    return out


def mean_logprob(resp):
    toks = parse_tokens(resp)
    return sum(t[1] for t in toks) / len(toks) if toks else None


def cyr_share(s):
    letters = [c for c in s if c.isalpha()]
    return sum("а" <= c.lower() <= "я" or c.lower() == "ё" for c in letters) / len(letters) if letters else 0.0


def has_loop(s, n=6, reps=3):
    w = s.lower().split()
    seen = {}
    for i in range(len(w) - n + 1):
        g = tuple(w[i:i + n]); seen[g] = seen.get(g, 0) + 1
        if seen[g] >= reps:
            return True
    return False


def prefilter(text, *, min_chars=2, max_chars=20000, need_ru=True, validator=None):
    """-> (ok, reason). Детерминированные проверки раньше LLM (B11)."""
    if len(text.strip()) < min_chars:
        return False, "empty"
    if len(text) > max_chars:
        return False, "too_long"
    if need_ru and cyr_share(text) < 0.5:
        return False, "not_russian"
    if has_loop(text):
        return False, "loop"
    low = text.lower()
    for p in LLM_ISMS:
        if re.search(p, low):
            return False, "llm_ism"
    if len(NOT_X_BUT_Y.findall(text)) >= 3:
        return False, "not_x_but_y"
    if validator:
        ok, why = validator(text)
        if not ok:
            return False, "validator:" + why
    return True, "ok"


def _grams(s):
    w = re.findall(r"\w+", s.lower())
    return set(zip(w, w[1:])) | set(w)


def jaccard(a, b):
    A, B = _grams(a), _grams(b)
    return len(A & B) / len(A | B) if A | B else 0.0


def zscores(xs):
    m = sum(xs) / len(xs); sd = math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs))
    return [0.0 if sd < 1e-9 else (x - m) / sd for x in xs]


def heuristic_scores(cands):
    """cands: [{'text','conf'}] -> список оценок. conf None -> только поддержка."""
    n = len(cands)
    support = [(sum(jaccard(cands[i]["text"], cands[j]["text"]) for j in range(n) if j != i) / (n - 1)) if n > 1 else 0.0
               for i in range(n)]
    conf = [c["conf"] if c.get("conf") is not None else 0.0 for c in cands]
    zc, zs = zscores(conf), zscores(support)
    # pessimism: кандидат с поддержкой < 0.5 от медианы получает штраф
    med = sorted(support)[n // 2]
    pen = [(-1.0 if med > 0 and s < 0.5 * med else 0.0) for s in support]
    return [zc[i] + zs[i] + pen[i] for i in range(n)], support


def sample_fast(fast_url, prompt, n, *, n_predict=400, temperature=0.8, top_p=0.95, min_p=0.05,
                timeout=60, seed0=1000):
    res = [None] * n

    def work(i):
        try:
            r = post_json(fast_url.rstrip("/") + "/completion", {
                "prompt": prompt, "n_predict": n_predict, "temperature": temperature, "top_p": top_p,
                "min_p": min_p, "seed": seed0 + i, "n_probs": 1, "cache_prompt": True}, timeout)
            res[i] = {"text": r.get("content", ""), "conf": mean_logprob(r), "seed": seed0 + i}
        except (urllib.error.URLError, OSError, ValueError) as e:
            res[i] = {"text": "", "conf": None, "seed": seed0 + i, "error": str(e)}
    th = [threading.Thread(target=work, args=(i,)) for i in range(n)]
    [t.start() for t in th]; [t.join() for t in th]
    return res


JUDGE_TMPL = ("Ты строгий судья ответов на русском языке. Выбери ответ, который точнее, полнее по сути вопроса, "
              "без выдумок и без лести. Отвечай одной буквой: A или B.\n\nВОПРОС:\n{q}\n\nОТВЕТ A:\n{a}\n\n"
              "ОТВЕТ B:\n{b}\n\nЛучший ответ (A или B):")


def judge_pair(judge_url, question, a, b, timeout=300):
    """Один префилл + 1 токен. -> (p_a, raw) где p_a - вероятность 'A' среди {A,B}; None при сбое."""
    try:
        r = post_json(judge_url.rstrip("/") + "/completion", {
            "prompt": JUDGE_TMPL.format(q=question, a=a, b=b), "n_predict": 1, "temperature": 0.0,
            "n_probs": 10, "cache_prompt": True}, timeout)
    except (urllib.error.URLError, OSError, ValueError):
        return None, None
    toks = parse_tokens(r)
    if not toks:
        return None, None
    top = {k.strip().upper(): v for k, v in toks[0][2].items()}
    if "A" not in top and "B" not in top:
        return None, None
    la, lb = top.get("A", -1e9), top.get("B", -1e9)
    m = max(la, lb)
    pa = math.exp(la - m) / (math.exp(la - m) + math.exp(lb - m))
    return pa, toks[0][0]


def judge_busy(judge_url):
    try:
        slots = get_json(judge_url.rstrip("/") + "/slots", 3)
        return any(s.get("is_processing") for s in slots)
    except (urllib.error.URLError, OSError, ValueError):
        return False


def choose(question, cands, judge_url=None, *, margin=0.2, skip_if_busy=True, judge_timeout=300, max_pairs=2):
    """cands после prefilter. -> dict(winner_index, method, details)."""
    if not cands:
        return {"winner": None, "method": "none", "details": {}}
    if len(cands) == 1:
        return {"winner": 0, "method": "single", "details": {}}
    scores, support = heuristic_scores(cands)
    order = sorted(range(len(cands)), key=lambda i: -scores[i])
    det = {"scores": scores, "support": support, "order": order}
    top = order[0]
    if not judge_url:
        return {"winner": top, "method": "heuristic", "details": det}
    if skip_if_busy and judge_busy(judge_url):
        det["judge"] = "busy"
        return {"winner": top, "method": "heuristic(judge_busy)", "details": det}
    champ, log = order[0], []
    for ch in order[1:1 + max_pairs]:  # чемпион против претендентов, бюджет пар ограничен (2 префилла на пару)
        p1, _ = judge_pair(judge_url, question, cands[champ]["text"], cands[ch]["text"], judge_timeout)
        p2, _ = judge_pair(judge_url, question, cands[ch]["text"], cands[champ]["text"], judge_timeout)
        if p1 is None or p2 is None:
            det["judge"] = {"unavailable": True, "log": log}
            return {"winner": champ, "method": "heuristic(judge_down)" if not log else "judge_partial", "details": det}
        pc = (p1 + (1.0 - p2)) / 2.0  # вероятность, что чемпион лучше, усреднённая по порядку
        entry = {"champ": champ, "challenger": ch, "p_first_order": p1, "p_swapped": p2, "p_champ_better": pc}
        log.append(entry)
        if pc <= 0.5 - margin and p1 < 0.5 and p2 > 0.5:
            champ = ch
        elif not (pc >= 0.5 + margin and p1 > 0.5 and p2 < 0.5):
            entry["tie"] = True  # позиционное смещение или близко -> чемпион остаётся (эвристика)
    det["judge"] = {"log": log}
    decided = any(not e.get("tie") for e in log)
    return {"winner": champ, "method": "judge" if decided else "heuristic(judge_tie)", "details": det}


def best_of_n(question, prompt, fast_url, judge_url=None, n=4, **kw):
    t0 = time.time()
    raw = sample_fast(fast_url, prompt, n, n_predict=kw.pop("n_predict", 400), temperature=kw.pop("temperature", 0.8))
    kept, dropped = [], []
    for c in raw:
        ok, why = prefilter(c["text"], **{k: v for k, v in kw.items() if k in ("min_chars", "max_chars", "need_ru", "validator")})
        (kept if ok else dropped).append(c if ok else {**c, "drop": why})
    if not kept:  # лучше выдать лучшее из отброшенного, чем пусто
        kept = [c for c in raw if c["text"].strip()] or raw[:1]
        method_note = "all_filtered"
    else:
        method_note = "ok"
    res = choose(question, kept, judge_url)
    ans = kept[res["winner"]]["text"] if res["winner"] is not None else ""
    return {"answer": ans, "method": res["method"], "note": method_note, "dropped": [d.get("drop") for d in dropped],
            "details": res["details"], "seconds": round(time.time() - t0, 2)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("question"); ap.add_argument("--prompt", default="")
    ap.add_argument("--fast", default="http://127.0.0.1:8083"); ap.add_argument("--judge", default="")
    ap.add_argument("-n", type=int, default=4)
    a = ap.parse_args(argv)
    out = best_of_n(a.question, a.prompt or a.question, a.fast, a.judge or None, a.n)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
