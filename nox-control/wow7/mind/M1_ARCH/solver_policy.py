"""M1_ARCH: «обучаемый решатель» NOX (исполнитель №4 «Решатель» из BRAIN_DESIGN.md).

Политика выбора пути/глубины/исполнителей хода, которая УЧИТСЯ на исходах ходов, а не на промпте:
  * контекстный бандит, линейный Thompson sampling (байесовская ридж-регрессия на каждую «руку»);
  * жёсткие правила (STOP, приветствие, необратимое, нет апстрима, низкая ток/с, тихие часы) сужают допустимые руки ДО обучения: политика
    не может выбрать то, что запрещено правилами; обучается только выбор внутри разрешённого;
  * доверие к правилам (бонус базового роутера RTE.router) затухает по мере накопления опыта;
  * журнал jsonl с хеш-цепочкой (решения, обновления, откаты, чекпоинты); состояние = детерминированный пересчёт журнала, поэтому
    откат на любую ревизию = запись «rollback» + пересчёт; битый журнал не принимается молча;
  * сторож: если среднее вознаграждение последних W ходов упало ниже лучшего чекпоинта на watch_drop, автооткат на чекпоинт,
    «испытательный срок» без исследования, затем пересчёт базы (если мир изменился, а не политика испортилась).
Только stdlib. LLM не вызывается: судья исхода подаётся снаружи (Outcome.judge) и в тестах подменяется фейком.
"""
import hashlib
import json
import math
import os
import random
import threading
import time
from dataclasses import dataclass, field

INTENTS = ("chat", "question", "task", "command")


@dataclass(frozen=True)
class Arm:
    name: str
    tier: str            # ярус RTE.router: fast | deep | deep_think
    think: bool
    intro: bool          # Интуиция: быстрое вступление пока думает GLM
    advisor: bool        # СОВЕТ (советник в карантин)
    cost: float          # относительная цена 0..1 (время/ресурс), входит в вознаграждение с малым весом
    executors: tuple


_BASE = ("perception", "attention", "memory", "solver")
_TAIL = ("conscience", "chronicler")
DEFAULT_ARMS = (
    Arm("reflex", "fast", False, False, False, 0.05, _BASE + ("mind_fast",) + _TAIL),
    Arm("thought", "deep", False, True, False, 0.5, _BASE + ("intuition", "mind_glm") + _TAIL),
    Arm("deep", "deep_think", True, True, False, 0.9, _BASE + ("intuition", "mind_glm_think") + _TAIL),
    Arm("council", "deep_think", True, True, True, 1.0, _BASE + ("intuition", "mind_glm_think", "advisor_quarantine") + _TAIL),
)
TIER_TO_ARM = {"fast": "reflex", "bridge_deep": "thought", "deep": "thought", "deep_think": "deep"}


# ------------------------------------------------------------------ признаки
FEATURE_NAMES = (["bias", "complexity", "words", "code", "reason", "think_kw", "list", "questions", "history", "tools", "creator", "tps_low", "quiet"]
                 + ["intent_" + i for i in INTENTS])


def featurize(ctx):
    """ctx -> вектор [0..1]^d фиксированной длины. Неизвестные ключи игнорируются, пропуски = 0."""
    g = ctx.get
    intent = g("intent") or "chat"
    tps = g("tps")
    v = [1.0,
         min(max(float(g("complexity", 0.0) or 0.0), 0.0), 1.0),
         min(float(g("words", 0) or 0) / 200.0, 1.0),
         1.0 if g("code") else 0.0, 1.0 if g("reason") else 0.0, 1.0 if g("think_kw") else 0.0, 1.0 if g("list") else 0.0,
         min(float(g("q", 0) or 0) / 4.0, 1.0), min(float(g("history_turns", 0) or 0) / 40.0, 1.0),
         1.0 if g("tools") else 0.0, 1.0 if g("creator") else 0.0,
         1.0 if (tps is not None and float(tps) < 4.0) else 0.0, 1.0 if g("quiet") else 0.0]
    v += [1.0 if intent == i else 0.0 for i in INTENTS]
    return [round(x, 6) for x in v]


def allowed_arms(ctx, arms=DEFAULT_ARMS, tps_think_min=4.0):
    """Жёсткие правила. Возвращает (список имён, причина). Обучение здесь ничего не меняет."""
    names = [a.name for a in arms]
    g = ctx.get
    fast_up, deep_up = g("fast_up", True) is not False, g("deep_up", True) is not False
    if not deep_up:
        return ["reflex"], "deep_down"
    if g("greet"):
        return ["reflex"], "greet"
    if g("irreversible"):
        return ["deep"], "irreversible"
    mode = g("mode")
    if mode == "fast" and fast_up:
        return ["reflex"], "mode_fast"
    if mode == "max":
        return ["deep"], "mode_max"
    ok = list(names)
    if not fast_up:
        ok.remove("reflex")
    if mode == "deep":
        ok = [n for n in ok if n in ("thought", "deep", "council")]
    explicit = bool(g("think_kw")) or mode in ("deep",)
    tps = g("tps")
    if tps is not None and float(tps) < tps_think_min and not explicit:
        ok = [n for n in ok if n not in ("deep", "council")]
    if g("quiet") or not g("advisor_ok", False):
        ok = [n for n in ok if n != "council"]
    return (ok or ["reflex"]), ("rules" if len(ok) != len(names) else "free")


# ------------------------------------------------------------------ вознаграждение
@dataclass
class Outcome:
    """Сигналы исхода хода. Всё необязательное; судья (judge 0..1) подаётся снаружи, сама политика его не вызывает."""
    conscience_ok: object = None      # Совесть пропустила без переписывания? True/False/None
    rewrites: int = 0
    empty: bool = False
    stopped: bool = False             # Создатель нажал STOP
    corrected_next: bool = False      # следующей репликой поправил/отверг
    creator_feedback: int = 0         # -1 / 0 / +1 явная оценка
    judge: object = None              # 0..1 от младшего судьи (selftools/judge_run) или None
    latency_s: float = 0.0
    budget_s: float = 0.0


def _clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def reward_from_outcome(o, cost=0.0, cost_weight=0.04):
    if o.empty:
        q = 0.0
    else:
        q = float(o.judge) if o.judge is not None else (1.0 if o.conscience_ok is True else 0.0 if o.conscience_ok is False else 0.6)
        q -= 0.15 * min(max(o.rewrites, 0), 2)
        q -= 0.3 if o.stopped else 0.0
        q -= 0.4 if o.corrected_next else 0.0
    q = _clamp(q)
    if o.creator_feedback:
        q = 0.5 * q + 0.5 * (1.0 if o.creator_feedback > 0 else 0.0)
    pen = 0.0
    if o.budget_s and o.latency_s > o.budget_s:
        pen = min(0.3, 0.15 * (o.latency_s / o.budget_s - 1.0))
    return round(_clamp(q - pen - cost_weight * cost), 6)


# ------------------------------------------------------------------ линейная алгебра (d ~ 17, чистый python)
def _chol(A):
    n = len(A)
    L = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            s = A[i][j] - sum(L[i][k] * L[j][k] for k in range(j))
            if i == j:
                L[i][i] = math.sqrt(max(s, 1e-12))
            else:
                L[i][j] = s / L[j][j]
    return L


def _solve_lower(L, b):
    y = []
    for i in range(len(b)):
        y.append((b[i] - sum(L[i][k] * y[k] for k in range(i))) / L[i][i])
    return y


def _solve_upper_T(L, y):
    """Решает Lᵀ x = y."""
    n = len(y)
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = (y[i] - sum(L[k][i] * x[k] for k in range(i + 1, n))) / L[i][i]
    return x


def _dot(a, b):
    return sum(p * q for p, q in zip(a, b))



def _h(prev, body):
    return hashlib.sha256((prev + json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))).encode()).hexdigest()


def read_journal(path):
    """-> (записи валидного префикса, хеш последней, ok). ok=False: цепочка нарушена после префикса."""
    out, prev, ok = [], "0" * 64, True
    if not path or not os.path.exists(path):
        return out, prev, True
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
                h = e.pop("h")
                if e.get("prev") != prev or _h(prev, {k: v for k, v in e.items() if k != "prev"}) != h:
                    raise ValueError
            except Exception:
                ok = False
                break
            e["h"] = h
            out.append(e)
            prev = h
    return out, prev, ok


@dataclass
class Decision:
    turn_id: str
    arm: str
    tier: str
    baseline: str
    allowed: list
    reason: str
    explored: bool
    learn: bool
    x: list
    rev: int
    mean: dict = field(default_factory=dict)
    sampled: dict = field(default_factory=dict)
    executors: tuple = ()

    def to_dict(self):
        return dict(self.__dict__, executors=list(self.executors))


class SolverPolicy:
    def __init__(self, journal_path=None, arms=DEFAULT_ARMS, seed=None, lam=1.0, sigma=0.2, gamma=0.999, prior_bonus=0.08, n0=200, prior_mean=0.5,
                 watch_window=40, watch_drop=0.12, ckpt_every=20, tps_think_min=4.0, clock=time.time):
        self.arms = {a.name: a for a in arms}
        self.order = [a.name for a in arms]
        self.d = len(FEATURE_NAMES)
        self.lam, self.sigma, self.gamma, self.prior_bonus, self.n0, self.prior_mean = lam, sigma, gamma, prior_bonus, n0, prior_mean
        self.W, self.drop, self.ckpt_every, self.tps_think_min = watch_window, watch_drop, ckpt_every, tps_think_min
        self.rng = random.Random(seed)
        self.clock = clock
        self.path = journal_path
        self.lock = threading.RLock()
        self._eff = []                 # действующие обновления: (arm, x, r)
        self._pending = {}             # turn_id -> Decision без исхода
        self._done = set()
        self.best_rev, self.best_score = 0, None
        self.probation = 0
        self.rollbacks = 0
        self.corrupt = False
        self._seq = 0
        self._last_prev = "0" * 64
        self._reset_model()
        if self.path:
            self._replay()

    # ---------------- модель
    def _reset_model(self):
        lam_pm = self.lam * self.prior_mean      # априор: средняя польза любой руки ~prior_mean (на признаке bias)
        self.A = {n: [[self.lam if i == j else 0.0 for j in range(self.d)] for i in range(self.d)] for n in self.order}
        self.b = {n: [lam_pm] + [0.0] * (self.d - 1) for n in self.order}
        self.n = {n: 0 for n in self.order}

    def _apply(self, arm, x, r):
        A, b, g, lam = self.A[arm], self.b[arm], self.gamma, self.lam
        for i in range(self.d):
            for j in range(self.d):
                A[i][j] = g * (A[i][j] - (lam if i == j else 0.0)) + (lam if i == j else 0.0) + x[i] * x[j]
            pb = lam * self.prior_mean if i == 0 else 0.0
            b[i] = g * (b[i] - pb) + pb + r * x[i]
        self.n[arm] += 1

    def _rebuild(self, upd):
        self._reset_model()
        for arm, x, r in upd:
            self._apply(arm, x, r)

    def _post(self, arm):
        L = _chol(self.A[arm])
        mu = _solve_upper_T(L, _solve_lower(L, self.b[arm]))
        return L, mu

    @property
    def rev(self):
        return len(self._eff)

    # ---------------- журнал
    def _write(self, kind, **body):
        with self.lock:
            self._seq += 1
            body = dict(k=kind, n=self._seq, t=round(self.clock(), 3), **body)
            h = _h(self._last_prev, body)
            if self.path:
                os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
                rec = dict(body)
                rec["prev"] = self._last_prev
                rec["h"] = h
                fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
                try:
                    os.write(fd, (json.dumps(rec, ensure_ascii=False) + "\n").encode())
                    os.fsync(fd)
                finally:
                    os.close(fd)
            self._last_prev = h
            return h

    def _replay(self):
        recs, last, ok = read_journal(self.path)
        if not ok:
            self.corrupt = True
            os.replace(self.path, "%s.corrupt.%d" % (self.path, int(self.clock())))
            with open(self.path, "w", encoding="utf-8") as f:   # валидный префикс переписываем в новый журнал
                for e in recs:
                    f.write(json.dumps(e, ensure_ascii=False) + "\n")
        self._seq = max([e["n"] for e in recs] or [0])
        self._last_prev = last
        eff, pend = [], {}
        for e in recs:
            k = e["k"]
            if k == "decide":
                pend[e["turn"]] = e
            elif k == "update":
                eff.append((e["arm"], e["x"], e["r"]))
                pend.pop(e["turn"], None)
                self._done.add(e["turn"])
            elif k == "rollback":
                eff = eff[:e["to"]]
                self.rollbacks += 1
            elif k == "ckpt":
                self.best_rev, self.best_score = e["rev"], e["score"]
            elif k == "rebaseline":
                self.best_score = e["score"]
        self._eff = eff
        self._rebuild(eff)
        for t, e in list(pend.items())[-500:]:
            self._pending[t] = Decision(t, e["arm"], self.arms[e["arm"]].tier, e.get("base", e["arm"]), e.get("allowed", []), e.get("why", ""),
                                        e.get("explored", False), e.get("learn", True), e["x"], e.get("rev", 0), executors=self.arms[e["arm"]].executors)
        if self.corrupt:
            self._write("corruption", note="журнал обрезан до валидного префикса")

    # ---------------- решение
    def decide(self, ctx, baseline_tier=None, turn_id=None):
        with self.lock:
            turn_id = turn_id or "t%08x" % self.rng.getrandbits(32)
            ok, why = allowed_arms(ctx, tuple(self.arms.values()), self.tps_think_min)
            base = TIER_TO_ARM.get(baseline_tier or "", None)
            if base not in ok:
                base = ok[0]
            x = featurize(ctx)
            learn = len(ok) > 1
            noise_off = self.probation > 0
            mean, samp = {}, {}
            if learn:
                bonus = self.prior_bonus * (1.0 if noise_off else max(0.0, 1.0 - self.rev / float(self.n0)))
                for a in ok:
                    L, mu = self._post(a)
                    m = _dot(mu, x)
                    z = [self.rng.gauss(0, 1) for _ in range(self.d)]
                    s = m if noise_off else m + self.sigma * _dot(_solve_upper_T(L, z), x)
                    mean[a], samp[a] = round(m, 4), round(s + (bonus if a == base else 0.0), 4)
                arm = max(ok, key=lambda a: (samp[a], a == base))
            else:
                arm = ok[0]
            d = Decision(turn_id, arm, self.arms[arm].tier, base, ok, why, arm != base, learn, x, self.rev, mean, samp, self.arms[arm].executors)
            if learn:
                self._pending[turn_id] = d
                while len(self._pending) > 500:
                    self._pending.pop(next(iter(self._pending)))
            self._write("decide", turn=turn_id, arm=arm, base=base, allowed=ok, why=why, explored=d.explored, learn=learn, x=x, rev=self.rev)
            return d

    # ---------------- исход
    def record(self, turn_id, outcome, reward=None):
        """Первый исход хода. Повторные сигналы (поправка в следующей реплике) — через amend()."""
        with self.lock:
            d = self._pending.pop(turn_id, None)
            if d is None or turn_id in self._done:
                return None
            self._done.add(turn_id)
            r = reward if reward is not None else reward_from_outcome(outcome, self.arms[d.arm].cost)
            self._learn(d.arm, d.x, r, turn_id, "outcome")
            return r

    def amend(self, turn_id, reward, arm, x):
        """Запоздалый сигнал по уже закрытому ходу: ещё одно наблюдение (arm и x берутся из trace хода)."""
        with self.lock:
            self._learn(arm, x, _clamp(reward), turn_id, "late")

    def _learn(self, arm, x, r, turn_id, src):
        self._apply(arm, x, r)
        self._eff.append((arm, x, r))
        self._write("update", turn=turn_id, arm=arm, x=x, r=r, src=src)
        self._watch()

    def _recent(self):
        w = self._eff[-self.W:]
        return sum(r for _, _, r in w) / len(w) if w else 0.0

    def _watch(self):
        rev = self.rev
        if self.probation > 0:
            self.probation -= 1
            if self.probation == 0 and self.best_score is not None and self._recent() < self.best_score - self.drop:
                self.best_score = round(self._recent(), 4)      # мир изменился, а не политика испортилась
                self._write("rebaseline", score=self.best_score)
            return
        if rev >= self.W and rev % self.ckpt_every == 0:
            s = round(self._recent(), 4)
            if self.best_score is None or s >= self.best_score:
                self.best_rev, self.best_score = rev, s
                self._write("ckpt", rev=rev, score=s)
        if self.best_score is not None and rev >= self.best_rev + self.W and self._recent() < self.best_score - self.drop:
            self.rollback(self.best_rev, "watchdog: %.3f < %.3f-%.2f" % (self._recent(), self.best_score, self.drop))
            self.probation = self.W

    def rollback(self, to_rev, why="manual"):
        with self.lock:
            to_rev = max(0, min(int(to_rev), self.rev))
            self._eff = self._eff[:to_rev]
            self._rebuild(self._eff)
            self.rollbacks += 1
            self._write("rollback", to=to_rev, why=why)
            return to_rev

    # ---------------- наблюдаемость
    def verify(self):
        _, _, ok = read_journal(self.path) if self.path else ([], "", True)
        return ok

    def stats(self):
        per = {n: {"n": 0, "mean_r": 0.0} for n in self.order}
        for a, _, r in self._eff:
            per[a]["n"] += 1
            per[a]["mean_r"] += r
        for v in per.values():
            v["mean_r"] = round(v["mean_r"] / v["n"], 4) if v["n"] else None
        return {"rev": self.rev, "arms": per, "best_rev": self.best_rev, "best_score": self.best_score, "rollbacks": self.rollbacks,
                "probation": self.probation, "pending": len(self._pending), "recent_mean": round(self._recent(), 4), "corrupt": self.corrupt}

    def weights(self):
        """Средние веса по признакам для каждой руки: что решатель «понял» (читаемо человеком)."""
        return {a: dict(zip(FEATURE_NAMES, [round(v, 3) for v in self._post(a)[1]])) for a in self.order}


# ------------------------------------------------------------------ стык с BRAIN / RTE
def ctx_from_router(text, ctx=None, complexity_fn=None):
    """Контекст решателя из текста и ctx PRIME (deep_tps, deep_up, fast_up, mode, history_turns, tools) + поля CORE (intent, creator, quiet, ...)."""
    ctx = dict(ctx or {})
    if complexity_fn is None:
        try:
            from RTE.router import complexity as complexity_fn
        except Exception:
            complexity_fn = None
    if complexity_fn:
        c, f = complexity_fn(text, ctx.get("history_turns", 0))
        ctx.update(complexity=c, words=f["words"], code=f["code"], reason=f["reason"], think_kw=f["think_kw"], list=f["list"], q=f["q"], greet=f["greet"])
    else:
        ctx.setdefault("words", len(text.split()))
        ctx.setdefault("complexity", min(len(text.split()) / 120.0, 1.0))
    if "deep_tps" in ctx:
        ctx.setdefault("tps", ctx["deep_tps"])
    return ctx


class SolverExecutor:
    """Исполнитель «Решатель» (п.4 конвейера CORE). run() ≤ 50 мс, чистый CPU. Летописец вызывает observe() после хода.
    base_router(text, ctx) -> {"tier","why","degraded","plan"} (RTE.router.prime_router). Ответ совместим с форматом PRIME + поля turn_id/arm/executors."""

    def __init__(self, policy, base_router, complexity_fn=None):
        self.policy, self.base, self.cfn = policy, base_router, complexity_fn
        self._ctx = {}

    def run(self, text, ctx=None, turn_id=None):
        res = self.base(text, ctx or {})
        pctx = ctx_from_router(text, ctx, self.cfn)
        d = self.policy.decide(pctx, baseline_tier=res["plan"]["tier"] if res.get("plan") else res["tier"], turn_id=turn_id)
        res = json.loads(json.dumps(res))
        res.update(turn_id=d.turn_id, arm=d.arm, executors=list(d.executors), learned=d.explored, policy_rev=d.rev)
        if d.arm != d.baseline:
            arm = self.policy.arms[d.arm]
            plan = res.setdefault("plan", {})
            tps = max(float(pctx.get("tps") or 1.5), 0.05)
            think = min(3000 if pctx.get("complexity", 0) >= 0.8 else 1200, int(tps * 60)) if arm.think else 0
            ans = {"fast": 120, "deep": 400, "deep_think": 900}[arm.tier]
            plan.update(tier=arm.tier, enable_thinking=think > 0, effort="high" if think else "low", think_budget=think, max_tokens=ans + think,
                        intro=arm.intro, reason="learned:%s" % d.arm, notes=list(plan.get("notes", [])) + ["solver_policy:rev%d" % d.rev])
            res["tier"], res["why"] = arm.tier, "learned:%s (base %s)" % (d.arm, d.baseline)
        self._ctx[d.turn_id] = (d.arm, d.x)
        if len(self._ctx) > 1000:
            self._ctx.pop(next(iter(self._ctx)))
        return res

    async def arun(self, *a, **k):
        return self.run(*a, **k)

    def observe(self, turn_id, outcome, reward=None):
        return self.policy.record(turn_id, outcome, reward)

    def observe_late(self, turn_id, outcome):
        """Поправка Создателя в СЛЕДУЮЩЕЙ реплике по уже закрытому ходу."""
        if turn_id in self._ctx:
            arm, x = self._ctx[turn_id]
            self.policy.amend(turn_id, reward_from_outcome(outcome, self.policy.arms[arm].cost), arm, x)
