"""RTE-12: sleep-time черновики ответов на частые вопросы (идея Letta sleep-time compute, arXiv 2504.13171).
Ночью (23-08 МСК) берёт топ-N повторяющихся вопросов из журнала ходов (+ необязательный источник S03), просит GLM ответить и кладёт в drafts.json
с TTL 24 ч и пометкой источника. Роутер (rte_server.Pipeline) до GLM ищет точное/семантическое совпадение и отдаёт заготовку мгновенно (stage=draft).
Защиты: не заготавливаем вопросы про «сейчас/сегодня/погода/курс/новости», личную память и действия; ответ с пометкой «заготовлено ночью»; TTL;
порог минимума: вопрос должен повториться >= MIN_REPEATS раз; режимы deep/max всегда идут в GLM. Оценка: evaluate() = доля мгновенных + паритет judge.
Запуск: python3 drafts.py build [--state DIR] [--top 10] [--force] [--dry-run] | stats | purge
"""
import argparse, json, os, re, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
for _c in (os.environ.get("NOX_COMMON", ""), os.path.join(HERE, "..", "COMMON"), os.path.join(HERE, "common")):
    if _c and os.path.isdir(_c) and _c not in sys.path:
        sys.path.append(_c)
import statefile
from quiet import in_quiet
import tune

TTL_S = 24 * 3600
MIN_REPEATS, MIN_WORDS, SIM = 2, 3, 0.8
SKIP_RE = re.compile(r"сейчас|сегодня|вчера|завтра|на этой неделе|погод|курс\b|курс[ае]? (?:доллар|евро|бит)|новост|который час|времен[иь]|что нового|"
                     r"ты помнишь|помнишь|мой |моя |моё |мои |мне |напомни|запомни|забудь|сделай|запусти|удали|отправь|перезапусти|"
                     r"пароль|токен|ключ\b|секрет", re.I)


def norm(text):
    t = re.sub(r"[^\w\s]", " ", (text or "").lower().replace("ё", "е"))
    return re.sub(r"\s+", " ", t).strip()


def stems(text):
    return {w[:5] for w in norm(text).split() if len(w) > 1}


def similar(a, b):
    """Точное совпадение после нормализации или Jaccard по основам >= SIM при тех же числах."""
    na, nb = norm(a), norm(b)
    if na == nb:
        return True
    if re.findall(r"\d+", na) != re.findall(r"\d+", nb):
        return False
    sa, sb = stems(a), stems(b)
    return bool(sa and sb) and len(sa & sb) / len(sa | sb) >= SIM


def eligible(q):
    return len(norm(q).split()) >= MIN_WORDS and not SKIP_RE.search(q or "") and len(q) <= 400


def top_questions(turns, top=10, min_repeats=MIN_REPEATS, extra=None):
    """Группирует похожие вопросы; -> [(представитель, число повторов)] по убыванию."""
    groups = []   # [rep, n]
    items = [t["text"] for t in turns if t.get("text") and t.get("status") == "done"] + list(extra or [])
    for q in items:
        if not eligible(q):
            continue
        for g in groups:
            if similar(g[0], q):
                g[1] += 1
                break
        else:
            groups.append([q, 1])
    return [(g[0], g[1]) for g in sorted(groups, key=lambda g: -g[1]) if g[1] >= min_repeats][:top]


class DraftStore:
    def __init__(self, path, clock=time.time):
        self.path, self.clock = path, clock

    def _all(self):
        return (statefile.load(self.path, None) or {}).get("drafts", [])

    def live(self):
        now = self.clock()
        return [d for d in self._all() if now - d["created"] <= d.get("ttl_s", TTL_S)]

    def put(self, question, answer, source="GLM"):
        now = self.clock()
        key = norm(question)

        def upd(cur):
            ds = [d for d in cur.get("drafts", []) if d["key"] != key and now - d["created"] <= d.get("ttl_s", TTL_S)]
            ds.append({"key": key, "question": question, "answer": answer, "source": source, "created": now, "ttl_s": TTL_S, "hits": 0})
            return {"drafts": ds[-200:]}
        statefile.update(self.path, upd, {})

    def lookup(self, text, count_hit=True):
        """-> {'text', 'draft'} или None. text содержит пометку источника и времени заготовки."""
        if not eligible(text):
            return None
        for d in self.live():
            if similar(d["question"], text):
                if count_hit:
                    def upd(cur):
                        for x in cur.get("drafts", []):
                            if x["key"] == d["key"]:
                                x["hits"] = x.get("hits", 0) + 1
                        return cur
                    try:
                        statefile.update(self.path, upd, {})
                    except OSError:
                        pass
                hh = time.strftime("%H:%M", time.gmtime(d["created"] + 3 * 3600))
                return {"text": d["answer"].rstrip() + "\n\n(заготовлено ночью в %s по Москве, источник: %s; если вопрос про свежие данные - спросите «обнови»)" % (hh, d["source"]), "draft": d}
        return None

    def purge(self):
        live = self.live()
        statefile.save(self.path, {"drafts": live})
        return len(live)


def gen_via_gateway(question, url=None, timeout=900):
    """Ответ GLM через шлюз (deep_only, без размышлений): медленно (~1,5 ток/с), поэтому только ночью."""
    url = url or os.environ.get("NOX_GATEWAY_URL", "http://127.0.0.1:8082")
    body = {"nox_mode": "deep_only", "nox_no_route": True, "max_tokens": 600, "stream": False, "messages": [{"role": "user", "content": question}],
            "chat_template_kwargs": {"enable_thinking": False}}
    req = urllib.request.Request(url.rstrip("/") + "/v1/chat/completions", json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return (json.loads(r.read())["choices"][0]["message"].get("content") or "").strip()


def build(state_dir, gen=gen_via_gateway, now=None, top=10, force=False, dry_run=False, extra=None, days=14, clock_check=None, store=None):
    """gen(question)->str. clock_check() -> True, чтобы прервать (вышли из тихих часов: ночь кончилась - не мешаем днём)."""
    now = time.time() if now is None else now
    if not force and not in_quiet(now):
        return {"status": "skipped", "reason": "не тихие часы"}
    turns = tune.load_turns(state_dir, now, days)
    cand = top_questions(turns, top, extra=extra)
    if not cand:
        return {"status": "no_candidates", "turns": len(turns)}
    store = store or DraftStore(os.path.join(state_dir, "drafts.json"), clock=lambda: now)
    have = store.live()
    made, failed, kept = [], [], 0
    for q, n in cand:
        if any(similar(d["question"], q) for d in have):
            kept += 1
            continue
        if clock_check and clock_check():
            break
        try:
            a = gen(q)
        except Exception as e:
            failed.append({"q": q[:80], "err": type(e).__name__})
            continue
        if not a or len(a) < 20:
            failed.append({"q": q[:80], "err": "empty"})
            continue
        if not dry_run:
            store.put(q, a)
        made.append({"q": q[:80], "repeats": n})
    return {"status": "dry" if dry_run else "built", "made": made, "failed": failed, "kept": kept}


def evaluate(store, records, judge=None, n=50):
    """Проверочный набор: records=[{text, answer}] (эталонные ответы GLM). -> доля мгновенных и паритет по judge(draft_text, ref)->0..1 (по умолч. Jaccard основ)."""
    judge = judge or (lambda d, r: len(stems(d) & stems(r)) / max(1, len(stems(d) | stems(r))))
    hits, par = 0, []
    rs = records[-n:]
    for r in rs:
        h = store.lookup(r["text"], count_hit=False)
        if h:
            hits += 1
            par.append(judge(h["draft"]["answer"], r["answer"]))
    return {"n": len(rs), "instant_share": round(hits / len(rs), 3) if rs else 0.0, "parity": round(sum(par) / len(par), 3) if par else None}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "stats", "purge"])
    ap.add_argument("--state", default=os.environ.get("RTE_STATE_DIR", "/root/nox/state/rte"))
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    st = DraftStore(os.path.join(a.state, "drafts.json"))
    if a.cmd == "build":
        r = build(a.state, top=a.top, force=a.force, dry_run=a.dry_run, clock_check=lambda: not in_quiet(time.time()) and not a.force)
    elif a.cmd == "purge":
        r = {"status": "purged", "left": st.purge()}
    else:
        ds = st.live()
        r = {"status": "stats", "live": len(ds), "hits": sum(d.get("hits", 0) for d in ds)}
    print(json.dumps(r, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
