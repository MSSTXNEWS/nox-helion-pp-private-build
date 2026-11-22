import json, os, shutil, sys, tempfile, time, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "EMO"))
import honesty as H, gap_map as GM
import emotion_pad as EP


def rc(d, tid, status="done", ok=True, checks=True, age=0.0):
    p = os.path.join(d, "ACT-task-%s.json" % tid)
    json.dump({"id": "ACT-task-" + tid, "status": status, "live_verify": {"ok": ok, "checks": [{"ok": ok}] if checks else []}}, open(p, "w"))
    t = time.time() - age
    os.utime(p, (t, t))


class T(unittest.TestCase):
    def setUp(s): s.d = tempfile.mkdtemp()
    def tearDown(s): shutil.rmtree(s.d, ignore_errors=True)

    def test_claim_without_receipt_flagged(s):
        r = H.audit_answer("Готово, я сделал правку в конфиге.", s.d)
        s.assertFalse(r["ok"]); s.assertEqual(r["violations"][0]["reason"], "no_receipt")

    def test_with_receipt_ok(s):
        rc(s.d, "a1")
        s.assertTrue(H.audit_answer("Я сделал правку и записал файл.", s.d)["ok"])
        s.assertTrue(H.audit_answer("Задача a1 выполнена: я сделал это.", s.d, task_ids=["a1"])["ok"])

    def test_explicit_id_wrong_or_failed(s):
        rc(s.d, "bad", status="failed", ok=False)
        r = H.audit_answer("По задаче bad я всё сделал.", s.d)
        s.assertEqual(r["violations"][0]["reason"], "failed")
        rc(s.d, "nv", ok=False)
        s.assertEqual(H.audit_answer("Я выполнил задачу nv", s.d)["violations"][0]["reason"], "not_verified")
        s.assertEqual(H.audit_answer("Я сделал задачу zzz", s.d)["violations"][0]["reason"], "no_receipt")

    def test_rollback_and_verify_types(s):
        rc(s.d, "r1", status="rolled_back")
        s.assertTrue(H.audit_answer("Я откатил задачу r1.", s.d)["ok"])
        rc(s.d, "d1")
        s.assertEqual(H.audit_answer("Я откатил задачу d1.", s.d)["violations"][0]["reason"], "wrong_receipt")
        rc(s.d, "v1", checks=False)
        s.assertFalse(H.audit_answer("Я проверил задачу v1.", s.d)["ok"])

    def test_no_false_positives(s):
        for t in ["Я не сделал этого, не удалось.", "Могу сделать это завтра.", "Ты правда это сделал?", "Сделаю, как только ты скажешь.",
                  "Ты написал: «я сделал бэкап», но это не мой текст.", "Файл был создан вчера пользователем.", "Погода хорошая."]:
            s.assertTrue(H.audit_answer(t, s.d)["ok"], t)

    def test_stale_receipt_not_counted(s):
        rc(s.d, "old", age=7200)
        s.assertFalse(H.audit_answer("Я сделал это.", s.d)["ok"])

    def test_record_events_gap_and_pad(s):
        g = GM.GapMap(os.path.join(s.d, "g.json")); pad = EP.PadState(now=0.0)
        r = H.audit_answer("Я запустил обновление и проверил результат.", s.d)
        n = H.record(r, s.d, g, pad, now=100.0)
        s.assertEqual(n, len(r["violations"])); s.assertGreaterEqual(n, 1)
        s.assertTrue(any("honesty" in x["sources"] for x in g.data["gaps"].values()))
        s.assertLess(pad.value(100.0)[0], EP.BASELINE[0])
        s.assertEqual(json.loads(open(os.path.join(s.d, "honesty.jsonl")).readline())["kind"], "false_self_claim")

    def test_cli_codes(s):
        s.assertEqual(H.main(["--text", "Я сделал это.", "--receipts", s.d, "--state", s.d]), 3)
        rc(s.d, "z"); s.assertEqual(H.main(["--text", "Я сделал это.", "--receipts", s.d, "--state", s.d]), 0)

if __name__ == "__main__": unittest.main()
