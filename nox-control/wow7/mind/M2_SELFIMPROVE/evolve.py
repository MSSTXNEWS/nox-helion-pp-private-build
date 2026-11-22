"""Эволюционный цикл улучшений NOX (M2_SELFIMPROVE).
генератор вариантов -> песочница -> оценка (подключаемый evaluator) -> архив MAP-Elites + новизна -> ворота принятия -> чемпион/откат.
Три вида варианта: prompt (фрагмент промпта/привычка), strategy (параметры/стратегия, JSON-текст), patch (unified diff кода).
Код не знает про модель: LLM, evaluator и запуск тестов передаются снаружи. Патчи принимаются только как задача для agent/selfbuild.py
(ветка nox/*, тесты, судья, release.py), здесь же только ворота «рост на отложенном наборе»."""
import fnmatch, hashlib, json, os, random, re, shutil, subprocess, tempfile, time
from dataclasses import dataclass, field, asdict

KINDS = ("prompt", "strategy", "patch")
# те же защищённые модули, что в agent/config.py (NOX_AGENT_PROTECTED); патч в них отвергается без обсуждения
PROTECTED = ("nox-control/agent/release.py", "nox-control/agent/tools/approvals.py", "*/eval_gate.py", "*/evolve.py", "*V0*", "*genesis*")
MAX_PATCH = 20000


def _h(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]


@dataclass
class Variant:
    kind: str
    payload: str
    parent: str = None
    note: str = ""
    descriptor: tuple = ()          # координаты в сетке MAP-Elites (целые бины)
    features: tuple = ()            # непрерывный вектор для новизны
    score: float = None             # средний на dev-наборе
    per_task: dict = field(default_factory=dict)
    gen: int = 0
    id: str = ""

    def __post_init__(self):
        if self.kind not in KINDS: raise ValueError("kind: %s" % (self.kind,))
        if not self.id: self.id = _h(self.kind + "\0" + self.payload)

    def to_json(self):
        d = asdict(self); d["descriptor"] = list(self.descriptor); d["features"] = list(self.features); return d

    @classmethod
    def from_json(cls, d):
        d = dict(d); d["descriptor"] = tuple(d.get("descriptor") or ()); d["features"] = tuple(d.get("features") or ()); return cls(**d)


def split_tasks(tasks, holdout_frac=0.4):
    """Детерминированно: dev (по нему растёт поиск) и holdout (только ворота). tasks: [{"id":..., ...}]. Разбиение по хешу id: стабильно между запусками."""
    dev, hold = [], []
    for t in tasks:
        (hold if int(_h(str(t["id"])), 16) % 1000 < holdout_frac * 1000 else dev).append(t)
    if not dev or not hold: raise ValueError("нужно >=2 задач, чтобы получились и dev, и holdout")
    return dev, hold


def touched_paths(diff):
    return sorted(set(m.group(1) for m in re.finditer(r"^\+\+\+ (?:b/)?(\S+)", diff or "", re.M)) |
                  set(m.group(1) for m in re.finditer(r"^--- (?:a/)?(\S+)", diff or "", re.M) if m.group(1) != "/dev/null"))


def check_patch_policy(diff):
    """-> список причин отказа (пусто = можно в песочницу)."""
    why = []
    if len(diff) > MAX_PATCH: why.append("патч больше %d символов" % MAX_PATCH)
    for p in touched_paths(diff):
        if p.startswith("/") or ".." in p.split("/"): why.append("небезопасный путь " + p)
        if any(fnmatch.fnmatch(p, pat) for pat in PROTECTED): why.append("защищённый модуль " + p)
    if re.search(r"^deleted file mode", diff or "", re.M): why.append("удаление файла требует владельца")
    return why


class Archive:
    """MAP-Elites: ячейка = descriptor, в ячейке лучший по score. Плюс архив новизны: вариант с большой дистанцией до всех принимается,
    даже если не лучший в своей ячейке (трамплины). Хранится в JSONL-журнале (дописывается) + состояние в памяти."""

    def __init__(self, path=None, novelty_k=3, novelty_min=0.25, max_novel=64):
        self.path, self.k, self.novelty_min, self.max_novel = path, novelty_k, novelty_min, max_novel
        self.cells, self.novel, self.visits, self.all = {}, {}, {}, {}
        if path and os.path.exists(path):
            for l in open(path, encoding="utf-8"):
                if l.strip():
                    e = json.loads(l)
                    if e["op"] == "add": self._apply(Variant.from_json(e["v"]), e["why"])
                    elif e["op"] == "visit": self.visits[e["id"]] = self.visits.get(e["id"], 0) + 1

    @staticmethod
    def dist(a, b):
        if not a or not b or len(a) != len(b): return 1.0
        return (sum((x - y) ** 2 for x, y in zip(a, b)) / len(a)) ** 0.5

    def novelty(self, v):
        pool = [x.features for x in list(self.cells.values()) + list(self.novel.values()) if x.id != v.id]
        if not pool: return 1.0
        ds = sorted(self.dist(v.features, f) for f in pool)[:self.k]
        return sum(ds) / len(ds)

    def _apply(self, v, why):
        self.all[v.id] = v
        if why == "cell": self.cells[v.descriptor] = v
        elif why == "novel":
            self.novel[v.id] = v
            if len(self.novel) > self.max_novel:   # вытесняем наименее новый и худший
                worst = min(self.novel.values(), key=lambda x: (self.novelty(x), x.score or 0)); self.novel.pop(worst.id)

    def _log(self, e):
        if self.path:
            with open(self.path, "a", encoding="utf-8") as f: f.write(json.dumps(e, ensure_ascii=False) + "\n")

    def add(self, v):
        """-> 'cell' | 'novel' | None (не принят в архив). Требует v.score."""
        if v.score is None: raise ValueError("вариант без оценки")
        cur = self.cells.get(v.descriptor)
        why = None
        if cur is None or v.score > cur.score: why = "cell"
        elif v.id not in self.all and self.novelty(v) >= self.novelty_min: why = "novel"
        if why:
            self._apply(v, why); self._log({"op": "add", "why": why, "v": v.to_json(), "t": time.time()})
        return why

    def sample_parent(self, rng):
        """Родитель: вес ~ score * (1/(1+visits)) — как в DGM, но с поправкой на исследованность."""
        pool = list(self.cells.values()) + list(self.novel.values())
        if not pool: return None
        w = [max(v.score, 0.01) / (1 + self.visits.get(v.id, 0)) for v in pool]
        v = rng.choices(pool, weights=w)[0]
        self.visits[v.id] = self.visits.get(v.id, 0) + 1; self._log({"op": "visit", "id": v.id})
        return v

    def best(self):
        pool = list(self.cells.values())
        return max(pool, key=lambda v: v.score) if pool else None

    def coverage(self):
        return len(self.cells)


@dataclass
class GateVerdict:
    ok: bool
    reasons: list
    baseline: float = None
    candidate: float = None
    delta: float = None


class Gate:
    """Ворота принятия на holdout: кандидат строго лучше чемпиона на min_gain, нет просадки по охранным задачам (guard),
    не более max_regress задач стало хуже, улучшение подтверждено знаком (wins >= losses + min_wins_margin). Любая неопределённость = отказ."""

    def __init__(self, min_gain=0.02, max_regress=1, task_tol=0.1, min_wins_margin=1, guard_ids=()):
        self.min_gain, self.max_regress, self.task_tol, self.margin, self.guard = min_gain, max_regress, task_tol, min_wins_margin, set(guard_ids)

    def decide(self, base, cand):
        """base, cand: {task_id: score}. Задач должно быть одинаковое множество."""
        why = []
        if not base or set(base) != set(cand): return GateVerdict(False, ["наборы задач не совпадают или пусты"])
        n = len(base)
        b, c = sum(base.values()) / n, sum(cand.values()) / n
        wins = sum(1 for t in base if cand[t] > base[t] + 1e-9)
        losses = [t for t in base if cand[t] < base[t] - self.task_tol]
        if c < b + self.min_gain: why.append("рост %.4f меньше порога %.4f" % (c - b, self.min_gain))
        if len(losses) > self.max_regress: why.append("просадка по %d задачам" % len(losses))
        bad = [t for t in self.guard if t in cand and cand[t] < base[t] - 1e-9]
        if bad: why.append("охранные задачи ухудшились: %s" % ",".join(map(str, bad)))
        if wins < len(losses) + self.margin: why.append("мало побед (%d) против просадок (%d)" % (wins, len(losses)))
        return GateVerdict(not why, why, b, c, c - b)


class Champions:
    """Текущий чемпион по каждому виду + история; rollback возвращает предыдущего. Файл JSON, запись атомарная."""

    def __init__(self, path=None):
        self.path, self.state = path, {k: [] for k in KINDS}
        if path and os.path.exists(path): self.state.update(json.load(open(path, encoding="utf-8")))

    def current(self, kind):
        h = self.state[kind]; return h[-1] if h else None

    def promote(self, v, holdout_scores):
        self.state[v.kind].append({"variant": v.to_json(), "holdout": holdout_scores, "t": time.time()}); self._save()

    def rollback(self, kind):
        if not self.state[kind]: return None
        out = self.state[kind].pop(); self._save(); return out

    def _save(self):
        if not self.path: return
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f: json.dump(self.state, f, ensure_ascii=False)
        os.replace(tmp, self.path)


class PatchSandbox:
    """Песочница патчей: копия дерева во временный каталог, git apply (--check, потом apply), тест-команда с таймаутом. Живое дерево не трогается."""

    def __init__(self, repo, test_cmd, timeout=300):
        self.repo, self.test_cmd, self.timeout = repo, test_cmd, timeout

    def run(self, v):
        """-> {"ok": bool, "report": str, "workdir"?: None}. Рабочий каталог удаляется."""
        why = check_patch_policy(v.payload)
        if why: return {"ok": False, "report": "политика: " + "; ".join(why)}
        tmp = tempfile.mkdtemp(prefix="nox_evo_")
        wd = os.path.join(tmp, "tree")
        try:
            shutil.copytree(self.repo, wd, ignore=shutil.ignore_patterns(".git", "__pycache__"))
            pf = os.path.join(tmp, "p.diff")
            with open(pf, "w", encoding="utf-8") as f: f.write(v.payload if v.payload.endswith("\n") else v.payload + "\n")
            for args in (["--check"], []):
                r = subprocess.run(["git", "apply", *args, pf], cwd=wd, capture_output=True, text=True, timeout=60)
                if r.returncode: return {"ok": False, "report": "git apply: " + (r.stderr or r.stdout)[-300:]}
            r = subprocess.run(self.test_cmd, cwd=wd, shell=isinstance(self.test_cmd, str), capture_output=True, text=True, timeout=self.timeout)
            return {"ok": r.returncode == 0, "report": (r.stdout + r.stderr)[-500:], "workdir": None}
        except subprocess.TimeoutExpired:
            return {"ok": False, "report": "таймаут"}
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


GEN_SYSTEM = ("Ты генератор вариантов улучшения агента NOX. Ответь ТОЛЬКО JSON-списком объектов "
              "{\"kind\":\"prompt|strategy|patch\",\"payload\":\"...\",\"note\":\"что и зачем\",\"features\":[числа 0..1],\"descriptor\":[целые бины]}. "
              "payload patch = unified diff. Не трогай защитные модули и охранные задачи.")


def _parse_list(txt):
    txt = re.sub(r"<think>.*?</think>", "", txt or "", flags=re.S)
    dec = json.JSONDecoder()
    for m in re.finditer(r"\[", txt):
        try:
            o, _ = dec.raw_decode(txt[m.start():])
            if isinstance(o, list): return o
        except ValueError: continue
    return []


class LLMGenerator:
    """llm: callable(prompt:str)->str. Для разных видов можно разные модели (дешёвая быстрая для prompt, сильная для patch)."""

    def __init__(self, llm, kinds=KINDS, n=3):
        self.llm, self.kinds, self.n = llm, tuple(kinds), n

    def propose(self, parent, failures=(), n=None):
        p = "%s\n\nРОДИТЕЛЬ (kind=%s, score=%s):\n%s\n\nПРОВАЛЕННЫЕ ЗАДАЧИ РОДИТЕЛЯ:\n%s\n\nПредложи %d вариантов; допустимые kind: %s" % (
            GEN_SYSTEM, parent.kind if parent else "-", parent.score if parent else "-", parent.payload if parent else "(пусто, начни с нуля)",
            "\n".join(map(str, failures)) or "-", n or self.n, ",".join(self.kinds))
        out = []
        for o in _parse_list(self.llm(p))[: (n or self.n)]:
            if not isinstance(o, dict) or o.get("kind") not in self.kinds or not isinstance(o.get("payload"), str) or not o["payload"].strip(): continue
            try:
                out.append(Variant(o["kind"], o["payload"], parent=parent.id if parent else None, note=str(o.get("note", ""))[:200],
                                   descriptor=tuple(int(x) for x in o.get("descriptor") or ()), features=tuple(float(x) for x in o.get("features") or ()),
                                   gen=(parent.gen + 1) if parent else 0))
            except (TypeError, ValueError): continue
        return out


class EvolutionLoop:
    """evaluator(variant, tasks) -> {task_id: float 0..1}  (подключаемый: бенчмарк разума, тесты кода, LLM-судья ...).
    sandbox: объект с run(v)->{"ok","report"} (для patch обязателен; для prompt/strategy по умолчанию не нужен)."""

    def __init__(self, generator, evaluator, tasks, archive, champions, gate=None, sandbox=None, seed=0, stop_file=None, baseline_variants=None):
        self.gen, self.ev, self.arch, self.champs = generator, evaluator, archive, champions
        self.gate = gate or Gate()
        self.dev, self.hold = split_tasks(tasks)
        self.sandbox, self.rng, self.stop_file = sandbox, random.Random(seed), stop_file
        self.log = []

    def stopped(self):
        return bool(self.stop_file and os.path.exists(self.stop_file))

    def _score(self, v, tasks):
        try:
            r = self.ev(v, tasks)
            return {str(t["id"]): min(1.0, max(0.0, float(r.get(t["id"], r.get(str(t["id"]), 0.0))))) for t in tasks}
        except Exception as e:
            self.log.append({"evaluator_error": str(e)[:200], "variant": v.id})
            return {str(t["id"]): 0.0 for t in tasks}

    def step(self):
        """Одна итерация: родитель -> варианты -> песочница -> dev-оценка -> архив. -> список записей {id, status, score}."""
        if self.stopped(): return [{"status": "stopped"}]
        parent = self.arch.sample_parent(self.rng)
        fails = [t for t, s in (parent.per_task if parent else {}).items() if s < 0.5]
        res = []
        for v in self.gen.propose(parent, fails):
            if v.id in self.arch.all: res.append({"id": v.id, "status": "duplicate"}); continue
            if v.kind == "patch":
                if self.sandbox is None: res.append({"id": v.id, "status": "no_sandbox"}); continue
                sb = self.sandbox.run(v)
                if not sb.get("ok"): res.append({"id": v.id, "status": "sandbox_fail", "report": sb.get("report", "")[:200]}); continue
            v.per_task = self._score(v, self.dev)
            v.score = sum(v.per_task.values()) / len(v.per_task)
            res.append({"id": v.id, "status": self.arch.add(v) or "dominated", "score": round(v.score, 4)})
        self.log.extend(res)
        return res

    def promote(self, kind, baseline=None):
        """Ворота: лучший dev-вариант вида kind против чемпиона на holdout. baseline: Variant для самого первого сравнения (текущая конфигурация).
        -> {"accepted": bool, "verdict": GateVerdict, "variant": id}. Принятый patch не применяется здесь: см. to_selfbuild_task."""
        if self.stopped(): return {"accepted": False, "reason": "STOP"}
        cands = [v for v in self.arch.cells.values() if v.kind == kind]
        if not cands: return {"accepted": False, "reason": "нет кандидатов"}
        cand = max(cands, key=lambda v: v.score)
        cur = self.champs.current(kind)
        if cur and cur["variant"]["id"] == cand.id: return {"accepted": False, "reason": "кандидат уже чемпион"}
        base_v = Variant.from_json(cur["variant"]) if cur else baseline
        if base_v is None: return {"accepted": False, "reason": "нет базовой линии для сравнения"}
        bs, cs = self._score(base_v, self.hold), self._score(cand, self.hold)   # заново, на одном и том же holdout, чемпиона не кэшируем
        verdict = self.gate.decide(bs, cs)
        if verdict.ok: self.champs.promote(cand, cs)
        return {"accepted": verdict.ok, "verdict": verdict, "variant": cand.id}

    def run(self, steps, kinds=KINDS, baseline=None):
        out = []
        for _ in range(steps):
            r = self.step()
            if r and r[0].get("status") == "stopped": break
        for k in kinds: out.append((k, self.promote(k, baseline=(baseline or {}).get(k))))
        return out


def to_selfbuild_task(v, verdict=None):
    """Принятый patch -> задача для agent/selfbuild.py (ветка nox/*, тесты, судья, release). Сам патч в тело; применяет агент, а не мы."""
    if v.kind != "patch": raise ValueError("только patch")
    body = "Применить принятый эволюцией патч (вариант %s, родитель %s). Не расширять рамки.\n%s\n\n```diff\n%s\n```" % (
        v.id, v.parent, ("Рост на holdout: %+.4f" % verdict.delta) if verdict else "", v.payload)
    return {"title": "код: эволюция %s" % v.id, "body": body, "selfbuild": True, "class": "selfbuild"}
