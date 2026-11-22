#!/usr/bin/env python3
"""SLP-02 build_kto: дневные данные NOX -> KTO-датасет (prompt/completion/label) + replay + holdout + статистика.
Источники: feedback.jsonl (👍/👎 мессира, главный сигнал), turns.jsonl (неявные сигналы: поправка мессира = негатив, явная благодарность = слабый позитив),
опционально учитель (GLM) переписывает ответы с 👎 в позитивы (дистилляция), replay из принятых прежде датасетов.
Защиты: секреты вырезаются, промпты из теста верности не попадают в обучение (нет утечки holdout), лимит примеров за ночь,
баланс весов по рекомендации TRL (desirable*pos : undesirable*neg ≈ 1.1:1), режим kto|sft|skip по наличию классов.
Только stdlib. Пример:
  python3 build_kto.py --state /root/nox/state --system soul_prompt_ru.txt --out /root/nox/state/sleep/2026-11-22/data --since-hours 24
"""
import argparse, hashlib, json, os, random, re, sys, time, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SECRET = re.compile(r"(ghp_[A-Za-z0-9]{20,}|github_pat_\w{20,}|sk-[A-Za-z0-9]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY|AKIA[0-9A-Z]{16}|(?i:password|пароль|token|токен)\s*[:=]\s*\S{6,})")
CORRECTION = re.compile(r"^\W*(?:нет\b|неправильно|не так\b|ты ошиб|ошибся|ты не прав|неверно|это не то|я не об этом|не то\b|опять не так)", re.I)
THANKS = re.compile(r"(?:спасибо|отлично|супер|молодец|именно то|то что нужно|вот это да|класс\b)", re.I)


def jl(path):
    if not os.path.exists(path):
        return []
    out = []
    for l in open(path, encoding="utf-8", errors="replace"):
        l = l.strip()
        if l:
            try:
                out.append(json.loads(l))
            except ValueError:
                pass
    return out


def nkey(s):
    return re.sub(r"\s+", " ", (s or "").lower().replace("ё", "е")).strip()


def hkey(p, c):
    return hashlib.sha1((nkey(p) + "\x1f" + nkey(c)).encode()).hexdigest()


def bucket(key):  # детерминированный сплит: 10% в eval
    return int(key[:8], 16) % 10 == 0


def teacher_rewrite(url, model, system, q, bad, timeout):
    msg = [{"role": "system", "content": system}, {"role": "user", "content": q + "\n\n(Прежний ответ мессиру не понравился, он был таким: «" + bad[:600] + "». Дай лучший ответ в своём характере: честно, по делу, без лести.)"}]
    req = urllib.request.Request(url.rstrip("/") + "/v1/chat/completions", data=json.dumps({"model": model, "messages": msg, "temperature": 0.7, "max_tokens": 400}).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        t = json.loads(r.read().decode())["choices"][0]["message"]["content"] or ""
    return re.sub(r"<think>.*?</think>", "", t, flags=re.S).strip()


def collect(state, since, extra_block=()):
    """-> список кандидатов {q, a, label, src, t}."""
    out = []
    for f in jl(os.path.join(state, "feedback.jsonl")):
        if f.get("q") and f.get("a") and (f.get("t") or since) >= since:
            c = {"q": f["q"], "a": f["a"], "label": f.get("v") == 1, "src": "predictive" if f.get("src") == "predictive_self" else "explicit", "t": f.get("t") or since}
            for k in ("outcome", "disagree"):   # проверяемый исход / возражение NOX (проставляет R2/sleep_feed)
                if k in f:
                    c[k] = f[k]
            out.append(c)
    turns = sorted([t for t in jl(os.path.join(state, "turns.jsonl")) if t.get("u") and t.get("a")], key=lambda t: t.get("t", 0))
    for i in range(1, len(turns)):
        prev, cur = turns[i - 1], turns[i]
        if cur.get("t", 0) < since or cur["t"] - prev.get("t", 0) > 900:
            continue
        if CORRECTION.search(cur["u"]):
            out.append({"q": prev["u"], "a": prev["a"], "label": False, "src": "implicit_correction", "t": cur["t"], "correction": cur["u"][:300]})
        elif THANKS.search(cur["u"]) and len(cur["u"]) < 80:
            out.append({"q": prev["u"], "a": prev["a"], "label": True, "src": "implicit_thanks", "t": cur["t"]})
    return out


def clean(cands, block_prompts, min_len=5, max_len=1800):
    seen, res, dropped = set(), [], {"secret": 0, "short": 0, "dup": 0, "leak": 0, "long": 0}
    for c in cands:
        q, a = (c["q"] or "").strip(), (c["a"] or "").strip()
        if SECRET.search(q) or SECRET.search(a):
            dropped["secret"] += 1; continue
        if len(a) < min_len or len(q) < 2:
            dropped["short"] += 1; continue
        if len(a) > max_len:
            dropped["long"] += 1; continue
        if nkey(q) in block_prompts:
            dropped["leak"] += 1; continue
        k = hkey(q, a)
        if k in seen:
            dropped["dup"] += 1; continue
        seen.add(k); c["key"] = k; res.append(c)
    return res, dropped


# ---- защита «учится нравиться, а не быть точной» (решение Создателя 22.11) ----
APPROVAL_WEIGHT = 0.5      # награда только от согласия/похвалы без проверяемого исхода
DISAGREE_RIGHT_WEIGHT = 1.5  # NOX возразил и оказался прав (исход проверен)
APPROVAL_CAP = 0.2         # доля approval_only в датасете не больше


def reward_kind(c):
    """approval_only | disagree_right | verified | negative. Проверяемый исход: outcome=True, правила/исполнитель (growth_/corpus/teacher не от похвалы)."""
    if c.get("reward_kind"):
        return c["reward_kind"]
    if not c["label"]:
        return "negative"
    if c.get("disagree") and c.get("outcome") is True:
        return "disagree_right"
    if c.get("outcome") is True or c["src"] in ("corpus", "teacher"):
        return "verified"
    if c["src"] in ("implicit_thanks", "predictive") or (c["src"] == "explicit" and ("outcome" in c or "disagree" in c)):
        return "approval_only"       # «спасибо»/реакция/👍 без исхода (👍 - после аннотации ночью sleep_feed.annotate_feedback; без аннотации исход неизвестен)
    return "verified"


def row_weight(kind):
    return {"approval_only": APPROVAL_WEIGHT, "disagree_right": DISAGREE_RIGHT_WEIGHT}.get(kind, 1.0)


def cap_approval(rows, cap=APPROVAL_CAP):
    """Оставляет approval_only не больше cap от всех строк (свежие приоритетнее). -> (rows, отброшено)."""
    ap = [r for r in rows if r["reward_kind"] == "approval_only"]
    others = len(rows) - len(ap)
    keep = int(cap / (1 - cap) * others + 1e-9) if cap < 1 else len(ap)
    if len(ap) <= keep:
        return rows, 0
    ap.sort(key=lambda r: -r.get("t", 0))
    drop = {r["key"] for r in ap[keep:]}
    return [r for r in rows if r["key"] not in drop], len(drop)


def balance(pos, neg, target=1.1):
    if not pos or not neg:
        return 1.0, 1.0
    if pos >= neg * target:
        return 1.0, round(pos / neg / target, 3)
    return round(neg * target / pos, 3), 1.0


def build(a, now=None):
    now = now or int(time.time())
    since = now - int(a.since_hours * 3600)
    system = open(a.system, encoding="utf-8").read().strip() if a.system else ""
    block = set()
    if not a.no_leak_guard:
        import fidelity_cases
        block = {nkey(c["prompt"]) for c in fidelity_cases.all_cases()}
    cands = collect(a.state, since)
    cands, dropped = clean(cands, block)
    # приоритет: явные оценки, затем поправки, затем благодарности; внутри — свежие. Лимит за ночь + не более 25% позитивов из неявной благодарности.
    order = {"explicit": 0, "predictive": 1, "implicit_correction": 1, "implicit_thanks": 2}
    cands.sort(key=lambda c: (order[c["src"]], -c["t"]))
    thanks_cap = None
    sel, n_thanks = [], 0
    pos_exp = sum(1 for c in cands if c["label"] and c["src"] == "explicit")
    thanks_cap = max(2, pos_exp // 3)
    for c in cands:
        if c["src"] == "implicit_thanks":
            if n_thanks >= thanks_cap:
                continue
            n_thanks += 1
        sel.append(c)
        if len(sel) >= a.max_new:
            break
    # дистилляция: ответы с 👎 -> позитив от учителя (GLM). Медленно (≈1,5 ток/с), поэтому малый лимит и таймаут; сбой не критичен.
    distilled, teach_err = 0, 0
    if a.teacher:
        for c in [c for c in sel if not c["label"] and c["src"] == "explicit"][:a.teacher_max]:
            try:
                better = teacher_rewrite(a.teacher, a.teacher_model, system, c["q"], c["a"], a.teacher_timeout)
            except Exception:
                teach_err += 1
                continue
            if len(better) >= 5 and not SECRET.search(better) and nkey(better) != nkey(c["a"]):
                sel.append({"q": c["q"], "a": better, "label": True, "src": "teacher", "t": c["t"], "key": hkey(c["q"], better)})
                distilled += 1
    # знания процедурные: строки corpus_build (instruction/output из карточек и коммитов) как позитивы, не более доли от новых
    n_corpus = 0
    if a.corpus and os.path.exists(a.corpus):
        have = {c["key"] for c in sel}
        pool = [r for r in jl(a.corpus) if r.get("instruction") and r.get("output")]
        random.Random(a.seed + 1).shuffle(pool)
        cap = min(a.corpus_max, max(0, int(len(sel) * 0.2)) if sel else a.corpus_max)
        for r in pool:
            if n_corpus >= cap:
                break
            k = hkey(r["instruction"], r["output"])
            if k in have or SECRET.search(r["output"]) or nkey(r["instruction"]) in block or len(r["output"]) > 1800:
                continue
            sel.append({"q": r["instruction"], "a": r["output"], "label": True, "src": "corpus", "t": since, "key": k}); have.add(k); n_corpus += 1
    # replay: ранее принятые данные (против забывания), доля от новых
    replay = []
    if a.replay_dir and os.path.isdir(a.replay_dir):
        pool = []
        for fn in sorted(os.listdir(a.replay_dir)):
            if fn.endswith(".jsonl"):
                pool += [r for r in jl(os.path.join(a.replay_dir, fn)) if r.get("key") and r.get("src") != "replay"]
        have = {c["key"] for c in sel}
        pool = [r for r in pool if r["key"] not in have]
        rnd = random.Random(a.seed)
        rnd.shuffle(pool)
        replay = [dict(r, src="replay") for r in pool[:int(len(sel) * a.replay_ratio + 0.999) if sel else min(len(pool), a.replay_min)]]
    allrows = sel + replay
    for r in allrows:
        r["reward_kind"] = reward_kind(r)
        r["weight"] = row_weight(r["reward_kind"])
    allrows, approval_dropped = cap_approval(allrows, a.approval_cap)
    train = [r for r in allrows if not bucket(r["key"])]
    evalr = [r for r in allrows if bucket(r["key"])]
    npos = sum(1 for r in train if r["label"]); nneg = len(train) - npos
    dw, uw = balance(sum(r["weight"] for r in train if r["label"]), sum(r["weight"] for r in train if not r["label"]))
    reasons = []
    if npos >= a.min_pos and nneg >= a.min_neg:
        mode = "kto"
    elif npos >= a.min_pos:
        mode = "sft"; reasons.append("негативов %d < %d: только SFT по позитивам" % (nneg, a.min_neg))
    else:
        mode = "skip"; reasons.append("позитивов %d < %d: учиться нечему, ночь без обучения" % (npos, a.min_pos))
    stats = {"t": now, "since": since, "mode": mode, "reasons": reasons, "train": len(train), "eval": len(evalr), "pos": npos, "neg": nneg,
             "desirable_weight": dw, "undesirable_weight": uw, "new": len(sel), "replay": len(replay), "distilled": distilled, "corpus": n_corpus, "teacher_errors": teach_err,
             "dropped": dropped, "approval_dropped": approval_dropped, "approval_share": round(sum(1 for r in allrows if r["reward_kind"] == "approval_only") / max(1, len(allrows)), 3),
             "by_kind": {k: sum(1 for r in allrows if r["reward_kind"] == k) for k in ("approval_only", "disagree_right", "verified", "negative")},
             "by_src": {s: sum(1 for r in allrows if r["src"] == s) for s in ("explicit", "implicit_correction", "implicit_thanks", "predictive", "teacher", "corpus", "replay")}}
    return stats, train, evalr, system


def to_row(r, system):
    prompt = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": r["q"]}]
    return {"prompt": prompt, "completion": [{"role": "assistant", "content": r["a"]}], "label": bool(r["label"]), "key": r["key"], "src": r["src"],
            "weight": r.get("weight", 1.0), "reward_kind": r.get("reward_kind", "verified")}


def write(out, stats, train, evalr, system):
    os.makedirs(out, exist_ok=True)
    for name, rows in (("kto_train.jsonl", train), ("kto_eval.jsonl", evalr)):
        with open(os.path.join(out, name), "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(to_row(r, system), ensure_ascii=False) + "\n")
    # архив «сырых» строк для будущего replay (с ключами)
    with open(os.path.join(out, "replay_pool.jsonl"), "w", encoding="utf-8") as f:
        for r in train:
            if r["src"] != "replay":
                f.write(json.dumps({k: r[k] for k in ("q", "a", "label", "src", "t", "key", "reward_kind")}, ensure_ascii=False) + "\n")
    with open(os.path.join(out, "stats.json"), "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=1)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--state", default="/root/nox/state"); ap.add_argument("--system", help="soul_prompt_ru.txt (тот же, что в проде)")
    ap.add_argument("--out", required=True); ap.add_argument("--since-hours", type=float, default=24)
    ap.add_argument("--max-new", type=int, default=600); ap.add_argument("--min-pos", type=int, default=30); ap.add_argument("--min-neg", type=int, default=30)
    ap.add_argument("--replay-dir", help="каталог с прежними replay_pool.jsonl"); ap.add_argument("--replay-ratio", type=float, default=0.5); ap.add_argument("--replay-min", type=int, default=0)
    ap.add_argument("--teacher"); ap.add_argument("--teacher-model", default="default"); ap.add_argument("--teacher-max", type=int, default=20); ap.add_argument("--teacher-timeout", type=int, default=300)
    ap.add_argument("--corpus", help="jsonl из selftools corpus_build"); ap.add_argument("--corpus-max", type=int, default=60)
    ap.add_argument("--approval-cap", type=float, default=APPROVAL_CAP); ap.add_argument("--seed", type=int, default=7); ap.add_argument("--no-leak-guard", action="store_true"); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    stats, train, evalr, system = build(a)
    if not a.dry_run:
        write(a.out, stats, train, evalr, system)
    print(json.dumps(stats, ensure_ascii=False))
    return 0 if stats["mode"] != "skip" else 3


if __name__ == "__main__":
    sys.exit(main())
