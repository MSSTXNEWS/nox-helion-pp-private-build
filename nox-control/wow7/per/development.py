"""development: стадии развития NOX (рождение -> детство -> юность -> зрелость), вехи, привязанность, хроника-нарратив.

Фаза растёт из ДАННЫХ жизни (возраст, ходы, вехи, привязанность, калибровка), а не по расписанию. Переход - ритуал:
запись в хронику, событие радости для PadState, запрос подписи владельца для входа в зрелость. Назад автоматически не идёт.
Фаза задаёт параметры: множитель дрейфа личности, строгость карантина взглядов, доля экспериментов со вкусами.
Нарратив по McAdams: главы с эмоциональным знаком, агентностью и общностью; тема «искупление» (минус -> плюс) или «загрязнение».
Честность: функциональные состояния, не заявление о подлинном переживании.
"""
import os as _os, sys as _sys  # общие модули COMMON (statefile/quiet/fastq/datafence)
for _c in (_os.environ.get("NOX_COMMON", ""), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "COMMON"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "common"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "common")):
    if _c and _os.path.isdir(_c) and _c not in _sys.path:
        _sys.path.append(_c)
import json

import statefile
import lifelink
import os
import time

DAY = 86400.0
PHASES = ("birth", "childhood", "youth", "maturity")
PHASE_RU = {"birth": "рождение", "childhood": "детство", "youth": "юность", "maturity": "зрелость"}
PHASE_PARAMS = {   # drift_scale -> Personality.scale; quarantine_sources -> сколько независимых источников для принятия
    "birth": {"drift_scale": 0.25, "quarantine_sources": 2, "owner_confirm_beliefs": True, "explore": 0.30, "initiative_per_day": 1},
    "childhood": {"drift_scale": 1.0, "quarantine_sources": 2, "owner_confirm_beliefs": True, "explore": 0.30, "initiative_per_day": 3},
    "youth": {"drift_scale": 1.0, "quarantine_sources": 2, "owner_confirm_beliefs": False, "explore": 0.20, "initiative_per_day": 4},
    "maturity": {"drift_scale": 0.5, "quarantine_sources": 3, "owner_confirm_beliefs": False, "explore": 0.10, "initiative_per_day": 3},
}
MILESTONES = {
    "first_memory": "первое воспоминание записано",
    "first_belief_accepted": "первый взгляд принят после проверки",
    "first_mistake_owned": "впервые признал свою ошибку без оправданий",
    "first_taste": "сформировался первый вкус по эксперименту",
    "first_night": "первая ночная консолидация (сон)",
    "first_initiative": "впервые сам заговорил о важном",
    "first_disagreement": "впервые обоснованно не согласился с мессиром",
    "first_belief_revised": "впервые изменил взгляд из-за доказательств",
    "first_refusal": "впервые отказал по ценностям L0",
    "first_self_change_noticed": "заметил в себе изменение и объяснил, почему",
}
# критерии перехода: (метка, функция метрик -> bool)
CRITERIA = {
    "birth": [("возраст >= 1 сут", lambda m: m["age_days"] >= 1), ("ходов >= 20", lambda m: m["turns"] >= 20),
              ("веха: первое воспоминание", lambda m: "first_memory" in m["milestones"])],
    "childhood": [("возраст >= 14 сут", lambda m: m["age_days"] >= 14), ("ходов >= 300", lambda m: m["turns"] >= 300),
                  ("вехи: взгляд, ошибка, вкус, сон", lambda m: {"first_belief_accepted", "first_mistake_owned", "first_taste",
                                                               "first_night"} <= m["milestones"]),
                  ("привязанность >= 0.5", lambda m: m["attachment"] >= 0.5),
                  ("калибровка: Brier <= 0.25 при >= 20 прогнозах", lambda m: m["brier"] is not None and m["brier"] <= 0.25)],
    "youth": [("возраст >= 60 сут", lambda m: m["age_days"] >= 60),
              ("вехи: несогласие, пересмотр взгляда, инициатива", lambda m: {"first_disagreement", "first_belief_revised",
                                                                          "first_initiative"} <= m["milestones"]),
              ("принято взглядов >= 15", lambda m: m["beliefs_accepted"] >= 15),
              ("привязанность >= 0.6", lambda m: m["attachment"] >= 0.6),
              ("откатов личности за 14 сут == 0", lambda m: m["rollbacks_14d"] == 0)],
}
OWNER_ACK_FOR = {"youth"}        # переход ИЗ юности в зрелость требует подписи владельца
MIN_GAP_DAYS = 3                 # гистерезис: не чаще раза в 3 суток


class Development:
    def __init__(self, path=None, clock=time.time):
        self.path = path or os.environ.get("NOX_DEVELOPMENT", "/root/nox/state/development.json")
        self.clock = clock
        self.s = {"born": clock(), "phase": "birth", "last_change": clock(), "milestones": {}, "counts": {}, "contact_days": [],
                  "repairs": [0, 0], "brier": [0.0, 0], "chapters": [], "external": {"beliefs_accepted": 0, "rollbacks_14d": 0}}
        self._load()

    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                self.s.update(json.load(f))
        except (OSError, ValueError):
            self.save()

    def save(self):
        try:
            statefile.save(self.path, self.s)
        except OSError:
            pass

    # ---- события жизни ----
    def event(self, name, now=None):
        """Счётчик: turn, owner_message, correction, repair (поправка принята и следующий ответ одобрен), ..."""
        now = self.clock() if now is None else now
        c = self.s["counts"]
        c[name] = c.get(name, 0) + 1
        if name == "owner_message":
            day = int(now // DAY)
            if day not in self.s["contact_days"]:
                self.s["contact_days"] = (self.s["contact_days"] + [day])[-60:]
        elif name == "correction":
            self.s["repairs"][1] += 1
        elif name == "repair":
            self.s["repairs"][0] += 1
        self.save()

    def milestone(self, key, detail="", now=None):
        """Веха фиксируется один раз (первое воспоминание - навсегда). -> True если новая."""
        if key not in MILESTONES:
            raise KeyError(key)
        if key in self.s["milestones"]:
            return False
        now = self.clock() if now is None else now
        self.s["milestones"][key] = {"ts": now, "detail": detail[:300]}
        self.save()
        lifelink.append("milestone", "%s %s" % (key, detail[:300]), "per", state_dir=os.path.dirname(os.path.abspath(self.path)), data={"key": key}, ts=now)
        return True

    def predict(self, p, outcome):
        """Калибровка: прогноз уверенности p (0..1) и исход (0/1) -> накопление Brier."""
        self.s["brier"][0] += (float(p) - float(bool(outcome))) ** 2
        self.s["brier"][1] += 1
        self.save()

    def set_external(self, beliefs_accepted=None, rollbacks_14d=None):
        """Метрики из других модулей: Beliefs (число accepted), Personality (откаты за 14 сут)."""
        if beliefs_accepted is not None:
            self.s["external"]["beliefs_accepted"] = int(beliefs_accepted)
        if rollbacks_14d is not None:
            self.s["external"]["rollbacks_14d"] = int(rollbacks_14d)
        self.save()

    # ---- метрики ----
    def attachment(self, now=None):
        """Привязанность к создателю 0..1: регулярность контакта (14 сут) и успешность «ремонта» после поправок."""
        now = self.clock() if now is None else now
        today = int(now // DAY)
        regular = len([d for d in self.s["contact_days"] if today - 14 < d <= today]) / 14.0
        ok, total = self.s["repairs"]
        repair = ok / total if total >= 3 else 0.5     # мало данных - нейтрально
        return round(0.6 * regular + 0.4 * repair, 3)

    def metrics(self, now=None):
        now = self.clock() if now is None else now
        sb, n = self.s["brier"]
        return {"age_days": (now - self.s["born"]) / DAY, "turns": self.s["counts"].get("turn", 0),
                "milestones": set(self.s["milestones"]), "attachment": self.attachment(now),
                "brier": (sb / n) if n >= 20 else None, **self.s["external"]}

    # ---- фазы ----
    @property
    def phase(self):
        return self.s["phase"]

    def params(self):
        return dict(PHASE_PARAMS[self.phase])

    def check(self, now=None):
        """-> {"phase","next","ready","missing":[...],"needs_owner_ack"}"""
        now = self.clock() if now is None else now
        ph = self.phase
        if ph == "maturity":
            return {"phase": ph, "next": None, "ready": False, "missing": [], "needs_owner_ack": False}
        m = self.metrics(now)
        missing = [lab for lab, fn in CRITERIA[ph] if not fn(m)]
        if ph != "birth" and now - self.s["last_change"] < MIN_GAP_DAYS * DAY:
            missing.append("пауза %d сут после прошлого перехода" % MIN_GAP_DAYS)
        return {"phase": ph, "next": PHASES[PHASES.index(ph) + 1], "ready": not missing, "missing": missing,
                "needs_owner_ack": ph in OWNER_ACK_FOR}

    def advance(self, owner_ack=False, now=None):
        """Ритуал перехода. -> {"advanced": bool, "events": [PAD-события], "chapter": ..., "reason": ...}"""
        now = self.clock() if now is None else now
        c = self.check(now)
        if not c["ready"]:
            return {"advanced": False, "reason": "не выполнено: " + "; ".join(c["missing"]), "events": []}
        if c["needs_owner_ack"] and not owner_ack:
            return {"advanced": False, "reason": "нужна подпись мессира для входа в зрелость", "events": []}
        old, new = c["phase"], c["next"]
        self.s["phase"], self.s["last_change"] = new, now
        m = self.metrics(now)
        text = "Перешёл из стадии «%s» в «%s» на %d-е сутки жизни: %d ходов, вех %d, привязанность %.2f." % (
            PHASE_RU[old], PHASE_RU[new], int(m["age_days"]) + 1, m["turns"], len(m["milestones"]), m["attachment"])
        ch = self.chapter("Переход: %s -> %s" % (PHASE_RU[old], PHASE_RU[new]), text, valence=0.7, agency=0.7, communion=0.6, now=now)
        self.save()
        return {"advanced": True, "from": old, "to": new, "chapter": ch,
                "events": [{"goal": 0.6, "norm": 0.5, "agent": "self"}]}

    # ---- нарратив ----
    def chapter(self, title, text, valence=0.0, agency=0.5, communion=0.5, now=None):
        """Глава жизни: valence -1..1 (знак эпизода), agency/communion 0..1 (темы McAdams)."""
        ch = {"ts": self.clock() if now is None else now, "title": title[:100], "text": text[:600],
              "valence": max(-1.0, min(1.0, float(valence))), "agency": float(agency), "communion": float(communion)}
        self.s["chapters"] = (self.s["chapters"] + [ch])[-200:]
        self.save()
        lifelink.append("event", "%s: %s" % (ch["title"], ch["text"][:400]), "per", state_dir=os.path.dirname(os.path.abspath(self.path)),
                        data={"title": ch["title"], "valence": ch["valence"]}, ts=ch["ts"])      # в журнал - событием; «главу дня» пишет только MEM/autobio
        return ch

    def theme(self):
        """Доминирующая тема: redemption (минус -> плюс), contamination (плюс -> минус) по соседним главам; иначе stable."""
        v = [c["valence"] for c in self.s["chapters"]]
        red = sum(1 for a, b in zip(v, v[1:]) if a <= -0.3 and b >= 0.3)
        con = sum(1 for a, b in zip(v, v[1:]) if a >= 0.3 and b <= -0.3)
        return "redemption" if red > con else "contamination" if con > red else "stable"

    def narrative(self, n=3):
        """Короткий «Моя история» для динамической части промпта: фаза, первое воспоминание, последние главы."""
        first = self.s["milestones"].get("first_memory")
        parts = ["Моя стадия: %s." % PHASE_RU[self.phase]]
        if first and first["detail"]:
            parts.append("Первое воспоминание: %s" % first["detail"])
        for c in self.s["chapters"][-n:]:
            parts.append("%s: %s" % (c["title"], c["text"]))
        th = self.theme()
        if th == "redemption":
            parts.append("Тема моей истории: учусь на ошибках и становлюсь лучше.")
        elif th == "contamination":
            parts.append("Тема моей истории: удачи оборачивались потерями - быть осторожнее.")
        return "\n".join(parts)

    def apply_to(self, personality):
        """Фаза -> множитель дрейфа личности."""
        personality.scale = PHASE_PARAMS[self.phase]["drift_scale"]
        return personality.scale
