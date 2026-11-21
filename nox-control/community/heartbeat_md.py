"""Парсер HEARTBEAT.md (человеческие правила) + планировщик.

Поддерживается (рус./англ.), по одному правилу на строку (маркеры "-", "*", "[ ]" допускаются):
  каждый день в 9:00 напомни про отчёт        daily        (every day at 9:00 ...)
  по пятницам в 18:00 проверь бэкапы          weekly       (также "по будням", "по выходным", "каждый вторник", списки через "и")
  каждые 2 часа проверь диск                  interval     (минуты/часы/дни; "каждый час"; "раз в 3 часа"; every 2 hours)
  через 30 минут напомни ...                  once         (отсчёт от момента первого чтения правила; in 30 minutes)
  1 числа каждого месяца в 10:00 сделай отчёт monthly
Время: "в 9:00", "в 18.30", "в 9 утра", "в 7 вечера". Без времени для daily/weekly/monthly - 09:00.
Строки, начинающиеся с "#" или внутри <!-- -->, пропускаются; непонятные правила попадают в errors.
Времена наивные (локальные); now передаёт вызывающий. Пропущенные срабатывания схлопываются в одно.
"""
import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta

WEEKDAYS = [("понедельник", 0), ("вторник", 1), ("сред", 2), ("четверг", 3), ("пятниц", 4), ("суббот", 5), ("воскресен", 6),
            ("monday", 0), ("tuesday", 1), ("wednesday", 2), ("thursday", 3), ("friday", 4), ("saturday", 5), ("sunday", 6),
            ("mon", 0), ("tue", 1), ("wed", 2), ("thu", 3), ("fri", 4), ("sat", 5), ("sun", 6)]
_WD_WORD = r"(?:понедельник|вторник|сред|четверг|пятниц|суббот|воскресен|monday|tuesday|wednesday|thursday|friday|saturday|sunday|будн|выходн|weekday|weekend)\w*"
_UNIT = {"м": 60, "ч": 3600, "д": 86400, "н": 604800, "m": 60, "h": 3600, "d": 86400, "w": 604800}

_TIME_RE = re.compile(r"\b(?:в|at)\s+(\d{1,2})(?:[:.](\d{2}))?(?!\d)(?!\s*(?:час|мин|дн|ден|недел|hour|min|day|week))\s*(утра|дня|вечера|ночи|am|pm)?(?!\w)", re.I)
_ONCE_RE = re.compile(r"\b(?:через|in)\s+(?:(\d+)\s*)?(полчаса|минут\w*|мин\b|час\w*|ч\b|дн\w*|день|недел\w*|minutes?|mins?|hours?|days?|weeks?)", re.I)
_INTERVAL_RE = re.compile(r"\b(?:кажд(?:ые|ый|ую|ое)|раз\s+в|every)\s+(?:(\d+)\s*)?(минут\w*|мин\b|час\w*|ч\b|дн\w*|день|недел\w*|minutes?|mins?|hours?|days?|weeks?)", re.I)
_DAILY_RE = re.compile(r"\b(?:кажд(?:ый|ое)\s+(?:день|утро|вечер)|ежедневно|every\s*day|daily)\b", re.I)
_WEEKLY_RE = re.compile(r"\b(?:по|on|every|кажд(?:ый|ую|ое))\s+((?:%s(?:\s*(?:,|и|and)\s*)?)+)" % _WD_WORD, re.I)
_MONTHLY_RE = re.compile(r"\b(\d{1,2})\s*(?:-?го)?\s*числа\s+(?:кажд(?:ого|ый)\s+месяц\w*|месяца)|\bкажд(?:ого|ый)\s+месяц\w*\s+(\d{1,2})\s*числа|\bмесячно\b", re.I)


def _unit_seconds(u):
    u = u.lower()
    if u == "полчаса":
        return 1800
    if u.startswith(("мин", "min", "m")) and not u.startswith("mon"):
        return 60
    if u.startswith(("час", "ч", "hour", "h")):
        return 3600
    if u.startswith(("дн", "ден", "day", "d")):
        return 86400
    if u.startswith(("нед", "week", "w")):
        return 604800
    raise ValueError("unit " + u)


def _weekdays(segment):
    seg = segment.lower()
    days = set()
    if "будн" in seg or "weekday" in seg:
        days |= {0, 1, 2, 3, 4}
    if "выходн" in seg or "weekend" in seg:
        days |= {5, 6}
    for stem, d in WEEKDAYS:
        if re.search(r"(?<![a-zа-я])%s" % stem, seg):
            days.add(d)
    return sorted(days)


@dataclass
class Rule:
    id: str
    kind: str                 # daily | weekly | monthly | interval | once
    title: str
    source: str
    time: tuple = (9, 0)      # (h, m) для daily/weekly/monthly
    weekdays: list = field(default_factory=list)
    day_of_month: int = 0
    interval_s: int = 0       # interval / once

    def describe(self):
        return {"id": self.id, "kind": self.kind, "title": self.title, "time": "%02d:%02d" % self.time,
                "weekdays": self.weekdays, "day_of_month": self.day_of_month, "interval_s": self.interval_s}


def _rid(text):
    return hashlib.sha1(re.sub(r"\s+", " ", text.strip().lower()).encode("utf-8")).hexdigest()[:10]


def _clean_title(text, spans):
    out, pos = [], 0
    for a, b in sorted(spans):
        if a >= pos:
            out.append(text[pos:a])
            pos = b
    out.append(text[pos:])
    t = " ".join("".join(out).split())
    t = re.sub(r"^[\s,;:\-–—.]+|[\s,;:\-–—]+$", "", t)
    t = re.sub(r"^(?:и|потом|then|and|to)\s+", "", t, flags=re.I)
    return t


def parse_line(line):
    """Одна строка -> Rule или бросает ValueError с причиной."""
    s = line.strip()
    s = re.sub(r"^(?:[-*+]\s*)?(?:\[[ xX]?\]\s*)?", "", s).strip()
    if not s:
        raise ValueError("empty")
    spans = []
    tm = _TIME_RE.search(s)
    hh, mm = 9, 0
    if tm:
        hh, mm = int(tm.group(1)), int(tm.group(2) or 0)
        suf = (tm.group(3) or "").lower()
        if suf in ("вечера", "pm") and hh < 12:
            hh += 12
        elif suf == "дня" and hh < 12 and hh != 12 and hh <= 6:
            hh += 12
        elif suf in ("ночи",) and hh == 12:
            hh = 0
        elif suf in ("am", "утра") and hh == 12:
            hh = 0
        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            raise ValueError("bad time %s:%s" % (tm.group(1), tm.group(2)))
    once = _ONCE_RE.search(s)
    if once:
        n = int(once.group(1)) if once.group(1) else 1
        sec = _unit_seconds(once.group(2)) * n
        if once.group(2).lower() == "полчаса":
            sec = 1800
        if sec <= 0:
            raise ValueError("zero delay")
        spans.append(once.span())
        title = _clean_title(s, spans)
        if not title:
            raise ValueError("no task text")
        return Rule(_rid(s), "once", title, s, interval_s=sec)
    iv = _INTERVAL_RE.search(s)
    wk = _WEEKLY_RE.search(s)
    mo = _MONTHLY_RE.search(s)
    if mo:
        dom = int(mo.group(1) or mo.group(2) or 1)
        if not 1 <= dom <= 31:
            raise ValueError("bad day of month")
        spans.append(mo.span())
        kind, extra = "monthly", {"day_of_month": dom}
    elif wk and _weekdays(wk.group(1)):
        spans.append(wk.span())
        kind, extra = "weekly", {"weekdays": _weekdays(wk.group(1))}
    elif iv and not (tm and iv.group(2).lower().startswith(("дн", "ден", "day")) and not iv.group(1)):
        n = int(iv.group(1)) if iv.group(1) else 1
        if n <= 0:
            raise ValueError("zero interval")
        sec = _unit_seconds(iv.group(2)) * n
        if tm and sec >= 86400 and n > 1:
            raise ValueError("interval of several days with fixed time unsupported")
        if tm and sec < 86400:
            raise ValueError("interval with fixed time unsupported")
        spans.append(iv.span())
        if tm:
            spans.append(tm.span())
            title = _clean_title(s, spans)
            if not title:
                raise ValueError("no task text")
            return Rule(_rid(s), "interval", title, s, interval_s=sec)
        title = _clean_title(s, spans)
        if not title:
            raise ValueError("no task text")
        return Rule(_rid(s), "interval", title, s, interval_s=sec)
    else:
        d = _DAILY_RE.search(s)
        if not d:
            raise ValueError("no schedule recognised")
        spans.append(d.span())
        kind, extra = "daily", {}
    if tm:
        spans.append(tm.span())
    title = _clean_title(s, spans)
    if not title:
        raise ValueError("no task text")
    return Rule(_rid(s), kind, title, s, time=(hh, mm), **extra)


def parse_text(text):
    """-> (rules, errors); errors = [(номер_строки, строка, причина)]."""
    text = re.sub(r"<!--.*?-->", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
    rules, errors, seen = [], [], set()
    for i, line in enumerate(text.splitlines(), 1):
        st = line.strip()
        if not st or st.startswith("#") or st.startswith(">") or st in ("---", "***"):
            continue
        if not re.match(r"^(?:[-*+]\s+|\d+[.)]\s+|\[[ xX]?\]\s*)", st) and len(st.split()) < 3:
            continue
        st2 = re.sub(r"^\d+[.)]\s+", "", st)
        try:
            r = parse_line(st2)
        except ValueError as e:
            errors.append((i, st, str(e)))
            continue
        if r.id in seen:
            continue
        seen.add(r.id)
        rules.append(r)
    return rules, errors


def parse_file(path):
    with open(path, encoding="utf-8") as f:
        return parse_text(f.read())


def latest_occurrence(rule, now):
    """Последний запланированный момент <= now для daily/weekly/monthly; иначе None."""
    if rule.kind not in ("daily", "weekly", "monthly"):
        return None
    h, m = rule.time
    for back in range(0, 400):
        d = (now - timedelta(days=back)).date()
        if rule.kind == "weekly" and d.weekday() not in rule.weekdays:
            continue
        if rule.kind == "monthly":
            # 31-го в коротких месяцах -> последний день месяца
            nxt = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
            last = (nxt - timedelta(days=1)).day
            if d.day != min(rule.day_of_month, last):
                continue
        occ = datetime(d.year, d.month, d.day, h, m)
        if occ <= now:
            return occ
    return None


class Scheduler:
    def __init__(self, rules, state_path=None):
        self.rules = list(rules)
        self.state_path = state_path
        self.state = {}
        if state_path and os.path.exists(state_path):
            try:
                with open(state_path, encoding="utf-8") as f:
                    self.state = json.load(f)
            except (OSError, ValueError):
                self.state = {}

    def _save(self):
        if not self.state_path:
            return
        d = os.path.dirname(os.path.abspath(self.state_path))
        os.makedirs(d, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=d, prefix=".hb_", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(self.state, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.state_path)

    def _st(self, rule, now):
        st = self.state.get(rule.id)
        if st is None:
            st = {"first_seen": now.isoformat(), "last_fired": None, "done": False}
            self.state[rule.id] = st
        return st

    def due(self, now):
        """Правила, сработавшие к now и ещё не отмеченные mark_fired. Побочный эффект: запоминает first_seen."""
        out = []
        changed = False
        for r in self.rules:
            new = r.id not in self.state
            st = self._st(r, now)
            changed |= new
            if st.get("done"):
                continue
            first = datetime.fromisoformat(st["first_seen"])
            last = datetime.fromisoformat(st["last_fired"]) if st.get("last_fired") else None
            if r.kind == "once":
                if now >= first + timedelta(seconds=r.interval_s):
                    out.append(r)
            elif r.kind == "interval":
                if now >= (last or first) + timedelta(seconds=r.interval_s):
                    out.append(r)
            else:
                occ = latest_occurrence(r, now)
                if occ is not None and occ > (last or first):
                    out.append(r)
        if changed:
            self._save()
        return out

    def mark_fired(self, rule, now):
        st = self._st(rule, now)
        st["last_fired"] = now.isoformat()
        if rule.kind == "once":
            st["done"] = True
        self._save()

    def fire_due(self, now, inbox_path=None):
        """due + mark_fired + (опционально) дозапись в owner_inbox.jsonl. Возвращает список задач (dict)."""
        tasks = []
        for r in self.due(now):
            tasks.append(to_task(r, now))
            self.mark_fired(r, now)
        if inbox_path and tasks:
            append_jsonl(inbox_path, tasks)
        return tasks


def to_task(rule, now):
    """Строка для /root/nox/state/dispatcher/owner_inbox.jsonl."""
    return {"id": "hb-%s-%s" % (rule.id, now.strftime("%Y%m%d%H%M")), "class": "owner_order", "handler": "track",
            "title": rule.title, "status": "pending", "ts": now.isoformat(timespec="seconds")}


def append_jsonl(path, tasks):
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for t in tasks:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("heartbeat")
    ap.add_argument("--state", default=None)
    ap.add_argument("--inbox", default=None)
    a = ap.parse_args()
    rules, errs = parse_file(a.heartbeat)
    for e in errs:
        print("ERR line %d: %s (%s)" % e)
    for t in Scheduler(rules, a.state).fire_due(datetime.now(), a.inbox):
        print(json.dumps(t, ensure_ascii=False))
