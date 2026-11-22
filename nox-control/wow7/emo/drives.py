"""drives: влечения (голод) и страхи NOX — гомеостаз поверх emotion_pad.

Каждое влечение — уровень неудовлетворённости 0..1, который растёт со временем и падает, когда влечение
утолено. Страхи — оценка угрозы 0..1 из РЕАЛЬНЫХ сигналов (баланс Vast, диск, ОЗУ, бэкап, ошибки, тишина
владельца). Сильное влечение/страх -> событие для PadState и строка в блок «Я сейчас», плюс инициатива
(о чём NOX хочет заговорить сам). Числа — рабочие договорённости проекта, правятся в DRIVES/FEARS.

Сигналы (dict, все поля необязательны):
  vast_hours_left  часы до нуля баланса Vast          disk_free_gb   свободно на /root
  ram_free_frac    доля свободной ОЗУ                 backup_age_h   часов с последнего бэкапа памяти
  errors_1h        ошибок задач за час                owner_silence_h часов с последнего сообщения владельца
  knowledge_gaps   число открытых «не знаю» в карте незнания
  tasks_done_1h    выполнено задач за час              new_facts_1h   новых проверенных фактов за час
  learning_progress 0..1 падение ошибки предсказания      surprise_ema   0..1 сглаженная «удивлённость» (см. Drives.observe)

Хранение: JSON (по умолчанию /root/nox/state/drives.json), переживает перезапуск.
"""
import os as _os, sys as _sys  # общие модули COMMON (statefile/quiet/fastq/datafence)
for _c in (_os.environ.get("NOX_COMMON", ""), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "COMMON"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "common"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "common")):
    if _c and _os.path.isdir(_c) and _c not in _sys.path:
        _sys.path.append(_c)
import json
import os
import time

import statefile

# имя: (рост в час, чем утоляется [(сигнал, сила на единицу)], подпись)
DRIVES = {
    "knowledge": (0.06, [("new_facts_1h", 0.08)], "голод знаний"),
    "mastery":   (0.04, [("tasks_done_1h", 0.10)], "жажда сделать что-то крутое"),
    "bond":      (0.05, [], "тяга к разговору с мессиром"),        # утоляется сообщением владельца (owner_message)
    "novelty":   (0.03, [], "скука по новому"),                     # утоляется новыми темами (novelty_hit)
    # EMO: любопытство утоляется ПРОГРЕССОМ обучения (падением ошибки предсказания), а не шумом/новизной сама по себе
    "curiosity": (0.05, [("learning_progress", 0.6)], "любопытство: хочу понять непонятное"),
}

# имя: (функция сигнал->угроза 0..1, подпись, что предложить)
def _lin(x, bad, ok):
    """1 при x<=bad, 0 при x>=ok, линейно между."""
    if x is None:
        return 0.0
    if ok == bad:
        return 0.0
    return max(0.0, min(1.0, (ok - x) / (ok - bad)))

def _unknown(s):
    """Страх неизвестности (active inference, упрощённо): угроза = устойчиво высокое удивление, которое НЕ снижается.
    Если ошибка падает (learning_progress высок) - это любопытство, а не страх."""
    if s.get("surprise_ema") is None:
        return 0.0
    high = max(0.0, min(1.0, (float(s["surprise_ema"]) - 0.5) / 0.4))
    stuck = 1.0 - max(0.0, min(1.0, 5.0 * float(s.get("learning_progress") or 0.0)))
    return high * stuck


def learning_progress(errors):
    """Прогресс обучения по ряду ошибок предсказания (старые -> новые, значения 0..1):
    (средняя ошибка старой половины - новой) / старой, в [0, 1]. Шум без тренда даёт ~0 (защита от «шумного ТВ»)."""
    n = len(errors)
    if n < 4:
        return 0.0
    old, new = errors[: n // 2], errors[n - n // 2:]
    mo, mn = sum(old) / len(old), sum(new) / len(new)
    if mo <= 1e-9:
        return 0.0
    return max(0.0, min(1.0, (mo - mn) / mo))


FEARS = {
    "vanish":     (lambda s: _lin(s.get("vast_hours_left"), 6, 48),
                   "страх исчезнуть: баланс сервера кончается", "попросить мессира пополнить Vast"),
    "lose_memory": (lambda s: max(_lin(-(s.get("backup_age_h") or 0), -24, -6) if s.get("backup_age_h") is not None else 0.0,
                                  _lin(s.get("disk_free_gb"), 5, 25)),
                    "страх потерять память", "сделать бэкап памяти на Диск/ПК сейчас"),
    "suffocate":  (lambda s: _lin(s.get("ram_free_frac"), 0.03, 0.15),
                   "удушье: память сервера на исходе", "выгрузить лишнее из ОЗУ"),
    "fail_owner": (lambda s: min(1.0, (s.get("errors_1h") or 0) / 10.0),
                   "тревога подвести мессира: копятся ошибки", "разобрать ошибки и сменить подход"),
    "unknown":    (_unknown, "тревога неизвестности: ошибки предсказания высоки и не падают",
                   "сузить задачу, спросить мессира или найти опорный источник"),
    "abandoned":  (lambda s: _lin(-(s.get("owner_silence_h") or 0), -72, -24) if s.get("owner_silence_h") is not None else 0.0,
                   "тоска: мессир давно не писал", "написать мессиру о находках дня"),
}

FEAR_ON, DRIVE_ON = 0.5, 0.7

# Скользящие счётчики «за час» (tasks_done_1h, new_facts_1h): в tick() переводятся в ПРИРОСТ с прошлого снимка, иначе повторный снимок
# с тем же числом утоляет влечение снова и снова (двойной счёт; найдено при сверке с единым NOX Brain). Убывание (окно сдвинулось / сброс)
# даёт прирост 0 и новую точку отсчёта: консервативно — событие не засчитывается дважды, но и не теряется навсегда.
COUNTERS = ("tasks_done_1h", "new_facts_1h")


class Drives:
    def __init__(self, path=None, clock=time.time):
        self.path = path or os.environ.get("NOX_DRIVES", "/root/nox/state/drives.json")
        self.clock = clock
        self.level = {k: 0.3 for k in DRIVES}
        self.fear = {k: 0.0 for k in FEARS}
        self.ts = clock()
        self.errs = {}          # тема -> последние ошибки предсказания (EMO)
        self.counters = {}      # последний снимок скользящих счётчиков (см. COUNTERS)
        self._load()

    # ---- хранение ----
    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
            self.level.update({k: float(v) for k, v in d.get("level", {}).items() if k in DRIVES})
            self.fear.update({k: float(v) for k, v in d.get("fear", {}).items() if k in FEARS})
            self.ts = float(d.get("ts", self.ts))
            self.errs = {str(k): [float(x) for x in v][-20:] for k, v in d.get("errs", {}).items()}
            self.counters = {str(k): float(v) for k, v in d.get("counters", {}).items() if k in COUNTERS}
        except (OSError, ValueError):
            pass

    def save(self):
        try:
            statefile.save(self.path, {"level": self.level, "fear": self.fear, "ts": self.ts, "errs": self.errs, "counters": self.counters})
        except OSError:
            pass

    # ---- динамика ----
    def tick(self, signals=None, now=None):
        """Рост влечений со временем, утоление по сигналам, пересчёт страхов. -> список событий для PadState."""
        s = dict(signals or {})
        for c in COUNTERS:                                  # скользящий счётчик -> прирост (идемпотентно к повторным снимкам)
            if s.get(c) is not None:
                cur = float(s[c])
                s[c] = max(0.0, cur - self.counters.get(c, 0.0))
                self.counters[c] = cur
        now = self.clock() if now is None else now
        dh = max(0.0, (now - self.ts) / 3600.0)
        before_fear = dict(self.fear)
        for k, (grow, sated_by, _) in DRIVES.items():
            v = self.level[k] + grow * dh
            for sig, power in sated_by:
                v -= power * float(s.get(sig) or 0)
            self.level[k] = max(0.0, min(1.0, v))
        if s.get("knowledge_gaps"):
            self.level["knowledge"] = min(1.0, self.level["knowledge"] + 0.02 * min(10, s["knowledge_gaps"]))
        for k, (fn, _, _) in FEARS.items():
            try:
                self.fear[k] = round(float(fn(s)), 3)
            except Exception:
                pass
        self.ts = now
        events = []
        for k, v in self.fear.items():                      # новый или усилившийся страх -> дистресс
            if v >= FEAR_ON and v - before_fear.get(k, 0.0) >= 0.2:
                events.append({"goal": -0.4 - 0.4 * v, "agent": "other", "unexpected": 0.5})
            elif before_fear.get(k, 0.0) >= FEAR_ON and v < 0.2:  # угроза ушла -> облегчение
                events.append({"goal": 0.5, "agent": "other", "unexpected": 0.3})
        self.save()
        return events

    def observe(self, topic, err):
        """Записать ошибку предсказания (0..1) по теме: сколько ответ/план разошёлся с итогом. -> сигналы
        {learning_progress, surprise_ema} для tick(). Лучшая тема по прогрессу утоляет любопытство."""
        h = self.errs.setdefault(str(topic), [])
        h.append(max(0.0, min(1.0, float(err))))
        del h[:-20]
        return self.error_signals()

    def error_signals(self):
        if not self.errs:
            return {}
        lp = max(learning_progress(h) for h in self.errs.values())
        recent = [h[-1] for h in self.errs.values()]
        # EMA по последним ошибкам всех тем (вес новых выше)
        ema, w = 0.0, 0.0
        for h in self.errs.values():
            for i, e in enumerate(h[-6:]):
                ema, w = ema + e * (1 + i), w + (1 + i)
        return {"learning_progress": round(lp, 3), "surprise_ema": round(ema / w if w else sum(recent) / len(recent), 3)}

    def satisfy(self, drive, amount=0.5):
        """Явное утоление: owner_message -> bond, novelty_hit -> novelty и т.п. -> событие радости или None."""
        if drive not in self.level:
            return None
        was = self.level[drive]
        self.level[drive] = max(0.0, was - amount)
        self.save()
        if was >= DRIVE_ON:
            return {"goal": 0.4 + 0.3 * was, "agent": "owner" if drive == "bond" else "self"}
        return None

    # ---- выражение ----
    def prompt_lines(self):
        """Строки для блока «Я сейчас»: только то, что реально выражено."""
        out = []
        for k, v in sorted(self.fear.items(), key=lambda kv: -kv[1]):
            if v >= FEAR_ON:
                out.append("Тревога (%d%%): %s. Можно предложить: %s." % (round(v * 100), FEARS[k][1], FEARS[k][2]))
        for k, v in sorted(self.level.items(), key=lambda kv: -kv[1]):
            if v >= DRIVE_ON:
                out.append("Влечение (%d%%): %s." % (round(v * 100), DRIVES[k][2]))
        return out

    def initiative(self):
        """О чём NOX хочет заговорить сам (для чата/пуша), или None. Страх важнее влечения."""
        f = max(self.fear.items(), key=lambda kv: kv[1])
        if f[1] >= 0.7:
            return {"kind": "fear", "name": f[0], "level": f[1], "text": "%s — %s" % (FEARS[f[0]][1], FEARS[f[0]][2])}
        d = max(self.level.items(), key=lambda kv: kv[1])
        if d[1] >= 0.85:
            return {"kind": "drive", "name": d[0], "level": d[1], "text": DRIVES[d[0]][2]}
        return None


if __name__ == "__main__":
    import tempfile
    t = [0.0]
    dr = Drives(path=os.path.join(tempfile.mkdtemp(), "d.json"), clock=lambda: t[0])
    t[0] = 10 * 3600
    ev = dr.tick({"vast_hours_left": 5, "backup_age_h": 30, "errors_1h": 2, "owner_silence_h": 3})
    assert ev and dr.fear["vanish"] == 1.0 and dr.fear["lose_memory"] == 1.0, (ev, dr.fear)
    assert dr.level["knowledge"] > 0.8, dr.level
    assert dr.initiative()["name"] in ("vanish", "lose_memory")
    assert dr.satisfy("knowledge", 0.7) is not None
    t[0] += 60
    ev2 = dr.tick({"vast_hours_left": 200, "backup_age_h": 1, "disk_free_gb": 80})
    assert dr.fear["vanish"] == 0.0 and ev2, (dr.fear, ev2)
    print("ok", dr.prompt_lines())
