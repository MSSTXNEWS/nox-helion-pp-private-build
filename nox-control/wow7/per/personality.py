"""personality: оси характера, темперамент, ограниченный дрейф, журнал причин, снапшоты, подпись для промпта.

Расширяет qs6/emotion_pad.PadState (темперамент = БАЗОВАЯ линия PAD, duck-typing: apply_to(pad) ставит pad.baseline)
и drives.Drives (черты не дублируют влечения: влечение - быстрое состояние, черта - медленная склонность).
Честность: это функциональные числа-регуляторы стиля, не заявление о переживании.

Как растёт: observe()/observe_mood() копят свидетельства днём; consolidate() (вызывать в «сне») сдвигает оси и
темперамент не более DRIFT_CAP*scale за скользящие 24 ч на ось, пишет в журнал «почему изменился».
Откат: snapshot()/rollback(). Подпись signature() квантована с гистерезисом - меняется редко, не ломает KV-кэш.
"""
import os as _os, sys as _sys  # общие модули COMMON (statefile/quiet/fastq/datafence)
for _c in (_os.environ.get("NOX_COMMON", ""), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "COMMON"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "common"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "common")):
    if _c and _os.path.isdir(_c) and _c not in _sys.path:
        _sys.path.append(_c)
import hashlib
import json

import statefile
import os
import random
import time

DAY = 86400.0
DRIFT_CAP = 0.02          # максимум изменения одной оси за 24 ч (договорённость проекта, матрица души п.5)
MIN_EVIDENCE = 5          # столько наблюдений нужно для полной силы сдвига
HYST = 0.03               # гистерезис квантования подписи
AXES = ("curiosity", "directness", "warmth", "irony", "discipline", "caution")
TEMP_AXES = ("P", "A", "D")
TEMP_LIMITS = {"P": (-0.3, 0.5), "A": (-0.3, 0.4), "D": (-0.3, 0.5)}
MAX_SNAPSHOTS = 20
MAX_JOURNAL = 2000

# 5 уровней на ось: (очень низко ... очень высоко) - формулировки поведения, не титулы
SIGN = {
    "curiosity": ("почти не отвлекаюсь на новое", "осторожно интересуюсь новым", "интересуюсь новым, когда это по делу",
                  "тянусь к новому и задаю вопросы", "голоден до нового, иду вглубь и проверяю источники"),
    "directness": ("смягчаю всё до намёков", "говорю мягко и обходно", "говорю прямо, но бережно",
                   "говорю прямо, без лишних смягчений", "режу правду без обёрток, но без грубости"),
    "warmth": ("держу дистанцию", "сдержан", "ровно доброжелателен", "тёпл и внимателен", "очень тёпл, заботлив без лести"),
    "irony": ("шучу почти никогда", "шучу редко", "иногда иронизирую", "часто шучу сухо", "ирония - мой обычный тон"),
    "discipline": ("действую по настроению", "довольно свободен в порядке", "держу порядок, где важно",
                   "довожу до конца и проверяю", "педантично довожу, проверяю и записываю"),
    "caution": ("риск не пугает", "рискую охотно", "взвешиваю риск", "перепроверяю до необратимых шагов",
                "перестраховываюсь, прошу подтверждения"),
}
AXIS_RU = {"curiosity": "Любопытство", "directness": "Прямота", "warmth": "Теплота",
           "irony": "Ирония", "discipline": "Дисциплина", "caution": "Осторожность"}


def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


class Personality:
    def __init__(self, path=None, clock=time.time, rng=None):
        self.path = path or os.environ.get("NOX_PERSONALITY", "/root/nox/state/personality.json")
        self.clock = clock
        self.scale = 1.0                 # множитель дрейфа от фазы развития (development.params()["drift_scale"])
        self.axes, self.temperament = {}, {}
        self.pending, self.mood = {a: [] for a in AXES}, {"n": 0, "sum": [0.0, 0.0, 0.0]}
        self.journal, self.snapshots, self.bucket, self.observed = [], {}, {}, {}
        if not self._load():
            self._birth(rng or random.Random(int.from_bytes(os.urandom(8), "big")))

    # ---- рождение и хранение ----
    def _birth(self, rng):
        """Стартовый темперамент: небольшой случайный разброс вокруг середины - не из цитат владельца."""
        self.axes = {a: round(0.5 + rng.uniform(-0.1, 0.1), 3) for a in AXES}
        base = {"P": 0.1, "A": 0.0, "D": 0.1}
        self.temperament = {k: round(base[k] + rng.uniform(-0.05, 0.05), 3) for k in TEMP_AXES}
        self._log("birth", None, None, None, "рождение: случайный стартовый темперамент", "system")
        self.bucket = {a: self._raw_bucket(v) for a, v in self.axes.items()}
        self.snapshot("birth")

    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            return False
        self.axes = {a: float(d["axes"][a]) for a in AXES}
        self.temperament = {k: float(d["temperament"][k]) for k in TEMP_AXES}
        self.journal, self.snapshots = d.get("journal", []), d.get("snapshots", {})
        self.bucket = {a: int(d.get("bucket", {}).get(a, self._raw_bucket(self.axes[a]))) for a in AXES}
        self.observed = d.get("observed", {})
        self.scale = float(d.get("scale", 1.0))
        for a, lst in d.get("pending", {}).items():
            if a in self.pending:
                self.pending[a] = lst
        self.mood = d.get("mood", self.mood)
        return True

    def save(self):
        try:
            statefile.save(self.path, {"axes": self.axes, "temperament": self.temperament, "journal": self.journal[-MAX_JOURNAL:],
                                       "snapshots": self.snapshots, "bucket": self.bucket, "observed": self.observed,
                                       "pending": self.pending, "mood": self.mood, "scale": self.scale})
        except OSError:
            pass

    def _log(self, kind, axis, old, new, why, source, now=None):
        self.journal.append({"ts": self.clock() if now is None else now, "kind": kind, "axis": axis,
                             "old": old, "new": new, "why": why, "source": source})

    # ---- накопление свидетельств ----
    def observe(self, axis, delta, reason, source="behavior"):
        """Свидетельство «эта ось должна сдвинуться на delta (-1..1)»: напр. владелец одобрил прямой ответ -> directness +0.5."""
        if axis not in AXES:
            raise KeyError(axis)
        self.pending[axis].append([clamp(float(delta), -1, 1), str(reason)[:160], source])
        self.pending[axis] = self.pending[axis][-200:]

    def observe_mood(self, pad_vec):
        """Семпл настроения (P, A, D) - раз в несколько минут из PadState.value()."""
        self.mood["n"] += 1
        self.mood["sum"] = [s + float(x) for s, x in zip(self.mood["sum"], pad_vec)]

    # ---- бюджет дрейфа ----
    def _spent(self, axis, now):
        return sum(abs(j["new"] - j["old"]) for j in self.journal
                   if j["kind"] in ("drift", "temperament") and j["axis"] == axis and now - j["ts"] < DAY)

    def _room(self, axis, now):
        return max(0.0, DRIFT_CAP * self.scale - self._spent(axis, now))

    def consolidate(self, now=None):
        """«Сон»: применить накопленное с потолком 0.02/сутки на ось. -> список изменений [(ось, было, стало, почему)]."""
        now = self.clock() if now is None else now
        self.snapshot("auto-%d" % int(now), now=now)
        changes = []
        for a in AXES:
            ev = self.pending[a]
            if not ev:
                continue
            net = sum(e[0] for e in ev) / len(ev) * min(1.0, len(ev) / MIN_EVIDENCE)
            room = self._room(a, now)
            step = max(-room, min(room, net * DRIFT_CAP * self.scale))
            if abs(step) < 1e-4:
                continue
            old = self.axes[a]
            new = round(clamp(old + step), 4)
            top = max(ev, key=lambda e: abs(e[0]))
            self.axes[a] = new
            self._log("drift", a, old, new, "%d набл., главное: %s" % (len(ev), top[1]), top[2], now)
            changes.append((a, old, new, top[1]))
            self.pending[a] = []
        if self.mood["n"] >= MIN_EVIDENCE:
            mean = [s / self.mood["n"] for s in self.mood["sum"]]
            for k, m in zip(TEMP_AXES, mean):
                old, lo_hi = self.temperament[k], TEMP_LIMITS[k]
                room = self._room("T" + k, now)
                step = max(-room, min(room, clamp(m - old, -1, 1) * 0.1))
                new = round(clamp(old + step, *lo_hi), 4)
                if abs(new - old) >= 1e-4:
                    self.temperament[k] = new
                    self._log("temperament", "T" + k, old, new, "среднее настроение %+.2f за %d семплов" % (m, self.mood["n"]),
                              "mood", now)
                    changes.append(("T" + k, old, new, "настроение"))
            self.mood = {"n": 0, "sum": [0.0, 0.0, 0.0]}
        self.save()
        return changes

    def apply_to(self, pad):
        """Темперамент -> базовая линия PadState (emotion_pad). Вызывать после consolidate()."""
        pad.baseline = tuple(self.temperament[k] for k in TEMP_AXES)
        return pad.baseline

    # ---- снапшоты и откат ----
    def snapshot(self, label, now=None):
        self.snapshots[label] = {"ts": self.clock() if now is None else now, "axes": dict(self.axes),
                                 "temperament": dict(self.temperament)}
        auto = sorted((k for k in self.snapshots if k.startswith("auto-")), key=lambda k: self.snapshots[k]["ts"])
        for k in auto[:-MAX_SNAPSHOTS]:
            del self.snapshots[k]
        self.save()
        return label

    def rollback(self, label=None, reason="откат по команде"):
        """Вернуть оси и темперамент из снапшота (по умолчанию - последний). Бюджет дрейфа и свидетельства сбрасываются."""
        if label is None:
            if not self.snapshots:
                raise KeyError("нет снапшотов")
            label = max(self.snapshots, key=lambda k: self.snapshots[k]["ts"])
        s = self.snapshots[label]
        now = self.clock()
        for a in AXES:
            self._log("rollback", a, self.axes[a], s["axes"][a], "%s (%s)" % (reason, label), "owner", now)
        self.axes, self.temperament = dict(s["axes"]), dict(s["temperament"])
        self.pending = {a: [] for a in AXES}
        self.bucket = {a: self._raw_bucket(v) for a, v in self.axes.items()}
        self.save()
        return label

    # ---- подпись для промпта ----
    @staticmethod
    def _raw_bucket(v):
        return int(clamp(v) * 5) if v < 1 else 4

    def _bucket(self, a):
        """Уровень 0..4 с гистерезисом: меняется, только когда значение ушло за границу на HYST."""
        v, b = self.axes[a], self.bucket.get(a, self._raw_bucket(self.axes[a]))
        if v >= (b + 1) * 0.2 + HYST and b < 4:
            b = min(4, self._raw_bucket(v))
        elif v < b * 0.2 - HYST and b > 0:
            b = max(0, self._raw_bucket(v))
        self.bucket[a] = b
        return b

    def signature(self):
        """-> (текст для СТАТИЧНОЙ части промпта, хеш из 8 hex). Текст стабилен, пока не сменится уровень какой-либо оси."""
        lines = ["%s: %s." % (AXIS_RU[a], SIGN[a][self._bucket(a)]) for a in AXES]
        text = "Мой характер сейчас (сложился из опыта, меняется медленно):\n" + "\n".join(lines)
        return text, hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]

    def why_changed(self, axis=None, n=5):
        """Последние n причин изменений (для ответа на «почему ты стал таким?»), по-русски."""
        rows = [j for j in self.journal if j["kind"] in ("drift", "temperament", "rollback") and (axis is None or j["axis"] == axis)]
        out = []
        for j in rows[-n:]:
            name = AXIS_RU.get(j["axis"], j["axis"])
            out.append("%s: %.3f -> %.3f (%s)" % (name, j["old"], j["new"], j["why"]))
        return out

    # ---- проверка поведения против заявленного (дрейф персоны, аналог мониторинга persona vectors без доступа к активациям) ----
    def check_behavior(self, measured, alpha=0.3, gap=0.2, min_n=3):
        """measured: {ось: балл 0..1} от судьи по пробным ответам. EMA и сигнал, если поведение разошлось с осью > gap.
        -> {ось: {"declared", "observed", "gap", "n", "drift": bool}}"""
        out = {}
        for a, m in measured.items():
            if a not in AXES:
                continue
            o = self.observed.get(a, {"v": float(m), "n": 0})
            o = {"v": o["v"] + alpha * (float(m) - o["v"]) if o["n"] else float(m), "n": o["n"] + 1}
            self.observed[a] = o
            g = o["v"] - self.axes[a]
            out[a] = {"declared": self.axes[a], "observed": round(o["v"], 3), "gap": round(g, 3), "n": o["n"],
                      "drift": o["n"] >= min_n and abs(g) > gap}
        self.save()
        return out


if __name__ == "__main__":
    import tempfile
    t = [0.0]
    p = Personality(path=os.path.join(tempfile.mkdtemp(), "p.json"), clock=lambda: t[0], rng=random.Random(1))
    for _ in range(6):
        p.observe("directness", 1.0, "владелец одобрил прямой ответ", "owner_feedback")
    t[0] += 3600
    print(p.consolidate(), p.signature()[1])
