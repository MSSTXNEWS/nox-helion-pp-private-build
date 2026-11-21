import json
import sys
import os
import sqlite3
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from qs6.s03_store import Store, split_ref


def w(root, rel, data, mode="w"):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, mode, **({} if "b" in mode else {"encoding": "utf-8"})) as f:
        f.write(data)
    return p


class StoreT(unittest.TestCase):
    def setUp(self):
        self.s = Store()
        self.addCleanup(self.s.close)

    def test_fact_ladder_and_dedup(self):
        a = self.s.add_fact("Мессир живёт в Москве", kind="owner")
        b = self.s.add_fact("мессир живёт в москве.", kind="owner", source="chat:1", source_kind="chat")
        self.assertEqual(a, b)
        f = self.s.get_fact(a)
        self.assertEqual(f["level"], 1)           # 2 независимых источника: «подозреваю»; подтверждено нужно 3 и сильный
        self.assertIn(f["level_name"], ("заметил", "подозреваю"))
        self.assertEqual(self.s.stats()["facts"], 1)
        with self.assertRaises(ValueError):
            self.s.add_fact("  ")
        with self.assertRaises(ValueError):
            self.s.add_fact("x", kind="bad")

    def test_profile_and_get(self):
        ref = self.s.set_profile("имя", "NOX", "persona")
        self.assertEqual(ref, "p:имя")
        self.assertEqual(self.s.get(ref)["value"], "NOX")
        self.s.set_profile("имя", "НОКС", "persona")
        self.assertEqual(self.s.profile("persona")[0]["value"], "НОКС")
        self.assertEqual(split_ref("f:7"), ("fact", 7))
        with self.assertRaises(ValueError):
            split_ref("z:1")

    def test_episode(self):
        e = self.s.add_episode("Мы обсуждали сервер", role="user", ts=1000.0)
        self.assertEqual(e, self.s.add_episode("Мы обсуждали сервер", role="user", ts=1000.0))
        self.assertEqual(self.s.get("e:%d" % e)["text"], "Мы обсуждали сервер")

    def test_file_db_persists(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "m.db")
            s = Store(p); s.add_fact("факт один"); s.close()
            s2 = Store(p)
            self.assertEqual(s2.stats()["facts"], 1)
            s2.close()


class ImportT(unittest.TestCase):
    def setUp(self):
        self.s = Store()
        self.addCleanup(self.s.close)
        self.d = tempfile.TemporaryDirectory()
        self.addCleanup(self.d.cleanup)
        r = self.d.name
        w(r, "memory/facts.json", json.dumps({"facts": [{"text": "Сервер S1 стоит в Финляндии", "ts": "2026-01-02T10:00:00Z"},
                                                      {"text": "Сервер S1 стоит в Финляндии"}, {"text": "ок"}, {"text": ""},
                                                      {"text": "token = abcdef123456789"}]}, ensure_ascii=False))
        w(r, "memory/chat_history.jsonl", "\n".join([json.dumps({"role": "user", "content": "Привет, нокс", "ts": 1700000000}, ensure_ascii=False),
                                                    json.dumps({"role": "assistant", "content": "Здравствуй, мессир", "ts": 1700000005}, ensure_ascii=False),
                                                    "{битая строка"]))
        w(r, "knowledge/soul.md", "# Характер\nСпокойный и прямой.\n\n# Речь\nКоротко и по делу.\n")
        w(r, "knowledge/owner_notes.md", "# Мессир\n- Любит чёрный кофе\n- Работает по ночам\n")
        w(r, "state/settings.json", json.dumps({"язык": "русский", "режим": "тихий"}, ensure_ascii=False))
        w(r, "backup.tar.zstd", "xx")
        w(r, "bin/blob.dat", b"\x00\x01\x02" * 100, "wb")
        con = sqlite3.connect(os.path.join(r, "state/old.db"))
        con.execute("CREATE TABLE memories(id INTEGER, text TEXT, created_at TEXT)")
        con.execute("INSERT INTO memories VALUES(1,'Пароль от сейфа не храним в памяти','2026-02-01')")
        con.execute("INSERT INTO memories VALUES(2,'Любимый цвет мессира тёмно-синий','2026-02-02')")
        con.execute("CREATE TABLE weird(a INT, b INT)")
        con.execute("INSERT INTO weird VALUES(1,2)")
        con.commit(); con.close()

    def test_dry_run_writes_nothing(self):
        rep = self.s.import_dir(self.d.name, dry_run=True)
        self.assertTrue(rep.totals["facts"] > 0)
        self.assertEqual(self.s.stats()["facts"], 0)
        self.assertEqual(self.s.stats()["profile"], 0)

    def test_import_report(self):
        rep = self.s.import_dir(self.d.name)
        t = rep.totals
        st = self.s.stats()
        self.assertEqual(st["episodes"], 2)
        self.assertEqual(t["episodes"], 2)
        texts = [f["text"] for f in self.s.active_facts()]
        self.assertIn("Сервер S1 стоит в Финляндии", texts)
        self.assertIn("Любимый цвет мессира тёмно-синий", texts)
        self.assertIn("Любит чёрный кофе", texts)
        kinds = {f["text"]: f["kind"] for f in self.s.active_facts()}
        self.assertEqual(kinds["Любит чёрный кофе"], "owner")
        keys = {p["key"]: p["section"] for p in self.s.profile()}
        self.assertEqual(keys["soul/Характер"], "persona")
        self.assertEqual(keys["settings/язык"], "settings")
        reasons = " ".join(rep.reasons)
        for part in ("дубликат", "слишком коротко", "нет текстового поля", "секрет", "битая строка", "без текстового столбца"):
            self.assertIn(part, reasons)
        sk = {f["path"]: f["reason"] for f in rep.skipped}
        self.assertIn("backup.tar.zstd", sk)
        self.assertIn(os.path.join("bin", "blob.dat"), sk)
        self.assertIn("принято фактов", rep.text())
        self.assertEqual(st["changes"] > 0, True)

    def test_reimport_idempotent(self):
        self.s.import_dir(self.d.name)
        a = self.s.stats()
        rep = self.s.import_dir(self.d.name)
        self.assertEqual(self.s.stats()["facts"], a["facts"])
        self.assertEqual(self.s.stats()["episodes"], a["episodes"])
        self.assertEqual(rep.totals["facts"] + rep.totals["episodes"], 0)

    def test_does_not_overwrite_owner_profile(self):
        self.s.set_profile("settings/язык", "английский", "settings", source="owner")
        rep = self.s.import_dir(self.d.name)
        self.assertEqual(self.s.get_profile("settings/язык")["value"], "английский")
        self.assertIn("не перезаписываю", " ".join(rep.reasons))

    def test_missing_root(self):
        with self.assertRaises(FileNotFoundError):
            self.s.import_dir("/nonexistent/qs6")

    def test_cp1251_text(self):
        w(self.d.name, "notes/cp.txt", "- Факт в кодировке cp1251 тоже читается\n".encode("cp1251"), "wb")
        self.s.import_dir(self.d.name)
        self.assertIn("Факт в кодировке cp1251 тоже читается", [f["text"] for f in self.s.active_facts()])


if __name__ == "__main__":
    unittest.main()
