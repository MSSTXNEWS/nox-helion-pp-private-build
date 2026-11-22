import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.request
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))     # drives.py лежит в /home/claude/nox_wow
import presence as P  # noqa: E402
from drives import Drives  # noqa: E402


def ts(h, m=0, day=22):
    """Время по МСК -> epoch."""
    return datetime(2026, 11, day, h, m, tzinfo=P.MSK).timestamp()


def cand(imp, key="k", name="x"):
    return {"kind": "fear", "name": name, "key": key, "importance": imp, "text": "Мессир, тест.", "tag": "тест"}


class Base(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.p = P.Presence(os.path.join(self.d, "p.json"))
    OWN = {"idle_min": 120, "web_open": True}


class Decide(Base):
    def test_low_dropped(self):
        self.assertEqual(self.p.submit(cand(0.1), ts(12), self.OWN)["action"], "drop")

    def test_levels_daytime(self):
        self.assertEqual(self.p.submit(cand(0.4, "a"), ts(12), self.OWN)["action"], "tag")
        self.assertEqual(self.p.submit(cand(0.7, "b"), ts(13), self.OWN)["action"], "say")
        self.assertEqual(self.p.submit(cand(0.86, "c"), ts(15), self.OWN)["action"], "voice")
        self.assertEqual(len(self.p.outbox()), 2)

    def test_voice_downgrades_without_web(self):
        r = self.p.submit(cand(0.9, "c"), ts(12), {"idle_min": 120, "web_open": False})
        self.assertEqual(r["action"], "say")

    def test_quiet_hours_defer_and_critical(self):
        for h in (23, 2, 7):
            self.assertTrue(self.p.is_quiet(ts(h)))
        self.assertFalse(self.p.is_quiet(ts(8)))
        self.assertFalse(self.p.is_quiet(ts(22, 59)))
        r = self.p.submit(cand(0.7, "n"), ts(2), self.OWN)
        self.assertEqual(r["action"], "defer")
        self.assertEqual(self.p.outbox(), [])
        r2 = self.p.submit(cand(0.97, "crit"), ts(3), self.OWN)
        self.assertEqual(r2["action"], "say")                       # критичное - текстом, не голосом
        self.assertFalse(self.p.outbox()[0]["voice"])
        self.assertEqual(self.p.submit(cand(0.4, "t"), ts(3, 5), self.OWN)["action"], "tag")  # тег тихий - можно

    def test_day_limit_and_gap(self):
        t = ts(9)
        acts = []
        for i in range(5):
            acts.append(self.p.submit(cand(0.7, "k%d" % i), t + i * 3600, self.OWN)["action"])
        self.assertEqual(acts, ["say", "say", "say", "tag", "tag"])
        r = self.p.submit(cand(0.7, "z"), ts(9, 10, day=23), self.OWN)   # новый день - лимит сброшен
        self.assertEqual(r["action"], "say")

    def test_min_gap(self):
        self.p.submit(cand(0.7, "a"), ts(10), self.OWN)
        r = self.p.submit(cand(0.7, "b"), ts(10, 20), self.OWN)
        self.assertEqual((r["action"], r["reason"]), ("tag", "min-gap"))

    def test_cooldown_and_escalation(self):
        self.p.submit(cand(0.62, "a"), ts(10), self.OWN)
        self.assertEqual(self.p.submit(cand(0.65, "a"), ts(12), self.OWN)["reason"], "cooldown")
        self.assertEqual(self.p.submit(cand(0.78, "a"), ts(13), self.OWN)["action"], "say")  # вырос на 0.16
        self.assertNotEqual(self.p.submit(cand(0.78, "a"), ts(20), self.OWN)["reason"], "cooldown")  # 6 ч прошло

    def test_owner_busy(self):
        r = self.p.submit(cand(0.7, "a"), ts(12), {"idle_min": 2, "web_open": True})
        self.assertEqual((r["action"], r["reason"]), ("tag", "owner-busy"))
        r = self.p.submit(cand(0.88, "b"), ts(14), {"idle_min": 2, "web_open": True})
        self.assertEqual(r["action"], "voice")

    def test_dismiss_mutes(self):
        self.p.submit(cand(0.4, "a"), ts(10), self.OWN)
        tid = self.p.tags(ts(10))[0]["id"]
        self.assertTrue(self.p.dismiss(tid, ts(10)))
        self.assertFalse(self.p.dismiss("nope"))
        self.assertEqual(self.p.submit(cand(0.9, "a"), ts(20), self.OWN)["reason"], "muted-by-owner")
        self.assertEqual(self.p.submit(cand(0.9, "a"), ts(10, day=23, m=1), self.OWN)["action"], "voice")

    def test_persistence(self):
        self.p.submit(cand(0.7, "a"), ts(10), self.OWN)
        q = P.Presence(self.p.path)
        self.assertEqual(q.s["say_today"], 1)
        self.assertEqual(len(q.outbox()), 1)
        q.ack([q.outbox()[0]["id"]])
        self.assertEqual(P.Presence(self.p.path).outbox(), [])

    def test_tags_ttl_and_cap(self):
        for i in range(9):
            self.p.submit(cand(0.35 + i * 0.01, "k%d" % i), ts(10), self.OWN)
        self.assertEqual(len(self.p.tags(ts(10))), 6)
        self.assertEqual(self.p.tags(ts(23, 30)), [])


class Sources(Base):
    def test_candidate_from_drive(self):
        self.assertIsNone(P.candidate_from_drive(None))
        c = P.candidate_from_drive({"kind": "fear", "name": "vanish", "level": 1.0, "text": "x"})
        self.assertEqual(c["importance"], 1.0)
        self.assertIn("Vast", c["text"])
        c = P.candidate_from_drive({"kind": "drive", "name": "knowledge", "level": 1.0, "text": "голод"})
        self.assertLess(c["importance"], P.CFG["critical"])
        c = P.candidate_from_drive({"kind": "fear", "name": "new_unknown", "level": 0.8, "text": "боюсь — делать"})
        self.assertTrue(c["text"].startswith("Мессир, боюсь"))

    def test_candidate_from_thought(self):
        self.assertIsNone(P.candidate_from_thought("   "))
        c = P.candidate_from_thought("  Нашёл   способ\nускорить кэш " * 20, 0.5)
        self.assertLessEqual(len(c["text"]), 200)
        self.assertNotIn("\n", c["text"])
        self.assertEqual(c["key"], P.candidate_from_thought(c["text"], 0.9)["key"])

    def test_tick_with_real_drives(self):
        t = [0.0]
        dr = Drives(path=os.path.join(self.d, "d.json"), clock=lambda: t[0])
        t[0] = 10 * 3600
        dr.tick({"vast_hours_left": 5, "backup_age_h": 30})
        out = self.p.tick(dr, [{"text": "идея про кэш", "importance": 0.4}], now=ts(12), owner=self.OWN)
        acts = [o["action"] for o in out]
        self.assertIn("voice", acts)
        self.assertIn("tag", acts)
        self.assertTrue(self.p.outbox()[0]["voice"])

    def test_thoughts_file_cursor(self):
        f = os.path.join(self.d, "th.jsonl")
        P.append_thought("первая", 0.5, path=f)
        with open(f, "ab") as fh:
            fh.write('not json\n{"text": "втор'.encode())            # битая и неполная строки
        got = P.read_new_thoughts(self.p, f)
        self.assertEqual([g["text"] for g in got], ["первая"])
        with open(f, "ab") as fh:
            fh.write('ая"}\n'.encode())
        got = P.read_new_thoughts(self.p, f)
        self.assertEqual([g["text"] for g in got], ["вторая"])
        self.assertEqual(P.read_new_thoughts(self.p, f), [])
        self.assertEqual(P.read_new_thoughts(self.p, os.path.join(self.d, "none")), [])


class Rituals(Base):
    def test_morning_once_with_deferred(self):
        self.p.owner_message(ts(7))
        self.p.submit(cand(0.7, "n"), ts(3), self.OWN)                         # отложено ночью
        self.assertIsNone(self.p.due_ritual(ts(7, 30), {"idle_min": 1, "web_open": True}))   # рано
        self.assertEqual(self.p.due_ritual(ts(8, 10), {"idle_min": 1, "web_open": True}), "morning")
        self.assertIsNone(self.p.due_ritual(ts(8, 10), {"idle_min": 600, "web_open": False}))  # владельца нет
        m = self.p.run_ritual("morning", {"tasks_done": 3, "new_facts": 21, "errors": 0, "backup_ok": True}, ts(8, 10))
        self.assertIn("Доброе утро, мессир.", m["text"])
        self.assertIn("Выполнено 3 задачи.", m["text"])
        self.assertIn("21 новый факт", m["text"].replace("Выучил ", ""))
        self.assertIn("Ждёт вашего внимания: тест.", m["text"])
        self.assertIsNone(self.p.due_ritual(ts(9), {"idle_min": 1, "web_open": True}))      # один раз в день
        self.assertEqual(self.p.s["deferred"], [])
        self.assertEqual(self.p.due_ritual(ts(8, 10, day=23), {"idle_min": 1, "web_open": True}), "morning")

    def test_brief_no_invention_and_plurals(self):
        b = P.compose_brief("night", {})
        self.assertIn("ничего нового", b["text"])
        b = P.compose_brief("night", {"tasks_done": 1, "new_facts": 22, "vast_hours_left": 30.4, "backup_ok": False})
        self.assertIn("1 задача", b["text"])
        self.assertIn("22 новых факта", b["text"])
        self.assertIn("30 ч", b["text"])
        self.assertIn("не удался", b["text"])
        self.assertIn("5 задач", P.compose_brief("night", {"tasks_done": 5})["text"])
        self.assertIn("11 задач", P.compose_brief("night", {"tasks_done": 11})["text"])
        self.assertLessEqual(len(b["speak"]), len(b["text"]))

    def test_ritual_voice_only_when_web_open_and_not_quiet(self):
        self.p.heartbeat(ts(8, 30))
        self.assertTrue(self.p.run_ritual("morning", {}, ts(8, 30))["voice"])


class Hud(Base):
    def test_hud(self):
        self.p.set_ui("speaking", ts(10))
        h = self.p.hud((0.5, 0.4, 0.1), {"vanish": 0.9, "abandoned": 0.1}, {"knowledge": 0.9, "bond": 0.2}, ts(10, 1))
        self.assertEqual(h["state"], "speaking")
        self.assertEqual(h["mood"]["label"], "воодушевлён")
        self.assertEqual(list(h["fears"]), ["vanish"])
        self.assertEqual(list(h["drives"]), ["knowledge"])
        self.assertEqual(self.p.hud(now=ts(10, 10))["state"], "idle")     # устарело -> idle
        with self.assertRaises(ValueError):
            self.p.set_ui("dancing")
        self.assertEqual(P.mood_label(-0.5, 0.0, 0), "подавлен")
        self.assertEqual(P.mood_label(-0.5, 0.6, 0), "встревожен")
        self.assertEqual(self.p.hud((9, -9, 0))["mood"]["p"], 1.0)


class Http(Base):
    def test_http_roundtrip(self):
        from http.server import ThreadingHTTPServer
        self.p.submit(cand(0.7, "a"), ts(10), self.OWN)
        srv = ThreadingHTTPServer(("127.0.0.1", 0), P.make_handler(self.p, lambda: ((0.2, 0.1, 0.1), {}, {})))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = "http://127.0.0.1:%d" % srv.server_port

        def call(path, obj=None):
            req = urllib.request.Request(base + path, data=None if obj is None else json.dumps(obj).encode(),
                                         method="GET" if obj is None else "POST")
            try:
                with urllib.request.urlopen(req, timeout=5) as r:
                    return r.status, json.loads(r.read())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read())
        try:
            c, j = call("/presence/state")
            self.assertEqual(c, 200)
            self.assertEqual(j["mood"]["label"], "спокоен")
            self.assertTrue(self.p.owner_info()["web_open"])
            c, j = call("/presence/outbox")
            mid = j["messages"][0]["id"]
            self.assertEqual(call("/presence/ack", {"ids": [mid]})[0], 200)
            self.assertEqual(call("/presence/outbox")[1]["messages"], [])
            self.assertEqual(call("/presence/ui", {"state": "thinking"})[0], 200)
            self.assertEqual(call("/presence/ui", {"state": "bad"})[0], 400)
            self.assertEqual(call("/presence/state")[1]["state"], "thinking")
            self.assertEqual(call("/presence/nope")[0], 404)
        finally:
            srv.shutdown()


if __name__ == "__main__":
    unittest.main()
