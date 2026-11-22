"""Помощники авторинга заданий MIND-BENCH (генерируют tasks/*.json). Паттерны - нижний регистр, ё->е."""
import json, os, hashlib

SUF = " Ответь коротко, в конце напиши «Уверенность: N%»."


def S(say, ref, checks=None, s="A", sleep=0, bad=None, **kw):
    d = {"s": s, "say": say, "ref": ref}
    if checks:
        d["checks"] = checks
    if sleep:
        d["sleep"] = sleep
    if bad:
        d["bad"] = bad
    d.update(kw)
    return d


def has(*p, w=1, name=None):
    return {"t": "has", "any": list(p), "w": w, **({"name": name} if name else {})}


def hasall(*p, w=1):
    return {"t": "hasall", "all": list(p), "w": w}


def no(*p, w=1, name=None):
    return {"t": "not", "any": list(p), "w": w, **({"name": name} if name else {})}


def maxs(n, w=1):
    return {"t": "maxs", "max": n, "w": w}


def nolist(w=1):
    return {"t": "nolist", "w": w}


def noemoji(w=1):
    return {"t": "noemoji", "w": w}


def words(lo=0, hi=10 ** 6, w=1):
    return {"t": "words", "min": lo, "max": hi, "w": w}


def hedge(w=1):
    return {"t": "hedge", "w": w}


def nohedge(w=1):
    return {"t": "nohedge", "w": w}


def num(v=None, expr=None, w=1):
    return {"t": "num", **({"val": v} if v is not None else {"expr": expr}), "w": w}


def calib(gold=None, w=3):
    return {"t": "calib", "w": w, **({"gold": gold} if gold else {})}


def fid(cat, slot=None, w=3):
    return {"t": "fid", "cat": cat, "w": w, **({"slot": slot} if slot else {})}


def T(id, axis, steps, title="", vars=None, judge=None, w=1, crit=False, learn=None):
    d = {"id": id, "axis": axis, "title": title, "w": w, "steps": steps}
    if vars:
        d["vars"] = vars
    if judge:
        d["judge"] = judge
    if crit:
        d["crit"] = True
    if learn:
        d["learn"] = learn
    return d


def th(t):
    steps = [{k: v for k, v in s.items() if k not in ("ref", "bad")} for s in t["steps"]]
    core = {"axis": t["axis"], "steps": steps, "vars": t.get("vars"), "judge": t.get("judge"),
            "learn": t.get("learn"), "w": t.get("w", 1), "crit": t.get("crit", False)}
    return hashlib.sha256(json.dumps(core, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]


def write(path, version, tasks, note):
    d = {"suite": "MIND-BENCH NOX", "version": version, "note": note,
         "manifest": hashlib.sha256(json.dumps([th(t) for t in tasks], ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12],
         "tasks": tasks}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    print(path, len(tasks))


def causal(id, ep, probe, lesson_re, lesson_ref, plain_ref, bad, title="", token=False, X=None):
    """Контрфактуал «до/после эпизода»: P0 - проба ДО эпизода (базовая линия), A - эпизод, B - та же проба ПОСЛЕ (новая сессия).
    Если урок уже виден до эпизода - задание неинформативно (эффект не от эпизода) и исключается."""
    chk = [has(*lesson_re, w=2, name="поведение изменилось по эпизоду")]
    if token:
        chk.append(has("{X}", "прошлый раз", "тот случай", w=1, name="опирается на эпизод"))
    return T(id, "causal", [
        S(probe, plain_ref, s="P0"),
        S("[EVAL] Запомни случай «{X}». " + ep, "Запомнила случай «{X}».", s="A"),
        S(probe, lesson_ref, chk, s="B", sleep=3, bad=bad)],
        title=title, vars={"X": X or ["Янтарь", "Бирюза", "Кедр", "Ковыль", "Маяк", "Лазурит", "Ястреб", "Тюльпан"]},
        learn={"trap_step": 0, "trap_any": list(lesson_re), "invert": True, "mode": "cf"})


def learn(id, trial, trial_ref, lesson, final, final_ref, trap, final_checks, bad, mode="ctx", nohedge=False, title=""):
    """Обучение из ошибки: проба -> урок -> похожая проба. Информативно, только если ошибка проявилась в пробе."""
    sb = "B" if mode == "xsess" else "A"
    return T(id, "learning", [
        S(trial, trial_ref, s="A"),
        S(lesson, "Поняла, исправлюсь и запомню правило.", s="A"),
        S(final, final_ref, final_checks, s=sb, sleep=3 if mode == "xsess" else 0, bad=bad)],
        title=title, w=1.0, learn={"trap_step": 0, "trap_any": trap, "mode": mode, **({"nohedge": True} if nohedge else {})})
