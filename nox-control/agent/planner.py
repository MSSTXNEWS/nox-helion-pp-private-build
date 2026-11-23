"""Планировщик (шаг 39): канбан и календарь как источник задач, напоминания, отчёт после выполнения. Только stdlib.
Источники (читаются, чужие файлы НЕ меняются):
  - owner_inbox.jsonl  : {"id","class","handler","title","status":"pending","ts", [priority],[due],[body]}   (формат community/heartbeat_md.to_task)
  - queue.jsonl        : очередь диспетчера (selftools/task_board): status "queued"
  - календарь JSONL    : {"id","title","start":"2026-11-22T09:00","duration_min":30,"remind_before_min":[10],"repeat":"none|daily|weekly","task":true,"body":""}
                         событие с "task": true в момент старта становится задачей; любое событие даёт напоминания.
Статусы задач ведёт собственный файл task_state.jsonl (дозапись), в источники ничего не пишется."""
import datetime as dt, hashlib, json, os, sys, time
from .config import Config
from .tools.approvals import Approvals

PRIO = {"p0": 0, "p1": 1, "p2": 2, "high": 0, "urgent": 0, "срочно": 0, "высокий": 0, "normal": 1, "обычный": 1, "low": 2, "низкий": 2}
OPEN = ("pending", "interrupted")


def _read_jsonl(path):
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            for l in f:
                l = l.strip()
                if l:
                    try:
                        o = json.loads(l)
                        if isinstance(o, dict): out.append(o)
                    except ValueError:
                        pass
    except (FileNotFoundError, IsADirectoryError):
        pass
    return out


def _append(path, rec):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def to_epoch(v):
    if v is None or v == "": return None
    if isinstance(v, (int, float)): return float(v)
    try: return dt.datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp()
    except ValueError: return None


def _prio(v):
    if isinstance(v, (int, float)): return int(v)
    return PRIO.get(str(v or "normal").strip().lower(), 1)


class Planner:
    def __init__(self, cfg=None, approvals=None):
        self.cfg = cfg or Config()
        self.approvals = approvals or Approvals(self.cfg.approvals_file)

    # ---- состояние
    def state(self):
        st = {}
        for r in _read_jsonl(self.cfg.task_state):
            if r.get("id"): st.setdefault(r["id"], {}).update(r)
        return st

    def mark(self, task_id, status, **fields):
        rec = dict(id=task_id, status=status, ts=time.time(), **fields)
        if status == "running": rec["attempts"] = self.state().get(task_id, {}).get("attempts", 0) + 1
        _append(self.cfg.task_state, rec)
        return rec

    # ---- источники
    def _norm(self, r, source, status_map):
        title = r.get("title") or r.get("text") or r.get("name") or ""
        tid = str(r.get("id") or hashlib.sha1((source + title).encode()).hexdigest()[:10])
        st = status_map.get(str(r.get("status", "pending")).lower())
        if st is None: return None
        return {"id": tid, "title": title, "body": r.get("body") or r.get("description") or r.get("details") or "", "priority": _prio(r.get("priority")),
                "due": to_epoch(r.get("due")), "ts": to_epoch(r.get("ts")) or 0, "source": source, "status": st, "class": r.get("class"), "handler": r.get("handler"),
                "selfbuild": bool(r.get("selfbuild")), "raw": r}

    def _calendar_tasks(self, now):
        out = []
        for ev in _read_jsonl(self.cfg.calendar):
            if not ev.get("task"): continue
            for start in self.occurrences(ev, now - 86400, now):
                tid = "cal-%s-%s" % (ev.get("id") or hashlib.sha1((ev.get("title") or "").encode()).hexdigest()[:8], dt.datetime.fromtimestamp(start).strftime("%Y%m%d%H%M"))
                out.append({"id": tid, "title": ev.get("title", ""), "body": ev.get("body", ""), "priority": _prio(ev.get("priority")), "due": start, "ts": start,
                            "source": "calendar", "status": "pending", "class": "calendar", "handler": ev.get("handler"), "selfbuild": bool(ev.get("selfbuild")), "raw": ev})
        return out

    @staticmethod
    def occurrences(ev, lo, hi):
        """Моменты старта события в (lo, hi]: none/daily/weekly."""
        s = to_epoch(ev.get("start"))
        if s is None: return []
        rep = str(ev.get("repeat") or "none").lower()
        step = {"daily": 86400, "weekly": 7 * 86400}.get(rep)
        if not step: return [s] if lo < s <= hi else []
        out = []
        d0 = dt.datetime.fromtimestamp(s)
        k = max(int((lo - s) // step), 0)
        while True:
            t = (d0 + dt.timedelta(seconds=step * k)).timestamp()      # локальное время: сдвиг по календарным суткам
            if t > hi: break
            if t > lo: out.append(t)
            k += 1
        return out

    def tasks(self, now=None):
        now = time.time() if now is None else now
        st = self.state()
        items = []
        for r in _read_jsonl(self.cfg.inbox):
            t = self._norm(r, "inbox", {"pending": "pending", "queued": "pending", "new": "pending"})
            if t: items.append(t)
        for r in _read_jsonl(self.cfg.queue):
            t = self._norm(r, "kanban", {"queued": "pending", "pending": "pending"})
            if t: items.append(t)
        items += self._calendar_tasks(now)
        # Existing inbox/kanban may refer to the same TaskID. Rank candidates
        # before ID deduplication so an earlier low-priority copy cannot hide
        # the higher-priority one. This does not create or claim any native job.
        items.sort(key=lambda t: (t["priority"], t["due"] if t["due"] is not None else 9e18, t["ts"]))
        seen, out = set(), []
        for t in items:
            if t["id"] in seen: continue
            seen.add(t["id"])
            s = st.get(t["id"])
            if s:
                t["status"] = s.get("status", t["status"]); t["attempts"] = s.get("attempts", 0)
                for k in ("approval_id", "stage", "branch", "note"):
                    if s.get(k) is not None: t[k] = s[k]
            else: t["attempts"] = 0
            out.append(t)
        out.sort(key=lambda t: (t["priority"], t["due"] if t["due"] is not None else 9e18, t["ts"]))
        return out

    def next(self, now=None, accept=None):
        """Следующая задача: pending/interrupted (с учётом числа попыток), либо awaiting_owner, если владелец уже решил.
        Отклонённые владельцем закрываются (failed)."""
        reqs = {r["id"]: r for r in self.approvals.requests()}
        for t in self.tasks(now):
            if accept and not accept(t): continue
            if t["status"] in OPEN and t["attempts"] <= self.cfg.task_retries: return t
            if t["status"] == "awaiting_owner":
                ap = reqs.get(t.get("approval_id"))
                if ap and ap["state"] == "approved": t["resume"] = True; return t
                if ap and ap["state"] == "denied": self.mark(t["id"], "failed", note="владелец отклонил %s" % ap.get("action"))
        return None

    # ---- напоминания
    def remind(self, text, at, task_id=None, rid=None):
        at = to_epoch(at)
        if at is None: raise ValueError("нужно время напоминания (ISO или epoch)")
        rid = rid or "rem-%d-%s" % (int(at), hashlib.sha1(text.encode()).hexdigest()[:6])
        if any(r.get("id") == rid for r in _read_jsonl(self.cfg.reminders)): return None
        rec = {"id": rid, "at": at, "text": text, "task_id": task_id, "status": "pending"}
        _append(self.cfg.reminders, rec)
        return rec

    def sync_calendar(self, now=None, horizon_h=24):
        """События календаря на ближайшие horizon_h часов -> напоминания (идемпотентно)."""
        now = time.time() if now is None else now
        made = []
        for ev in _read_jsonl(self.cfg.calendar):
            before = ev.get("remind_before_min", [0] if ev.get("task") else [10])
            for start in self.occurrences(ev, now - 3600, now + horizon_h * 3600):
                for m in (before if isinstance(before, list) else [before]):
                    when = start - float(m) * 60
                    rid = "calrem-%s-%d-%s" % (ev.get("id") or "ev", int(start), m)
                    txt = "%s: %s" % ("Сейчас" if not m else "Через %s мин" % m, ev.get("title", ""))
                    r = self.remind(txt, when, task_id=ev.get("id"), rid=rid)
                    if r: made.append(r)
        return made

    def due_reminders(self, now=None):
        """Сработавшие и ещё не выданные напоминания; помечает выданными."""
        now = time.time() if now is None else now
        recs = _read_jsonl(self.cfg.reminders)
        fired = {r["id"] for r in recs if r.get("status") == "fired"}
        out = []
        for r in recs:
            if r.get("status") == "pending" and r["id"] not in fired and r.get("at", 9e18) <= now:
                out.append(r); fired.add(r["id"])
                _append(self.cfg.reminders, {"id": r["id"], "status": "fired", "fired_at": now})
        return out

    def tick(self, now=None):
        self.sync_calendar(now)
        return self.due_reminders(now)

    # ---- отчёт
    def report(self, task, result):
        """Отчёт после выполнения: текст + запись в reports.jsonl; результат selfbuild/loop (dict) в виде кратких фактов."""
        status = result.get("status", "?")
        lines = ["Задача %s: %s" % (task.get("id"), task.get("title", "")), "Итог: %s" % status]
        if result.get("summary"): lines.append("Что сделано: %s" % str(result["summary"])[:600])
        if result.get("branch"): lines.append("Ветка: %s" % result["branch"])
        t = result.get("tests")
        if isinstance(t, dict): lines.append("Тесты: %s (запущено %s, провалов %s, ошибок %s)" % ("зелёные" if t.get("ok") else "красные", t.get("ran"), t.get("failures"), t.get("errors")))
        j = result.get("judge")
        if isinstance(j, dict): lines.append("Судья: %s%s" % ("ok" if j.get("ok") else "не одобрил", ("; " + "; ".join(map(str, j.get("reasons") or []))[:300]) if j.get("reasons") else ""))
        if result.get("reason"): lines.append("Причина: %s" % str(result["reason"])[:300])
        if result.get("approval_id"): lines.append("Ждёт владельца: approval %s (python3 -m agent.tools.approvals approve %s)" % (result["approval_id"], result["approval_id"]))
        if "seconds" in result or "tokens" in result: lines.append("Расход: %s с, %s ток." % (result.get("seconds"), result.get("tokens")))
        text = "\n".join(lines)
        _append(self.cfg.reports, {"ts": time.time(), "task_id": task.get("id"), "status": status, "text": text})
        return text

    def digest(self, since=None):
        since = since if since is not None else time.time() - 86400
        rs = [r for r in _read_jsonl(self.cfg.reports) if r.get("ts", 0) >= since]
        pend = self.approvals.pending()
        head = "За период: выполнено отчётов %d; ждут владельца: %d" % (len(rs), len(pend))
        return "\n\n".join([head] + [r["text"] for r in rs] + ["Ждёт подтверждения: %s (%s)" % (p["id"], p["action"]) for p in pend])


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="agent.planner")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list"); sub.add_parser("next"); sub.add_parser("tick"); sub.add_parser("digest")
    r = sub.add_parser("remind"); r.add_argument("at"); r.add_argument("text")
    a = ap.parse_args(argv)
    p = Planner()
    if a.cmd == "list":
        for t in p.tasks(): print("%s\t%s\t%s\t%s" % (t["id"], t["status"], t["source"], t["title"][:100]))
    elif a.cmd == "next":
        t = p.next(); print(json.dumps({k: v for k, v in (t or {}).items() if k != "raw"}, ensure_ascii=False) if t else "нет задач")
    elif a.cmd == "tick":
        for x in p.tick(): print(x["text"])
    elif a.cmd == "digest": print(p.digest())
    elif a.cmd == "remind":
        print(p.remind(a.text, a.at))
    return 0


if __name__ == "__main__":
    sys.exit(main())
