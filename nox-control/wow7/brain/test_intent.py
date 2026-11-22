"""Тесты nox_intent. NOX_INTENT_TEST_DB - КОПИЯ реального S03 (запуск на S1); иначе временная БД с таблицей mem_facts (синтетика)."""
import json, os, shutil, sqlite3, sys, tempfile, time, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nox_intent as N

REAL = os.environ.get("NOX_INTENT_TEST_DB")


def make_db():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "s03.db")
    if REAL:
        shutil.copy(REAL, p)
    else:
        c = sqlite3.connect(p); c.execute("CREATE TABLE mem_facts(id INTEGER PRIMARY KEY, text TEXT)"); c.execute("INSERT INTO mem_facts(text) VALUES('старый факт')"); c.commit(); c.close()
    return p


class T(unittest.TestCase):
    def setUp(self):
        self.p = make_db(); self.n = N.Intent(self.p)
        c = sqlite3.connect(self.p)
        self.before = {t: c.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0] for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'intent_%' AND name NOT LIKE 'sqlite_%'").fetchall()}
        c.close()

    def test_00_existing_untouched(self):
        self.n.status()
        c = sqlite3.connect(self.p)
        for t, k in self.before.items():
            self.assertEqual(c.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0], k)

    def test_choices_price(self):
        a = self.n.refuse("вспышка", "на телефоне закрывала первые слова", ["phone", "text-first"])
        b = self.n.refuse("градиент", None)                       # причина не названа
        c = self.n.refuse("сепия", "не люблю", reason_kind="taste")
        self.assertEqual((a["reason_kind"], b["reason_kind"]), ("context", "unknown"))
        self.assertEqual(self.n.revisit_options(["phone"]), [])            # условие отказа действует
        got = self.n.revisit_options(["cinema", "silent-scene"])
        self.assertEqual([g["option"] for g in got], ["вспышка"])         # unknown и taste не возвращаются

    def test_futures_montage(self):
        r = self.n.future_pair({"тишина": "1с", "поворот": "ранний"}, {"тишина": "0.3с", "поворот": "после имени"}, scene="пробуждение")
        self.assertEqual(r["diff"], ["поворот", "тишина"])
        d = self.n.future_compose(r["a"]["id"], r["b"]["id"], {"поворот": "b"})
        s = json.loads(d["segments"]); self.assertEqual((s["тишина"], s["поворот"]), ("1с", "после имени"))
        self.assertEqual(d["status"], "draft")
        d = self.n.future_edit(d["id"], "тишина", "1.2с")
        with self.assertRaises(ValueError): self.n.future_edit(r["a"]["id"], "тишина", "x")   # оригинал неприкосновенен
        self.assertEqual(json.loads(self.n._get("futures", r["a"]["id"])["segments"])["тишина"], "1с")
        d2 = self.n.future_compose(r["a"]["id"], r["b"]["id"], {"поворот": "b"}); d2 = self.n.future_undo(d2["id"])
        self.assertEqual(json.loads(d2["segments"])["поворот"], "ранний")

    def test_objection(self):
        o = self.n.object_("вспышка на каждое слово", "вспыхивать", "одна на мысль", sample=None, scene="s1")
        self.assertEqual(o["kind"], "гипотеза")
        o2 = self.n.object_("вспышка", "вспыхивать", "одна на мысль", sample="5с@360px", scene="s1")
        self.assertEqual(o2["kind"], "образец")
        self.n.object_resolve(o["id"], "owner"); self.assertEqual(len(self.n.object_open(scene="s1")), 1)

    def test_delivered_resume(self):
        t = "Сначала он замечает, с чем ты пришёл. Потом поворачивается к абзацу. Затем молчит."
        r = self.n.propose(t, "c1"); self.n.delivered(r["id"], 9)
        out = self.n.resume(r["id"], correction="без слова затем")
        self.assertTrue(out["remaining"].startswith("Потом поворачивается"))          # оборвалось в 2-м предложении? 9 слов = в конце 1-го
        self.n.delivered(r["id"], 11); out = self.n.resume(r["id"])
        self.assertTrue(out["remaining"].startswith("Затем"))                           # предложение 2 дозвучало целиком
        out = self.n.resume(r["id"], user_read_words=12); self.assertTrue(out["remaining"].startswith("Затем")); self.assertEqual(self.n.resume(r["id"], user_read_words=13)["remaining"], "")
        r2 = self.n.propose("Один два три четыре пять шесть семь восемь девять десять", "c2")
        u = self.n.resume(r2["id"]); self.assertEqual(u["position"], "unknown")
        self.assertIsNone(self.n._get("delivered", r2["id"])["chosen"])             # предложено != выбрано
        self.assertEqual(self.n.choose(r["id"], "вариант 1")["chosen"], "вариант 1")

    def test_idea_sleep(self):
        i = self.n.idea_add("вспышка для немой сцены", project="cinema", scene="s5")
        self.assertEqual(len(self.n.idea_due("cinema", "s5")), 1)
        self.n.idea_react(i["id"], "too_early", delay_s=3600)
        self.assertEqual(self.n.idea_due("cinema", "s5"), [])                          # момент сдвинут
        self.n._q("UPDATE intent_idea_sleep SET show_after=0 WHERE id=?", (i["id"],), commit=True)
        self.assertEqual(len(self.n.idea_due("cinema", "s5", mark_shown=True)), 1)
        j = self.n.idea_add("другая", project="cinema", scene="s5"); self.n.idea_react(j["id"], "not_fit")
        self.assertEqual([x["id"] for x in self.n.idea_due("cinema", "s5")], [])      # закрытая ветка не выдаётся

    def test_lessons(self):
        l = self.n.teach("спокойный голос", "энергичный голос", "спокойный - личное приглашение, энергичный - афиша", ["приглашение", "личное"], ["афиша", "реклама"])
        self.assertEqual(self.n.lesson_apply(["афиша"])[0]["picked"], "энергичный голос")
        a = self.n.lesson_apply(["приглашение", "афиша"]); self.assertEqual(a, [])    # неоднозначно - не применяем
        r = self.n.lesson_apply(["личное"], "письмо")[0]; self.assertEqual(r["basis"], "единственный пример")
        self.assertEqual(self.n.learned()[0]["next_choice"]["picked"], "спокойный голос")

    def test_second_thoughts(self):
        self.assertTrue(self.n.check_second_thoughts()["initialized_cursor"] is not None)
        th = self.n.advise("Озвучить приглашение спокойным голосом", "получатель - близкий друг", {"keywords": ["получатель", "афиша"], "min_hits": 2})
        self.assertEqual(self.n.check_second_thoughts()["triggered"], [])
        c = sqlite3.connect(self.p)
        c.close()
        con = self.n.con(); t, tc = self.n._fact_source(con)
        if t == "mem_facts" and not REAL:
            con.execute("INSERT INTO mem_facts(text) VALUES('Получатель теперь вся аудитория: это афиша')")
        else:
            cols = [r["name"] for r in con.execute("PRAGMA table_info(%s)" % t)]
            con.execute("INSERT INTO %s(%s) VALUES(?)" % (t, tc), ("Получатель теперь вся аудитория: это афиша",))   # тест идёт на КОПИИ
        con.commit(); con.close()
        out = self.n.check_second_thoughts()
        self.assertEqual(len(out["triggered"]), 1); self.assertIn("Основание", out["triggered"][0]["message"])
        self.assertEqual(self.n._get("second_thoughts", th["id"])["status"], "revisit_due")
        self.n.rethink(th["id"], True, "Озвучить энергично", "аудитория шире")
        ev = [b["event"] for b in self.n.biography()]; self.assertEqual(ev, ["advised", "revisit_due", "revised"])

    def test_http(self):
        st, o = self.n.handle("POST", "/intent/choices", "", {"option": "x", "reason": "r", "context": ["a"]}); self.assertEqual(st, 200)
        st, o = self.n.handle("GET", "/intent/choices/revisit", "context=b", {}); self.assertEqual(len(o["options"]), 1)
        st, o = self.n.handle("POST", "/intent/choices", "", {}); self.assertEqual(st, 400)
        st, o = self.n.handle("GET", "/intent/nope", "", {}); self.assertEqual(st, 404)
        self.assertEqual(N.Intent("/no/such.db").handle("GET", "/intent/status", "", {})[0], 503)


if __name__ == "__main__":
    unittest.main(verbosity=2)
