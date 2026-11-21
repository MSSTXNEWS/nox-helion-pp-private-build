"""self_knowledge: NOX знает, где он работает, на чём и что с ним было, ТОЛЬКО из данных.

Источники: переменные окружения (NOX_SERVER=S1|S2, NOX_MODEL, NOX_PORT, NOX_BUILD), файлы версии
(NOX_BUILD_FILE или VERSION/BUILD_ID в NOX_HOME), имя хоста системы и журнал ключевых событий JSONL
(NOX_JOURNAL): по строке {"ts":..., "event":"...", "details":..., "key":true}. Чего нет в данных,
о том ответ «не знаю: не задано ...», ничего не придумывается.
"""
import json
import os
import re
import socket
import time

LABELS = {"server": "сервер", "host": "хост", "model": "модель", "port": "порт", "build": "версия сборки"}
INTENTS = [
    ("history", re.compile(r"что с тобой (было|случилось|происходило)|твоя истори|что было|журнал|последние событ|что с тобой", re.I)),
    ("where", re.compile(r"где ты|где работаешь|на каком сервере|где запущен|где находишься|на каком ты сервере", re.I)),
    ("version", re.compile(r"верси|сборк|релиз", re.I)),
    ("runs", re.compile(r"на ч[её]м (ты )?(работаешь|запущен|крутишься)|какая (у тебя )?модель|на какой модели|какой порт|на каком порту", re.I)),
]


def _ts_fmt(ts):
    return time.strftime("%Y-%m-%d %H:%M", time.gmtime(ts)) + " UTC"


class SelfKnowledge:
    def __init__(self, env=None, base_dir=None, journal_path=None, hostname=None):
        self.env = dict(os.environ if env is None else env)
        self.base = base_dir or self.env.get("NOX_HOME") or ""
        self.journal = journal_path or self.env.get("NOX_JOURNAL") or ""
        self._hostname = hostname

    # --- факты ---
    def _read_first_line(self, path):
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                line = f.readline().strip()
            return line or None
        except OSError:
            return None

    def facts(self):
        """{ключ: {"value", "source"}} только для найденного."""
        e, out = self.env, {}
        if e.get("NOX_SERVER", "").strip():
            out["server"] = {"value": e["NOX_SERVER"].strip(), "source": "env NOX_SERVER"}
        if e.get("NOX_MODEL", "").strip():
            out["model"] = {"value": e["NOX_MODEL"].strip(), "source": "env NOX_MODEL"}
        if e.get("NOX_PORT", "").strip():
            out["port"] = {"value": e["NOX_PORT"].strip(), "source": "env NOX_PORT"}
        if e.get("NOX_BUILD", "").strip():
            out["build"] = {"value": e["NOX_BUILD"].strip(), "source": "env NOX_BUILD"}
        else:
            cands = [e.get("NOX_BUILD_FILE", "")] + ([os.path.join(self.base, n) for n in ("BUILD_ID", "VERSION")] if self.base else [])
            for p in cands:
                if p and (v := self._read_first_line(p)):
                    out["build"] = {"value": v, "source": "файл " + p}
                    break
        try:
            h = self._hostname or socket.gethostname()
            if h:
                out["host"] = {"value": h, "source": "система (имя хоста)"}
        except OSError:
            pass
        return out

    def missing(self):
        have = self.facts()
        return [k for k in ("server", "model", "port", "build") if k not in have]

    # --- журнал ---
    def record_event(self, event, details=None, key=True, ts=None):
        if not self.journal:
            raise ValueError("журнал не задан (NOX_JOURNAL)")
        rec = {"ts": ts or time.time(), "event": str(event), "key": bool(key)}
        if details is not None:
            rec["details"] = details
        os.makedirs(os.path.dirname(os.path.abspath(self.journal)), exist_ok=True)
        with open(self.journal, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec

    def history(self, limit=5, key_only=True):
        """-> (события новейшие последними, число битых строк, журнал найден)."""
        if not self.journal or not os.path.isfile(self.journal):
            return [], 0, False
        evs, bad = [], 0
        with open(self.journal, encoding="utf-8", errors="replace") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    r = json.loads(line)
                    if not isinstance(r, dict) or "event" not in r:
                        raise ValueError
                except ValueError:
                    bad += 1
                    continue
                if key_only and r.get("key") is False:
                    continue
                evs.append(r)
        evs.sort(key=lambda r: r.get("ts") or 0)
        return evs[-limit:], bad, True

    # --- ответы ---
    def _line(self, f, keys):
        return [("%s: %s" % (LABELS[k], f[k]["value"])) for k in keys if k in f]

    def answer(self, question, history_limit=5):
        """-> {"intent","answer","used":[...],"missing":[...]}; answer=None если вопрос не про самого NOX."""
        intent = next((n for n, rx in INTENTS if rx.search(question or "")), None)
        if intent is None:
            return {"intent": None, "answer": None, "used": [], "missing": []}
        f = self.facts()
        if intent == "history":
            evs, bad, found = self.history(history_limit)
            if not found:
                return {"intent": intent, "answer": "Не знаю, что со мной было: журнал событий не задан или не найден.",
                        "used": [], "missing": ["journal"]}
            if not evs:
                return {"intent": intent, "answer": "В журнале нет ключевых событий.", "used": ["journal"], "missing": []}
            lines = []
            for r in evs:
                d = r.get("details")
                lines.append("%s — %s%s" % (_ts_fmt(r["ts"]) if isinstance(r.get("ts"), (int, float)) else "время неизвестно",
                                            r["event"], (" (%s)" % (d if isinstance(d, str) else json.dumps(d, ensure_ascii=False))) if d else ""))
            tail = " Битых строк в журнале пропущено: %d." % bad if bad else ""
            return {"intent": intent, "answer": "Последние ключевые события из журнала:\n" + "\n".join(lines) + tail,
                    "used": ["journal"], "missing": []}
        keys = {"where": ["server", "host", "port"], "runs": ["model", "server", "port"], "version": ["build"]}[intent]
        have = self._line(f, keys)
        miss = [k for k in keys if k not in f and k != "host"]
        if not have:
            return {"intent": intent, "answer": "Не знаю: эти данные мне не заданы (%s)." % ", ".join(LABELS[k] for k in miss),
                    "used": [], "missing": miss}
        ans = "Мои данные: " + "; ".join(have) + "."
        if miss:
            ans += " Не знаю (не задано): " + ", ".join(LABELS[k] for k in miss) + "."
        return {"intent": intent, "answer": ans, "used": [k for k in keys if k in f], "missing": miss}

    def summary(self):
        """Короткий текст для промпта (только известное)."""
        f = self.facts()
        parts = self._line(f, ["server", "model", "port", "build"])
        return "; ".join(parts)
