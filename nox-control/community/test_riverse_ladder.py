import os, sys, json, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from riverse_ladder import Ladder, DAY

T0 = 1_700_000_000.0


class Rules(unittest.TestCase):
    def setUp(self):
        self.l = Ladder()
        self.addCleanup(self.l.close)
        self.f = self.l.add_fact("Я живу в Казани", T0)

    def test_start_and_dedup(self):
        self.assertEqual(self.l.level_name(self.f), "заметил")
        self.assertEqual(self.l.add_fact("я живу в казани.", T0 + 1), self.f)

    def test_same_source_does_not_count(self):
        for i in range(5):
            self.l.add_evidence(self.f, "chat1", "chat", T0 + i)
        self.assertEqual(self.l.level(self.f), 0)

    def test_promotion_chain(self):
        self.l.add_evidence(self.f, "a", "chat", T0)
        self.assertEqual(self.l.add_evidence(self.f, "b", "chat", T0 + 1), 1)
        # 3 источника, но нет сильного -> остаётся «подозреваю»
        self.assertEqual(self.l.add_evidence(self.f, "c", "chat", T0 + 2), 1)
        self.assertEqual(self.l.add_evidence(self.f, "d", "owner", T0 + 3), 2)
        self.assertEqual(self.l.add_evidence(self.f, "e", "doc", T0 + 4), 2)  # span < 7 дн
        self.assertEqual(self.l.add_evidence(self.f, "f", "doc", T0 + 8 * DAY), 3)
        names = [b for a, b, r in self.l.history(self.f)]
        self.assertEqual(names, ["подозреваю", "подтверждено", "установлено"])

    def test_contradiction_demotes_and_blocks_old_evidence(self):
        for i, (s, k) in enumerate([("a", "chat"), ("b", "chat"), ("c", "owner")]):
            self.l.add_evidence(self.f, s, k, T0 + i)
        self.assertEqual(self.l.level(self.f), 2)
        self.assertEqual(self.l.contradict(self.f, "x", "chat", T0 + 100), 1)
        self.assertEqual(self.l.contradict(self.f, "x", "chat", T0 + 101), 1)  # тот же источник не штрафует дважды
        self.assertEqual(self.l.evaluate(self.f, T0 + 102), 0)  # старые свидетельства до противоречия не считаются
        self.assertTrue(any("противоречие" in r for _, _, r in self.l.history(self.f)))
        self.assertEqual(self.l.contradict(self.f, "y", "chat", T0 + 103), 0)  # ниже «заметил» нельзя

    def test_recency(self):
        self.l.add_evidence(self.f, "a", "owner", T0)
        self.l.add_evidence(self.f, "b", "chat", T0 + 1)
        self.assertEqual(self.l.level(self.f), 1)
        self.assertEqual(self.l.evaluate(self.f, T0 + 400 * DAY), 0)
        self.assertEqual(self.l.history(self.f)[-1][:2], ("подозреваю", "заметил"))


CHATGPT = [{"id": "c1", "title": "t", "create_time": T0, "mapping": {
    "n0": {"id": "n0", "message": None, "parent": None, "children": ["n1"]},
    "n1": {"id": "n1", "message": {"author": {"role": "user"}, "create_time": T0, "content": {"content_type": "text",
           "parts": ["Я работаю ночью над сервером. Как включить swap?"]}}, "children": ["n2"]},
    "n2": {"id": "n2", "message": {"author": {"role": "assistant"}, "create_time": T0 + 1, "content": {"content_type": "text",
           "parts": ["Я могу помочь с этим."]}}, "children": []}}}]
CLAUDE = [{"uuid": "u1", "name": "x", "created_at": "2025-01-01T10:00:00Z", "chat_messages": [
    {"uuid": "m1", "sender": "human", "text": "Я работаю ночью над сервером.", "created_at": "2025-01-01T10:00:00Z",
     "content": [{"type": "text", "text": "Я работаю ночью над сервером."}]},
    {"uuid": "m2", "sender": "assistant", "text": "Я понял, продолжаем.", "created_at": "2025-01-01T10:00:05Z", "content": []}]}]
GEMINI = [{"header": "Gemini Apps", "title": "Prompted Я работаю ночью над сервером", "time": "2025-02-02T08:00:00.000Z"},
          {"header": "Gemini Apps", "title": "Used Gemini Apps", "time": "2025-02-02T08:01:00.000Z"}]


class Imports(unittest.TestCase):
    def test_each_format(self):
        for fn, data, src in [("import_chatgpt", CHATGPT, "chatgpt"), ("import_claude", CLAUDE, "claude"), ("import_gemini", GEMINI, "gemini")]:
            l = Ladder()
            self.addCleanup(l.close)
            self.assertEqual(getattr(l, fn)(data), 1, fn)
            self.assertEqual(l.facts_at(0), [l.facts_at(0)[0]])
            self.assertIn("работаю ночью над сервером", l.facts_at(0)[0].lower())

    def test_cross_import_independent_sources_and_files(self):
        l = Ladder()
        self.addCleanup(l.close)
        with tempfile.TemporaryDirectory() as d:
            for name, data, fn in [("a.json", CHATGPT, l.import_chatgpt), ("b.json", CLAUDE, l.import_claude), ("c.json", GEMINI, l.import_gemini)]:
                p = os.path.join(d, name)
                with open(p, "w", encoding="utf-8") as fh:
                    json.dump(data, fh, ensure_ascii=False)
                fn(p)
        fid = l.db.execute("SELECT id FROM facts").fetchone()[0]
        self.assertEqual(l.evidence_count(fid), 3)
        self.assertEqual(l.level(fid), 0)           # импорт сам не повышает
        l.evaluate_all(now=T0 + 10 * DAY * 400)      # всё устарело
        self.assertEqual(l.level(fid), 0)
        self.assertEqual(l.evaluate(fid, now=1_738_500_000), 1)  # в окне давности: 3 источника -> «подозреваю»

    def test_questions_and_assistant_skipped(self):
        self.assertEqual(Ladder.candidates("Как мне это сделать? Просто текст без местоимений."), [])


if __name__ == "__main__":
    unittest.main()
