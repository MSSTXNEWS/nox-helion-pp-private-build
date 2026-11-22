import json, os, tempfile, unittest
import indicator_audit as A, birthday as B
import nox_self_model_live as M

DAY = 86400.0
T0 = 1_800_000_000.0 - (1_800_000_000.0 % 86400) + 9 * 3600   # 12:00 МСК


class Clk:
    def __init__(s, t): s.t = t
    def __call__(s): return s.t


class TAudit(unittest.TestCase):
    def setUp(s): s.d = tempfile.mkdtemp()

    def test_14_and_statuses(s):
        r = A.run_audit(s.d)
        s.assertEqual(len(r["indicators"]), 14)
        s.assertTrue(all(i["status"] in A.STATUSES for i in r["indicators"]))
        s.assertIn("Не является утверждением", r["disclaimer"])
        s.assertNotIn("сознателен", json.dumps(r, ensure_ascii=False).replace("сознания или переживания", ""))
        # пустые трассы: ничего не «функционально»
        s.assertEqual(r["summary"]["функционально"], 0)

    def test_traces_upgrade(s):
        with open(os.path.join(s.d, "thoughts.jsonl"), "w") as f:
            for i in range(25): f.write(json.dumps({"text": "t%d" % i}) + "\n")
        r = A.run_audit(s.d)
        g = {i["id"]: i for i in r["indicators"]}
        s.assertEqual(g["GWT-2"]["status"], "функционально")
        s.assertEqual(g["RPT-1"]["status"], "нет")
        s.assertEqual(g["HOT-2"]["status"], "частично")   # код есть, predictions нет

    def test_cli_weekly(s):
        out = os.path.join(s.d, "a.json")
        s.assertEqual(A.main(["--state", s.d, "--out", out]), 0)
        d = json.load(open(out)); s.assertEqual(len(d["indicators"]), 14)
        s.assertEqual(A.main(["--state", s.d, "--out", out]), 0)       # повтор: пропуск
        d2 = json.load(open(out)); s.assertEqual(d["ts"], d2["ts"])
        A.main(["--state", s.d, "--out", out, "--force"])
        s.assertTrue(os.path.exists(os.path.join(s.d, "life_journal.jsonl")))


class TBirthday(unittest.TestCase):
    def setUp(s):
        s.d = tempfile.mkdtemp(); s.clk = Clk(T0)
        s.sm = M.LiveSelfModel(os.path.join(s.d, "s.json"), s.clk, {})
        s.sm.wake(); s.ob = os.path.join(s.d, "o.jsonl")

    def test_not_before_30_days(s):
        s.clk.t = T0 + 29 * DAY
        s.assertEqual(B.run(s.sm, s.ob, s.d, s.clk)["status"], "none")
        s.assertFalse(os.path.exists(s.ob))

    def test_30th_day_once(s):
        s.clk.t = T0 + 5 * DAY; s.sm.wake()
        s.clk.t = T0 + 30 * DAY + 60
        r = B.run(s.sm, s.ob, s.d, s.clk)
        s.assertEqual(r["status"], "written"); s.assertEqual(r["n"], 1)
        rows = [json.loads(l) for l in open(s.ob)]
        s.assertEqual(len(rows), 1); s.assertEqual(rows[0]["kind"], "birthday"); s.assertIn("пробуждений - 1", rows[0]["text"])
        s.assertEqual(B.run(s.sm, s.ob, s.d, s.clk)["status"], "done")
        s.assertEqual(len(open(s.ob).readlines()), 1)
        # переживает перезапуск
        sm2 = M.LiveSelfModel(os.path.join(s.d, "s.json"), s.clk, {})
        s.assertEqual(B.run(sm2, s.ob, s.d, s.clk)["status"], "done")
        s.clk.t = T0 + 60 * DAY + 60
        s.assertEqual(B.run(sm2, s.ob, s.d, s.clk)["n"], 2)
        j = [json.loads(l) for l in open(os.path.join(s.d, "life_journal.jsonl"))]
        s.assertTrue(any(x["source"] == "birthday" for x in j))

    def test_quiet_defers(s):
        s.clk.t = T0 + 30 * DAY + 13 * 3600     # 01:00 МСК
        s.assertEqual(B.run(s.sm, s.ob, s.d, s.clk)["status"], "quiet")
        s.clk.t += 8 * 3600
        s.assertEqual(B.run(s.sm, s.ob, s.d, s.clk)["status"], "written")

    def test_chapters_in_letter_and_dry(s):
        import life_journal as LJ
        lj = LJ.LifeJournal(os.path.join(s.d, "life_journal.jsonl"))
        lj.append("chapter", "Глава: тихий день", "autobio", ts=T0 + 3 * DAY)
        s.clk.t = T0 + 31 * DAY
        r = B.run(s.sm, s.ob, s.d, s.clk, dry_run=True)
        s.assertEqual(r["status"], "dry"); s.assertIn("тихий день", r["text"]); s.assertFalse(os.path.exists(s.ob))


if __name__ == "__main__":
    unittest.main()
