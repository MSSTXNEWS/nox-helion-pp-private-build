"""disturb_check: можно ли беспокоить владельца перед проактивным сообщением.

Только stdlib. Конфиг JSON. Камера/микрофон учитываются ТОЛЬКО при явном
consent в конфиге (по умолчанию выключено) - иначе сигналы игнорируются.
"""
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta

URGENCY = {"low": 0, "normal": 1, "high": 2, "critical": 3}

DEFAULT_CONFIG = {
    "night_start": "23:00",
    "night_end": "07:00",
    "dnd_windows": [],            # [["13:00", "14:00"], ...]
    "min_idle_minutes": 10,       # активен меньше N минут назад = занят
    "max_idle_minutes": 720,      # дольше - владелец, вероятно, отсутствует (low/normal не пишем)
    "max_proactive_per_day": 3,
    "min_gap_minutes": 30,        # пауза между проактивными сообщениями
    "night_min_urgency": "critical",
    "dnd_min_urgency": "high",
    "busy_min_urgency": "high",   # владелец активен прямо сейчас (< min_idle)
    "consent": {"camera": False, "microphone": False},
}


def _hm(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def _in_window(minute, start, end):
    if start == end:
        return False
    if start < end:
        return start <= minute < end
    return minute >= start or minute < end  # через полночь


@dataclass
class Decision:
    allow: bool
    code: str
    reason: str
    used_sensors: list = field(default_factory=list)


def load_config(path=None, data=None):
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    if path is not None:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    for k, v in (data or {}).items():
        if k == "consent" and isinstance(v, dict):
            cfg["consent"].update({a: bool(b) for a, b in v.items()})
        else:
            cfg[k] = v
    return cfg


class DisturbCheck:
    def __init__(self, config=None):
        self.cfg = config or load_config()
        self.sent = []  # datetime проактивных сообщений

    def record_sent(self, when):
        self.sent.append(when)

    def _sent_today(self, now):
        return [t for t in self.sent if t.date() == now.date()]

    def decide(self, now, last_activity=None, urgency="normal", sensors=None):
        """now/last_activity: datetime. sensors: {"camera_presence": bool,
        "mic_speech": bool} - используются только при consent."""
        cfg = self.cfg
        u = URGENCY[urgency]
        sensors = sensors or {}
        used = []
        ignored = []
        cons = cfg.get("consent", {})
        speech = presence = None
        if "camera_presence" in sensors:
            if cons.get("camera"):
                presence = bool(sensors["camera_presence"]); used.append("camera")
            else:
                ignored.append("camera")
        if "mic_speech" in sensors:
            if cons.get("microphone"):
                speech = bool(sensors["mic_speech"]); used.append("microphone")
            else:
                ignored.append("microphone")

        def d(allow, code, reason):
            if ignored:
                reason += " (сенсоры %s проигнорированы: нет согласия)" % ",".join(ignored)
            return Decision(allow, code, reason, used)

        if u == URGENCY["critical"]:
            return d(True, "critical", "критическая срочность: пропускаем все фильтры")

        minute = now.hour * 60 + now.minute
        if _in_window(minute, _hm(cfg["night_start"]), _hm(cfg["night_end"])) \
                and u < URGENCY[cfg["night_min_urgency"]]:
            return d(False, "night", "ночные часы, срочности недостаточно")
        for a, b in cfg.get("dnd_windows", []):
            if _in_window(minute, _hm(a), _hm(b)) and u < URGENCY[cfg["dnd_min_urgency"]]:
                return d(False, "dnd", "окно «не беспокоить» %s-%s" % (a, b))

        today = self._sent_today(now)
        if len(today) >= cfg["max_proactive_per_day"] and u < URGENCY["high"]:
            return d(False, "daily_limit", "лимит проактивных сообщений на сутки исчерпан")
        if today and u < URGENCY["high"]:
            gap = now - max(today)
            if gap < timedelta(minutes=cfg["min_gap_minutes"]):
                return d(False, "gap", "слишком рано после прошлого проактивного сообщения")

        if speech:
            if u < URGENCY["high"]:
                return d(False, "speech", "микрофон: рядом идёт разговор (consent выдан)")
        if presence is False and u < URGENCY["high"]:
            return d(False, "absent", "камера: владельца нет рядом (consent выдан)")

        if last_activity is not None:
            idle = (now - last_activity).total_seconds() / 60
            if idle < cfg["min_idle_minutes"] and u < URGENCY[cfg["busy_min_urgency"]]:
                return d(False, "busy", "владелец только что был активен (%.0f мин назад)" % idle)
            if idle > cfg["max_idle_minutes"] and u < URGENCY["high"] and presence is not True:
                return d(False, "away", "владелец давно не активен (%.0f мин)" % idle)
        return d(True, "ok", "беспокоить можно")
