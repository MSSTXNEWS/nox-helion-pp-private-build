"""R2/curiosity.py: единые порты данных между процессами (правило «один писатель на файл состояния»).

  drives.json        пишет только EMO (affect_loop). Остальные процессы шлют наблюдения в очередь FeedDrives -> EMO вызывает drain_feed().
  growth.json        пишет только процесс growth. Ядро шлёт исходы жизни и закрытые пробелы в GrowthInbox -> growth.session() начинает с drain().
  Источники любопытства (drives.observe): РОВНО два пространства имён, чтобы не считать одно и то же дважды:
    gr:<область>   Growth (ячейка/область, 1-score) - единственный источник «любопытства по прогрессу» для учёбы;
    pe:<тип хода>  predictive_self (удивление на ходах диалога), агрегировано раз в период (CuriosityHub), а не на каждый ход.
  drives.observe напрямую из других мест не вызывается.
"""
import json
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(_HERE, "..", "..", "COMMON"), os.environ.get("NOX_COMMON", "")):
    if _p and os.path.isdir(_p) and _p not in sys.path:
        sys.path.append(_p)
import statefile


def _jl(path):
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            for l in f:
                l = l.strip()
                if l:
                    try:
                        out.append(json.loads(l))
                    except ValueError:
                        pass
    except OSError:
        pass
    return out


def _drain_lines(path):
    """Атомарно забрать все строки очереди и очистить файл."""
    if not os.path.exists(path):
        return []
    with statefile.locked(path):
        rows = _jl(path)
        with open(path, "w", encoding="utf-8"):
            pass
    return rows


# ------------------------------------------------------------------ очередь к EMO
class FeedDrives:
    """Drives-подобный прокси для процессов, не владеющих drives.json: observe/satisfy -> очередь; level читается из файла (только чтение)."""

    def __init__(self, drives_path, feed_path=None, clock=time.time):
        self.path, self.feed, self.clock = drives_path, feed_path or drives_path + ".feed.jsonl", clock

    @property
    def level(self):
        d = statefile.load(self.path, {}) or {}
        return dict(d.get("level") or {})

    def observe(self, topic, err):
        statefile.append_line(self.feed, json.dumps({"op": "observe", "topic": str(topic), "err": max(0.0, min(1.0, float(err))), "t": self.clock()}, ensure_ascii=False))
        return {}

    def satisfy(self, drive, amount=0.5):
        statefile.append_line(self.feed, json.dumps({"op": "satisfy", "drive": drive, "amount": float(amount), "t": self.clock()}, ensure_ascii=False))
        return None


def drain_feed(drives, feed_path):
    """Вызывает владелец drives.json (EMO) перед tick(). -> {observe: n, satisfy: m}."""
    n = {"observe": 0, "satisfy": 0}
    for r in _drain_lines(feed_path):
        try:
            if r.get("op") == "observe":
                drives.observe(r["topic"], r["err"])
                n["observe"] += 1
            elif r.get("op") == "satisfy":
                drives.satisfy(r["drive"], r["amount"])
                n["satisfy"] += 1
        except Exception:
            pass
    if n["observe"] or n["satisfy"]:
        try:
            drives.save()
        except Exception:
            pass
    return n


# ------------------------------------------------------------------ любопытство ходов диалога
class CuriosityHub:
    """predictive_self -> drives: удивление по типу хода копится и уходит в drives.observe('pe:<ctx>', среднее) не чаще раза в period_s."""

    def __init__(self, sink, clock=time.time, period_s=3600.0):
        self.sink, self.clock, self.period = sink, clock, period_s
        self.buf, self.last_flush = {}, None
        self.ledger = {}

    def feed(self, ctx, surprise, src="predictive"):
        t = "pe:" + str(ctx)
        self.buf.setdefault(t, []).append(max(0.0, min(1.0, float(surprise))))
        self.ledger[src] = self.ledger.get(src, 0) + 1

    def flush(self, now=None, force=False):
        now = self.clock() if now is None else now
        if not self.buf:
            return []
        if not force and self.last_flush is not None and now - self.last_flush < self.period:
            return []
        out = []
        for t, xs in sorted(self.buf.items()):
            m = sum(xs) / len(xs)
            try:
                self.sink(t, m)
                out.append((t, round(m, 4), len(xs)))
            except Exception:
                pass
        self.buf, self.last_flush = {}, now
        return out


# ------------------------------------------------------------------ почтовый ящик Growth
class GrowthInbox:
    def __init__(self, path, clock=time.time):
        self.path, self.clock = path, clock

    def post_ingest(self, area, score, src="rule", ref=""):
        statefile.append_line(self.path, json.dumps({"op": "ingest", "area": area, "score": float(score), "src": src, "ref": ref, "t": self.clock()}, ensure_ascii=False))

    def post_lesson(self, area, question, quote, url=""):
        statefile.append_line(self.path, json.dumps({"op": "lesson", "area": area, "question": question, "quote": quote, "url": url, "t": self.clock()}, ensure_ascii=False))

    def drain(self, growth, now=None):
        """Вызывает процесс growth (единственный писатель growth.json). -> счётчики."""
        n = {"ingest": 0, "lesson": 0, "lesson_failed": 0, "errors": 0}
        for r in _drain_lines(self.path):
            try:
                if r.get("op") == "ingest":
                    growth.ingest(r["area"], r["score"], r.get("src", "rule"), now=r.get("t") if now is None else now, ref=r.get("ref", ""))
                    n["ingest"] += 1
                elif r.get("op") == "lesson":
                    res = growth.learn_from_resolved(r["area"], r["question"], r["quote"], r.get("url", ""), now=now)
                    n["lesson" if res.get("ok") else "lesson_failed"] += 1
            except Exception:
                n["errors"] += 1
        return n

    def pending(self):
        return len(_jl(self.path))
