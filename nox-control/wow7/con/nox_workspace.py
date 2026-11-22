"""Глобальное рабочее пространство NOX (CON-02): конкурс сигналов за фокус -> блок «Я сейчас».

Идея Global Workspace Theory (Baars/Dehaene; для LLM-агентов см. «Global Workspace Agents», arXiv 2604.08206):
много специализированных источников (тело, влечения, страхи, память, мысли, сообщения владельца) постят
сигналы; узкое «горлышко» пропускает один победитель (зажигание, если оценка >= порога); победитель
рассылается всем подписчикам (broadcast) и попадает в блок «Я сейчас». Привыкание (habituation) не даёт
застрять на одном сигнале. Схема внимания (Attention Schema Theory) — краткая модель собственного внимания:
что в фокусе, почему, что вытеснено, как долго.
Функциональная модель, не заявление о переживании.
"""
import hashlib
import time
from collections import deque

KIND_WEIGHT = {"owner": 1.3, "fear": 1.2, "discrepancy": 1.1, "drive": 1.0, "body": 0.9, "time": 0.85,
               "memory": 0.8, "thought": 0.7}


class Workspace:
    def __init__(self, clock=time.time, threshold=0.35, half_life=1800.0, habituation=0.18, habit_window=3600.0):
        self.clock = clock
        self.threshold = threshold
        self.half_life = half_life
        self.habituation = habituation
        self.habit_window = habit_window
        self.signals = {}            # key -> dict
        self.wins = deque(maxlen=200)  # (ts, key)
        self.subscribers = []
        self.focus = None            # последний победитель (dict) или None
        self.focus_since = None
        self.last_ranking = []

    def post(self, key, text, salience, kind="body", ttl=3600.0):
        """Добавить/обновить сигнал. salience 0..1."""
        self.signals[key] = {"key": key, "text": text, "salience": max(0.0, min(1.0, float(salience))),
                             "kind": kind, "ts": self.clock(), "ttl": ttl}

    def subscribe(self, fn):
        self.subscribers.append(fn)

    def _score(self, s, now):
        age = max(0.0, now - s["ts"])
        fresh = 0.5 ** (age / self.half_life)
        recent = sum(1 for ts, k in self.wins if k == s["key"] and now - ts <= self.habit_window)
        base = s["salience"] * KIND_WEIGHT.get(s["kind"], 0.8) * (0.4 + 0.6 * fresh)
        return max(0.0, base - self.habituation * recent)

    def compete(self):
        """Один цикл конкурса. -> победитель (dict с 'score') или None (тишина: ничто не прошло порог)."""
        now = self.clock()
        for k in [k for k, s in self.signals.items() if now - s["ts"] > s["ttl"]]:
            del self.signals[k]
        ranking = sorted(({**s, "score": round(self._score(s, now), 4)} for s in self.signals.values()),
                         key=lambda x: -x["score"])
        self.last_ranking = ranking
        if not ranking or ranking[0]["score"] < self.threshold:
            self.focus = None
            return None
        win = ranking[0]
        if not self.focus or self.focus["key"] != win["key"]:
            self.focus_since = now
        self.focus = win
        self.wins.append((now, win["key"]))
        for fn in list(self.subscribers):
            try:
                fn(win, ranking)
            except Exception:
                pass
        return win

    def schema(self):
        """Схема внимания: модель собственного внимания (что, почему, что отодвинуто)."""
        if not self.focus:
            return {"focus": None, "why": "ничто не превысило порог", "suppressed": [], "since_s": None}
        f, now = self.focus, self.clock()
        why = "%s, острота %.2f, вес класса %.2f" % (f["kind"], f["salience"], KIND_WEIGHT.get(f["kind"], 0.8))
        sup = [r["text"][:60] for r in self.last_ranking[1:3] if r["score"] >= self.threshold * 0.6]
        return {"focus": f["text"], "why": why, "suppressed": sup, "since_s": now - (self.focus_since or now)}

    def render_block(self, extra_lines=None, max_chars=900):
        """Блок «Я сейчас»: фокус + схема внимания + строки от я-модели/тела."""
        sc = self.schema()
        lines = ["[Я СЕЙЧАС]"]
        lines.append("Фокус: %s." % sc["focus"] if sc["focus"] else "Фокус: тишина, спокойное ожидание.")
        if sc["focus"]:
            lines.append("Почему он: %s." % sc["why"])
        if sc["suppressed"]:
            lines.append("Отодвинуто: " + "; ".join(sc["suppressed"]) + ".")
        now = self.clock()
        lines += [s["text"] for k, s in sorted(self.signals.items())      # сигналы EMO (настроение/влечения): их поставляет EMO, рендерит только этот метод
                  if k.startswith("emo:") and now - s["ts"] <= s["ttl"] and not (self.focus and self.focus["key"] == k)]
        lines += list(extra_lines or [])
        out = "\n".join(lines)
        return out if len(out) <= max_chars else out[:max_chars - 1].rsplit("\n", 1)[0]


def thought_key(text):
    return "thought:" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]


def drives_sensor(drives, drive_on=0.7, fear_on=0.5):
    """Сенсор для InnerLoop: превращает drives.Drives (уровни .level/.fear) в сигналы рабочего пространства.
    Подписи берутся из drives.DRIVES/FEARS, если модуль доступен, иначе имя ключа."""
    try:
        import drives as D
        dl = {k: v[2] for k, v in D.DRIVES.items()}
        fl = {k: v[1] for k, v in D.FEARS.items()}
    except Exception:
        dl, fl = {}, {}

    def sense(ws, sm=None):
        for k, v in drives.fear.items():
            if v >= fear_on:
                ws.post("fear:" + k, "%s (%d%%)" % (fl.get(k, k), round(v * 100)), v, "fear", ttl=1800)
        for k, v in drives.level.items():
            if v >= drive_on:
                ws.post("drive:" + k, "%s (%d%%)" % (dl.get(k, k), round(v * 100)), v, "drive", ttl=1800)
    return sense
