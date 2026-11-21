"""nell_reflex: рефлексы по «Nell» (stdlib).

(а) dream(): ассоциативные «сны» - пары воспоминаний с общими ключевыми словами/эмоцией;
(б) EmotionDiary: сильная эмоция сама пишет запись в дневник;
(в) BodyModel: энергия + суточный ритм, режим active/low;
(г) forgetting: экспоненциальное затухание веса, укрепление при обращении,
    удаление ниже порога с журналом.
Хранилище воспоминаний: JSONL или SQLite (по расширению .db/.sqlite/.sqlite3).
Время - epoch-секунды (float).
"""
import json
import math
import os
import random
import re
import sqlite3
import time

DAY = 86400.0
_STOP = set("это как что так для при или его она они были быть было есть чтобы потому который "
            "когда тоже ещё еще очень надо себя этот этой the and that this with have from was were for not you".split())


def keywords(text):
    return {w for w in re.findall(r"[^\W\d_]{4,}", (text or "").casefold()) if w not in _STOP}


def shared_keywords(ka, kb):
    """Общие ключевые слова с учётом словоформ: общий префикс >= max(3, min_len-1)
    (река/реки, ночь/ночью). Возвращает множество общих префиксов."""
    out = set()
    for x in ka:
        for y in kb:
            n = 0
            while n < min(len(x), len(y)) and x[n] == y[n]:
                n += 1
            if n >= max(3, min(len(x), len(y)) - 1):
                out.add(x[:n])
    return out


class MemoryStore:
    """Воспоминание: id, text, emotion, intensity(0..1), ts, weight, last_access, half_life_days."""
    FIELDS = ("id", "text", "emotion", "intensity", "ts", "weight", "last_access", "half_life_days")

    def __init__(self, path):
        self.path = path
        self.sqlite = os.path.splitext(path)[1].lower() in (".db", ".sqlite", ".sqlite3")
        if self.sqlite:
            self.db = sqlite3.connect(path)
            self.db.execute("""CREATE TABLE IF NOT EXISTS memories(id TEXT PRIMARY KEY, text TEXT, emotion TEXT,
                intensity REAL, ts REAL, weight REAL, last_access REAL, half_life_days REAL)""")
            self.db.commit()

    def _norm(self, m):
        now = m.get("ts") or time.time()
        return {"id": str(m["id"]), "text": m.get("text", ""), "emotion": m.get("emotion") or "",
                "intensity": float(m.get("intensity", 0.0)), "ts": float(now),
                "weight": float(m.get("weight", 1.0)), "last_access": float(m.get("last_access", now)),
                "half_life_days": float(m.get("half_life_days", 30.0))}

    def all(self):
        if self.sqlite:
            cur = self.db.execute("SELECT %s FROM memories ORDER BY ts, id" % ",".join(self.FIELDS))
            return [dict(zip(self.FIELDS, r)) for r in cur]
        if not os.path.exists(self.path):
            return []
        with open(self.path, encoding="utf-8") as f:
            return [self._norm(json.loads(l)) for l in f if l.strip()]

    def save_all(self, mems):
        mems = [self._norm(m) for m in mems]
        if self.sqlite:
            self.db.execute("DELETE FROM memories")
            self.db.executemany("INSERT INTO memories VALUES(%s)" % ",".join("?" * 8),
                                [tuple(m[k] for k in self.FIELDS) for m in mems])
            self.db.commit()
        else:
            with open(self.path, "w", encoding="utf-8") as f:
                for m in mems:
                    f.write(json.dumps(m, ensure_ascii=False) + "\n")

    def add(self, m):
        mems = [x for x in self.all() if x["id"] != str(m["id"])]
        mems.append(self._norm(m))
        self.save_all(mems)

    def get(self, mid):
        return next((m for m in self.all() if m["id"] == str(mid)), None)

    def close(self):
        if self.sqlite:
            self.db.close()


def _append_jsonl(path, rec):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _read_jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


# (а) сны
def dream(memories, dreams_path=None, max_pairs=3, min_shared=1, seed=None, now=None):
    """Пары воспоминаний с общими ключевыми словами; одна эмоция даёт бонус.
    Пара без общих слов берётся только при одинаковой эмоции И min_shared<=0.
    Возвращает список сон-записей (и дописывает в dreams_path)."""
    rnd = random.Random(seed)
    kws = {m["id"]: keywords(m["text"]) for m in memories}
    cands = []
    for i in range(len(memories)):
        for j in range(i + 1, len(memories)):
            a, b = memories[i], memories[j]
            shared = shared_keywords(kws[a["id"]], kws[b["id"]])
            same_em = bool(a.get("emotion")) and a.get("emotion") == b.get("emotion")
            if len(shared) < min_shared:
                continue
            if not shared and not same_em:
                continue
            cands.append((len(shared) + (1.5 if same_em else 0.0) + rnd.random() * 0.1, a, b, shared, same_em))
    cands.sort(key=lambda c: -c[0])
    out, used = [], set()
    for score, a, b, shared, same_em in cands:
        if len(out) >= max_pairs:
            break
        if (a["id"], b["id"]) in used:
            continue
        used.add((a["id"], b["id"]))
        out.append({"type": "dream", "ts": now or time.time(), "pair": [a["id"], b["id"]],
                    "shared": sorted(shared), "emotion": a["emotion"] if same_em else None, "score": round(score, 3),
                    "text": "Сон: «%s» сплетается с «%s»%s." % (
                        a["text"][:60], b["text"][:60], " через " + ", ".join(sorted(shared)) if shared else "")})
    if dreams_path:
        for d in out:
            _append_jsonl(dreams_path, d)
    return out


# (б) дневник
class EmotionDiary:
    def __init__(self, path, threshold=0.7):
        self.path, self.threshold = path, threshold

    def observe(self, memory, now=None):
        """Если intensity >= порога и записи по этому воспоминанию ещё нет - пишет в дневник."""
        if float(memory.get("intensity", 0)) < self.threshold:
            return None
        if any(e.get("memory_id") == str(memory["id"]) for e in _read_jsonl(self.path)):
            return None
        rec = {"type": "diary", "ts": now or time.time(), "memory_id": str(memory["id"]),
               "emotion": memory.get("emotion"), "intensity": memory["intensity"],
               "text": "Сильное чувство (%s, %.2f): %s" % (memory.get("emotion") or "?", memory["intensity"], memory["text"])}
        _append_jsonl(self.path, rec)
        return rec

    def entries(self):
        return _read_jsonl(self.path)


# (в) тело
class BodyModel:
    """Энергия 0..1. Суточный ритм: пик ~15:00, минимум ~03:00 (множитель 0.6..1.0).
    Активность тратит энергию, sleep() восстанавливает; mode(): 'active' | 'low'."""
    def __init__(self, energy=1.0, low_threshold=0.3, drain_per_unit=0.05, restore_per_hour=0.12, path=None):
        self.energy, self.low_threshold = energy, low_threshold
        self.drain, self.restore, self.path = drain_per_unit, restore_per_hour, path
        self.sleeping = False
        if path and os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                self.energy = json.load(f)["energy"]

    @staticmethod
    def circadian(hour):
        return 0.8 + 0.2 * math.cos((hour - 15.0) / 24.0 * 2 * math.pi)

    def activity(self, units=1.0, hour=12.0):
        """Расход выше при низком ритме."""
        self.energy = max(0.0, self.energy - units * self.drain / self.circadian(hour) * 0.8)
        self._save(); return self.energy

    def sleep(self, hours):
        """«Сон»: восстановление; ночью (ритм низкий) эффективнее. Возвращает энергию."""
        self.energy = min(1.0, self.energy + hours * self.restore)
        self._save(); return self.energy

    def mode(self, hour):
        eff = self.energy * self.circadian(hour) / 1.0
        return "low" if eff < self.low_threshold or self.energy < self.low_threshold else "active"

    def _save(self):
        if self.path:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump({"energy": self.energy}, f)


# (г) забывание
def current_weight(m, now):
    """w = w0 * 2^(-dt/half_life); сильная эмоция замедляет затухание (период x(1+intensity))."""
    hl = m["half_life_days"] * DAY * (1.0 + m.get("intensity", 0.0))
    dt = max(0.0, now - m["last_access"])
    return m["weight"] * math.pow(0.5, dt / hl)


def reinforce(m, now, boost=0.3, hl_growth=1.5):
    """Обращение к воспоминанию: вес поднимается, период полураспада растёт (эффект повторения)."""
    m["weight"] = min(1.0, current_weight(m, now) + boost)
    m["last_access"] = now
    m["half_life_days"] *= hl_growth
    return m


def forget_sweep(store, now=None, threshold=0.05, journal_path=None):
    """Применить затухание, удалить воспоминания с весом < порога (запись в журнал). Возвращает удалённые id."""
    now = now or time.time()
    keep, gone = [], []
    for m in store.all():
        w = current_weight(m, now)
        if w < threshold:
            gone.append(m["id"])
            if journal_path:
                _append_jsonl(journal_path, {"type": "forgot", "ts": now, "id": m["id"], "text": m["text"],
                                             "weight": round(w, 5), "threshold": threshold})
        else:
            m["weight"], m["last_access"] = w, now
            keep.append(m)
    store.save_all(keep)
    return gone
