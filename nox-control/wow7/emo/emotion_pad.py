"""emotion_pad: оценка события по OCC (цель / норма / вкус) -> вектор PAD, затухание, подсказки для тона.

Это РЕГУЛЯТОР СТИЛЯ ответа, а не «психика»: все правила и числа ниже заданы явно и вручную
(якоря эмоций - рабочая договорённость проекта, не данные психологических исследований).
NOX ничего не чувствует; подсказки лишь меняют теплоту, краткость и осторожность формулировок.

Событие (dict): goal -1..1 (желательность последствия для цели), norm -1..1 (похвальность действия по норме),
taste -1..1 (привлекательность объекта), agent "self"|"owner"|"other"|None, unexpected 0..1.
PAD: P удовольствие, A возбуждение, D доминирование, каждое в [-1, 1].
"""
import math
import time

THRESH = 0.2     # ось слабее порога игнорируется
GAIN = 0.6       # доля импульса, добавляемая в состояние
BASELINE = (0.1, 0.0, 0.1)
HALF_LIFE = (600.0, 300.0, 900.0)   # секунд, по осям P, A, D

ANCHORS = {      # P, A, D
    "joy": (0.6, 0.3, 0.3), "distress": (-0.6, 0.3, -0.4),
    "pride": (0.5, 0.2, 0.5), "shame": (-0.5, 0.2, -0.5),
    "admiration": (0.5, 0.3, -0.1), "reproach": (-0.4, 0.2, 0.3),
    "gratification": (0.6, 0.3, 0.5), "remorse": (-0.6, 0.2, -0.5),
    "gratitude": (0.6, 0.2, -0.1), "anger": (-0.5, 0.6, 0.3),
    "liking": (0.4, 0.1, 0.1), "disliking": (-0.4, 0.2, 0.0),
}
PRESETS = {      # удобные готовые события; вызывающий может задавать свои
    "task_done": {"goal": 0.6, "norm": 0.5, "agent": "self"},
    "task_failed": {"goal": -0.7, "norm": -0.4, "agent": "self"},
    "owner_thanks": {"goal": 0.5, "norm": 0.5, "agent": "owner"},
    "owner_correction": {"goal": -0.3, "agent": "owner"},
    "tool_error": {"goal": -0.5, "agent": "other"},
    "harmful_by_other": {"goal": -0.7, "norm": -0.7, "agent": "other"},
    "pleasant_surprise": {"goal": 0.6, "unexpected": 1.0},
    "false_self_claim": {"goal": -0.4, "norm": -0.8, "agent": "self"},     # ACT-11: «сделал» без квитанции -> стыд/раскаяние
}


def clamp(x, lo=-1.0, hi=1.0):
    return max(lo, min(hi, x))


def appraise(event):
    """OCC -> список эмоций [(имя, интенсивность 0..1)] по явным правилам."""
    g = float(event.get("goal", 0.0))
    n = float(event.get("norm", 0.0))
    t = float(event.get("taste", 0.0))
    agent = event.get("agent")
    surprise = 1.0 + 0.5 * clamp(float(event.get("unexpected", 0.0)), 0.0, 1.0)
    out = []
    gs, ns = abs(g) >= THRESH, abs(n) >= THRESH
    if gs and ns and agent and (g > 0) == (n > 0):      # составные эмоции: цель и норма одного знака
        pos = g > 0
        name = ({"self": "gratification", "owner": "gratitude", "other": "gratitude"} if pos
                else {"self": "remorse", "owner": "anger", "other": "anger"})[agent]
        out.append((name, (abs(g) + abs(n)) / 2))
    else:
        if gs:
            out.append(("joy" if g > 0 else "distress", abs(g)))
        if ns:
            if agent == "self":
                out.append(("pride" if n > 0 else "shame", abs(n)))
            elif agent in ("owner", "other"):
                out.append(("admiration" if n > 0 else "reproach", abs(n)))
    if abs(t) >= THRESH:
        out.append(("liking" if t > 0 else "disliking", abs(t)))
    return [(name, min(1.0, i * surprise)) for name, i in out]


def impulse(event):
    p = [0.0, 0.0, 0.0]
    for name, inten in appraise(event):
        for k in range(3):
            p[k] += inten * ANCHORS[name][k]
    return tuple(p)


class PadState:
    def __init__(self, baseline=BASELINE, half_life=HALF_LIFE, gain=GAIN, now=None):
        self.baseline, self.half_life, self.gain = tuple(baseline), tuple(half_life), gain
        self.vec, self.ts = tuple(baseline), now if now is not None else time.time()
        self.log = []

    def value(self, now=None):
        """Состояние с затуханием к базовому уровню: x = b + (x0 - b) * 0.5^(dt / T)."""
        now = self.ts if now is None else now
        dt = max(0.0, now - self.ts)
        return tuple(b + (x - b) * 0.5 ** (dt / h) for x, b, h in zip(self.vec, self.baseline, self.half_life))

    def apply(self, event, now=None):
        """Принять событие (dict или имя из PRESETS). -> новое состояние (P, A, D)."""
        if isinstance(event, str):
            event = PRESETS[event]
        now = time.time() if now is None else now
        cur = self.value(now)
        imp = impulse(event)
        self.vec = tuple(clamp(c + self.gain * i) for c, i in zip(cur, imp))
        self.ts = now
        self.log.append({"ts": now, "emotions": appraise(event), "pad": self.vec})
        return self.vec

    def style(self, now=None):
        """Подсказки тона: теплота, краткость, осторожность (0..1) + русские пометки для промпта."""
        p, a, d = self.value(now)
        warmth = clamp(0.5 + 0.5 * p, 0.0, 1.0)
        brevity = clamp(0.4 + 0.4 * max(a, 0.0) + 0.3 * max(-p, 0.0), 0.0, 1.0)
        caution = clamp(0.3 + 0.4 * max(-d, 0.0) + 0.3 * max(-p, 0.0), 0.0, 1.0)
        notes = []
        if warmth >= 0.6:
            notes.append("Тон теплее обычного, но без лести.")
        elif warmth <= 0.4:
            notes.append("Тон суше и собраннее обычного, без грубости.")
        if brevity >= 0.5:
            notes.append("Отвечай короче обычного.")
        if caution >= 0.45:
            notes.append("Сверяйся с фактами внимательнее и помечай то, в чём не уверен.")
        if not notes:
            notes.append("Тон обычный.")
        return {"warmth": round(warmth, 3), "brevity": round(brevity, 3), "caution": round(caution, 3),
                "pad": tuple(round(x, 3) for x in (p, a, d)), "notes": notes}

    def prompt_line(self, now=None):
        return " ".join(self.style(now)["notes"])
