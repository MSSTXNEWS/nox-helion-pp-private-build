import os
import sqlite3
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import zamysel as Z


class Clock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now


class FakeJournal:
    def __init__(self):
        self.rows = []

    def append(self, kind, text, source, data=None, ts=None):
        row = {"kind": kind, "text": text, "source": source, "data": data, "ts": ts}
        self.rows.append(row)
        return row


class RaisingJournal:
    def append(self, *args, **kwargs):
        raise OSError("journal unavailable")


class FakeStore:
    def __init__(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = None
        self.path = ":memory:"
        self.records = {}

    def get(self, ref):
        return self.records.get(ref)

    @staticmethod
    def text_of(record):
        return record["text"]


class TestAdvice(unittest.TestCase):
    def setUp(self):
        self.store = FakeStore()
        self.clock = Clock()
        self.journal = FakeJournal()
        self.store.records["f:1"] = {"text": "Сервер S1 работает на порту 8080", "status": "active",
                                      "type": "fact", "source": "owner", "source_kind": "owner"}

    def tearDown(self):
        self.store.db.close()

    def add_advice(self):
        return Z.record_advice(
            self.store,
            "Открыть порт сервера через reverse proxy.",
            [{"ref": "f:1"}],
            clock=self.clock,
            journal=self.journal,
        )

    def test_record_persists_snapshot_and_cited_explanation(self):
        aid = self.add_advice()["id"]
        exp = Z.explain_advice(self.store, aid)
        self.assertEqual(exp["status"], "live")
        self.assertEqual(exp["privacy"], "owner_only")
        self.assertEqual(exp["premises"][0]["ref"], "f:1")
        self.assertEqual(exp["premises"][0]["text"], self.store.records["f:1"]["text"])
        self.assertEqual(len(exp["premises"][0]["sha"]), 64)
        self.assertIn("[zm:advice:%d]" % aid, exp["lines"][0])
        self.assertIn("[f:1@", exp["lines"][1])
        self.assertEqual(self.journal.rows[0]["source"], "zamysel")

    def test_supplied_stale_sha_or_snippet_is_rejected(self):
        sha = Z._sha(self.store.records["f:1"]["text"])
        with self.assertRaisesRegex(ValueError, "SHA"):
            Z.record_advice(self.store, "совет", [{"ref": "f:1", "sha": "0" * 64}],
                            clock=self.clock, journal=self.journal)
        with self.assertRaisesRegex(ValueError, "не совпадает"):
            Z.record_advice(self.store, "совет", [{"ref": "f:1", "sha": sha, "text": "старое"}],
                            clock=self.clock, journal=self.journal)

    def test_changed_source_marks_advice_stale_with_history_and_journal(self):
        aid = self.add_advice()["id"]
        self.clock.now = 1100.0
        self.store.records["f:1"]["text"] = "Сервер S1 работает на порту 9090"
        out = Z.refresh_stale_advice(self.store, clock=self.clock, journal=self.journal)
        self.assertEqual(out["stale"][0]["id"], aid)
        exp = Z.explain_advice(self.store, aid)
        self.assertEqual(exp["status"], "stale")
        self.assertEqual(exp["history"][-1].get("reason"), "sha_changed")
        self.assertIn("изменилось", exp["lines"][-1])
        self.assertEqual(self.journal.rows[-1]["data"]["reason"], "sha_changed")

    def test_correction_event_marks_stale_even_if_text_was_restored(self):
        aid = self.add_advice()["id"]
        self.clock.now = 1200.0
        self.store.db.execute(
            "INSERT INTO mem_corrections(ts,ref,op,old,new,verified,detail) VALUES(?,?,?,?,?,?,?)",
            (1100.0, "f:1", "correct", "текст", "текст", 1, "{}"),
        )
        self.store.db.commit()
        out = Z.refresh_stale_advice(self.store, ref="f:1", clock=self.clock, journal=self.journal)
        self.assertEqual(out["stale"][0]["id"], aid)
        self.assertEqual(out["stale"][0]["reason"]["reason"], "memory_correction")

    def test_speaker_isolation_and_revoke(self):
        aid = self.add_advice()["id"]
        with self.assertRaises(KeyError):
            Z.explain_advice(self.store, aid, speaker="nox")
        self.store.records["f:1"]["status"] = "deleted"
        out = Z.refresh_stale_advice(self.store, speaker="owner", clock=self.clock, journal=self.journal)
        self.assertEqual(out["stale"][0]["reason"]["reason"], "missing_or_inactive")

    def test_counterfactual_is_explicit_and_does_not_mutate_advice(self):
        aid = self.add_advice()["id"]
        with self.assertRaisesRegex(ValueError, "явному запросу"):
            Z.counterfactual_premises(self.store, aid, "f:1", "сервер работает на другом порту")
        alt = Z.counterfactual_premises(
            self.store, aid, "f:1", "Сервер S1 работает на порту 9000", explicit=True
        )
        self.assertNotEqual(alt["before"][0]["sha"], alt["after"][0]["sha"])
        self.assertIn("8080", Z.explain_advice(self.store, aid)["premises"][0]["text"])

    def test_secret_or_unaddressable_premise_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "секретные"):
            Z.record_advice(self.store, "пароль: supersecret123", [{"ref": "f:1"}],
                            clock=self.clock, journal=self.journal)
        with self.assertRaisesRegex(ValueError, "адресуем"):
            Z.record_advice(self.store, "совет без ссылок", [],
                            clock=self.clock, journal=self.journal)
        with self.assertRaisesRegex(ValueError, "недоступна"):
            Z.record_advice(self.store, "совет", [{"ref": "f:999"}],
                            clock=self.clock, journal=self.journal)

    def test_owner_speaker_rejects_non_owner_source(self):
        self.store.records["f:2"] = {"text": "Наблюдение из общего чата", "status": "active",
                                      "type": "fact", "source": "chat:session", "source_kind": "chat"}
        with self.assertRaisesRegex(ValueError, r"owner_\*"):
            Z.record_advice(self.store, "совет", [{"ref": "f:2"}], clock=self.clock, journal=self.journal)

    def test_free_premise_text_requires_addressable_ref(self):
        with self.assertRaisesRegex(ValueError, r"ref\+SHA"):
            Z.record_advice(self.store, "совет", [{"ref": "f:1"}], free_premises=["непривязанный текст"],
                            clock=self.clock, journal=self.journal)

    def test_journal_failure_does_not_mask_committed_write(self):
        result = Z.record_advice(self.store, "совет", [{"ref": "f:1"}], clock=self.clock,
                                 journal=RaisingJournal())
        self.assertFalse(result["journaled"])
        self.assertEqual(result["journal_error"], "OSError")
        exp = Z.explain_advice(self.store, result["id"])
        self.assertEqual(exp["status"], "live")
        self.clock.now = 1100.0
        self.store.records["f:1"]["text"] = "Новый текст факта"
        stale = Z.refresh_stale_advice(self.store, clock=self.clock, journal=RaisingJournal())
        self.assertEqual(stale["stale"][0]["id"], result["id"])
        self.assertEqual(stale["journal_failures"][0]["error"], "OSError")
        self.assertEqual(Z.explain_advice(self.store, result["id"])["status"], "stale")


if __name__ == "__main__":
    unittest.main(verbosity=2)

