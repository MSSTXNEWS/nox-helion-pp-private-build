import json, os, sys, tempfile, unittest
from datetime import datetime as D
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from community.heartbeat_md import parse_line, parse_text, Scheduler, to_task, latest_occurrence


class P(unittest.TestCase):
    def test_daily(self):
        r = parse_line("каждый день в 9:00 напомни про отчёт")
        self.assertEqual((r.kind, r.time, r.title), ("daily", (9, 0), "напомни про отчёт"))

    def test_weekly(self):
        r = parse_line("по пятницам в 18:00 проверь бэкапы")
        self.assertEqual((r.kind, r.weekdays, r.time, r.title), ("weekly", [4], (18, 0), "проверь бэкапы"))
        r = parse_line("по понедельникам и средам в 7 вечера сделай обзор")
        self.assertEqual((r.weekdays, r.time), ([0, 2], (19, 0)))
        self.assertEqual(parse_line("по будням в 8:30 зарядка").weekdays, [0, 1, 2, 3, 4])
        self.assertEqual(parse_line("по выходным в 11 утра отдых").weekdays, [5, 6])
        self.assertEqual(parse_line("каждый вторник в 8.15 проверь почту").weekdays, [1])
        self.assertEqual(parse_line("каждую среду в 12:00 обед").weekdays, [2])

    def test_interval(self):
        r = parse_line("каждые 2 часа проверь диск")
        self.assertEqual((r.kind, r.interval_s, r.title), ("interval", 7200, "проверь диск"))
        self.assertEqual(parse_line("каждый час проверь сеть").interval_s, 3600)
        self.assertEqual(parse_line("каждые 15 минут пингуй шлюз").interval_s, 900)
        self.assertEqual(parse_line("раз в 3 часа пей воду").interval_s, 10800)

    def test_once(self):
        r = parse_line("через 30 минут напомни выключить плиту")
        self.assertEqual((r.kind, r.interval_s, r.title), ("once", 1800, "напомни выключить плиту"))
        self.assertEqual(parse_line("через полчаса напомни про чай").interval_s, 1800)
        self.assertEqual(parse_line("через час позвони").interval_s, 3600)

    def test_monthly_english(self):
        r = parse_line("1 числа каждого месяца в 10:00 сделай отчёт")
        self.assertEqual((r.kind, r.day_of_month, r.time), ("monthly", 1, (10, 0)))
        r = parse_line("every day at 7:45 check mail")
        self.assertEqual((r.kind, r.time, r.title), ("daily", (7, 45), "check mail"))
        self.assertEqual(parse_line("every 2 hours check disk").interval_s, 7200)
        self.assertEqual(parse_line("in 10 minutes call mom").kind, "once")

    def test_bad(self):
        for t in ["каждый день в 25:00 что-то", "просто заметка без времени", "каждый день в 9:00", "через 0 минут сделай"]:
            with self.assertRaises(ValueError, msg=t): parse_line(t)

    def test_parse_text(self):
        txt = "# Заголовок\n\n- каждый день в 9:00 напомни про отчёт\n- [ ] по пятницам в 18:00 проверь бэкапы\n<!-- - каждый день в 1:00 скрыто -->\n- бред какой-то\n- каждый день в 9:00 напомни про отчёт\nобычная проза\n"
        rules, errs = parse_text(txt)
        self.assertEqual(len(rules), 2); self.assertEqual(len(errs), 1); self.assertEqual(errs[0][0], 6)


class S(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.sp = os.path.join(self.d, "st.json")

    def test_occurrence(self):
        r = parse_line("по пятницам в 18:00 x")
        self.assertEqual(latest_occurrence(r, D(2026, 11, 21, 12, 0)), D(2026, 11, 20, 18, 0))  # 21.11.2026 - суббота
        self.assertEqual(latest_occurrence(r, D(2026, 11, 20, 17, 59)), D(2026, 11, 13, 18, 0))
        m = parse_line("31 числа каждого месяца в 10:00 x")
        self.assertEqual(latest_occurrence(m, D(2026, 11, 30, 12, 0)), D(2026, 11, 30, 10, 0))

    def test_daily_flow(self):
        r = parse_line("каждый день в 9:00 напомни про отчёт")
        s = Scheduler([r], self.sp)
        self.assertEqual(s.due(D(2026, 11, 21, 8, 0)), [])        # первый запуск: прошлое не срабатывает
        self.assertEqual(s.due(D(2026, 11, 21, 8, 59)), [])
        self.assertEqual(s.due(D(2026, 11, 21, 9, 0)), [r])
        s.mark_fired(r, D(2026, 11, 21, 9, 0))
        self.assertEqual(s.due(D(2026, 11, 21, 15, 0)), [])
        self.assertEqual(s.due(D(2026, 11, 22, 9, 1)), [r])

    def test_state_persists(self):
        r = parse_line("каждый день в 9:00 x")
        s = Scheduler([r], self.sp); s.due(D(2026, 11, 21, 8, 0)); s.mark_fired(r, D(2026, 11, 21, 9, 0))
        s2 = Scheduler([r], self.sp)
        self.assertEqual(s2.due(D(2026, 11, 21, 10, 0)), [])
        self.assertEqual(s2.due(D(2026, 11, 22, 10, 0)), [r])

    def test_missed_collapse(self):
        r = parse_line("каждый день в 9:00 x")
        s = Scheduler([r], self.sp); s.due(D(2026, 11, 1, 0, 0))
        self.assertEqual(len(s.due(D(2026, 11, 20, 10, 0))), 1)
        s.mark_fired(r, D(2026, 11, 20, 10, 0)); self.assertEqual(s.due(D(2026, 11, 20, 10, 5)), [])

    def test_interval(self):
        r = parse_line("каждые 2 часа проверь диск")
        s = Scheduler([r], self.sp); s.due(D(2026, 11, 21, 10, 0))
        self.assertEqual(s.due(D(2026, 11, 21, 11, 59)), [])
        self.assertEqual(s.due(D(2026, 11, 21, 12, 0)), [r])
        s.mark_fired(r, D(2026, 11, 21, 12, 0))
        self.assertEqual(s.due(D(2026, 11, 21, 13, 0)), []); self.assertEqual(s.due(D(2026, 11, 21, 14, 0)), [r])

    def test_once_fires_once(self):
        r = parse_line("через 30 минут напомни позвонить")
        s = Scheduler([r], self.sp); s.due(D(2026, 11, 21, 10, 0))
        self.assertEqual(s.due(D(2026, 11, 21, 10, 29)), [])
        self.assertEqual(s.due(D(2026, 11, 21, 10, 30)), [r])
        s.mark_fired(r, D(2026, 11, 21, 10, 31))
        self.assertEqual(s.due(D(2026, 11, 22, 10, 0)), [])
        self.assertEqual(Scheduler([r], self.sp).due(D(2026, 11, 23, 10, 0)), [])

    def test_weekly(self):
        r = parse_line("по пятницам в 18:00 проверь бэкапы")
        s = Scheduler([r], self.sp); s.due(D(2026, 11, 19, 10, 0))
        self.assertEqual(s.due(D(2026, 11, 20, 17, 0)), [])
        self.assertEqual(s.due(D(2026, 11, 20, 18, 0)), [r])

    def test_task_and_inbox(self):
        r = parse_line("каждый день в 9:00 напомни про отчёт")
        t = to_task(r, D(2026, 11, 21, 9, 0, 5))
        self.assertEqual((t["class"], t["handler"], t["status"], t["title"]), ("owner_order", "track", "pending", "напомни про отчёт"))
        self.assertTrue(t["id"].startswith("hb-")); self.assertEqual(t["ts"], "2026-11-21T09:00:05")
        inbox = os.path.join(self.d, "sub", "owner_inbox.jsonl")
        s = Scheduler([r], self.sp); s.due(D(2026, 11, 21, 8, 0))
        tasks = s.fire_due(D(2026, 11, 21, 9, 1), inbox)
        self.assertEqual(len(tasks), 1)
        rows = [json.loads(l) for l in open(inbox, encoding="utf-8")]
        self.assertEqual(rows, tasks)
        self.assertEqual(s.fire_due(D(2026, 11, 21, 9, 2), inbox), [])
        self.assertEqual(len(open(inbox, encoding="utf-8").readlines()), 1)


if __name__ == "__main__":
    unittest.main()
