"""Внутренний цикл мыслей NOX (CON-03): непрерывный «монолог» в простое поверх рабочего пространства.

Каждый шаг: тихие часы? чат занят? -> иначе конкурс сигналов (nox_workspace) -> победитель + блок «Я сейчас»
идут в быструю модель (OpenAI-совместимый HTTP, по умолчанию :8083) -> мысль + уверенность -> журнал,
рекуррентно возвращается в рабочее пространство, уверенность попадает в калибровку (nox_self_model_live).
Защиты: тихие часы 23:00-08:00 МСК (LLM не зовётся), приоритет чата (отдаём слот), дневной бюджет мыслей,
анти-руминация (похожая мысль отбрасывается, температура растёт — приём из arXiv 2604.08206).
Ежедневно, после тихих часов, пишет «главу дня» в автобиографию.

Запуск: python3 nox_inner_loop.py --once | --daemon [--interval 300] [--dry-run]
"""
import os as _os, sys as _sys  # общие модули COMMON (statefile/quiet/fastq/datafence)
for _c in (_os.environ.get("NOX_COMMON", ""), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "COMMON"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "common"), _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "common")):
    if _c and _os.path.isdir(_c) and _c not in _sys.path:
        _sys.path.append(_c)
import argparse
import json

from quiet import in_quiet as _in_quiet
import fastq
import statefile
import lifelink
import os
import re
import sys
import time
import urllib.request
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nox_self_model_live import LiveSelfModel, MSK, _get_json  # noqa: E402
from nox_workspace import Workspace, thought_key  # noqa: E402

SYSTEM = ("Ты NOX HELION, личный ИИ мессира. Сейчас никто не пишет, и ты думаешь про себя. "
          "Опирайся ТОЛЬКО на блок [Я СЕЙЧАС]: не выдумывай фактов, воспоминаний и чувств, которых в нём нет. "
          "Состояния — рабочие сигналы, а не доказательство переживания.")
THINK_RE = re.compile(r"Мысль:\s*(.+?)(?:\n\s*Уверенность:|\Z)", re.S | re.I)
CONF_RE = re.compile(r"Уверенность:\s*(\d{1,3})\s*%", re.I)
THINK_TAG = re.compile(r"<think>.*?</think>", re.S)


def in_quiet(ts, quiet=None):
    """Единые тихие часы (COMMON/quiet.py); quiet=(a, b) - только явное переопределение в тестах."""
    return _in_quiet(ts, None if quiet is None else "%d-%d" % tuple(quiet))


def http_llm(url=None, model="nox-fast", timeout=60):
    """Фабрика llm(messages, max_tokens, temperature) -> str: быстрая модель только через COMMON/fastq, приоритет P2 (мысли)."""
    url = url or os.environ.get("NOX_FAST_URL", "http://127.0.0.1:8083/v1/chat/completions")
    return fastq.get(url, model).llm(fastq.P2, timeout=timeout, wait=timeout)


def make_chat_busy(activity_file=None, window=120.0, props_port=8083, clock=time.time, get=_get_json):
    """Занят ли чат: свежий mtime файла активности ИЛИ обрабатывающий слот llama-server. Ошибка пробы = не занят."""
    activity_file = activity_file or os.environ.get("NOX_CHAT_ACTIVITY", "/root/nox/state/chat_activity")

    def busy():
        try:
            if clock() - os.path.getmtime(activity_file) < window:
                return True
        except OSError:
            pass
        try:
            slots = get("http://127.0.0.1:%d/slots" % props_port, 1.0)
            return any(s.get("is_processing") for s in slots)
        except Exception:
            return False
    return busy


def jaccard(a, b):
    A, B = set(re.findall(r"\w+", a.lower())), set(re.findall(r"\w+", b.lower()))
    return len(A & B) / len(A | B) if A | B else 0.0


class InnerLoop:
    def __init__(self, ws, selfmodel, llm, journal_path=None, clock=time.time, chat_busy=lambda: False,
                 quiet=None, daily_budget=60, max_tokens=160, sensors=None, claimed_text="", outbox_path=None):
        self.ws, self.sm, self.llm, self.clock = ws, selfmodel, llm, clock
        self.journal = journal_path or os.environ.get("NOX_THOUGHTS", "/root/nox/state/thoughts.jsonl")
        self.outbox = outbox_path or os.environ.get("NOX_OUTBOX", "/root/nox/state/outbox.jsonl")
        self.chat_busy, self.quiet, self.budget, self.max_tokens = chat_busy, quiet, daily_budget, max_tokens
        self.sensors = sensors or []         # callables(ws, selfmodel): постят сигналы
        self.claimed_text = claimed_text
        self.temp = 0.8
        self.recent = []                     # последние тексты мыслей
        self.day, self.used = None, 0
        self._load_recent()

    def _append(self, path, rec):
        statefile.append_line(path, json.dumps(rec, ensure_ascii=False))

    def _read_journal(self):
        try:
            with open(self.journal, encoding="utf-8") as f:
                return [json.loads(l) for l in f if l.strip()]
        except (OSError, ValueError):
            return []

    def _load_recent(self):
        self.recent = [r["text"] for r in self._read_journal()[-6:] if r.get("text")]

    def _day_key(self, ts):
        return datetime.fromtimestamp(ts, MSK).strftime("%Y-%m-%d")

    def sense(self):
        """Собрать сигналы: я-модель (поправка к описанию, время) + внешние сенсоры."""
        live = self.sm.refresh_models()
        for d in self.sm.discrepancies(self.claimed_text, live):
            self.ws.post("disc:" + d["role"], "в описании меня %s, а запущено %s" % ("/".join(d["claimed"]), d["running"]),
                         0.8, "discrepancy", ttl=6 * 3600)
        ow = self.sm.s.get("last_owner_ts")
        if ow:
            hours = (self.clock() - ow) / 3600.0
            if hours >= 6:
                self.ws.post("time:silence", "мессир не писал %.0f ч" % hours, min(0.9, 0.3 + hours / 48), "time", ttl=3600)
        for fn in self.sensors:
            try:
                fn(self.ws, self.sm)
            except Exception:
                pass
        return live

    def maybe_digest(self):
        """Первый шаг нового дня вне тихих часов: глава дня в автобиографию (1 вызов LLM)."""
        now = self.clock()
        today = self._day_key(now)
        last = self.sm.s.get("last_digest_day")
        if last == today or in_quiet(now, self.quiet):
            return None
        prev = [r for r in self._read_journal() if r.get("day") and r["day"] < today and (last is None or r["day"] > last)]
        if not prev:
            self.sm.s["last_digest_day"] = today
            self.sm.save()
            return None
        day = prev[-1]["day"]
        n = sum(1 for r in prev if r["day"] == day)
        # «Главу дня» пишет ТОЛЬКО MEM/autobio (единый журнал жизни). CON отдаёт ему событие-счётчик, без LLM.
        lifelink.append("thought", "за %s мыслей: %d" % (day, n), "con", state_dir=os.path.dirname(os.path.abspath(self.sm.path)), data={"day": day, "n": n})
        self.sm.s["last_digest_day"] = today
        self.sm.save()
        return None

    def step(self):
        now = self.clock()
        day = self._day_key(now)
        if day != self.day:
            self.day, self.used = day, sum(1 for r in self._read_journal() if r.get("day") == day)
        self.sm.beat()
        if in_quiet(now, self.quiet):
            return {"status": "quiet"}
        if self.chat_busy():
            return {"status": "chat"}
        if self.used >= self.budget:
            return {"status": "budget"}
        self.maybe_digest()
        self.sense()
        win = self.ws.compete()
        if win is None:
            return {"status": "silence"}
        block = self.ws.render_block(self.sm.render(self.claimed_text))
        user = ("%s\n\nФокус внимания: %s\nПодумай про себя в 1-2 фразах (до 40 слов): наблюдение, вопрос к себе или что предложить мессиру. "
                "Формат строго:\nМысль: ...\nУверенность: N%%" % (block, win["text"]))
        try:
            raw = self.llm([{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}], self.max_tokens, self.temp)
        except Exception as e:
            return {"status": "llm_error", "error": type(e).__name__, "detail": str(e)[:80]}
        m = THINK_RE.search(raw)
        text = (m.group(1) if m else raw).strip().replace("\n", " ")[:400]
        c = CONF_RE.search(raw)
        conf = min(1.0, int(c.group(1)) / 100.0) if c else 0.5
        if not text:
            return {"status": "empty"}
        if any(jaccard(text, r) > 0.6 for r in self.recent[-5:]):
            self.temp = min(1.3, self.temp + 0.2)          # застрял: добавить разнообразия
            self.ws.wins.append((now, win["key"]))          # и усилить привыкание к этому фокусу
            self.ws.wins.append((now, win["key"]))
            return {"status": "rumination", "temp": self.temp}
        self.temp = max(0.8, self.temp - 0.1)
        pid = self.sm.predict("мысль: " + text[:120], conf)
        rec = {"ts": now, "day": day, "focus": win["key"], "text": text, "conf": conf, "pred_id": pid}
        self._append(self.journal, rec)
        self.recent.append(text)
        self.recent = self.recent[-6:]
        self.used += 1
        self.ws.post(thought_key(text), text, 0.5 * conf + 0.2, "thought", ttl=1800)   # рекуррентность
        if win["kind"] in ("fear", "drive", "discrepancy") and conf >= 0.6 and now - (self.sm.s.get("last_owner_ts") or 0) > 3600:
            self._append(self.outbox, {"ts": now, "kind": win["kind"], "text": text, "pred_id": pid})
        return {"status": "thought", "text": text, "conf": conf, "pred_id": pid, "focus": win["key"]}

    def feedback(self, pred_id, ok):
        """Оценка владельца (кнопки 👍/👎) закрывает прогноз уверенности -> калибровка."""
        return self.sm.resolve(pred_id, ok)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--daemon", action="store_true")
    ap.add_argument("--interval", type=float, default=300.0)
    ap.add_argument("--dry-run", action="store_true", help="не звать LLM и не писать журнал: показать, что было бы")
    a = ap.parse_args(argv)
    sm = LiveSelfModel()
    ws = Workspace()
    claimed = os.environ.get("NOX_CLAIMED_TEXT", "быстрый ответ — Qwen3.5-9B; глубокий — GLM-5.3")
    llm = http_llm()
    if a.dry_run:
        llm = lambda m, n, t: "Мысль: (dry-run) %s\nУверенность: 50%%" % m[-1]["content"][:40]
    lp = InnerLoop(ws, sm, llm, chat_busy=make_chat_busy(), claimed_text=claimed,
                   journal_path=os.devnull if a.dry_run else None, outbox_path=os.devnull if a.dry_run else None)
    print(json.dumps(sm.wake() if not a.dry_run else {"dry_run": True}, ensure_ascii=False))
    while True:
        print(json.dumps(lp.step(), ensure_ascii=False), flush=True)
        if a.once or not a.daemon:
            break
        time.sleep(a.interval)


if __name__ == "__main__":
    main()
