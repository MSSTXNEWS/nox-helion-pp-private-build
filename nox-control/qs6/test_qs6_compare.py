import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from qs6 import skill_compare_spec as C

SPEC = """# ТЗ
1. Сервис должен слушать порт 8080.
2. В файле должен быть раздел «Резервное копирование» с описанием ротации.
3. Файл должен упоминать `backup_memory.py`.
4. Система должна поддерживать экспорт в формат XML.
- Пароли не должны храниться в открытом виде.
"""
DOC = """# Описание сервиса
Сервис слушает порт 8080 на локальном интерфейсе.

## Резервное копирование
Скрипт backup_memory.py делает копии раз в час, ротация хранит 24 копии.

## Прочее
Экспорт в JSON поддерживается.
"""


class ParseT(unittest.TestCase):
    def test_parse_formats(self):
        items = C.parse_spec(SPEC)
        self.assertEqual([i["id"] for i in items], ["1", "2", "3", "4", "5"])
        self.assertIn("порт 8080", items[0]["text"])
        t = C.parse_spec("| № | Требование |\n|---|---|\n| ТЗ-1 | Должен быть режим `тихий` |\n| ТЗ-2 | Должен писать журнал |\n")
        self.assertEqual([x["id"] for x in t], ["ТЗ-1", "ТЗ-2"])
        s = C.parse_spec("Система обязана хранить копии. Это просто описание. Нужно проверять сумму.")
        self.assertEqual(len(s), 2)
        j = C.parse_spec(json.dumps({"requirements": [{"id": "A", "text": "Поле «port» равно 8080"}, "строка"], }, ensure_ascii=False))
        self.assertEqual([x["id"] for x in j], ["A", "2"])
        cont = C.parse_spec("1. Первая часть\n   продолжение строки\n2. Вторая")
        self.assertIn("продолжение", cont[0]["text"])

    def test_tokens(self):
        st, wk = C.tokens("Файл `backup_memory.py` слушает порт 8080 и FTS5, раздел «Резервное копирование»")
        self.assertIn("backup_memory.py", st); self.assertIn("8080", st); self.assertIn("FTS5", st); self.assertIn("Резервное копирование", st)
        self.assertTrue(any(w.startswith("слуш") for w in wk))


class CompareT(unittest.TestCase):
    def test_markdown(self):
        rows = {r["id"]: r for r in C.compare(SPEC, DOC)}
        self.assertEqual(rows["1"]["status"], "да")
        self.assertIn("строка 2", rows["1"]["where"])
        self.assertEqual(rows["2"]["status"], "да")
        self.assertIn("Резервное копирование", rows["2"]["where"] + rows["2"]["requirement"])
        self.assertEqual(rows["3"]["status"], "да")
        self.assertEqual(rows["4"]["status"], "частично")      # экспорт есть, XML нет
        self.assertIn("XML", rows["4"]["remark"])
        self.assertEqual(rows["5"]["status"] in ("нет", "частично"), True)
        self.assertIn("запрет", rows["5"]["remark"])
        self.assertTrue(all(0 <= r["confidence"] <= 1 for r in rows.values()))

    def test_number_mismatch_and_heading_check(self):
        r = C.compare("1. Сервис слушает порт 9090.\n2. Должен быть раздел «Безопасность».", DOC)
        self.assertIn("число не встречается", r[0]["remark"]); self.assertNotEqual(r[0]["status"], "да")
        self.assertIn("нет заголовка раздела", r[1]["remark"]); self.assertNotEqual(r[1]["status"], "да")

    def test_json_target(self):
        target = json.dumps({"server": {"port": 8080, "host": "127.0.0.1"}, "backup": {"keep": 24, "interval": "1h"}})
        spec = "1. Поле «port» равно 8080\n2. Поле «keep» равно 24\n3. Поле «timeout» равно 30\n"
        rows = C.compare(spec, target)
        self.assertEqual(rows[0]["status"], "да"); self.assertEqual(rows[0]["where"], "server.port")
        self.assertIn("server", rows[0]["where"])
        self.assertEqual(rows[1]["status"], "да")
        self.assertEqual(rows[2]["status"], "нет")
        self.assertIn("нет поля/ключа", rows[2]["remark"])

    def test_no_checkable_tokens(self):
        r = C.compare("1. Всё должно быть.", "что угодно")
        self.assertEqual(r[0]["status"], "нет"); self.assertIn("нет проверяемых признаков", r[0]["remark"])

    def test_render_and_cli(self):
        t = C.render_table(C.compare(SPEC, DOC))
        self.assertIn("| № | Требование | Найдено | Где | Уверенность | Замечание |", t)
        self.assertIn("Итого требований: 5", t)
        with tempfile.TemporaryDirectory() as d:
            sp, tp = os.path.join(d, "tz.md"), os.path.join(d, "doc.md")
            open(sp, "w", encoding="utf-8").write(SPEC); open(tp, "w", encoding="utf-8").write(DOC)
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(C.main([sp, tp]), 0)
            self.assertIn("порт 8080", buf.getvalue())
            with redirect_stdout(io.StringIO()):
                self.assertEqual(C.main([sp, tp, "--strict"]), 1)
            buf = io.StringIO()
            with redirect_stdout(buf):
                C.main([sp, tp, "--json"])
            self.assertEqual(len(json.loads(buf.getvalue())), 5)
            self.assertEqual(C.main([sp, os.path.join(d, "nope")]), 2)


if __name__ == "__main__":
    unittest.main()
