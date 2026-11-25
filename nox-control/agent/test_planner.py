import datetime as dt, json, os, tempfile, unittest
from ._testutil import mkcfg, touch
from .planner import Planner, to_epoch
from .tools.approvals import Approvals


def jl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows: f.write(json.dumps(r, ensure_ascii=False) + "\n")


class TestPlanner(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cfg = mkcfg(self.tmp, NOX_AGENT_CALENDAR=os.path.join(self.tmp, "cal.jsonl"))
        self.p = Planner(self.cfg)

    def test_reads_inbox_and_kanban_formats_in_priority_order(self):
        jl(self.cfg.inbox, [{"id": "hb-1", "class": "owner_order", "handler": "track", "title": "Бэкап", "status": "pending", "ts": "2026-11-20T10:00:00"},
                            {"id": "o2", "class": "owner_order", "handler": "selfbuild", "title": "Срочно чинить", "status": "pending", "priority": "high", "ts": "2026-11-21T10:00:00"},
                            {"id": "o3", "title": "уже готово", "status": "done"}])
        jl(self.cfg.queue, [{"id": "k1", "title": "из канбана", "status": "queued", "ts": 1.0e9}, {"id": "k2", "title": "в работе", "status": "running"}])
        ts = self.p.tasks()
        self.assertEqual([t["id"] for t in ts], ["o2", "k1", "hb-1"])
        self.assertEqual(self.p.next()["id"], "o2")
        self.assertEqual(self.p.next(accept=lambda t: t["source"] == "kanban")["id"], "k1")
        with open(self.cfg.inbox, encoding="utf-8") as f: self.assertEqual(f.read().count("\n"), 3)    # источник не изменён

    def test_same_task_id_from_two_sources_keeps_global_highest_priority(self):
        jl(self.cfg.inbox, [
            {"id": "shared", "title": "old inbox", "status": "pending", "priority": "low", "ts": 1},
            {"id": "normal", "title": "other task", "status": "pending", "priority": "normal", "ts": 2},
        ])
        jl(self.cfg.queue, [
            {"id": "shared", "title": "updated kanban", "status": "queued", "priority": "high", "ts": 3},
        ])
        tasks = self.p.tasks()
        self.assertEqual([t["id"] for t in tasks], ["shared", "normal"])
        self.assertEqual(tasks[0]["source"], "kanban")
        self.assertEqual(self.p.next()["id"], "shared")
        self.p.mark("shared", "done")
        self.assertEqual(self.p.next()["id"], "normal")
        self.assertEqual(len([t for t in self.p.tasks() if t["id"] == "shared"]), 1)

    def test_dispatcher_non_open_state_vetoes_stale_inbox_copy(self):
        jl(self.cfg.inbox, [
            {"id": "busy", "title": "stale", "status": "pending", "priority": "P0"},
            {"id": "closed", "title": "stale", "status": "pending", "priority": "P0"},
            {"id": "fresh", "title": "eligible", "status": "pending", "priority": "P1"},
        ])
        jl(self.cfg.queue, [
            {"id": "busy", "status": "running"},
            {"id": "closed", "status": "done"},
        ])
        self.assertEqual([t["id"] for t in self.p.tasks()], ["fresh"])
        self.assertEqual(self.p.next()["id"], "fresh")
        # A genuinely requeued task is visible again; the filter is not a claim.
        jl(self.cfg.queue, [{"id": "busy", "status": "queued"}, {"id": "closed", "status": "done"}])
        self.assertEqual(self.p.next()["id"], "busy")

    def test_original_p0_p1_priority_labels_keep_order(self):
        jl(self.cfg.inbox, [
            {"id": "p1", "title": "later", "status": "pending", "priority": "P1", "ts": 1},
            {"id": "p0", "title": "critical", "status": "pending", "priority": "P0", "ts": 2},
        ])
        self.assertEqual([t["id"] for t in self.p.tasks()], ["p0", "p1"])

    def test_state_overlay_and_retries(self):
        jl(self.cfg.inbox, [{"id": "a", "title": "t1", "status": "pending", "ts": 1}, {"id": "b", "title": "t2", "status": "pending", "ts": 2}])
        self.p.mark("a", "running"); self.p.mark("a", "interrupted")
        self.assertEqual(self.p.next()["id"], "a")
        self.p.mark("a", "running"); self.p.mark("a", "failed", note="x")
        self.assertEqual(self.p.next()["id"], "b")
        self.p.mark("b", "done")
        self.assertIsNone(self.p.next())
        for _ in range(3): self.p.mark("a", "running")
        self.p.mark("a", "interrupted")
        self.assertIsNone(self.p.next())           # попытки исчерпаны (NOX_AGENT_TASK_RETRIES=2)

    def test_awaiting_owner_resume(self):
        jl(self.cfg.inbox, [{"id": "d", "title": "удалить старое", "status": "pending", "ts": 1}])
        ap = Approvals(self.cfg.approvals_file)
        g = ap.gate("task:удаление", "d: x")
        self.p.mark("d", "awaiting_owner", approval_id=g["id"], stage="start")
        self.assertIsNone(self.p.next())
        ap.decide(g["id"], "approved")
        t = self.p.next()
        self.assertTrue(t["resume"]); self.assertEqual(t["stage"], "start")
        # отказ закрывает задачу
        self.p.mark("d", "awaiting_owner", approval_id=g["id"])
        g2 = ap.gate("task:удаление", "d2")
        self.p.mark("d", "awaiting_owner", approval_id=g2["id"]); ap.decide(g2["id"], "denied")
        self.assertIsNone(self.p.next()); self.assertEqual(self.p.state()["d"]["status"], "failed")

    def test_calendar_tasks_and_reminders(self):
        now = to_epoch("2026-11-22T09:05")
        jl(self.cfg.calendar, [{"id": "e1", "title": "Проверить логи", "start": "2026-11-22T09:00", "task": True, "remind_before_min": [30, 0]},
                               {"id": "e2", "title": "Созвон", "start": "2026-11-22T10:00", "remind_before_min": [10]},
                               {"id": "e3", "title": "Ежедневный отчёт", "start": "2026-11-01T08:00", "repeat": "daily", "task": True},
                               {"id": "e4", "title": "Будущая", "start": "2026-12-30T08:00", "task": True}])
        ids = [t["id"] for t in self.p.tasks(now)]
        self.assertIn("cal-e1-202611220900", ids); self.assertIn("cal-e3-202611220800", ids)
        self.assertFalse([i for i in ids if "e2" in i or "e4" in i])
        self.p.mark("cal-e1-202611220900", "done")
        self.assertNotIn("cal-e1-202611220900", [t["id"] for t in self.p.tasks(now) if t["status"] == "pending"])
        made = self.p.sync_calendar(now)
        self.assertEqual(len(made), 4)               # e1: 2, e2: 1, e3: завтрашний старт 08:00 (сегодняшний уже старше часа)
        self.assertEqual(self.p.sync_calendar(now), [])          # идемпотентно
        due = self.p.due_reminders(now)
        texts = sorted(r["text"] for r in due)
        self.assertIn("Сейчас: Проверить логи", texts); self.assertIn("Через 30 мин: Проверить логи", texts)
        self.assertNotIn("Через 10 мин: Созвон", texts)          # 09:50 ещё не наступило
        self.assertEqual(self.p.due_reminders(now), [])          # выдаются один раз
        later = self.p.due_reminders(to_epoch("2026-11-22T09:55"))
        self.assertEqual([r["text"] for r in later], ["Через 10 мин: Созвон"])

    def test_remind_manual_and_tick(self):
        r = self.p.remind("позвонить", "2026-11-22T12:00", task_id="x")
        self.assertIsNone(self.p.remind("позвонить", "2026-11-22T12:00", task_id="x"))
        self.assertEqual(self.p.tick(to_epoch("2026-11-22T11:59")), [])
        self.assertEqual(self.p.tick(to_epoch("2026-11-22T12:01"))[0]["id"], r["id"])
        with self.assertRaises(ValueError): self.p.remind("x", "не время")

    def test_report_and_digest(self):
        t = {"id": "o2", "title": "Починить шлюз"}
        txt = self.p.report(t, {"status": "merged", "summary": "добавлен health", "branch": "nox/x", "tests": {"ok": True, "ran": 5, "failures": 0, "errors": 0},
                                "judge": {"ok": True, "reasons": ["чисто"]}, "seconds": 12.3, "tokens": 999})
        for s in ("Починить шлюз", "merged", "nox/x", "зелёные", "Судья: ok", "999"): self.assertIn(s, txt)
        r2 = self.p.report({"id": "q", "title": "Удалить"}, {"status": "awaiting_owner", "approval_id": "ap-1"})
        self.assertIn("approve ap-1", r2)
        self.assertIn("выполнено отчётов 2", self.p.digest())

    def test_occurrences(self):
        ev = {"start": "2026-11-20T08:00", "repeat": "weekly"}
        self.assertEqual(len(Planner.occurrences(ev, to_epoch("2026-11-19T00:00"), to_epoch("2026-12-05T00:00"))), 3)
        self.assertEqual(Planner.occurrences({"start": "bad"}, 0, 9e9), [])


if __name__ == "__main__":
    unittest.main()
