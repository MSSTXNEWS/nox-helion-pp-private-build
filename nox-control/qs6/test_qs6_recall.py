import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from qs6.s03_store import Store
from qs6.memory_search import MemorySearch
from qs6.recall_api import Recall
from qs6.events_bus import EventBus
import tempfile


class RecallT(unittest.TestCase):
    def setUp(self):
        self.s = Store()
        self.addCleanup(self.s.close)
        self.f1 = self.s.add_fact("Сервер S1 работает на порту 8080")
        self.f2 = self.s.add_fact("Мессир любит чёрный кофе", kind="owner")
        self.s.set_profile("имя", "NOX HELION", "persona")
        self.td = tempfile.TemporaryDirectory(); self.addCleanup(self.td.cleanup)
        self.bus = EventBus(os.path.join(self.td.name, "ev.jsonl"))
        self.r = Recall(self.s, MemorySearch(self.s, use_env_embedder=False), self.bus)

    def test_recall_records_usage_and_events(self):
        out = self.r.recall_for_reply("на каком порту сервер", turn_id="t1")
        rem = self.r.remembered("t1")
        ids = {i["id"] for i in rem["items"]}
        self.assertIn("f:%d" % self.f1, ids)
        self.assertIn("p:имя", ids)                       # из блока ядра
        vias = {i["id"]: i["via"] for i in rem["items"]}
        self.assertEqual(vias["f:%d" % self.f1], "search")
        self.assertEqual(vias["p:имя"], "core")
        self.assertEqual(rem["count"], len(rem["items"]))
        self.assertEqual(self.s.get_fact(self.f1)["access_count"], 1)
        ev = self.bus.read()
        self.assertEqual(ev[0]["type"], "memory.found")
        self.assertIn("f:%d" % self.f1, ev[0]["data"]["refs"])

    def test_confirm_raises_level(self):
        self.assertEqual(self.s.get_fact(self.f1)["level"], 0)
        self.r.confirm("f:%d" % self.f1)
        f = self.s.get_fact(self.f1)
        self.assertEqual(f["level"], 2)
        self.assertEqual(self.r.journal()[0]["action"], "confirm")

    def test_correct_updates_text_index_and_journal(self):
        ref = "f:%d" % self.f1
        self.r.correct(ref, "Сервер S1 работает на порту 9090", reason="владелец поправил")
        self.assertEqual(self.s.get_fact(self.f1)["text"], "Сервер S1 работает на порту 9090")
        hits = self.r.search.search("9090")["hits"]
        self.assertEqual(hits[0]["ref"], ref)
        self.assertEqual(self.r.search.search("8080")["hits"], [])
        j = self.r.journal(ref=ref)[0]
        self.assertEqual((j["action"], j["old"], j["reason"]), ("correct", "Сервер S1 работает на порту 8080", "владелец поправил"))
        with self.assertRaises(ValueError):
            self.r.correct(ref, "Мессир любит чёрный кофе")      # дубликат
        with self.assertRaises(ValueError):
            self.r.correct(ref, "  ")

    def test_delete_soft_and_revert(self):
        ref = "f:%d" % self.f1
        res = self.r.delete(ref, reason="неверно")
        self.assertEqual(self.r.search.search("порту")["hits"], [])
        self.r.recall_for_reply("кофе", turn_id="t2")
        self.r.mark_used("t3", [ref])
        it = self.r.remembered("t3")["items"][0]
        self.assertFalse(it["available"])
        with self.assertRaises(ValueError):
            self.r.delete(ref)
        self.r.revert(res["change_id"])
        self.assertEqual(self.r.search.search("порту")["hits"][0]["ref"], ref)
        self.assertEqual([c["action"] for c in self.r.journal(3)][:2], ["revert", "delete"])

    def test_profile_and_episode_edit(self):
        e = self.s.add_episode("Обсуждали бэкапы")
        self.r.correct("p:имя", "НОКС")
        self.assertEqual(self.s.get_profile("имя")["value"], "НОКС")
        self.r.confirm("e:%d" % e)
        self.assertEqual(self.s.get_episode(e)["owner_confirmed"], 1)
        self.r.delete("p:имя")
        self.assertEqual(self.s.profile("persona"), [])
        with self.assertRaises(KeyError):
            self.r.confirm("f:9999")

    def test_json_api(self):
        h = self.r.handle
        a = h({"op": "recall", "query": "кофе", "turn_id": "T"})
        self.assertTrue(a["ok"])
        b = h({"op": "remembered", "turn_id": "T"})
        self.assertTrue(any(i["id"] == "f:%d" % self.f2 for i in b["items"]))
        self.assertTrue(h({"op": "confirm", "id": "f:%d" % self.f2})["ok"])
        self.assertTrue(h({"op": "correct", "id": "f:%d" % self.f2, "text": "Мессир любит зелёный чай"})["ok"])
        d = h({"op": "delete", "id": "f:%d" % self.f2})
        self.assertTrue(d["ok"] and d["deleted"])
        self.assertTrue(h({"op": "revert", "change_id": d["change_id"]})["ok"])
        self.assertTrue(len(h({"op": "journal"})["changes"]) >= 4)
        self.assertIn("Ядро", h({"op": "core"})["text"])
        self.assertTrue(h({"op": "search", "query": "чай"})["ok"])
        self.assertFalse(h({"op": "nope"})["ok"])
        self.assertFalse(h({"op": "confirm"})["ok"])
        self.assertFalse(h({"op": "confirm", "id": "x"})["ok"])
        self.assertFalse(h({"op": "confirm", "id": "f:424242"})["ok"])
        import json
        json.dumps(a, ensure_ascii=False)     # ответ сериализуем


if __name__ == "__main__":
    unittest.main()
