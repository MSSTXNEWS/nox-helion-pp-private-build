"""RTE-01 router.py: авто-выбор fast / bridge_deep / deep / deep_think по сложности запроса и ТЕКУЩЕЙ ток/с GLM.
Расширяет glm53/qs6_core.route_tier (правила слов/кода) и community/chalie_router: здесь добавлен бюджет времени и бюджет размышлений.
Чистая функция, без сети. План -> параметры для шлюза (chat_template_kwargs.enable_thinking, max_tokens, reasoning_effort)."""
import re
from dataclasses import dataclass, field, asdict

CODE_RE = re.compile(r"```|\bdef |\bclass |\bSELECT\b|\bimport \w+|traceback|python|bash|sql|регуляр|скрипт|функци|код\b|баг|ошибк", re.I)
REASON_RE = re.compile(r"почему|докажи|сравни|проанализ\w*|оцени|спланируй|архитектур\w*|стратеги\w*|плюсы и минусы|объясни|разбер\w+|рассчитай|посчитай|вывед\w+|trade-?off|step by step", re.I)
THINK_RE = re.compile(r"подума\w*|глубок\w*|тщательно|детально|подробн\w*|в\s+деталях|think (?:hard|deeply|carefully)", re.I)
LIST_RE = re.compile(r"список|перечисли|таблиц\w*|по пунктам|план\b|пошагов\w*", re.I)
GREET_RE = re.compile(r"^\W*(привет\w*|здравствуй\w*|добр\w+ (?:день|вечер|утро|ночи)|хай|салют|спасибо|ок|окей|ага|угу|да|нет|понял\w*|ясно|пока)\W*$", re.I)

TIERS = ("fast", "bridge_deep", "deep", "deep_think")


@dataclass
class RouterConfig:
    wait_budget_s: float = 240.0      # дольше этого полный ответ GLM не планируем
    think_budget_s: float = 60.0      # сколько секунд готовы отдать на размышление
    min_think_tokens: int = 256       # меньший бюджет размышлений бессмыслен -> thinking выключаем
    intro_if_eta_s: float = 3.0       # если полный ответ ждать дольше, включаем быстрое вступление
    answer_tokens: tuple = (120, 400, 900)   # ожидаемая длина ответа по сложности (низкая/средняя/высокая), гипотеза, мерить A/B
    think_tokens_high: int = 3000     # желаемый бюджет размышлений для высокой сложности
    tps_think_min: float = 4.0        # ниже этой скорости размышление GLM без явной просьбы не включаем


def load_tuned(path):
    """RTE-11: файл порогов, записанный tune.py -> dict {think_budget_s, wait_budget_s, ...} или None (нет/битый)."""
    import json
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        if all(isinstance(d.get(k), (int, float)) and d[k] > 0 for k in ("think_budget_s", "wait_budget_s")):
            return d
    except (OSError, ValueError, AttributeError):
        pass
    return None


def tuned_config(path, base=None):
    """RouterConfig с порогами из файла (остальное - по умолчанию/base)."""
    d = load_tuned(path)
    cfg = base or RouterConfig()
    if d:
        cfg = RouterConfig(**dict(asdict(cfg), think_budget_s=float(d["think_budget_s"]), wait_budget_s=float(d["wait_budget_s"])))
    return cfg


@dataclass
class Plan:
    tier: str
    enable_thinking: bool
    effort: str
    max_tokens: int
    think_budget: int
    intro: bool
    eta_s: float
    reason: str
    notes: list = field(default_factory=list)
    features: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)

    def gateway_fields(self):
        """Поля тела запроса к шлюзу (см. gateway_patch.md, режим deep_only)."""
        return {"nox_mode": "deep_only", "nox_no_route": True, "max_tokens": self.max_tokens, "reasoning_effort": self.effort,
                "chat_template_kwargs": {"enable_thinking": self.enable_thinking}}


def complexity(text, history_turns=0):
    """0..1. Грубые признаки; калибровать по журналу A/B (гипотеза)."""
    w = len(text.split())
    f = {"words": w, "chars": len(text), "code": bool(CODE_RE.search(text)), "reason": bool(REASON_RE.search(text)),
         "think_kw": bool(THINK_RE.search(text)), "list": bool(LIST_RE.search(text)), "q": text.count("?"), "greet": bool(GREET_RE.match(text)),
         "history_turns": history_turns}
    c = min(w / 120.0, 0.4)
    c += 0.3 if f["code"] else 0
    c += 0.25 if f["reason"] else 0
    c += 0.2 if f["think_kw"] else 0
    c += 0.1 if f["list"] else 0
    c += min(0.1 * max(f["q"] - 1, 0), 0.2)
    c += min(history_turns / 40.0, 0.1)
    if f["greet"]:
        c = 0.0
    return min(c, 1.0), f


def route(text, *, deep_tps, fast_tps=40.0, deep_up=True, fast_up=True, mode=None, history_turns=0, tools=False, cfg=None):
    """mode: None|'fast'|'deep'|'max' (как режимы «Резонанса»). deep_tps — ИЗМЕРЕННАЯ ток/с GLM (SpeedMeter.tps('deep'))."""
    cfg = cfg or RouterConfig()
    c, f = complexity(text, history_turns)
    notes = []
    tps = max(float(deep_tps or 0.0), 0.05)
    lo, mid, hi = cfg.answer_tokens

    def eta(tokens, think=0):
        return round(2.0 + (tokens + think) / tps, 1)

    if not deep_up:
        if not fast_up:
            return Plan("fast", False, "low", 0, 0, False, 0.0, "all_down", ["no_upstream"], f)
        return Plan("fast", False, "low", 512, 0, False, round(0.3 + lo / fast_tps, 1), "deep_down", ["deep_unavailable"], f)
    if mode == "fast" and fast_up:
        return Plan("fast", False, "low", 512, 0, False, round(0.3 + lo / fast_tps, 1), "mode_fast", notes, f)
    if tools:
        c = max(c, 0.6)
        notes.append("tools")
    if mode == "max":
        c = 1.0
    if mode is None and fast_up and c < 0.25 and not tools:
        return Plan("fast", False, "low", 512, 0, False, round(0.3 + lo / fast_tps, 1), "simple", notes, f)

    if c < 0.55 and mode not in ("deep", "max"):
        tier, think_want, ans, effort = "bridge_deep", 0, mid, "low"
    else:
        tier, think_want, ans, effort = "deep_think", cfg.think_tokens_high if c >= 0.8 or mode == "max" else 1200, hi, "high"
        if mode == "max":
            effort = "max"
    # бюджет по скорости
    think_cap = int(tps * cfg.think_budget_s)
    think = min(think_want, think_cap)
    explicit = f["think_kw"] or mode in ("deep", "max")
    if tier == "deep_think" and (think < cfg.min_think_tokens or (tps < cfg.tps_think_min and not explicit)):
        notes.append("think_skipped_low_tps(%.1f)" % tps)
        tier, think, effort = "deep", 0, "low"
    if tier == "deep_think" and think < think_want:
        notes.append("think_budget_capped:%d<%d" % (think, think_want))
    # потолок ожидания: режем длину ответа, а не молча ждём
    left = cfg.wait_budget_s - 2.0 - think / tps
    max_ans = max(int(left * tps), 64)
    if ans > max_ans:
        notes.append("answer_capped:%d<%d" % (max_ans, ans))
        ans = max_ans
    e = eta(ans, think)
    intro = bool(fast_up) and e >= cfg.intro_if_eta_s
    if tier == "bridge_deep" and not intro:
        tier = "deep"
    max_tokens = ans + think
    return Plan(tier, think > 0, effort, max_tokens, think, intro, e, "complexity=%.2f" % c, notes, f)


def prime_router(text, ctx=None):
    """ЕДИНЫЙ роутер для PRIME (router=RTE.router.prime_router): формат ответа PRIME {"tier","why","degraded","plan"}.
    PRIME.default_router остаётся лишь запасным при ImportError, без собственных порогов (REVIEW_1 п.2, исправление 4).
    ctx: {"deep_tps": float|None, "deep_up": bool, "fast_up": bool, "mode": None|'fast'|'deep'|'max', "history_turns": int, "tools": bool}"""
    ctx = ctx or {}
    p = route(text, deep_tps=ctx.get("deep_tps") or 1.5, deep_up=ctx.get("deep_up", True) is not False, fast_up=ctx.get("fast_up", True) is not False,
              mode=ctx.get("mode"), history_turns=ctx.get("history_turns", 0), tools=bool(ctx.get("tools")))
    tier = {"bridge_deep": "deep"}.get(p.tier, p.tier)
    return {"tier": tier, "why": p.reason, "degraded": p.reason in ("deep_down", "all_down"), "plan": p.to_dict()}
