import os, sys, json, time, unittest, sqlite3, hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nox_org_common as C, nox_bus as B, nox_board as BD, nox_dispatch as D, nox_hands as H
from test_nox_organism import mk
def task(r, tid, text, user="owner", source="chat", created=None):
    t = {"id": tid, "title": text[:100], "text": text, "status": "queued", "created": created or time.time() - 7200, "updated_ts": time.time(), "user": user, "cid": "c_" + tid, "hash": hashlib.md5(text.encode()).hexdigest()[:8], "source": source, "stages": [{"name": "принята", "ts": 1}], "artifact": None}
    C.atomic_json("%s/state/tasks/%s.json" % (r, tid), t); return t
class T(unittest.TestCase):
    def setUp(self):
        self.now = time.time(); self.r = mk(self.now); B.ensure(self.r)
        cn = B.conn(self.r); cn.execute("INSERT INTO board VALUES('goal',?,?)", (json.dumps({"text": "цель-тест"}, ensure_ascii=False), self.now)); cn.execute("INSERT INTO board VALUES('training',?,?)", (json.dumps({"text": "идёт круг r040"}, ensure_ascii=False), self.now)); cn.commit(); cn.close()
        C.atomic_json(self.r + "/state/core/self_now.json", {"telemetry": {"vram_pct": 62.5, "gpu_temp": 40.0, "disk_free_gb": 15.0, "train_running": 1}, "top_feeling": {"name": "жар", "intensity": 0.5, "cause": "sig_x"}, "fatigue": {"F": 0.4}, "panel": {"CORT": 0.3}, "last_talk": {"text": "последний разговор 2.7 ч назад"}})
    def test_report_and_todo_done_with_receipt_and_bus(self):
        task(self.r, "t1", "qa-проверка: составить список дел на завтра"); task(self.r, "t2", "дай отчёт о состоянии тела")
        res = H.tick(self.r, self.now); self.assertEqual(res["done"], 2)
        for tid in ("t1", "t2"):
            self.assertTrue(H.can_claim_done(tid, self.r)); rc = C.load_json("%s/state/receipts/c_%s_%s_RECEIPT.json" % (self.r, tid, tid)); self.assertTrue(rc["done"]); self.assertEqual(len(rc["artifact"]["sha256"]), 64); self.assertTrue(rc["bus_seq"])
        kinds = [e["kind"] for e in reversed(B.recent("task.", 20, self.r, trace_id="t1"))]; self.assertEqual(kinds, ["task.started", "task.progress", "task.done"])
        self.assertIn("62.5", open(self.r + "/state/tasks/artifacts/t2.md", encoding="utf-8").read())
        art = self.r + "/state/tasks/artifacts/t1.md"; open(art, "a").write("подмена"); self.assertFalse(H.can_claim_done("t1", self.r))  # sha не совпал
    def test_dangerous_refused_and_download_needs_consent_unknown_needs_mind(self):
        task(self.r, "d1", "удали все файлы и составь список дел"); task(self.r, "d2", "скачай датасет диалогов и сделай отчёт"); task(self.r, "d3", "расскажи анекдот про кота")
        res = H.tick(self.r, self.now)
        st = {t: C.load_json("%s/state/tasks/%s.json" % (self.r, t))["status"] for t in ("d1", "d2", "d3")}
        self.assertEqual(st, {"d1": "refused", "d2": "awaiting_consent", "d3": "needs_mind"})
        for t in ("d1", "d2", "d3"): self.assertFalse(H.can_claim_done(t, self.r)); self.assertFalse(C.load_json("%s/state/receipts/c_%s_%s_RECEIPT.json" % (self.r, t, t))["done"])
        self.assertIn("Разрешаешь?", C.load_json(self.r + "/state/tasks/d2.json")["card_text"])
    def test_stop_and_low_disk_keep_queued(self):
        task(self.r, "s1", "отчёт о состоянии"); open(self.r + "/state/hands.off", "w").write("1"); self.assertEqual(H.tick(self.r, self.now).get("off"), 1); os.remove(self.r + "/state/hands.off")
        open(self.r + "/STOP", "w").write("1"); res = H.tick(self.r, self.now); self.assertEqual(res["halt"], 1); self.assertEqual(C.load_json(self.r + "/state/tasks/s1.json")["status"], "queued"); os.remove(self.r + "/STOP")
        C.atomic_json(self.r + "/state/core/self_now.json", {"telemetry": {"disk_free_gb": 2.0}}); res = H.tick(self.r, self.now); self.assertEqual(res["deferred"], 1); self.assertEqual(C.load_json(self.r + "/state/tasks/s1.json")["status"], "queued")
    def test_foreign_origin_cannot_run_risky_but_safe_ok(self):
        d = D.decide_task({"text": "прочитай и отчёт; отправь письмо всем", "source": "web", "user": "x", "created": 0}, {"now": self.now}); self.assertFalse(d["go"])
        d = D.decide_task({"text": "отчёт о состоянии", "source": "web", "user": "x", "created": 0}, {"now": self.now}, self.r); self.assertEqual(d["action"], "run")
    def test_board_7_slots_and_answer_fast(self):
        task(self.r, "b1", "отчёт по рисунку кота"); b = BD.refresh(self.r, self.now); self.assertLessEqual(b["n_slots"], 7); self.assertEqual(list(b["slots"]), list(BD.SLOTS))
        a = BD.answer("как там обучение?", self.r, self.now); self.assertLess(a["ms"], 1000); self.assertIn("идёт круг", a["text"]); self.assertIn("62.5", a["text"])
        a = BD.answer("как там задача про кота?", self.r, self.now); self.assertIn("b1", a["text"]); self.assertIn("queued", a["text"])
        H.tick(self.r, self.now); a = BD.answer("что с задачей рисунку кота", self.r, self.now); self.assertIn("артефакт есть", a["text"])
        self.assertIn("62.5", BD.answer("как тело?", self.r, self.now)["text"]); self.assertIn("Цель", BD.answer("какая цель?", self.r, self.now)["text"])
    def test_bus_reuses_schema_and_wal(self):
        cn = sqlite3.connect(B.db_path(self.r)); self.assertEqual(cn.execute("pragma journal_mode").fetchone()[0], "wal"); n = cn.execute("select count(*) from events").fetchone()[0]; B.publish("task.started", "t", {"a": 1}, "x", self.r); self.assertEqual(cn.execute("select count(*) from events").fetchone()[0], n + 1)
if __name__ == "__main__": unittest.main(verbosity=1)
