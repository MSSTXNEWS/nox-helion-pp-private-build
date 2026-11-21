import json
import os
import sqlite3
import sys
import tempfile
import threading
import unittest
import http.client

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "glm53"))
from qs6.fact_extract import extract, emotion_event
from qs6.memory_layer import MemoryLayer
from qs6.s03_store import Store
import qs6_resume as RS


def mk(tmp, **env):
    e = {"NOX_SOUL": "1"}
    e.update(env)
    logs = []
    return MemoryLayer(env=e, log=logs.append), logs


class TExtract(unittest.TestCase):
    def texts(self, t):
        return [f["text"] for f in extract(t)]

    def test_rules(self):
        self.assertEqual(self.texts("Меня зовут Игорь."), ["Владельца зовут Игорь"])
        self.assertEqual(self.texts("Я живу в Риге."), ["Владелец живёт в Риге"])
        self.assertEqual(self.texts("Запомни: сервер S1 стоит в Канаде"), ["Сервер S1 стоит в Канаде"])
        self.assertEqual(self.texts("Мой любимый язык — Python"), ["У владельца любимый язык: Python"])
        f = extract("Всегда отвечай коротко")[0]
        self.assertEqual((f["kind"], f["source_kind"]), ("setting", "direct"))

    def test_skips(self):
        self.assertEqual(extract("Меня зовут Игорь?"), [])
        self.assertEqual(extract("Привет, как дела"), [])
        self.assertEqual(extract(""), [])

    def test_no_secrets(self):
        for t in ("Запомни: пароль: hunter2hunter2", "Запомни: мой ключ sk-abcdefghijklmnopqrstuvwx", "Запомни: карта 4111 1111 1111 1111",
                  "Запомни: моя почта a.b@example.com", "Мой токен это ghp_abcdefghijklmnopqrstuvwxyz1234"):
            self.assertEqual(extract(t), [], t)

    def test_emotion_event(self):
        self.assertEqual(emotion_event("спасибо, отлично"), "owner_thanks")
        self.assertEqual(emotion_event("это неверно"), "owner_correction")
        self.assertIsNone(emotion_event("запусти сервер"))


class TLayer(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.db = os.path.join(self.d, "s03.db")

    def seed(self):
        s = Store(self.db)
        s.set_profile("имя", "NOX HELION", "persona")
        s.add_fact("Мессир работает по ночам", kind="owner", pinned=True)
        s.add_fact("Порт шлюза NOX равен 8082", kind="fact")
        s.add_episode("Обсуждали резервные копии базы", role="user")
        s.close()

    def test_no_env_no_memory_honest_log(self):
        m, logs = mk(self.d)
        self.assertFalse(m.memory_on)
        p = m.prepare("привет", "t1")
        self.assertEqual(p["info"]["memory"], "no_db_env")
        self.assertIn("мессир", p["system"].lower())          # душа есть и без памяти
        self.assertNotIn("## Память", p["system"])
        self.assertTrue(any("БЕЗ памяти" in l for l in logs))
        self.assertEqual(m.after_reply("меня зовут Игорь", "ок", "t1")["facts"], [])

    def test_missing_file_not_created_and_retry(self):
        t = [100.0]
        m = MemoryLayer(env={"NOX_SOUL": "1", "NOX_MEMORY_DB": self.db}, log=lambda x: None, clock=lambda: t[0])
        self.assertFalse(m.memory_on)
        self.assertFalse(os.path.exists(self.db))
        self.seed()
        self.assertFalse(m.memory_on)         # ещё рано повторять
        t[0] += 31
        self.assertTrue(m.memory_on)          # БД появилась после импорта: подхватили без перезапуска

    def test_create_flag(self):
        m, _ = mk(self.d, NOX_MEMORY_DB=self.db, NOX_MEMORY_CREATE="1")
        self.assertTrue(m.memory_on)
        self.assertTrue(os.path.isfile(self.db))

    def test_prepare_with_memory(self):
        self.seed()
        m, _ = mk(self.d, NOX_MEMORY_DB=self.db, NOX_SERVER="S1", NOX_MODEL="GLM-5.3")
        p = m.prepare("какой порт у шлюза NOX", "t1")
        s = p["system"]
        self.assertEqual(p["info"]["memory"], "ok")
        self.assertIn("Мессир работает по ночам", s)             # ядро
        self.assertIn("Вспомнилось по теме разговора", s)          # поиск
        self.assertIn("8082", s)
        self.assertIn("сервер: S1", s)                             # самознание
        self.assertTrue(s.rstrip().endswith("Отвечай коротко и по-русски."))   # повтор главного в конце
        self.assertEqual(p["info"]["search_mode"], "fts")
        used = m.store.db.execute("SELECT COUNT(*) FROM mem_usage WHERE turn_id='t1'").fetchone()[0]
        self.assertGreater(used, 0)                                 # что вспомнилось записано для «что NOX вспомнил»
        r = m.recall.remembered("t1")
        self.assertGreaterEqual(r["count"], 2)

    def test_prompt_budget(self):
        s = Store(self.db)
        for i in range(60):
            s.add_fact("Факт номер %d про серверы и порты и ключи работы" % i, kind="owner")
        s.close()
        m, _ = mk(self.d, NOX_MEMORY_DB=self.db, NOX_PROMPT_MAX="400", NOX_CORE_BUDGET="150")
        p = m.prepare("серверы", "t")
        self.assertLessEqual(p["info"]["prompt_tokens"], 400)
        self.assertFalse(p["info"]["over_budget"])

    def test_soul_off_uses_facts(self):
        self.seed()
        m, _ = mk(self.d, NOX_MEMORY_DB=self.db, NOX_SOUL="0")
        p = m.prepare("порт шлюза", "t")
        self.assertIsNone(p["system"])
        self.assertTrue(any("8082" in f for f in p["facts"]))

    def test_emotion_tone(self):
        t = [1000.0]
        m = MemoryLayer(env={"NOX_SOUL": "1", "NOX_EMOTION": "1"}, log=lambda x: None, clock=lambda: t[0])
        before = m.prepare("привет", "a")["system"]
        self.assertIn("## Тон сейчас", before)
        for _ in range(4):
            m.after_reply("ты ошибся, это неверно", "виноват", "a")
        after = m.prepare("привет", "b")["system"]
        self.assertNotEqual(before, after)
        off = MemoryLayer(env={"NOX_SOUL": "1"}, log=lambda x: None)
        self.assertNotIn("## Тон сейчас", off.prepare("привет", "a")["system"])

    def test_autowrite_and_ladder(self):
        self.seed()
        t = [1_700_000_000.0]
        m = MemoryLayer(env={"NOX_SOUL": "1", "NOX_MEMORY_DB": self.db}, log=lambda x: None, clock=lambda: t[0])
        rep = m.after_reply("Я живу в Риге. Какой порт?", "<think>скрытые мысли</think>Порт 8082.", "t1", session="s-a")
        self.assertEqual([f["text"] for f in rep["facts"]], ["Владелец живёт в Риге"])
        self.assertEqual(rep["facts"][0]["level"], 0)
        self.assertEqual(rep["episodes"], 2)
        eps = [r[0] for r in m.store.db.execute("SELECT text FROM mem_episodes ORDER BY id")]
        self.assertTrue(any("Порт 8082." == e for e in eps))
        self.assertFalse(any("скрытые" in e for e in eps))           # размышлений в памяти нет
        # то же в другой сессии, потом в третьей: независимые источники поднимают уровень
        for sess in ("s-b", "s-c"):
            t[0] += 86400
            rep = m.after_reply("Я живу в Риге.", "ок", "t", session=sess)
        self.assertEqual(rep["facts"][0]["level"], 1)                # «подозреваю»: 3 источника, но нет сильного
        n = m.store.db.execute("SELECT COUNT(*) FROM mem_facts WHERE text='Владелец живёт в Риге'").fetchone()[0]
        self.assertEqual(n, 1)                                       # без дублей
        # повтор в той же сессии не накручивает уверенность
        m.after_reply("Я живу в Риге.", "ок", "t", session="s-c")
        lid = m.store.db.execute("SELECT ladder_id FROM mem_facts WHERE text='Владелец живёт в Риге'").fetchone()[0]
        self.assertEqual(m.store.db.execute("SELECT COUNT(*) FROM evidence WHERE fact_id=?", (lid,)).fetchone()[0], 3)

    def test_autowrite_no_secrets(self):
        self.seed()
        m, _ = mk(self.d, NOX_MEMORY_DB=self.db)
        rep = m.after_reply("Запомни: пароль: hunter2hunter2", "Хорошо, ключ sk-abcdefghijklmnopqrstuvwx сохранён", "t")
        self.assertEqual(rep["facts"], [])
        self.assertEqual(rep["episodes"], 0)
        dump = " ".join(r[0] for r in m.store.db.execute("SELECT text FROM mem_episodes UNION SELECT text FROM mem_facts"))
        self.assertNotIn("hunter2", dump)
        self.assertNotIn("sk-abc", dump)

    def test_summary_jsonl_and_resume(self):
        p = os.path.join(self.d, "sum.jsonl")
        m, _ = mk(self.d, NOX_SESSION_SUMMARY=p)
        msgs = [{"role": "user", "content": "Давай настроим бэкап. Надо проверить cron каждый час"}, {"role": "assistant", "content": "ок"},
                {"role": "user", "content": "Теперь про порты"}]
        rep = m.after_reply("Теперь про порты", "Слушаю", "t", messages=msgs)
        self.assertEqual(rep["summary"], p)
        m.after_reply("Ещё вопрос", "ответ", "t2", messages=msgs + [{"role": "user", "content": "Ещё вопрос"}])
        rows = [json.loads(l) for l in open(p, encoding="utf-8")]
        self.assertEqual(len(rows), 2)
        self.assertIn("cron каждый час", rows[0]["open_items"][0])
        ans = RS.resume_answer(p)
        self.assertIn("Последняя сессия", ans)
        self.assertIn("Реплик владельца: 3", ans)
        self.assertIn("Ещё вопрос", ans)

    def test_summary_sqlite_and_secret(self):
        p = os.path.join(self.d, "sum.db")
        m, _ = mk(self.d, NOX_SESSION_SUMMARY=p)
        m.after_reply("пароль: hunter2hunter2", "нет", "t")
        row = sqlite3.connect(p).execute("SELECT summary,last_user FROM sessions").fetchone()
        self.assertNotIn("hunter2", " ".join(row))
        self.assertIn("Реплик", RS.resume_answer(p))

    def test_events(self):
        ev = os.path.join(self.d, "ev.jsonl")
        m, _ = mk(self.d, NOX_EVENTS=ev)
        m.started("r1", "auto")
        m.started("r2", "deep")
        m.finished("r2", 10)
        rows = [json.loads(l) for l in open(ev, encoding="utf-8")]
        self.assertEqual([r["type"] for r in rows], ["reply.started", "mode.changed", "reply.started", "reply.finished"])
        self.assertEqual(rows[1]["data"], {"from": "auto", "to": "deep", "reason": "запрос"})


class TRecallServer(unittest.TestCase):
    def test_serve_loopback_and_api(self):
        d = tempfile.mkdtemp()
        db = os.path.join(d, "s03.db")
        s = Store(db)
        fid = s.add_fact("Порт recall равен 8095", kind="fact")
        s.close()
        from qs6 import recall_server
        srv = recall_server.build({"NOX_MEMORY_DB": db, "NOX_RECALL_PORT": "0"})
        self.assertEqual(srv.server_address[0], "127.0.0.1")
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            c = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=5)
            c.request("POST", "/api", json.dumps({"op": "search", "query": "порт recall"}))
            r = json.loads(c.getresponse().read())
            self.assertTrue(r["ok"])
            self.assertEqual(r["hits"][0]["ref"], "f:%d" % fid)
        finally:
            srv.shutdown()
            srv.server_close()

    def test_refuses_bad_config(self):
        from qs6 import recall_server
        with self.assertRaises(SystemExit):
            recall_server.build({"NOX_MEMORY_DB": "/nonexistent/x.db"})
        d = tempfile.mkdtemp()
        db = os.path.join(d, "a.db")
        Store(db).close()
        with self.assertRaises(SystemExit):
            recall_server.build({"NOX_MEMORY_DB": db, "NOX_RECALL_HOST": "0.0.0.0"})


if __name__ == "__main__":
    unittest.main()
