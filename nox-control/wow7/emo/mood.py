"""mood: настроение = медленный интеграл PAD + влечений, суточный ритм, сохранение; эмоциональная память.

Mood.update(pad_vec, drives_level, fear, now): EMA с периодом полураспада HALF_H (часы) - «настроение» это то, что
остаётся от быстрых эмоций. Суточный ритм сдвигает базу PAD: ночью (23-08 МСК) низкое возбуждение, к полудню максимум.
Обратная связь: mood.baseline() -> новая база для PadState (настроение окрашивает эмоции, но не больше +-0.25).
memory_salience(): эмоция/возбуждение усиливают запоминание (множитель веса записи S03), с потолком.
Это функциональные состояния для стиля и приоритетов, не заявление о переживании.
"""
import os as _os, sys as _sys  # общие модули COMMON (statefile/quiet/fastq/datafence)
for _c in (_os.environ.get("NOX_COMMON", ""), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "COMMON"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "common"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "common")):
    if _c and _os.path.isdir(_c) and _c not in _sys.path:
        _sys.path.append(_c)
import json
import math
import os
import time

import statefile
from quiet import in_quiet

HALF_H = (6.0, 4.0, 8.0)                 # часы полураспада по P, A, D (гипотеза, мерить A/B)
MSK = 3 * 3600


def hour_msk(now):
    return ((now + MSK) % 86400) / 3600.0


def circadian(now):
    """Суточный сдвиг (dP, dA, dD): возбуждение - косинус с пиком в 14:00 МСК, ночью падает; P слегка выше днём."""
    h = hour_msk(now)
    c = math.cos((h - 14.0) / 24.0 * 2 * math.pi)       # +1 в 14:00, -1 в 02:00
    return (0.05 * c, 0.20 * c, 0.03 * c)


def quiet_hours(now):
    return in_quiet(now)       # единые тихие часы: COMMON/quiet.py


class Mood:
    def __init__(self, path=None, base=(0.1, 0.0, 0.1), clock=time.time):
        self.path = path or os.environ.get("NOX_MOOD", "/root/nox/state/mood.json")
        self.clock, self.base = clock, tuple(base)
        self.vec = tuple(base)
        self.drive_load = 0.0          # средняя неудовлетворённость 0..1 (медленная)
        self.fear_load = 0.0
        self.ts = clock()
        self.base_path = os.path.join(os.path.dirname(os.path.abspath(self.path)), "emo_base.json")   # EMO-09: откалиброванная база
        self.samples_path = os.path.join(os.path.dirname(os.path.abspath(self.path)), "mood_samples.jsonl")
        self._last_sample = 0.0
        self._load()
        self._apply_calibrated()

    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
            self.vec = tuple(float(x) for x in d["vec"])[:3]
            self.drive_load, self.fear_load = float(d["drive_load"]), float(d["fear_load"])
            self.ts = float(d["ts"])
            if len(self.vec) != 3:
                raise ValueError
        except (OSError, ValueError, KeyError, TypeError):
            self.vec, self.drive_load, self.fear_load = tuple(self.base), 0.0, 0.0

    def _apply_calibrated(self):
        """EMO-09: если ночная калибровка сдвинула базу - взять её (файл пишет emo_calib.py)."""
        try:
            with open(self.base_path, encoding="utf-8") as f:
                b = tuple(float(x) for x in json.load(f)["base"])
            if len(b) == 3 and all(-1.0 <= x <= 1.0 for x in b):
                self.base = b
        except (OSError, ValueError, KeyError, TypeError):
            pass

    def _sample(self, now, every=600.0):
        """Редкая выборка вектора настроения для недельной средней (EMO-09)."""
        if now - self._last_sample < every:
            return
        self._last_sample = now
        try:
            statefile.append_line(self.samples_path, json.dumps({"ts": now, "vec": [round(x, 4) for x in self.vec]}))
        except OSError:
            pass

    def save(self):
        try:
            statefile.save(self.path, {"vec": self.vec, "drive_load": self.drive_load, "fear_load": self.fear_load, "ts": self.ts})
        except OSError:
            pass

    def update(self, pad_vec, drives_level=None, fear=None, now=None):
        """Подмешать текущий PAD (интеграл по времени). Вызывать на каждом тике. -> вектор настроения."""
        now = self.clock() if now is None else now
        dh = max(0.0, (now - self.ts) / 3600.0)
        out = []
        for x, p, hl in zip(self.vec, pad_vec, HALF_H):
            a = 1.0 - 0.5 ** (dh / hl)            # доля «нового» за прошедшее время
            out.append(max(-1.0, min(1.0, x + a * (p - x))))
        self.vec = tuple(out)
        a = 1.0 - 0.5 ** (dh / 6.0)
        if drives_level:
            self.drive_load += a * (sum(drives_level.values()) / len(drives_level) - self.drive_load)
        if fear:
            self.fear_load += a * (max(fear.values()) - self.fear_load)
        self.ts = now
        self.save()
        self._sample(now)
        return self.vec

    def effective(self, now=None):
        """Настроение с учётом суток и нагрузки: P падает от тревоги, A растёт от неутолённых влечений."""
        now = self.clock() if now is None else now
        dp, da, dd = circadian(now)
        p, a, d = self.vec
        return (max(-1.0, min(1.0, p + dp - 0.3 * self.fear_load)),
                max(-1.0, min(1.0, a + da + 0.15 * self.drive_load)),
                max(-1.0, min(1.0, d + dd - 0.2 * self.fear_load)))

    def baseline(self, now=None):
        """База для PadState: исходная + настроение, не дальше +-0.25 от исходной."""
        e = self.effective(now)
        return tuple(b + max(-0.25, min(0.25, 0.5 * (x - b))) for b, x in zip(self.base, e))

    def label(self, now=None):
        p, a, d = self.effective(now)
        if p >= 0.25:
            return "бодрое" if a >= 0.1 else "спокойное"
        if p <= -0.2:
            return "напряжённое" if a >= 0.1 else "подавленное"
        return "собранное" if a >= 0.1 else "ровное"


def memory_salience(pad_vec, emotions=None, floor=1.0, cap=2.0):
    """Множитель веса записи в память: 1 + 0.6*|возбуждение| + 0.4*|удовольствие|, не выше cap.
    emotions - [(имя, интенсивность)] из appraise(); сильное чувство добавляет до +0.3. Нейтральное -> floor."""
    p, a, _ = pad_vec
    w = floor + 0.6 * abs(a) + 0.4 * abs(p)
    if emotions:
        w += 0.3 * max(i for _, i in emotions)
    return round(min(cap, w), 3)


def decay_weight(weight, age_h, salience=1.0, half_h=72.0):
    """Затухание значимости записи: эмоционально нагруженные забываются медленнее (период * salience)."""
    return weight * 0.5 ** (age_h / (half_h * max(1.0, salience)))
