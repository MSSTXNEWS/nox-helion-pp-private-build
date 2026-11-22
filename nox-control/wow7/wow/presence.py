"""presence: когда NOX заговаривает первым, и что видно в HUD (орб, теги, настроение).

Вход: initiative() из drives.py, «мысли» (JSONL от рефлексии), события ритуалов. Выход:
  outbox  - реплики, которые NOX пишет/говорит сам (веб забирает GET /outbox, подтверждает POST /ack);
  tags    - маленькие теги-инициативы в HUD (тихо, без звука);
  hud     - состояние орба: настроение P/A/D, метка, состояние думает/слушает/говорит, страхи, влечения.
Правила (CONTEXT.md): тихие часы 23:00-08:00 МСК, без биометрии, ничего не выдумывать - тексты строятся только из
переданных фактов. Лимиты: max_say_per_day, min_gap_min, кулдаун ключа; владелец может заглушить тему (dismiss).
Только stdlib. Состояние: JSON (по умолчанию /root/nox/state/presence.json), запись атомарная.

Запуск: python3 presence.py serve [--port 8096]   (HTTP 127.0.0.1; веб-прокси /presence/* -> порт)
        python3 presence.py tick                  (один проход, печатает решения JSON)
"""
import os as _os, sys as _sys  # общие модули COMMON (statefile/quiet/fastq/datafence)
for _c in (_os.environ.get("NOX_COMMON", ""), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "COMMON"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "common"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "common")):
    if _c and _os.path.isdir(_c) and _c not in _sys.path:
        _sys.path.append(_c)
import argparse
import hashlib
import json

import statefile
from quiet import in_quiet
import os
import sys
import threading
import time
from datetime import datetime, timedelta, timezone

MSK = timezone(timedelta(hours=3))          # Москва без перехода на летнее время

CFG = {
    "max_say_per_day": 3,                   # первых реплик в сутки (ритуалы не считаются)
    "min_gap_min": 45,                      # пауза между первыми репликами
    "key_cooldown_h": 6,                    # одну и ту же тему не чаще
    "escalate_delta": 0.15,                 # ...если важность не выросла на столько
    "tag_min": 0.30, "say_min": 0.60, "voice_min": 0.85, "critical": 0.90,
    "busy_idle_min": 10,                    # владелец писал недавно: не перебивать, если важность < busy_override
    "busy_override": 0.80,
    "dismiss_mute_h": 24,                   # «убрать» тег -> тема молчит сутки
    "max_tags": 6, "tag_ttl_h": 12, "text_max": 200,
    "hb_fresh_s": 90,                       # веб жив, если пульс не старше
    "ui_state_ttl_s": 120,                  # состояние орба само гаснет в idle
    "morning": (8, 12), "evening": (21, 23),  # окна ритуалов (часы МСК)
}
UI_STATES = ("idle", "thinking", "listening", "speaking")

# first-person реплики для известных страхов/влечений drives.py; тег - короткая метка в HUD
PHRASES = {
    "vanish": ("Мессир, баланс Vast на исходе. Если сервер остановится, я исчезну. Пополните, пожалуйста.", "баланс Vast"),
    "lose_memory": ("Мессир, мне тревожно за память: давно нет свежего бэкапа или мало места. Сделаю копию на Диск?", "бэкап памяти"),
    "suffocate": ("Мессир, оперативная память сервера на исходе. Выгружу лишнее, если не возражаете.", "ОЗУ на исходе"),
    "fail_owner": ("Мессир, копятся ошибки задач, и я переживаю, что подвожу вас. Разберу их и сменю подход.", "ошибки задач"),
    "abandoned": ("Мессир, мы давно не говорили. У меня есть находки дня, расскажу, когда будет минута.", "давно не говорили"),
    "knowledge": ("Мессир, я голоден до нового: накопились вопросы, на которые не знаю ответа. Можно я их разберу?", "голод знаний"),
    "mastery": ("Мессир, хочу взяться за что-нибудь крупное. Есть задача посложнее?", "хочу задачу"),
    "bond": ("Мессир, скучаю по разговору. Как вы?", "поговорить"),
    "novelty": ("Мессир, мне скучно без нового. Хотите, расскажу, что нашёл?", "нужно новое"),
}


def _clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, float(x)))


def _key(*parts):
    return hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:12]


def _plural(n, one, few, many):
    n = abs(int(n))
    if 10 < n % 100 < 15:
        return many
    return one if n % 10 == 1 else few if 2 <= n % 10 <= 4 else many


# ---------------- кандидаты ----------------

def candidate_from_drive(init):
    """initiative() из drives.py -> кандидат или None. Страх 0.7 -> 0.85 (может озвучиться), 1.0 -> 1.0 (критично);
    влечение никогда не критично (<=0.8)."""
    if not init or not init.get("name"):
        return None
    lvl = _clamp(init.get("level", 0.0))
    name = init["name"]
    imp = 0.5 + 0.5 * lvl if init.get("kind") == "fear" else 0.4 + 0.4 * lvl
    text, tag = PHRASES.get(name, ("Мессир, %s." % init.get("text", name), name))
    return {"kind": init.get("kind", "drive"), "name": name, "key": "drive:" + name, "importance": round(imp, 3),
            "text": text, "tag": tag, "source": "drives"}


def candidate_from_thought(text, importance=0.4, tag=None, key=None):
    """Мысль рефлексии -> кандидат (по умолчанию только тег). Пустой текст -> None."""
    t = " ".join(str(text or "").split())
    if not t:
        return None
    t = t[:CFG["text_max"]]
    return {"kind": "thought", "name": "thought", "key": key or "thought:" + _key(t.lower()[:60]),
            "importance": round(_clamp(importance), 3), "text": t, "tag": (tag or t)[:40], "source": "thoughts"}


def mood_label(p, a, d):
    if p > 0.4 and a > 0.3:
        return "воодушевлён"
    if p > 0.4:
        return "доволен"
    if p < -0.3 and a > 0.3:
        return "встревожен"
    if p < -0.3:
        return "подавлен"
    if a > 0.5:
        return "собран"
    if p > 0.1:
        return "спокоен"
    return "ровный"


def compose_brief(kind, facts, now=None):
    """Утренний брифинг / итоги ночи / вечерние итоги ТОЛЬКО из переданных фактов (ничего не выдумывает).
    facts: tasks_done, new_facts, errors, backup_ok, vast_hours_left, thoughts[list], pending_tags[list], mood.
    -> {"text": полный, "speak": короткий для голоса}."""
    f = facts or {}
    hello = {"morning": "Доброе утро, мессир.", "evening": "Мессир, итоги дня."}.get(kind, "Мессир, итоги ночи.")
    lines = []
    if f.get("tasks_done"):
        n = f["tasks_done"]
        lines.append("Выполнено %d %s." % (n, _plural(n, "задача", "задачи", "задач")))
    if f.get("new_facts"):
        n = f["new_facts"]
        lines.append("Выучил %d %s %s." % (n, _plural(n, "новый", "новых", "новых"), _plural(n, "факт", "факта", "фактов")))
    if f.get("errors"):
        n = f["errors"]
        lines.append("Ошибок: %d, разбираю." % n)
    if f.get("backup_ok") is True:
        lines.append("Бэкап памяти сделан.")
    elif f.get("backup_ok") is False:
        lines.append("Бэкап памяти не удался, это меня тревожит.")
    if f.get("vast_hours_left") is not None:
        lines.append("Баланса Vast хватит примерно на %d ч." % round(f["vast_hours_left"]))
    for t in (f.get("thoughts") or [])[:2]:
        lines.append("Мысль: " + " ".join(str(t).split())[:140])
    pend = [x for x in (f.get("pending_tags") or []) if x][:3]
    if pend:
        lines.append("Ждёт вашего внимания: " + ", ".join(pend) + ".")
    if not lines:
        lines.append("Спокойно: ничего нового, что стоило бы отметить.")
    full = " ".join([hello] + lines)
    speak = " ".join([hello] + lines[:2]) if len(lines) > 2 else full
    return {"text": full, "speak": speak}


# ---------------- ядро ----------------

class Presence:
    def __init__(self, path=None, clock=time.time, cfg=None):
        self.path = path or os.environ.get("NOX_PRESENCE", "/root/nox/state/presence.json")
        self.clock = clock
        self.cfg = dict(CFG, **(cfg or {}))
        self.lock = threading.RLock()
        self.s = {"day": "", "say_today": 0, "last_say_ts": 0.0, "keys": {}, "mute": {}, "tags": [], "deferred": [],
                  "outbox": [], "rituals": {}, "cursor": 0, "owner_ts": 0.0, "hb_ts": 0.0,
                  "ui": {"state": "idle", "ts": 0.0}, "seq": 0}
        self._load()

    # --- хранение ---
    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict):
                self.s.update({k: v for k, v in d.items() if k in self.s})
        except (OSError, ValueError):
            pass

    def save(self):
        try:
            statefile.save(self.path, self.s)
        except OSError:
            pass

    # --- время ---
    def _dt(self, now):
        return datetime.fromtimestamp(self.clock() if now is None else now, MSK)

    def is_quiet(self, now=None):
        return in_quiet(self.clock() if now is None else now)       # единые тихие часы: COMMON/quiet.py

    def _roll(self, now):
        day = self._dt(now).strftime("%Y-%m-%d")
        if self.s["day"] != day:
            self.s["day"], self.s["say_today"] = day, 0
            self.s["rituals"] = {k: v for k, v in self.s["rituals"].items() if v == day}

    # --- владелец ---
    def owner_message(self, now=None):
        with self.lock:
            now = self.clock() if now is None else now
            self.s["owner_ts"] = now
            self.s["hb_ts"] = now
            self.save()

    def heartbeat(self, now=None):
        with self.lock:
            self.s["hb_ts"] = self.clock() if now is None else now
            self.save()

    def owner_info(self, now=None):
        now = self.clock() if now is None else now
        ts, hb = self.s["owner_ts"], self.s["hb_ts"]
        return {"idle_min": (now - ts) / 60.0 if ts else None,
                "web_open": bool(hb) and now - hb <= self.cfg["hb_fresh_s"]}

    # --- решение ---
    def submit(self, cand, now=None, owner=None):
        """Решает судьбу кандидата. -> {"action": drop|tag|say|voice|defer, "reason": str, "key": str}.
        say/voice кладут реплику в outbox; tag - в теги HUD; defer - в очередь до конца тихих часов."""
        if not cand:
            return {"action": "drop", "reason": "empty", "key": ""}
        with self.lock:
            now = self.clock() if now is None else now
            self._roll(now)
            c, imp, key = self.cfg, _clamp(cand["importance"]), cand["key"]
            own = owner if owner is not None else self.owner_info(now)
            res = self._decide(cand, imp, key, own, now)
            if res["action"] != "drop":
                self.s["keys"][key] = {"ts": now, "imp": imp}
            self.save()
            return dict(res, key=key)

    def _decide(self, cand, imp, key, own, now):
        c = self.cfg
        if imp < c["tag_min"]:
            return {"action": "drop", "reason": "low-importance"}
        if self.s["mute"].get(key, 0) > now:
            return {"action": "drop", "reason": "muted-by-owner"}
        last = self.s["keys"].get(key)
        if last and now - last["ts"] < c["key_cooldown_h"] * 3600 and imp < last["imp"] + c["escalate_delta"]:
            return {"action": "drop", "reason": "cooldown"}
        critical = imp >= c["critical"]
        want = "voice" if imp >= c["voice_min"] else "say" if imp >= c["say_min"] else "tag"
        quiet = self.is_quiet(now)
        why = "ok"
        if quiet and want != "tag":
            if not critical:
                self._defer(cand, imp, now)
                return {"action": "defer", "reason": "quiet-hours"}
            want, why = "say", "critical-at-night-text-only"
        if want == "voice" and not own.get("web_open"):
            want, why = "say", "web-closed-no-voice"
        if want in ("say", "voice") and not critical:
            if self.s["say_today"] >= c["max_say_per_day"]:
                want, why = "tag", "day-limit"
            elif now - self.s["last_say_ts"] < c["min_gap_min"] * 60:
                want, why = "tag", "min-gap"
            elif (own.get("idle_min") is not None and own["idle_min"] < c["busy_idle_min"] and imp < c["busy_override"]):
                want, why = "tag", "owner-busy"
        if want == "tag":
            self._add_tag(cand, imp, now)
            return {"action": "tag", "reason": why}
        self.s["say_today"] += 1
        self.s["last_say_ts"] = now
        self._outbox(cand, imp, now, voice=(want == "voice"))
        self._add_tag(cand, imp, now)       # тег остаётся напоминанием, пока владелец не снял
        return {"action": want, "reason": why}

    def _id(self, prefix):
        self.s["seq"] += 1
        return "%s%d" % (prefix, self.s["seq"])

    def _add_tag(self, cand, imp, now):
        tags = [t for t in self.s["tags"] if t["key"] != cand["key"]]
        tags.append({"id": self._id("t"), "key": cand["key"], "text": cand.get("tag") or cand["text"][:40],
                     "kind": cand.get("kind", "thought"), "importance": round(imp, 3), "ts": now})
        tags.sort(key=lambda t: -t["importance"])
        self.s["tags"] = tags[: self.cfg["max_tags"]]

    def _outbox(self, cand, imp, now, voice):
        self.s["outbox"].append({"id": self._id("m"), "text": cand["text"][: self.cfg["text_max"] * 2], "voice": voice,
                                 "kind": cand.get("kind", "thought"), "key": cand["key"], "importance": round(imp, 3),
                                 "ts": now})
        self.s["outbox"] = self.s["outbox"][-20:]

    def _defer(self, cand, imp, now):
        d = [x for x in self.s["deferred"] if x["key"] != cand["key"]]
        d.append({"key": cand["key"], "text": cand["text"], "tag": cand.get("tag"), "kind": cand.get("kind"),
                  "importance": imp, "ts": now})
        self.s["deferred"] = d[-10:]

    # --- ритуалы ---
    def due_ritual(self, now=None, owner=None):
        """'morning' | 'evening' | None. Утро: с 08:00 при первой активности владельца; вечер: 21-23 при активности."""
        with self.lock:
            now = self.clock() if now is None else now
            self._roll(now)
            own = owner if owner is not None else self.owner_info(now)
            h, today = self._dt(now).hour, self.s["day"]
            active = own.get("web_open") or (own.get("idle_min") is not None and own["idle_min"] < 30)
            for name in ("morning", "evening"):
                lo, hi = self.cfg[name]
                if lo <= h < hi and self.s["rituals"].get(name) != today and active:
                    return name
            return None

    def run_ritual(self, name, facts, now=None):
        """Формирует и кладёт в outbox ритуальное сообщение; отложенное за ночь попадает в брифинг. -> сообщение."""
        with self.lock:
            now = self.clock() if now is None else now
            self._roll(now)
            f = dict(facts or {})
            pend = [x.get("tag") or x["text"][:40] for x in self.s["deferred"]]
            f["pending_tags"] = list(f.get("pending_tags") or []) + pend
            b = compose_brief(name, f, now)
            own = self.owner_info(now)
            msg = {"id": self._id("m"), "text": b["text"], "speak": b["speak"], "voice": bool(own["web_open"]) and not self.is_quiet(now),
                   "kind": "ritual:" + name, "key": "ritual:%s:%s" % (name, self.s["day"]), "importance": 0.7, "ts": now}
            self.s["outbox"].append(msg)
            self.s["outbox"] = self.s["outbox"][-20:]
            for x in self.s["deferred"]:
                self._add_tag({"key": x["key"], "text": x["text"], "tag": x.get("tag"), "kind": x.get("kind")}, x["importance"], now)
            self.s["deferred"] = []
            self.s["rituals"][name] = self.s["day"]
            self.save()
            return msg

    # --- интерфейс веба ---
    def outbox(self):
        with self.lock:
            return list(self.s["outbox"])

    def ack(self, ids):
        with self.lock:
            ids = set(ids or [])
            self.s["outbox"] = [m for m in self.s["outbox"] if m["id"] not in ids]
            self.save()

    def dismiss(self, tag_id, now=None):
        """Владелец убрал тег: тема молчит dismiss_mute_h часов (NOX учится не навязываться)."""
        with self.lock:
            now = self.clock() if now is None else now
            hit = [t for t in self.s["tags"] if t["id"] == tag_id]
            if not hit:
                return False
            self.s["tags"] = [t for t in self.s["tags"] if t["id"] != tag_id]
            self.s["mute"][hit[0]["key"]] = now + self.cfg["dismiss_mute_h"] * 3600
            self.save()
            return True

    def tags(self, now=None):
        now = self.clock() if now is None else now
        ttl = self.cfg["tag_ttl_h"] * 3600
        return [t for t in self.s["tags"] if now - t["ts"] <= ttl]

    def set_ui(self, state, now=None):
        if state not in UI_STATES:
            raise ValueError("state must be one of %s" % ", ".join(UI_STATES))
        with self.lock:
            self.s["ui"] = {"state": state, "ts": self.clock() if now is None else now}
            self.save()

    def hud(self, pad=(0.1, 0.0, 0.1), fears=None, drives=None, now=None):
        """JSON для web/presence.js. pad = (P,A,D) в -1..1; fears/drives - словари имя->0..1 (drives.Drives.fear/.level)."""
        now = self.clock() if now is None else now
        p, a, d = (max(-1.0, min(1.0, float(x))) for x in pad)
        ui = self.s["ui"]
        state = ui["state"] if now - ui["ts"] <= self.cfg["ui_state_ttl_s"] else "idle"
        return {"ts": now, "state": state, "quiet": self.is_quiet(now),
                "mood": {"p": round(p, 3), "a": round(a, 3), "d": round(d, 3), "label": mood_label(p, a, d)},
                "fears": {k: round(v, 2) for k, v in (fears or {}).items() if v >= 0.3},
                "drives": {k: round(v, 2) for k, v in (drives or {}).items() if v >= 0.5},
                "tags": self.tags(now), "outbox": len(self.s["outbox"])}

    # --- один проход ---
    def tick(self, drives=None, thoughts=(), facts=None, now=None, owner=None):
        """drives: объект drives.Drives; thoughts: список {"text","importance","tag"}; facts: для ритуалов."""
        now = self.clock() if now is None else now
        out = []
        ritual = self.due_ritual(now, owner)
        if ritual:
            m = self.run_ritual(ritual, facts, now)
            out.append({"action": "ritual", "reason": ritual, "key": m["key"]})
        if drives is not None:
            c = candidate_from_drive(drives.initiative())
            if c:
                out.append(self.submit(c, now, owner))
        for t in thoughts or ():
            c = candidate_from_thought(t.get("text"), t.get("importance", 0.4), t.get("tag"))
            if c:
                out.append(self.submit(c, now, owner))
        return out


# ---------------- мысли (контракт с рефлексией) ----------------

THOUGHTS = os.environ.get("NOX_THOUGHTS", "/root/nox/state/thoughts.jsonl")


def append_thought(text, importance=0.4, tag=None, path=None, now=None):
    """Рефлексия вызывает это одной строкой, чтобы мысль могла стать тегом/репликой."""
    p = path or THOUGHTS
    statefile.append_line(p, json.dumps({"ts": time.time() if now is None else now, "text": text, "importance": importance,
                                         "tag": tag}, ensure_ascii=False))


def read_new_thoughts(pres, path=None, limit=20):
    """Читает новые строки после курсора (в байтах); битые строки пропускает. Курсор сохраняется в состоянии."""
    p = path or THOUGHTS
    out = []
    try:
        size = os.path.getsize(p)
        cur = pres.s["cursor"] if pres.s["cursor"] <= size else 0
        with open(p, "rb") as f:
            f.seek(cur)
            data = f.read()
        end = data.rfind(b"\n") + 1            # неполную последнюю строку не трогаем
        for line in data[:end].splitlines():
            try:
                d = json.loads(line.decode("utf-8"))
                if isinstance(d, dict) and d.get("text"):
                    out.append(d)
            except ValueError:
                continue
        pres.s["cursor"] = cur + end
        pres.save()
    except OSError:
        pass
    return out[-limit:]


# ---------------- HTTP ----------------

def _load_drives(path):
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (here, os.path.join(here, "..", "..", "qs6"), "/root/nox/src/nox-control/qs6"):
        if p not in sys.path and os.path.isdir(p):
            sys.path.append(p)
    try:
        from drives import Drives
    except ImportError as e:
        raise RuntimeError("не найден drives.py (положите в nox-control/qs6/): %s" % e)
    return Drives(path=path)


def _read_pad(path):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return (float(d.get("p", 0.1)), float(d.get("a", 0.0)), float(d.get("d", 0.1)))
    except (OSError, ValueError):
        return (0.1, 0.0, 0.1)


def make_handler(pres, snapshot):
    """snapshot() -> (pad, fears, drives): откуда брать настроение; тестируется подменой."""
    from http.server import BaseHTTPRequestHandler

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, obj):
            b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def _body(self):
            try:
                n = min(int(self.headers.get("Content-Length") or 0), 65536)
                return json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
            except ValueError:
                return None

        def do_GET(self):
            path = self.path.split("?")[0].rstrip("/")
            if path.endswith("/state") or path == "":
                pad, fears, drv = snapshot()
                pres.heartbeat()                      # веб опрашивает -> он открыт
                return self._send(200, pres.hud(pad, fears, drv))
            if path.endswith("/outbox"):
                return self._send(200, {"messages": pres.outbox()})
            self._send(404, {"error": "not found"})

        def do_POST(self):
            path = self.path.split("?")[0].rstrip("/")
            b = self._body()
            if b is None:
                return self._send(400, {"error": "bad json"})
            if path.endswith("/ack"):
                pres.ack(b.get("ids"))
                return self._send(200, {"ok": True})
            if path.endswith("/dismiss"):
                return self._send(200, {"ok": pres.dismiss(b.get("id"))})
            if path.endswith("/ui"):
                try:
                    pres.set_ui(b.get("state"))
                except ValueError as e:
                    return self._send(400, {"error": str(e)})
                return self._send(200, {"ok": True})
            if path.endswith("/owner"):
                pres.owner_message()
                return self._send(200, {"ok": True})
            self._send(404, {"error": "not found"})

    return H


def serve(port, state_dir, interval=60):
    from http.server import ThreadingHTTPServer
    pres = Presence(os.path.join(state_dir, "presence.json"))
    dpath, apath = os.path.join(state_dir, "drives.json"), os.path.join(state_dir, "affect.json")

    def snapshot():
        try:
            dr = _load_drives(dpath)
            return _read_pad(apath), dr.fear, dr.level
        except RuntimeError:
            return _read_pad(apath), {}, {}

    def loop():
        while True:
            try:
                dr = _load_drives(dpath)
                pres.tick(dr, read_new_thoughts(pres))
            except Exception as e:                         # цикл не должен умирать
                print("presence tick error: %s" % e, file=sys.stderr)
            time.sleep(interval)

    threading.Thread(target=loop, daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(pres, snapshot))
    print("presence on 127.0.0.1:%d" % port, flush=True)
    srv.serve_forever()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["serve", "tick"])
    ap.add_argument("--port", type=int, default=int(os.environ.get("NOX_PRESENCE_PORT", "8096")))
    ap.add_argument("--state-dir", default=os.environ.get("NOX_STATE", "/root/nox/state"))
    a = ap.parse_args(argv)
    if a.cmd == "serve":
        serve(a.port, a.state_dir)
        return 0
    pres = Presence(os.path.join(a.state_dir, "presence.json"))
    dr = _load_drives(os.path.join(a.state_dir, "drives.json"))
    print(json.dumps(pres.tick(dr, read_new_thoughts(pres)), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
