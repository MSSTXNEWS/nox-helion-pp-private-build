"""memory_layer: подключение памяти S03, души, самознания и тона к шлюзу NOX (один объект на процесс шлюза).

Env: NOX_MEMORY_DB (путь SQLite S03), NOX_SOUL=1 (системный промпт «мессир» через prompt_builder),
NOX_EMOTION=1 (тон от emotion_pad), NOX_EVENTS (JSONL шины событий; по умолчанию events.jsonl рядом с БД),
NOX_CORE_BUDGET (токены ядра, 400), NOX_PROMPT_MAX (токены всего промпта, 900), NOX_RECALL_K (6),
NOX_MEMORY_CREATE=1 (создать пустую БД, если файла нет; по умолчанию НЕ создаём, пишем в лог и работаем без памяти),
NOX_SESSION_SUMMARY (JSONL или SQLite; сюда пишется сводка после каждого ответа), NOX_JOURNAL, NOX_SERVER, NOX_MODEL...
Любой сбой памяти не ломает ответ: пишем причину в лог (stderr) и отвечаем без памяти.
"""
import json
import os
import re
import sqlite3
import sys
import threading
import time

from .emotion_pad import PadState
from .fact_extract import emotion_event, extract, unsafe
from .prompt_builder import build_system_prompt
from .self_knowledge import SelfKnowledge

THINK = re.compile(r"<think>.*?</think>", re.S)
OPEN_RE = re.compile(r"\b(?:надо|нужно|не забудь|todo|потом сделай)\s+([^.!?\n]{4,120})", re.I)
RETRY_S = 30.0


def _wow_path(sub, env=None):
    """Папка модулей WOW7 (nox-control/wow7/<sub>, либо NOX_WOW7_<SUB>) -> sys.path. Модули плоские: import correction / import per_wire."""
    d = (os.environ if env is None else env).get("NOX_WOW7_" + sub.upper()) or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "wow7", sub)
    if os.path.isdir(d) and d not in sys.path:
        sys.path.append(d)


def _guarded():
    """MEM-03: guarded_add_fact из wow7/mem/correction.py (отозванное не воскресает); нет модуля -> None, пишется прямой add_fact."""
    try:
        _wow_path("mem")
        from correction import guarded_add_fact
        return guarded_add_fact
    except Exception:
        return None


def _flag(v):
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def _clip(t, n):
    t = " ".join(str(t or "").split())
    return t if len(t) <= n else t[:n - 1].rstrip() + "…"


class MemoryLayer:
    def __init__(self, env=None, log=None, clock=time.time):
        self.env = dict(os.environ if env is None else env)
        e = self.env.get
        self.db_path = (e("NOX_MEMORY_DB") or "").strip()
        self.soul = _flag(e("NOX_SOUL"))
        self.emotion = _flag(e("NOX_EMOTION"))
        self.create = _flag(e("NOX_MEMORY_CREATE"))
        self.core_budget = int(e("NOX_CORE_BUDGET") or 400)
        self.prompt_max = int(e("NOX_PROMPT_MAX") or 900)
        self.k = int(e("NOX_RECALL_K") or 6)
        self.summary_path = (e("NOX_SESSION_SUMMARY") or "").strip()
        self.events_path = (e("NOX_EVENTS") or "").strip() or (
            os.path.join(os.path.dirname(os.path.abspath(self.db_path)), "events.jsonl") if self.db_path else "")
        self._log = log or (lambda m: print("[memory] " + m, file=sys.stderr, flush=True))
        self.clock = clock
        self.lock = threading.RLock()
        self.store = self.search = self.recall = self.bus = None
        self._next_try = 0.0
        self._warned = set()
        self.pad = PadState() if self.emotion else None
        self.per = None                      # PER-02: живая личность (NOX_PERSONA=1); флаг выключен -> поведение прежнее
        if _flag(e("NOX_PERSONA")):
            try:
                _wow_path("per")
                from per_wire import PerWire
                self.per = PerWire(state_dir=e("NOX_STATE") or None, pad=self.pad)
            except Exception as ex:
                self._log("NOX_PERSONA=1, но per_wire не загружен (%s): личность не живёт" % ex)
        self._guard = _guarded()
        if self._guard is None:
            self._log("MEM-03: wow7/mem/correction.py не найден: отозванные факты могут вернуться")
        self.sk = SelfKnowledge(env=self.env)
        self.last_mode = None
        self.telemetry = lambda: {}
        self._open_bus()
        self.status = self._connect(first=True)
        if not self.soul:
            self.warn_once("soul_off", "NOX_SOUL не 1: системный промпт «души» не строится, остаётся короткая персона")

    # --- журнал и подключение ---
    def warn_once(self, key, msg):
        if key not in self._warned:
            self._warned.add(key)
            self._log(msg)

    def _open_bus(self):
        self.bus = None
        if self.events_path:
            try:
                from .events_bus import EventBus
                os.makedirs(os.path.dirname(os.path.abspath(self.events_path)), exist_ok=True)
                self.bus = EventBus(self.events_path)
            except Exception as ex:
                self.warn_once("bus", "шина событий недоступна (%s): события не пишутся" % ex)

    def _connect(self, first=False):
        """-> строка состояния. Повторяет попытку не чаще раза в RETRY_S (БД могла появиться после импорта)."""
        if self.store is not None:
            return "ok"
        if not self.db_path:
            self.warn_once("nodb", "NOX_MEMORY_DB не задан: работаю БЕЗ памяти (без поиска и автозаписи)")
            return "no_db_env"
        now = self.clock()
        if not first and now < self._next_try:
            return "no_db_file"
        self._next_try = now + RETRY_S
        if not os.path.isfile(self.db_path) and not self.create:
            self.warn_once("nofile", "БД памяти %s не найдена: работаю БЕЗ памяти, проверю снова позже "
                           "(импорт: c126/memory_boot_s1.sh)" % self.db_path)
            return "no_db_file"
        try:
            from .memory_search import MemorySearch
            from .recall_api import Recall
            from .s03_store import Store
            self.store = Store(self.db_path)
            self.search = MemorySearch(self.store)
            self.recall = Recall(self.store, self.search, bus=self.bus)
            self._warned.discard("nofile")
            self._log("память подключена: %s %s" % (self.db_path, self.store.stats()))
            return "ok"
        except Exception as ex:
            self.store = self.search = self.recall = None
            self.warn_once("openfail:" + str(ex), "БД памяти %s не открылась (%s): работаю БЕЗ памяти" % (self.db_path, ex))
            return "error: %s" % ex

    @property
    def memory_on(self):
        with self.lock:
            self.status = self._connect()
            return self.store is not None

    # --- события ---
    def publish(self, typ, data):
        if self.bus is not None:
            try:
                self.bus.publish(typ, data, source="gateway")
            except Exception as ex:
                self.warn_once("pub", "событие %s не записано: %s" % (typ, ex))

    def started(self, turn_id, mode):
        if self.last_mode is not None and mode != self.last_mode:
            self.publish("mode.changed", {"from": self.last_mode, "to": mode, "reason": "запрос"})
        self.last_mode = mode
        self.publish("reply.started", {"turn_id": turn_id, "mode": mode})

    def finished(self, turn_id, chars=None):
        self.publish("reply.finished", {"turn_id": turn_id, "tokens": None, "chars": chars})

    # --- перед ответом ---
    def prepare(self, user_text, turn_id):
        """-> {"system": str|None, "facts": [str], "info": {...}}.
        system - готовый системный промпт (только при NOX_SOUL=1); facts - для nox_facts, если душа выключена."""
        info = {"memory": "off", "soul": self.soul, "emotion": self.emotion}
        core_text, recalled = "", []
        if user_text and self.memory_on:
            try:
                with self.lock:
                    r = self.recall.recall_for_reply(user_text, turn_id=turn_id, k=self.k, budget_tokens=self.core_budget)
                core_text = r["core"]["text"]
                recalled = [h["text"] for h in r["search"]["hits"]]
                info.update(memory="ok", turn_id=turn_id, core_items=len(r["core"]["items"]), found=len(recalled),
                            search_mode=r["search"]["mode"])
                if r["search"].get("warnings"):
                    info["search_warnings"] = r["search"]["warnings"]
            except Exception as ex:
                self._log("поиск по памяти упал (%s): отвечаю без памяти" % ex)
                info["memory"] = "error: %s" % ex
        else:
            info["memory"] = self.status
        if not self.soul:
            lines = [l[2:] if l.startswith("- ") else l for l in core_text.splitlines() if l.startswith("- ")] + recalled
            return {"system": None, "facts": lines[:12], "info": info}
        style = ""
        if self.pad is not None:
            with self.lock:
                style = self.pad.prompt_line(self.clock())
        sysm = build_system_prompt(core_text=core_text, recalled=recalled, self_text=self.self_text(), style_hint=style,
                                   max_tokens=self.prompt_max)
        info.update(prompt_tokens=sysm["tokens"], trimmed=sysm["trimmed"], over_budget=sysm["over_budget"])
        return {"system": sysm["text"], "facts": [], "info": info}

    def self_text(self):
        t = self.sk.summary()
        try:
            tel = self.telemetry() or {}
        except Exception:
            tel = {}
        bits = []
        for tier, label in (("deep", "глубокая модель"), ("fast", "быстрая модель")):
            v = (tel.get("speed") or {}).get(tier)
            if v and v.get("basis") == "measured":
                bits.append("%s ~%s ток/с" % (label, v["tps"]))
        if "fast_available" in tel:
            bits.append("быстрый тир " + ("доступен" if tel["fast_available"] else "недоступен"))
        if self.store is not None:
            try:
                st = self.store.stats()
                bits.append("память: " + ", ".join("%s %s" % (k, v) for k, v in st.items() if isinstance(v, int)))
            except Exception:
                pass
        return "; ".join(x for x in (t, "; ".join(bits)) if x)

    # --- после ответа ---
    def after_reply(self, user_text, reply_text, turn_id, messages=None, session=None):
        """Автозапись фактов о владельце и эпизодов разговора, тон, сводка сессии. Возвращает отчёт; не бросает."""
        rep = {"facts": [], "episodes": 0, "summary": None}
        reply = THINK.sub("", reply_text or "").strip()      # размышлений модели в памяти нет
        try:
            ev = emotion_event(user_text)
            if self.pad is not None and ev:
                with self.lock:
                    self.pad.apply(ev, self.clock())
        except Exception as ex:
            self._log("тон не обновлён: %s" % ex)
        if self.per is not None:
            try:
                with self.lock:
                    rep["persona"] = self.per.after_reply(user_text, reply, self.clock())
            except Exception as ex:
                self._log("личность не обновлена: %s" % ex)
        if self.memory_on:
            try:
                with self.lock:
                    sess = session or time.strftime("%Y-%m-%d", time.gmtime(self.clock()))
                    for f in extract(user_text):
                        add = (lambda *x, **k: self._guard(self.store, *x, **k)) if self._guard else self.store.add_fact
                        fid = add(f["text"], kind=f["kind"], source="chat:" + sess, source_kind=f["source_kind"], actor="gateway")
                        if fid is None:                      # отозвано владельцем: не добавляем
                            rep.setdefault("blocked", []).append(f["text"])
                            continue
                        rep["facts"].append({"ref": "f:%d" % fid, "text": f["text"], "rule": f["rule"],
                                             "level": self.store.get_fact(fid)["level"]})
                    now = self.clock()
                    if user_text and not unsafe(user_text):
                        self.store.add_episode(_clip(user_text, 1000), role="user", ts=now, session=sess, actor="gateway")
                        rep["episodes"] += 1
                    if reply and not unsafe(reply):
                        self.store.add_episode(_clip(reply, 1000), role="assistant", ts=now + 0.001, session=sess, actor="gateway")
                        rep["episodes"] += 1
                if rep["facts"]:
                    self.publish("memory.changed", {"turn_id": turn_id, "added": [f["ref"] for f in rep["facts"]]})
            except Exception as ex:
                self._log("автозапись в память не удалась (%s)" % ex)
                rep["error"] = str(ex)
        try:
            rep["summary"] = self.write_summary(user_text, messages or [], session)
        except Exception as ex:
            self._log("сводка сессии не записана (%s)" % ex)
            rep["summary_error"] = str(ex)
        return rep

    # --- сводка «на чём остановились» ---
    def write_summary(self, user_text, messages, session=None):
        """Дописывает строку сводки (без модели, из реплик владельца). -> путь или None, если NOX_SESSION_SUMMARY не задан."""
        if not self.summary_path or not (user_text or "").strip():
            return None
        users = [m.get("content") for m in messages if m.get("role") == "user" and isinstance(m.get("content"), str)]
        users = [u for u in users if u.strip()] or [user_text]
        opens = []
        for u in users:
            for m in OPEN_RE.finditer(u):
                if not unsafe(m.group(0)):
                    opens.append(_clip(m.group(1), 120))
        row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.clock())),
               "summary": "Реплик владельца: %d. Началось с: «%s». Последняя тема: «%s»." % (len(users), _clip(users[0], 100), _clip(users[-1], 100)),
               "open_items": opens[-7:], "next_step": opens[-1] if opens else "",
               "last_user": _clip(users[-1], 200), "session": session or ""}
        if unsafe(row["summary"]) or unsafe(row["last_user"]):
            row.update(summary="Реплик владельца: %d (текст скрыт: похоже на секрет)." % len(users), last_user="", open_items=[], next_step="")
        p = self.summary_path
        os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)
        if p.endswith((".db", ".sqlite", ".sqlite3")):
            with self.lock:
                c = sqlite3.connect(p)
                try:
                    c.execute("CREATE TABLE IF NOT EXISTS sessions(ts TEXT, summary TEXT, open_items TEXT, next_step TEXT, last_user TEXT, session TEXT)")
                    c.execute("INSERT INTO sessions VALUES(?,?,?,?,?,?)", (row["ts"], row["summary"], json.dumps(row["open_items"], ensure_ascii=False),
                                                                         row["next_step"], row["last_user"], row["session"]))
                    c.commit()
                finally:
                    c.close()
        else:
            with self.lock, open(p, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return p

    def journal(self, event, details=None):
        if self.sk.journal:
            try:
                self.sk.record_event(event, details)
            except Exception as ex:
                self._log("журнал событий не записан: %s" % ex)
