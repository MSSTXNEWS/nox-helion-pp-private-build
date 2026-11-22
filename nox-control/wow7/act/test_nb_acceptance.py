import json, os, sys, unittest
HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(HERE, "acceptance_nb.json")


class TestNBAcceptance(unittest.TestCase):
    def setUp(self):
        self.d = json.load(open(P, encoding="utf-8"))

    def test_counts_and_ids(self):
        it = self.d["items"]
        self.assertEqual(len(it), 56)
        self.assertEqual(len({x["id"] for x in it}), 56)
        self.assertEqual(sum(x["kind"] == "living12" for x in it), 12)
        self.assertEqual(sum(x["kind"] == "nox100_infra" for x in it), 44)

    def test_nothing_claimed_as_run(self):
        for x in self.d["items"]:
            self.assertEqual(x["state"], "NOT_RUN")
            self.assertIsNone(x["native_result"])

    def test_every_item_has_criteria_and_evidence(self):
        for x in self.d["items"]:
            self.assertTrue(x["pass_if"] and x["evidence"], x["id"])

    def test_offline_tools_exist(self):
        root = os.path.dirname(HERE)
        for x in self.d["items"]:
            t = x.get("covered_offline_by")
            if not t:
                continue
            for part in t.split(";"):
                path = part.strip().split(" ")[0]
                if "/" in path and not path.startswith("GENOME nb"):
                    self.assertTrue(os.path.exists(os.path.join(root, path.rstrip(","))), (x["id"], path))

    def test_text_cases_not_duplicated_in_infra(self):
        ids = {x["source"].split(":")[1] for x in self.d["items"] if x["kind"] == "nox100_infra"}
        m4 = json.load(open(os.path.join(os.path.dirname(HERE), "MIND", "M4_BENCH", "tasks", "nb100.json"), encoding="utf-8"))
        m4ids = {t["id"][3:] for t in m4["tasks"]}
        self.assertFalse(ids & m4ids)


if __name__ == "__main__":
    unittest.main()
