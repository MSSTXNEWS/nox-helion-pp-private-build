import os, tempfile, time, unittest
from ._testutil import touch
from .skills import SkillLibrary, terms, fts_query
from .codeindex import CodeIndex, parse_py, parse_md, parse_sh, split_ident


class TestSkills(unittest.TestCase):
    def setUp(self):
        self.lib = SkillLibrary(":memory:")

    def test_save_search_render(self):
        rid = self.lib.save({"name": "Добавить эндпоинт здоровья в шлюз", "condition": "нужен /health у шлюза", "steps": ["read_file(gateway.py)", "edit_file(gateway.py)", "run_tests()"],
                             "tools": ["read_file", "edit_file", "run_tests"], "check": "run_tests зелёные"})
        self.lib.save({"name": "Резервная копия базы памяти", "condition": "бэкап sqlite", "steps": ["shell(python3 backup.py)"], "tools": ["shell"], "check": "verify"})
        hits = self.lib.search("добавь health эндпоинт в шлюзе")
        self.assertEqual(hits[0]["id"], rid)
        self.assertEqual(self.lib.search("сделай бэкап базы")[0]["name"], "Резервная копия базы памяти")
        self.assertEqual(self.lib.search("совсем другое про космос"), [])
        txt = self.lib.render_prompt(hits)
        self.assertIn("Рецепт", txt); self.assertIn("1. read_file", txt); self.assertIn("Проверка: run_tests зелёные", txt)
        self.assertLessEqual(len(self.lib.render_prompt(hits, 50)), 50)

    def test_dedup_counts_and_secret_scrub(self):
        a = {"name": "x задача", "condition": "c", "steps": ["shell(echo token=abcdefghijk1234)"], "tools": ["shell"]}
        i1 = self.lib.save(a); i2 = self.lib.save(a)
        self.assertEqual(i1, i2); r = self.lib.get(i1)
        self.assertEqual(r["successes"], 2); self.assertNotIn("abcdefghijk1234", r["steps"][0])
        with self.assertRaises(ValueError): self.lib.save({"name": "", "steps": []})

    def test_from_run(self):
        recs = [{"kind": "tool", "name": "read_file", "args": {"path": "a.py"}, "ok": True}, {"kind": "tool", "name": "shell", "args": {"cmd": "boom"}, "ok": False},
                {"kind": "tool", "name": "run_tests", "args": {}, "ok": True}, {"kind": "tool", "name": "finish", "args": {"summary": "s"}, "ok": True}]
        r = self.lib.from_run({"title": "Починить a"}, recs, "готово")
        self.assertEqual(r["steps"], ["read_file(a.py)", "run_tests()"]); self.assertIn("run_tests", r["check"]); self.assertEqual(r["tools"], ["read_file", "run_tests"])
        self.assertIsNone(self.lib.from_run({"title": "t"}, []))
        self.assertTrue(self.lib.save_from_run({"title": "Починить a"}, recs))

    def test_persist_on_disk(self):
        p = os.path.join(tempfile.mkdtemp(), "s.sqlite3")
        SkillLibrary(p).save({"name": "n навык", "condition": "c", "steps": ["a"]})
        self.assertEqual(len(SkillLibrary(p).search("навык")), 1)

    def test_terms(self):
        self.assertEqual(terms("Создать резервную копию"), ["создат", "резерв", "копию"])
        self.assertIn('"копия"*', fts_query("копия"))


SRC = '''"""Модуль шлюза: маршрутизация запросов."""
import os

class Router:
    """Роутер тиров быстрый/глубокий."""
    def route_tier(self, messages):
        """Выбрать тир по тексту."""
        return 1

    async def stop_request(self, rid):
        pass

def build_core_block(store, budget):
    """Собрать блок ядра памяти."""
    return ""
'''


class TestCodeIndex(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        touch(os.path.join(self.root, "gw", "router.py"), SRC)
        touch(os.path.join(self.root, "gw", "NOTES.md"), "# Заметки\n\n## Резервное копирование памяти\ntext\n")
        touch(os.path.join(self.root, "ops", "run.sh"), "#!/bin/bash\n# Запуск сервиса шлюза\nstart_gateway() {\n  true\n}\n")
        touch(os.path.join(self.root, "node_modules", "x.py"), "def hidden(): pass\n")
        touch(os.path.join(self.root, "bad.py"), "def (:\n")
        self.ix = CodeIndex(":memory:", self.root)

    def test_parse(self):
        syms = {(k, q): (l, d) for k, q, l, d in parse_py(SRC)}
        self.assertIn(("module", ""), syms); self.assertEqual(syms[("method", "Router.route_tier")][0], 6); self.assertIn("Выбрать тир", syms[("method", "Router.route_tier")][1])
        self.assertIn(("method", "Router.stop_request"), syms); self.assertIn(("function", "build_core_block"), syms)
        self.assertEqual(parse_py("def (:"), [])
        self.assertEqual(parse_md("# A\ntext\n## B")[1][2], 3)
        self.assertEqual(parse_sh("start() {\n}\n")[0][1], "start")
        self.assertEqual(split_ident("buildCoreBlock_v2"), "build core block v2")

    def test_build_and_where(self):
        st = self.ix.build()
        self.assertEqual(st["files"], 4); self.assertNotIn("hidden", [h["symbol"] for h in self.ix.where("hidden")])
        h = self.ix.where("где у меня роутер тиров")
        self.assertEqual(h[0]["symbol"], "Router"); self.assertEqual(h[0]["at"], "gw/router.py:4")
        h = self.ix.where("route tier")
        self.assertEqual(h[0]["symbol"], "Router.route_tier")
        self.assertEqual(self.ix.where("блок ядра памяти")[0]["symbol"], "build_core_block")
        self.assertEqual(self.ix.where("резервное копирование")[0]["path"], "gw/NOTES.md")
        self.assertEqual(self.ix.where("start gateway")[0]["symbol"], "start_gateway")
        self.assertEqual(self.ix.where("zzzqqq"), [])

    def test_incremental(self):
        self.ix.build()
        self.assertEqual(self.ix.build()["updated"], 0)
        p = os.path.join(self.root, "gw", "router.py")
        touch(p, SRC + "\ndef brand_new_feature():\n    '''Новая штука.'''\n")
        time.sleep(0.01); os.utime(p, (time.time() + 5, time.time() + 5))
        self.assertEqual(self.ix.build()["updated"], 1)
        self.assertEqual(self.ix.where("brand new feature")[0]["symbol"], "brand_new_feature")
        os.remove(p)
        self.assertEqual(self.ix.build()["removed"], 1)
        self.assertEqual(self.ix.where("brand new feature"), [])

    def test_indexes_real_repo_package(self):
        here = os.path.dirname(os.path.abspath(__file__))
        ix = CodeIndex(":memory:", here)
        ix.build()
        self.assertIn("loop.py", [h["path"] for h in ix.where("агентный цикл", k=5)])
        self.assertIn("selfbuild.py", [h["path"] for h in ix.where("судья проверка диф", k=5)])


if __name__ == "__main__":
    unittest.main()
