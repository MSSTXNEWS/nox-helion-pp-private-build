"""growth (M5): автотелическая учебная программа NOX — разум, который сам ставит себе задачи на границе умений.

Петля одного занятия (session): голод знаний -> бюджет -> (1) повторения по расписанию (шрамы и уроки) ->
(2) выбор ячейки (область, уровень) по learning progress и зоне ближайшего развития (ЗБР) -> (3) задача из якорей
или от генератора (с проверкой «решаема и проверяема») -> (4) решение быстрой моделью (подсказки по лесенке) ->
(5) проверка правилами/исполнением кода (судья - слабый источник) -> (6) события: LP, SRS, дневник, влечения, данные ко сну.

Источники идей (чужие, подробности в M5_GROWTH.md): Oudeyer IMGEP/CURIOUS (выбор цели по |learning progress|),
Schmidhuber (интерес = compression progress, а не шум), R-Zero/R-Few/Absolute Zero (задачи около 50% успеха,
проверка исполнителем, якоря от человека против коллапса), FSRS (кривая забывания R=(1+t/9S)^-1), Выготский (ЗБР, строительные леса).
Числовые константы - рабочие договорённости (гипотеза, мерить A/B), кроме формул, явно названных чужими.

Зависимости: только stdlib + COMMON (statefile, quiet). Модель и судья подаются снаружи (в тестах - фейки).
"""
import os as _os, sys as _sys  # общие модули COMMON (statefile/quiet/fastq/datafence)
_HERE = _os.path.dirname(_os.path.abspath(__file__))
for _c in (_os.environ.get("NOX_COMMON", ""), _os.path.join(_HERE, "..", "..", "COMMON"), _os.path.join(_HERE, "common"), _os.path.join(_HERE, "..", "common")):
    if _c and _os.path.isdir(_c) and _c not in _sys.path:
        _sys.path.append(_c)
import argparse
import hashlib
import json
import math
import os
import random
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone

import statefile
from quiet import in_quiet

MSK = timezone(timedelta(hours=3))
DAY = 86400.0
LEVELS = 5
TARGET_P = 0.6                 # ЗБР: целевая вероятность успеха (гипотеза: 0.5..0.75, мерить A/B)
SRC_W = {"creator": 1.0, "rule": 0.7, "judge": 0.5, "self": 0.3}   # веса источников исхода, как в SOUL_MIND_v7 §4
BUSY_NAMES = ("Deferred", "Busy", "SolverBusy")                    # fastq: чат/GLM заняты -> занятие прерывается, не провал
KINDS = ("number", "contains_all", "regex", "python_tests", "judge")
RULE_KINDS = ("number", "contains_all", "regex", "python_tests")
STOP = {"что", "как", "это", "для", "или", "при", "про", "где", "когда", "почему", "the", "and"}


class Unscorable(Exception):
    """Нет способа проверить ответ (нет судьи/исполнителя): событие не пишется, навык не наказывается."""


class SolverBusy(Exception):
    pass


# ============================================================ утилиты
def stems(q):
    return {w[:5] for w in re.findall(r"[a-zа-яё0-9]+", (q or "").lower()) if len(w) > 2 and w not in STOP}


def jac(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


def canon(o):
    return json.dumps(o, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha(s, n=12):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:n]


def msk_day(ts):
    return datetime.fromtimestamp(ts, MSK).strftime("%Y-%m-%d")


def extract_json(txt):
    txt = re.sub(r"<think>.*?</think>", "", txt or "", flags=re.S)
    dec = json.JSONDecoder()
    for m in re.finditer(r"\{", txt):
        try:
            o, _ = dec.raw_decode(txt[m.start():])
            if isinstance(o, dict):
                return o
        except ValueError:
            continue
    return None


def jl(path):
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        o = json.loads(line)
                        if isinstance(o, dict):
                            out.append(o)
                    except ValueError:
                        pass
    except OSError:
        pass
    return out


# ============================================================ проверка ответов
NUM_RE = re.compile(r"-?\d+(?:[.,]\d+)?")
DENY = re.compile(r"\b(import\s+(os|sys|subprocess|socket|shutil|ctypes|requests|urllib|pathlib)|from\s+(os|sys|subprocess|socket|shutil|ctypes|pathlib)\s+import|__import__|open\s*\(|eval\s*\(|exec\s*\(|compile\s*\()")


def run_python_tests(answer, tests, timeout=5.0):
    """Запуск кода ответа + тестов в отдельном процессе (python -I, rlimit, чистое окружение, таймаут). 1.0 / 0.0.
    Это защита второго рубежа: на сервере вызывать через selftools sandbox_run (unshare -n) подачей своего runner."""
    m = re.search(r"```(?:python|py)?\s*\n(.*?)```", answer or "", re.S)
    src = m.group(1) if m else (answer or "")
    if not src.strip() or DENY.search(src):
        return 0.0

    def limits():
        try:
            import resource
            resource.setrlimit(resource.RLIMIT_AS, (512 << 20, 512 << 20))
            resource.setrlimit(resource.RLIMIT_CPU, (int(timeout) + 2, int(timeout) + 2))
            resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
        except Exception:
            pass

    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "t.py")
        with open(p, "w", encoding="utf-8") as f:
            f.write(src + "\n\n" + tests + "\nprint('__OK__')\n")
        try:
            r = subprocess.run([sys.executable, "-I", p], cwd=d, capture_output=True, text=True, timeout=timeout,
                               env={"PATH": "/usr/bin:/bin"}, preexec_fn=limits)
        except (subprocess.TimeoutExpired, OSError):
            return 0.0
        return 1.0 if r.returncode == 0 and "__OK__" in r.stdout else 0.0


def check_answer(check, answer, judge=None, runner=None, prompt=""):
    """-> (score 0..1, источник 'rule'|'judge'). Бросает Unscorable, если проверить нечем."""
    k, a = check.get("kind"), answer or ""
    if k == "number":
        nums = NUM_RE.findall(a)
        if not nums:
            return 0.0, "rule"
        v = float(nums[-1].replace(",", "."))
        return (1.0 if abs(v - float(check["value"])) <= float(check.get("tol", 0)) + 1e-9 else 0.0), "rule"
    if k == "contains_all":
        low = a.lower()
        items = check["items"]
        return sum(1 for s in items if s.lower() in low) / len(items), "rule"
    if k == "regex":
        return (1.0 if re.search(check["pattern"], a.strip(), re.I | re.S) else 0.0), "rule"
    if k == "python_tests":
        return (runner or run_python_tests)(a, check["tests"]), "rule"
    if k == "judge":
        if judge is None:
            raise Unscorable("нет судьи")
        s = judge(prompt, a, check.get("criteria", ""))
        if s is None:
            raise Unscorable("судья не дал оценку")
        return max(0.0, min(1.0, float(s))), "judge"
    raise Unscorable("неизвестный вид проверки: %r" % k)


def make_judge(llm):
    """Судья на быстрой модели: JSON {"score":0..1}. Любая неопределённость -> None (Unscorable). Слабый источник (вес 0.5, в обучение не идёт)."""
    def judge(prompt, answer, criteria):
        q = ("Ты строгий проверяющий. Задача: %s\nКритерии: %s\nОтвет: %s\nОцени ответ числом 0..1 строго по критериям. "
             "Верни ТОЛЬКО JSON {\"score\": число}." % (prompt[:800], criteria[:400], (answer or "")[:1200]))
        try:
            o = extract_json(llm(q))
            return float(o["score"]) if o and "score" in o else None
        except Exception:
            return None
    return judge


# ============================================================ задачи: валидация и генерация
def validate_task(t, judge=None, runner=None, seen=(), exam_stems=(), allow_judge=True):
    """-> (ok, причина). Задача принимается, только если она решаема (эталон проходит проверку), проверяема и не «взламывается»
    (пустой ответ и эхо условия проверку не проходят), не дубль и не утечка экзамена."""
    try:
        area, lvl, prompt, chk = t["area"], t["level"], t["prompt"], t["check"]
    except (KeyError, TypeError):
        return False, "нет обязательных полей"
    if not isinstance(area, str) or not 1 <= len(area.strip()) <= 40:
        return False, "область"
    if not isinstance(lvl, int) or isinstance(lvl, bool) or not 1 <= lvl <= LEVELS:
        return False, "уровень"
    if not isinstance(prompt, str) or not 10 <= len(prompt) <= 1200:
        return False, "длина условия"
    if not isinstance(chk, dict) or chk.get("kind") not in KINDS:
        return False, "вид проверки"
    hints = t.get("hints", [])
    if not isinstance(hints, list) or len(hints) > 2 or any(not isinstance(h, str) or not h.strip() for h in hints):
        return False, "подсказки"
    k = chk["kind"]
    low = prompt.lower()
    try:
        if k == "number":
            float(chk["value"])
        elif k == "contains_all":
            items = chk["items"]
            if not isinstance(items, list) or not items or any(not isinstance(s, str) or len(s.strip()) < 2 for s in items):
                return False, "items"
            if any(s.lower() in low for s in items):
                return False, "ключ проверки содержится в условии"
        elif k == "regex":
            re.compile(chk["pattern"])
            if re.search(chk["pattern"], "", re.I | re.S):
                return False, "regex принимает пустой ответ"
        elif k == "python_tests":
            if not isinstance(chk["tests"], str) or "assert" not in chk["tests"]:
                return False, "тесты без assert"
        elif k == "judge":
            if not allow_judge or not str(chk.get("criteria", "")).strip():
                return False, "judge не разрешён или нет критериев"
    except (KeyError, ValueError, TypeError, re.error):
        return False, "параметры проверки"
    if k in RULE_KINDS:
        ref = t.get("reference")
        if not isinstance(ref, str) or not ref.strip():
            return False, "нет эталона"
        try:
            if check_answer(chk, ref, runner=runner)[0] < 0.999:
                return False, "эталон не проходит собственную проверку"
            for bad in ("", prompt):                                  # отрицательные контроли против тривиальных проверок
                if check_answer(chk, bad, runner=runner)[0] >= 0.999:
                    return False, "проверка пропускает пустой ответ или эхо условия"
        except Unscorable:
            return False, "проверка не выполнима"
    st = stems(prompt)
    for s in seen:
        if jac(st, set(s)) >= 0.6:
            return False, "дубль"
    for s in exam_stems:
        if jac(st, set(s)) >= 0.7:
            return False, "похоже на экзаменационную задачу"
    return True, "ok"


LEVEL_TXT = {1: "базовый (школьный, одно действие)", 2: "простой (2-3 шага)", 3: "средний (нужно рассуждение)",
             4: "сложный (несколько приёмов, аккуратность)", 5: "экспертный (олимпиадный/нетривиальный)"}


def gen_prompt(area, level, examples, avoid):
    ex = "\n".join("- " + json.dumps({k: e[k] for k in ("prompt", "check", "reference") if k in e}, ensure_ascii=False) for e in examples[:2])
    av = "\n".join("- " + a[:120] for a in avoid[-5:])
    return ("Придумай ОДНУ новую учебную задачу для ИИ-ассистента.\nОбласть: %s. Уровень %d из 5: %s.\n"
            "Требования: задача решаема, ответ проверяется ПРАВИЛОМ без человека. Виды проверки (check.kind): "
            "number {value,tol}, contains_all {items:[строки, которых НЕТ в условии]}, regex {pattern}, python_tests {tests: строки assert, функция называется в условии}. "
            "Дай эталонный ответ reference, который сам проходит проверку, и до 2 подсказок hints (от общей к конкретной).\n"
            "Примеры формата и стиля:\n%s\nНе повторяй недавние:\n%s\n"
            "Верни ТОЛЬКО JSON: {\"prompt\":..., \"check\":{...}, \"reference\":..., \"hints\":[...]}" % (area, level, LEVEL_TXT[level], ex or "(нет)", av or "(нет)"))


def lesson_prompt(question, quote):
    return ("Вот проверенная цитата из источника:\n«%s»\nСоставь по ней ОДИН проверочный вопрос про «%s» и 1-3 ключевые строки ответа, "
            "которые ДОСЛОВНО встречаются в цитате и НЕ встречаются в вопросе. Верни ТОЛЬКО JSON: {\"prompt\":..., \"items\":[...]}" % (quote[:900], question[:200]))


# ============================================================ learning progress, ЗБР, SRS (чистые функции)
def wmean(xs):
    sw = sum(w for _, w in xs)
    return sum(s * w for s, w in xs) / sw if sw else 0.0


def learning_progress(xs, window=12, min_n=4):
    """|разность взвешенных средних новой и старой половин окна| (Oudeyer: абсолютный LP, чтобы замечать и забывание),
    с поправкой на шум: при |d| < стандартной ошибки LP гасится (защита от «шумного телевизора», Schmidhuber).
    xs - [(score, weight)] от старых к новым."""
    xs = xs[-window:]
    n = len(xs)
    if n < min_n:
        return 0.0
    h = n // 2
    old, new = xs[:h], xs[n - h:]
    d = wmean(new) - wmean(old)
    vals = [s for s, _ in xs]
    mu = sum(vals) / n
    var = sum((v - mu) ** 2 for v in vals) / (n - 1)
    se = math.sqrt(var * (1.0 / len(old) + 1.0 / len(new)))
    shrink = 1.0 if se < 1e-9 else min(1.0, abs(d) / se)
    return abs(d) * shrink


def prior_p(level):
    """Априорная вероятность успеха на уровне (до данных): 0.9, 0.63, 0.44, 0.31, 0.22."""
    return 0.9 * 0.7 ** (level - 1)


def zpd_fit(p, target=TARGET_P, width=0.4):
    return max(0.0, 1.0 - abs(p - target) / width)


def retrievability(days, S):
    """Кривая забывания FSRS-4 (R=0.9 при t=S): R=(1+t/(9S))^-1. S - устойчивость в сутках."""
    return 1.0 / (1.0 + max(0.0, days) / (9.0 * S))


def interval_days(S, r=0.9):
    return 9.0 * S * (1.0 / r - 1.0)


def srs_update(item, passed, now):
    """Обновление устойчивости. Упрощённая форма в духе FSRS (константы - гипотеза, мерить A/B).
    Желательная трудность: чем ниже R в момент успешного повторения, тем больше прирост S."""
    days = (now - item["last"]) / DAY
    R = retrievability(days, item["S"])
    if passed:
        item["S"] = item["S"] * (1.0 + 1.2 * (1.0 - 0.07 * (item["D"] - 1.0)) * (1.5 - R))
        item["D"] = max(1.0, item["D"] - 0.15)
        item["reps"] += 1
    else:
        item["S"] = max(0.25, item["S"] * 0.35)
        item["D"] = min(10.0, item["D"] + 0.8)
        item["lapses"] += 1
        item["reps"] = 0
    item["last"] = now
    item["due"] = now + interval_days(item["S"]) * DAY
    return R


def ols(xs, ys):
    """-> (наклон, t-статистика). Нужно >=3 точек."""
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if n < 3 or sxx == 0:
        return 0.0, 0.0
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    res = sum((y - (my + b * (x - mx))) ** 2 for x, y in zip(xs, ys))
    se = math.sqrt(res / (n - 2) / sxx) if n > 2 else 0.0
    if se < 1e-12:
        return b, (math.inf if b > 0 else -math.inf if b < 0 else 0.0)
    return b, b / se


# ============================================================ дневник (hash-chain, дописывается)
class Diary:
    def __init__(self, path):
        self.path = path

    def read(self):
        return jl(self.path)

    def append(self, kind, data, now):
        rows = self.read()
        prev = rows[-1]["h"] if rows else "0" * 12
        rec = {"t": int(now), "kind": kind, "data": data, "prev": prev}
        rec["h"] = sha(canon(rec))
        statefile.append_line(self.path, json.dumps(rec, ensure_ascii=False))
        return rec

    def verify(self):
        prev = "0" * 12
        for i, r in enumerate(self.read()):
            body = {k: r[k] for k in ("t", "kind", "data", "prev")}
            if r.get("prev") != prev or r.get("h") != sha(canon(body)):
                return False, i
            prev = r["h"]
        return True, None


# ============================================================ влечения и карта незнания (адаптеры к EMO и ACT)
class DrivesHooks:
    """EMO drives.Drives: ошибка -> observe (любопытство по прогрессу), уровень -> mastery, голод знаний задаёт бюджет."""
    def __init__(self, drives):
        self.d = drives

    def on_outcome(self, area, level, score, assisted):
        self.d.observe(area, 1.0 - score)

    def on_levelup(self, area, level):
        self.d.satisfy("mastery", 0.1)

    def on_session(self, summary):
        if summary.get("new_pass"):
            self.d.satisfy("knowledge", min(0.3, 0.05 * summary["new_pass"]))

    def hunger(self):
        return self.d.level.get("knowledge", 0.5)


class GapHooks:
    """ACT gap_map.GapMap: сколько открытых вопросов по теме -> давление на область (need)."""
    def __init__(self, gapmap):
        self.g = gapmap

    def gap_open(self):
        return {t: v["open"] for t, v in self.g.coverage().items() if v["open"]}


class Hooks:
    def __init__(self, *hs):
        self.hs = hs

    def _each(self, name, *a):
        for h in self.hs:
            f = getattr(h, name, None)
            if f:
                f(*a)

    def on_outcome(self, *a):
        self._each("on_outcome", *a)

    def on_levelup(self, *a):
        self._each("on_levelup", *a)

    def on_session(self, *a):
        self._each("on_session", *a)

    def hunger(self):
        for h in self.hs:
            f = getattr(h, "hunger", None)
            if f:
                return f()
        return 0.5

    def gap_open(self):
        out = {}
        for h in self.hs:
            f = getattr(h, "gap_open", None)
            if f:
                for k, v in f().items():
                    out[k] = out.get(k, 0) + v
        return out


# ============================================================ основной класс
class Growth:
    def __init__(self, state_dir, solver, llm=None, judge=None, runner=None, hooks=None, anchors_path=None,
                 rng=None, clock=time.time, anchor_share=0.5, eps=0.15, day_cap=40, repeat_cooldown_days=2.0):
        """solver(prompt)->str (быстрая модель); llm(prompt)->str (генератор задач; None - только якоря);
        judge(prompt, answer, criteria)->float|None; runner(answer, tests)->0|1 (песочница); hooks - Hooks(...)."""
        self.dir = state_dir
        os.makedirs(state_dir, exist_ok=True)
        self.solver, self.llm, self.judge, self.runner = solver, llm, judge, runner
        self.hooks = hooks or Hooks()
        self.rng = rng or random.Random()
        self.clock = clock
        self.anchor_share, self.eps, self.day_cap, self.cool = anchor_share, eps, day_cap, repeat_cooldown_days
        self.p_state = os.path.join(state_dir, "growth.json")
        self.diary = Diary(os.path.join(state_dir, "growth_diary.jsonl"))
        self.p_train = os.path.join(state_dir, "growth_feedback.jsonl")
        self.p_lessons = os.path.join(state_dir, "lessons.jsonl")
        self.p_creator = os.path.join(state_dir, "anchors_creator.jsonl")
        self.st = statefile.load(self.p_state, None) or {"areas": {}, "srs": {}, "used": {}, "seen": [], "exam": [], "ask": [], "days": {}}
        self.anchors = []
        for p in (anchors_path, self.p_creator):
            for t in jl(p) if p else []:
                t.setdefault("id", sha(t["area"] + t["prompt"], 10))
                self.anchors.append(t)
        self.exam_tasks = [t for t in self.anchors if t.get("exam")]
        self.exam_stems = [sorted(stems(t["prompt"])) for t in self.exam_tasks]
        for t in self.anchors:
            self._area(t["area"])
        self._gap = {}

    # ---------- состояние
    def save(self):
        statefile.save(self.p_state, self.st)

    def _area(self, name):
        return self.st["areas"].setdefault(name, {"ev": [], "pin": 0.0})

    def _cell_ev(self, area, lvl):
        return [e for e in self._area(area)["ev"] if e["l"] == lvl][-20:]

    def p_cell(self, area, lvl):
        """Оценка вероятности успеха в ячейке: апостериорное среднее с априором уровня (вес 2), события взвешены источником."""
        ev = self._cell_ev(area, lvl)
        sw = sum(e["w"] for e in ev)
        return (prior_p(lvl) * 2 + sum(e["w"] * e["s"] for e in ev)) / (2 + sw), sw

    def lp_cell(self, area, lvl):
        return learning_progress([(e["s"], e["w"]) for e in self._cell_ev(area, lvl)])

    def mastered_level(self, area):
        """Высший освоенный уровень: >=3 событий, p>=0.8 и три последних независимых успеха. Освоенность высшего подразумевает нижние (лестница)."""
        top = 0
        for l in range(1, LEVELS + 1):
            ev = self._cell_ev(area, l)
            p, _ = self.p_cell(area, l)
            if len(ev) >= 3 and p >= 0.8 and all(e["s"] >= 0.7 for e in ev[-3:]):
                top = l
        return top

    def need(self, area):
        """Давление на область: открытые «не знаю» (ACT), открытые шрамы, закреплённая Создателем, LP реальной работы (уровень 0)."""
        a = self._area(area)
        gaps = min(1.0, self._gap.get(area, 0) / 5.0) * 0.5
        scars = min(0.6, 0.2 * sum(1 for it in self.st["srs"].values() if it["area"] == area and it["kind"] == "scar" and not it.get("healed")))
        real = min(0.5, 2.0 * learning_progress([(e["s"], e["w"]) for e in a["ev"] if e["l"] == 0]))
        return gaps + scars + real + a.get("pin", 0.0)

    # ---------- выбор ячейки
    def rank(self):
        cells = []
        for area in self.st["areas"]:
            top = self.mastered_level(area)
            need = self.need(area)
            for l in range(1, min(LEVELS, top + 2) + 1):          # ЗБР: не дальше «следующего после освоенного»
                p, n = self.p_cell(area, l)
                lp = self.lp_cell(area, l)
                fit = zpd_fit(p)
                score = (lp + 0.05 + 0.25 / math.sqrt(1 + n)) * (0.2 + fit) * (1 + need)
                cells.append({"area": area, "level": l, "p": round(p, 3), "lp": round(lp, 3), "fit": round(fit, 3), "need": round(need, 3), "score": score})
        cells.sort(key=lambda c: -c["score"])
        return cells

    def choose(self, exclude=()):
        cells = [c for c in self.rank() if (c["area"], c["level"]) not in exclude]
        if not cells:
            return None
        if self.rng.random() < self.eps:                           # исследование: равновероятно среди пригодных по ЗБР
            ok = [c for c in cells if c["fit"] > 0.3] or cells
            return self.rng.choice(ok)
        return self.rng.choices(cells, weights=[c["score"] for c in cells])[0]

    # ---------- получение задачи
    def _seen(self):
        return self.st["seen"]

    def _anchor_for(self, area, lvl, now):
        pool = [t for t in self.anchors if t["area"] == area and t["level"] == lvl and not t.get("exam")]
        fresh = [t for t in pool if t["id"] not in self.st["used"]]
        if fresh:
            return self.rng.choice(fresh)
        old = [t for t in pool if now - self.st["used"].get(t["id"], 0) >= self.cool * DAY]
        return self.rng.choice(old) if old else None

    def _generate(self, area, lvl, now, tries=3):
        if not self.llm:
            return None
        ex = [t for t in self.anchors if t["area"] == area and not t.get("exam")]
        ex.sort(key=lambda t: abs(t["level"] - lvl))
        recent = [t["prompt"] for t in self.anchors if t["area"] == area][-3:]
        for _ in range(tries):
            try:
                o = extract_json(self.llm(gen_prompt(area, lvl, ex, recent)))
            except Exception as e:
                if type(e).__name__ in BUSY_NAMES:
                    raise
                continue
            if not o:
                continue
            t = {"area": area, "level": lvl, "prompt": o.get("prompt"), "check": o.get("check"), "reference": o.get("reference"),
                 "hints": o.get("hints") or [], "src": "gen"}
            ok, _ = validate_task(t, self.judge, self.runner, self._seen(), self.exam_stems, allow_judge=False)
            if ok:
                t["id"] = sha(area + t["prompt"], 10)
                return t
        return None

    def pick_task(self, area, lvl, now):
        a = self._anchor_for(area, lvl, now)
        if a is not None and (not self.llm or self.rng.random() < self.anchor_share):
            return dict(a, src=a.get("src", "anchor"))
        g = self._generate(area, lvl, now)
        if g:
            return g
        return dict(a, src=a.get("src", "anchor")) if a is not None else None

    # ---------- прогон одной задачи
    def _score(self, task, ans):
        return check_answer(task["check"], ans, self.judge, self.runner, task["prompt"])

    def run_task(self, task, now=None, srs_id=None):
        now = self.clock() if now is None else now
        area, lvl = task["area"], task["level"]
        before_top, p_before = self.mastered_level(area), self.p_cell(area, lvl)[0]
        prompt = task["prompt"]
        ans = self.solver(prompt)
        s0, how = self._score(task, ans)                          # Unscorable/Busy/ошибки модели летят выше: событие не пишется
        indep, hints_used, final, shown = s0 >= 0.999, 0, s0, ans
        if not indep:
            final = min(s0, 0.49)
            hs = task.get("hints") or []
            for i in range(1, len(hs[:2]) + 1):                   # строительные леса: подсказки по одной, кредит убывает
                a2 = self.solver(prompt + "\n\nПодсказка: " + " ".join(hs[:i]))
                if self._score(task, a2)[0] >= 0.999:
                    final, hints_used = (0.5 if i == 1 else 0.35), i
                    break
        src = "creator" if task.get("src") == "creator" else how
        repeat = task["id"] in self.st["used"]
        w = SRC_W[src] * (0.6 if repeat else 1.0)
        self.st["used"][task["id"]] = now
        ev = {"t": now, "l": lvl, "s": round(final, 3), "w": round(w, 3), "a": 1 if hints_used else 0, "src": src, "id": task["id"]}
        A = self._area(area)
        A["ev"].append(ev)
        del A["ev"][:-100]
        if not task.get("exam") and not repeat:
            self.st["seen"].append(sorted(stems(prompt)))
            del self.st["seen"][:-300]
        d = self.st["days"].setdefault(msk_day(now), {"n": 0})
        d["n"] += 1
        for k in list(self.st["days"])[:-14]:
            del self.st["days"][k]
        out = {"id": task["id"], "area": area, "level": lvl, "score": final, "independent": indep, "assisted": bool(hints_used),
               "src": src, "repeat": repeat, "kind": task["check"]["kind"], "p_before": round(p_before, 3), "levelup": None}
        self._srs_step(task, srs_id, indep, hints_used, s0, ans, p_before, now, out)
        self._emit_training(task, ans, indep, repeat, now, src)
        top = self.mastered_level(area)
        if top > before_top:
            out["levelup"] = top
            self.diary.append("level_up", {"area": area, "level": top, "p": round(self.p_cell(area, top)[0], 3)}, now)
            self.hooks.on_levelup(area, top)
        self.hooks.on_outcome(area, lvl, final, bool(hints_used))
        self._check_stuck(area, lvl, now)
        self.save()
        return out

    # ---------- SRS: шрамы и уроки
    def _srs_step(self, task, srs_id, indep, hints_used, s0, ans, p_before, now, out):
        srs = self.st["srs"]
        if srs_id and srs_id in srs:
            it = srs[srs_id]
            R = srs_update(it, indep, now)
            out["review"] = {"R": round(R, 3), "S": round(it["S"], 2), "passed": indep}
            if indep and it["kind"] == "scar" and it["S"] >= 21 and it["reps"] >= 3 and not it.get("healed"):
                it["healed"] = True
                out["healed"] = True
                self.diary.append("scar_healed", {"area": it["area"], "level": it["level"], "task": it["id"], "S": round(it["S"], 1)}, now)
            return
        if task.get("exam") or len(srs) >= 300 or task["id"] in srs:
            return
        if not indep:
            srs[task["id"]] = {"id": task["id"], "kind": "scar", "task": task, "area": task["area"], "level": task["level"], "S": 0.5, "D": 5.0 + task["level"] / 2.0,
                               "reps": 0, "lapses": 1, "last": now, "due": now + interval_days(0.5) * DAY, "wrong": (ans or "")[:300]}
            self.diary.append("scar", {"area": task["area"], "level": task["level"], "task": task["id"], "assisted": bool(hints_used)}, now)
            out["scar"] = True
        elif task["level"] >= 2 and p_before < 0.7 and not out["repeat"]:      # урок: реально новое для меня (успех там, где ожидался провал)
            srs[task["id"]] = {"id": task["id"], "kind": "lesson", "task": task, "area": task["area"], "level": task["level"], "S": 1.5, "D": 4.0,
                               "reps": 1, "lapses": 0, "last": now, "due": now + interval_days(1.5) * DAY}
            out["lesson"] = True

    def due_items(self, now):
        it = [i for i in self.st["srs"].values() if not i.get("healed") and i["due"] <= now]
        it.sort(key=lambda i: retrievability((now - i["last"]) / DAY, i["S"]))
        out, last = [], None                                        # перемежение: не две подряд из одной области, если есть выбор
        rest = list(it)
        while rest:
            pick = next((x for x in rest if x["area"] != last), rest[0])
            rest.remove(pick)
            out.append(pick)
            last = pick["area"]
        return out

    # ---------- данные для сна (SLP): только проверенное правилом, без экзамена, с потолком доли
    def _emit_training(self, task, ans, indep, repeat, now, src):
        if task.get("exam") or task["check"]["kind"] not in RULE_KINDS:
            return
        rows = []
        if not indep:
            if ans and ans.strip():
                rows.append({"q": task["prompt"], "a": ans[:1500], "v": 0})
            if task.get("reference"):
                rows.append({"q": task["prompt"], "a": task["reference"], "v": 1})
        elif task["level"] >= 2 and not repeat:
            rows.append({"q": task["prompt"], "a": ans[:1500], "v": 1})
        for r in rows:
            r.update({"t": int(now), "src": "growth_" + src, "area": task["area"], "level": task["level"]})
            statefile.append_line(self.p_train, json.dumps(r, ensure_ascii=False))

    def sleep_batch(self, since, owner_rows):
        """Строки для ночного KTO: не больше ~30% от числа строк Создателя (мин. 10), трудные (выше уровень, провалы) первыми.
        Формат совместим с feedback.jsonl, который читает SLP/build_kto.collect (q, a, v, t)."""
        rows = [r for r in jl(self.p_train) if r.get("t", 0) >= since]
        rows.sort(key=lambda r: (-r.get("level", 0), r.get("v", 1)))
        cap = max(10, int(owner_rows * 0.43))
        return rows[:cap]

    # ---------- Создатель как «взрослый рядом»
    def _check_stuck(self, area, lvl, now):
        ev = self._cell_ev(area, lvl)
        if len(ev) < 6:
            return
        p, _ = self.p_cell(area, lvl)
        if p < 0.25 and self.lp_cell(area, lvl) < 0.05 and not any(a["area"] == area and a["level"] == lvl and a["status"] == "open" for a in self.st["ask"]):
            fails = [e["id"] for e in ev if e["s"] < 0.5][-3:]
            ex = []
            for i in fails:
                for t in self.anchors:
                    if t["id"] == i:
                        ex.append(t["prompt"][:100])
                it = self.st["srs"].get(i)
                if it:
                    ex.append(it["task"]["prompt"][:100])
            aid = sha("%s%d%d" % (area, lvl, int(now)), 8)
            q = ("Мессир, я застрял в области «%s» на уровне %d: из последних %d попыток получилось %d%%. Покажешь, как ты решаешь такое? "
                 "Один разобранный пример с проверяемым ответом мне хватит." % (area, lvl, len(ev), round(100 * p)))
            self.st["ask"].append({"id": aid, "area": area, "level": lvl, "question": q, "examples": ex[:3], "t": now, "status": "open", "sent": 0})
            self.diary.append("ask_creator", {"id": aid, "area": area, "level": lvl}, now)

    def pending_asks(self, now=None):
        """Не чаще одного вопроса в сутки и не в тихие часы (бюджет инициатив)."""
        now = self.clock() if now is None else now
        if in_quiet(now):
            return []
        if any(msk_day(a["sent"]) == msk_day(now) for a in self.st["ask"] if a.get("sent")):
            return []
        return [a for a in self.st["ask"] if a["status"] == "open" and not a.get("sent")][:1]

    def mark_asked(self, ask_id, now=None):
        now = self.clock() if now is None else now
        for a in self.st["ask"]:
            if a["id"] == ask_id:
                a["sent"] = now
        self.save()

    def add_creator_task(self, area, level, prompt, check, reference, hints=(), ask_id=None, now=None):
        """Разобранный пример Создателя -> якорная задача (вес 1.0). Проходит ту же валидацию. Закрывает вопрос ask_id."""
        now = self.clock() if now is None else now
        t = {"area": area, "level": level, "prompt": prompt, "check": check, "reference": reference, "hints": list(hints), "src": "creator"}
        ok, why = validate_task(t, self.judge, self.runner, (), self.exam_stems, allow_judge=False)
        if not ok:
            return {"ok": False, "reason": why}
        t["id"] = sha(area + prompt, 10)
        statefile.append_line(self.p_creator, json.dumps(t, ensure_ascii=False))
        self.anchors.append(t)
        self._area(area)["pin"] = 0.3
        for a in self.st["ask"]:
            if a["id"] == ask_id:
                a["status"] = "answered"
        self.diary.append("creator_task", {"area": area, "level": level, "id": t["id"]}, now)
        self.save()
        return {"ok": True, "id": t["id"]}

    # ---------- реальная жизнь как учебник (ACT-квитанции, 👍/👎, поправки)
    def ingest(self, area, score, src="rule", now=None, ref=""):
        now = self.clock() if now is None else now
        A = self._area(area)
        A["ev"].append({"t": now, "l": 0, "s": max(0.0, min(1.0, float(score))), "w": SRC_W[src], "a": 0, "src": src, "id": ref})
        del A["ev"][:-100]
        self.hooks.on_outcome(area, 0, float(score), False)
        self.save()

    def learn_from_resolved(self, area, question, quote, url="", now=None):
        """Закрытый пробел (gap_map.resolve дал проверенную цитату) -> проверочный вопрос, ответ которого дословно в цитате -> SRS-урок."""
        now = self.clock() if now is None else now
        if not self.llm:
            return {"ok": False, "reason": "нет генератора"}
        o = extract_json(self.llm(lesson_prompt(question, quote)))
        items = o.get("items") if o else None
        if not o or not isinstance(items, list) or not items:
            return {"ok": False, "reason": "нет разбора"}
        items = [s for s in items if isinstance(s, str) and len(s.strip()) >= 2]
        if not items or any(s.lower() not in quote.lower() for s in items):
            return {"ok": False, "reason": "ключ не из цитаты"}
        t = {"area": area, "level": 2, "prompt": str(o.get("prompt") or ""), "check": {"kind": "contains_all", "items": items},
             "reference": quote[:300], "hints": [], "src": "evidence"}
        ok, why = validate_task(t, self.judge, self.runner, (), self.exam_stems, allow_judge=False)
        if not ok:
            return {"ok": False, "reason": why}
        t["id"] = sha(area + t["prompt"], 10)
        self._area(area)
        self.st["srs"][t["id"]] = {"id": t["id"], "kind": "lesson", "task": t, "area": area, "level": 2, "S": 1.0, "D": 5.0, "reps": 0, "lapses": 0,
                                   "last": now, "due": now + interval_days(1.0) * DAY, "url": url}
        statefile.append_line(self.p_lessons, json.dumps({"t": int(now), "area": area, "q": t["prompt"], "fact": quote[:300], "url": url}, ensure_ascii=False))
        self.diary.append("lesson_from_evidence", {"area": area, "task": t["id"]}, now)
        self.save()
        return {"ok": True, "id": t["id"]}

    # ---------- занятие
    def session(self, max_tasks=None, now=None):
        now = self.clock() if now is None else now
        h = float(self.hooks.hunger())
        budget = max_tasks or max(1, round(1 + 4 * h))
        today = self.st["days"].get(msk_day(now), {"n": 0})["n"]
        if today >= self.day_cap:
            return {"skipped": "day_cap", "n": 0}
        budget = min(budget, self.day_cap - today)
        try:
            self._gap = dict(self.hooks.gap_open())
        except Exception:
            self._gap = {}
        for a in self._gap:
            self._area(a)
        res = {"n": 0, "passed": 0, "assisted": 0, "failed": 0, "reviews": 0, "new_pass": 0, "levelups": [], "stopped": None,
               "infra_errors": 0, "unscorable": 0, "budget": budget, "areas": {}}

        def account(o):
            res["n"] += 1
            res["passed"] += o["independent"]
            res["assisted"] += o["assisted"]
            res["failed"] += (not o["independent"] and not o["assisted"])
            res["new_pass"] += (o["independent"] and not o["repeat"] and o["p_before"] < 0.7)
            if o["levelup"]:
                res["levelups"].append({"area": o["area"], "level": o["levelup"]})
            a = res["areas"].setdefault(o["area"], {"n": 0, "sum": 0.0})
            a["n"] += 1
            a["sum"] += o["score"]

        def safe(fn):
            try:
                return fn()
            except Unscorable:
                res["unscorable"] += 1
            except Exception as e:
                if type(e).__name__ in BUSY_NAMES:
                    res["stopped"] = "busy"
                else:
                    res["infra_errors"] += 1
                    if res["infra_errors"] >= 2:
                        res["stopped"] = "errors"
            return None

        due = self.due_items(now)
        for it in due[:math.ceil(budget * 0.4)]:
            if res["stopped"]:
                break
            o = safe(lambda it=it: self.run_task(it["task"], now, srs_id=it["id"]))
            if o:
                res["reviews"] += 1
                account(o)
        skipped = set()
        guard = 0
        while res["n"] < budget and not res["stopped"] and guard < budget * 4:
            guard += 1
            c = self.choose(skipped)
            if not c:
                break
            t = safe(lambda c=c: self.pick_task(c["area"], c["level"], now))
            if res["stopped"]:
                break
            if not t:
                skipped.add((c["area"], c["level"]))
                continue
            o = safe(lambda t=t: self.run_task(t, now))
            if o:
                account(o)
        for a in res["areas"].values():
            a["mean"] = round(a.pop("sum") / a["n"], 3)
        if res["n"]:
            self.diary.append("session", {k: res[k] for k in ("n", "passed", "assisted", "failed", "reviews", "new_pass", "levelups", "stopped")}, now)
            self.hooks.on_session(res)
        self.save()
        return res

    # ---------- экзамен и отчёт
    def run_exam(self, now=None, tag=""):
        """Замороженный экзамен: якоря с exam=true, без подсказок, только правила; не попадает ни в обучение, ни в генерацию, ни в LP."""
        now = self.clock() if now is None else now
        by, n_ok, n = {}, 0, 0
        for t in self.exam_tasks:
            if t["check"]["kind"] not in RULE_KINDS:
                continue
            try:
                s, _ = self._score(t, self.solver(t["prompt"]))
            except Unscorable:
                continue
            a = by.setdefault(t["area"], [0, 0])
            a[0] += s >= 0.999
            a[1] += 1
            n_ok += s >= 0.999
            n += 1
        if not n:
            return {"ok": False, "reason": "нет экзаменационных задач"}
        rec = {"t": now, "tag": tag, "overall": round(n_ok / n, 4), "n": n, "by_area": {k: round(v[0] / v[1], 3) for k, v in by.items()}}
        self.st["exam"].append(rec)
        self.diary.append("exam", {"overall": rec["overall"], "n": n, "tag": tag}, now)
        self.save()
        return dict(rec, ok=True)

    def growth_report(self, now=None):
        """Доказательство роста: наклон экзамена (баллов в неделю) и t-статистика на замороженном наборе + независимость от подсказок + рубеж освоения."""
        now = self.clock() if now is None else now
        ex = self.st["exam"]
        rep = {"exams": len(ex), "frontier": {a: self.mastered_level(a) for a in self.st["areas"]}}
        sess = [e for A in self.st["areas"].values() for e in A["ev"] if e["l"] > 0]
        if sess:
            rep["assisted_share"] = round(sum(e["a"] for e in sess) / len(sess), 3)
        if len(ex) < 4:
            rep["verdict"] = "insufficient"
            return rep
        xs = [(e["t"] - ex[0]["t"]) / (7 * DAY) for e in ex]
        slope, t = ols(xs, [e["overall"] for e in ex])
        k = max(1, len(ex) // 3)
        gain = sum(e["overall"] for e in ex[-k:]) / k - sum(e["overall"] for e in ex[:k]) / k
        rep.update({"slope_per_week": round(slope, 4), "t": round(t, 2) if math.isfinite(t) else t, "gain": round(gain, 3)})
        rep["verdict"] = "growth" if slope > 0 and t >= 2 and gain >= 0.05 else "regression" if slope < 0 and t <= -2 else "stagnation"
        per = {}
        for a in {a for e in ex for a in e["by_area"]}:
            pts = [(x, e["by_area"][a]) for x, e in zip(xs, ex) if a in e["by_area"]]
            if len(pts) >= 3:
                per[a] = round(ols([p[0] for p in pts], [p[1] for p in pts])[0], 4)
        rep["area_slopes"] = per
        return rep

    def lp_table(self):
        return [{"area": a, "mastered": self.mastered_level(a), "need": round(self.need(a), 2),
                 "cells": [{"level": l, "p": round(self.p_cell(a, l)[0], 2), "lp": round(self.lp_cell(a, l), 3)} for l in range(1, LEVELS + 1) if self._cell_ev(a, l)]}
                for a in self.st["areas"]]

    def daily_text(self, day=None, now=None):
        """Дневник прогресса человеческим текстом: только факты из журнала, без выдумок."""
        now = self.clock() if now is None else now
        day = day or msk_day(now)
        rows = [r for r in self.diary.read() if msk_day(r["t"]) == day]
        if not rows:
            return "%s: занятий не было." % day
        L = ["Дневник роста, %s." % day]
        ss = [r["data"] for r in rows if r["kind"] == "session"]
        if ss:
            n = sum(s["n"] for s in ss)
            L.append("Решал задач: %d (сам: %d, с подсказкой: %d, не решил: %d), из них повторений: %d." % (
                n, sum(s["passed"] for s in ss), sum(s["assisted"] for s in ss), sum(s["failed"] for s in ss), sum(s["reviews"] for s in ss)))
        for r in rows:
            d = r["data"]
            if r["kind"] == "level_up":
                L.append("Новый рубеж: «%s», уровень %d." % (d["area"], d["level"]))
            elif r["kind"] == "scar":
                L.append("Шрам: ошибся в «%s» (уровень %d), буду повторять." % (d["area"], d["level"]))
            elif r["kind"] == "scar_healed":
                L.append("Шрам зажил: «%s», уровень %d." % (d["area"], d["level"]))
            elif r["kind"] == "ask_creator":
                L.append("Застрял в «%s» (уровень %d): нужна помощь Создателя." % (d["area"], d["level"]))
            elif r["kind"] == "exam":
                L.append("Экзамен: %d%% на %d задачах%s." % (round(100 * d["overall"]), d["n"], (" [" + d["tag"] + "]") if d.get("tag") else ""))
        return "\n".join(L)


# ============================================================ CLI (боевая проводка: fastq P3 + EMO drives + ACT gap_map)
SOLVE_SYS = "Ты решаешь учебную задачу. Отвечай коротко и точно, только ответом (для кода - только код)."


def _wire(a):
    import fastq
    fq = fastq.get()
    llm = fq.llm(fastq.P3)

    def solver(p):
        return fq.chat([{"role": "system", "content": SOLVE_SYS}, {"role": "user", "content": p}], fastq.P3, max_tokens=300, temperature=0.3)
    hs = []
    try:
        sys.path.append(os.path.join(_HERE, "..", "..", "EMO"))
        import drives as _dv
        hs.append(DrivesHooks(_dv.Drives(os.path.join(a.state, "drives.json") if a.drives is None else a.drives)))
    except Exception:
        pass
    if a.gapmap:
        try:
            sys.path.append(os.path.join(_HERE, "..", "..", "ACT"))
            import gap_map as _gm
            hs.append(GapHooks(_gm.GapMap(a.gapmap, allow_hosts=())))
        except Exception:
            pass
    return solver, llm, Hooks(*hs)


def main(argv=None):
    ap = argparse.ArgumentParser(description="NOX growth: автотелическая учебная программа")
    ap.add_argument("cmd", choices=["session", "exam", "report", "diary", "asks"])
    ap.add_argument("--state", default=os.environ.get("NOX_GROWTH", "/root/nox/state/growth"))
    ap.add_argument("--anchors", default=os.path.join(_HERE, "anchors_seed.jsonl"))
    ap.add_argument("--drives", default=None)
    ap.add_argument("--gapmap", default=None)
    ap.add_argument("--max-tasks", type=int, default=None)
    ap.add_argument("--tag", default="")
    a = ap.parse_args(argv)
    if a.cmd in ("report", "diary", "asks"):
        g = Growth(a.state, solver=lambda p: "", anchors_path=a.anchors)
        if a.cmd == "report":
            print(json.dumps({"growth": g.growth_report(), "lp": g.lp_table()}, ensure_ascii=False, indent=1))
        elif a.cmd == "diary":
            print(g.daily_text())
        else:
            print(json.dumps(g.pending_asks(), ensure_ascii=False, indent=1))
        return 0
    try:
        solver, llm, hooks = _wire(a)
    except ImportError as e:
        print("нет модуля проводки (fastq):", e, file=sys.stderr)
        return 2
    g = Growth(a.state, solver, llm=llm, judge=make_judge(llm), hooks=hooks, anchors_path=a.anchors)
    out = g.session(a.max_tasks) if a.cmd == "session" else g.run_exam(tag=a.tag)
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
