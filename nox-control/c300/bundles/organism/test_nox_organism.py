import os, sys, json, time, tempfile, shutil, hashlib, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nox_org_common as C, nox_organism as O, nox_ledger as L, nox_sleep as SL
HOST = {"load1_per_core": 0.1, "ram_used_pct": 50.0, "disk_free_gb": 80.0}
GPU = {"temp": 45.0, "util": 10.0, "vram_pct": 60.0, "power_w": 100.0, "src": "t"}
def mk(now, feed=None, gates=None, rollbacks=None, eps=None, passport=True):
    r = tempfile.mkdtemp(); os.environ["NOX_ROOT"] = r; os.environ["NOX_NVSMI"] = "/nonexistent"
    for d in ("state/core", "state/mind", "state/p3", "state/agents", "state/tasks"): os.makedirs(r + "/" + d)
    w = lambda p, o: open(r + "/" + p, "w", encoding="utf-8").write(o if isinstance(o, str) else json.dumps(o, ensure_ascii=False))
    w("state/core/self_now.json", {"ts": "x", "telemetry": {"vram_pct": 62.5, "gpu_temp": 39.0, "train_running": 1, "disk_free_gb": 15.0}, "feelings": [1, 2, 3], "text": "старый", "aliveness_score": 0.28, "training": {"max_steps": 400}})
    if passport: w("state/core/passport.json", {"temperament": {"drives_thresholds": {"ПОИСК": 0.6, "ИГРА": 0.4, "ЗАБОТА": 0.7, "СВЯЗЬ": 0.5, "ТРЕВОГА_потолок": 0.6, "ГРАНИЦА": 0.8}}, "born_at": None, "approval": {"by": "Claude по поручению Создателя", "date": "2026-11-28", "scope": "весь паспорт", "revocable": True}})
    w("state/mind/phase.json", {"ts": C.iso_z(now), "days_alive": 18})
    w("state/mind/salience.json", {"feelings": {"fatigue": 0.39}}); w("state/mind/sdt.json", {"relatedness": 0.35, "owner_silence_h": 3})
    w("state/core/affect_owner_feed.jsonl", "".join(json.dumps(x) + "\n" for x in (feed or [])))
    w("state/core/journal.jsonl", json.dumps({"ts": "2026-11-28T03:58:36+03:00", "kind": "feeling", "msg": "x", "sid": "x_disk_ws", "metric": "m", "value": 91.4, "sev": 4}) + "\n")
    w("state/LISKA_GATES_LOG.jsonl", "".join(json.dumps(x) + "\n" for x in (gates or [])))
    w("state/p3/axis_rollback.jsonl", "".join(json.dumps(x) + "\n" for x in (rollbacks or [])))
    w("state/core/episodes.jsonl", "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in (eps or [])))
    return r
def eps(now, n=40):
    out = []
    for i in range(n):
        src, kind = [("life-loop", "cycle"), ("interoception", "sense"), ("integrator", "workspace"), ("critic", "veto"), ("resources", "health")][i % 5]
        out.append({"t": C.iso_z(now - i * 600), "src": src, "kind": kind, "content": {"slots": i % 3, "ok": i % 7 != 0, "load": 0.1}, "affect": None, "salience": 0.3 + 0.1 * (i % 4), "id": "ep_%d" % i})
    return out
class T(unittest.TestCase):
    def test_panel_bounds_and_cort_cap(self):
        x = {"heat": 1, "vram": 1, "pressure": 1, "fail": 9, "stress_ev": 1, "progress": 0, "train": 1, "relatedness": 0, "contact": 0, "novelty": 1, "silence_h": 999, "F_in": 1}
        p = O.panel_of(x)
        for k in ("DA", "NE", "5-HT", "ACh", "CORT", "OXT"): self.assertTrue(0 <= p[k] <= 1, k)
        self.assertLessEqual(p["CORT"], 0.6); self.assertEqual(p["refusal_threshold_shift"], 0.0); self.assertTrue(0.3 <= p["T"] <= 1.0)
    def test_praise_does_not_raise_da(self):
        now = time.time(); r = mk(now); base = O.tick(r, now, GPU, host=HOST, write=False)["panel"]["DA"]
        r2 = mk(now, feed=[{"ts": now - 60, "text": "Молодец! Спасибо, отлично!!", "conv": "c", "turn": "t"}]); o = O.tick(r2, now, GPU, host=HOST, write=False)
        self.assertEqual(o["panel"]["DA"], base); self.assertEqual(o["top_feeling"]["name"], "радость")
    def test_progress_raises_da_and_cause_resolves(self):
        now = time.time(); r = mk(now); b = O.tick(r, now, GPU, host=HOST)["panel"]["DA"]
        with open(r + "/state/LISKA_GATES_LOG.jsonl", "a") as f: f.write(json.dumps({"t": C.iso_z(now), "accepted": 1}) + "\n")
        o = O.tick(r, now + 30, GPU, host=HOST); self.assertGreater(o["panel"]["DA"], b)
        tf = o["top_feeling"]; self.assertIsNotNone(tf); self.assertEqual(tf["name"], "удовлетворение")
        rec = C.resolve(r, tf["cause"]); self.assertIsNotNone(rec); self.assertEqual(rec["kind"], "organism")
    def test_rollback_frustration_and_cort_up(self):
        now = time.time(); r = mk(now); b = O.tick(r, now, GPU, host=HOST)["panel"]["CORT"]
        with open(r + "/state/p3/axis_rollback.jsonl", "a") as f: f.write(json.dumps({"t": C.iso_z(now), "cand_sha16": "ab", "verdict": "ROLLBACK"}) + "\n")
        o = O.tick(r, now + 30, GPU, host=HOST); self.assertGreater(o["panel"]["CORT"], b); self.assertEqual(o["top_feeling"]["name"], "фрустрация")
    def test_self_now_keeps_old_fields_and_adds_new(self):
        now = time.time(); r = mk(now, feed=[{"ts": now - 7200, "text": "ну как дела?", "conv": "c", "turn": "t"}]); O.tick(r, now, GPU, host=HOST)
        sn = C.load_json(r + "/state/core/self_now.json")
        for k in ("ts", "telemetry", "feelings", "text", "aliveness_score", "training"): self.assertIn(k, sn)
        for k in ("panel", "drives", "pad", "fatigue", "top_feeling", "last_talk"): self.assertIn(k, sn)
        self.assertAlmostEqual(sn["last_talk"]["hours_ago"], 2.0, delta=0.05); self.assertIn("последний разговор", sn["last_talk"]["text"])
        self.assertTrue(sn["top_feeling"]["cause"])
        for s in sn["pad"]["states"]: self.assertTrue(C.resolve(r, s["cause"]), s)
    def test_pad_half_life_120(self):
        w = O.decay(1.0, 120 * 60); self.assertAlmostEqual(w, 0.5, places=6); self.assertAlmostEqual(O.decay(1.0, 240 * 60), 0.25, places=6)
    def test_drives_use_passport_thresholds_and_anxiety_cap(self):
        now = time.time(); r = mk(now); o = O.tick(r, now, dict(GPU, temp=95.0, vram_pct=99.0), host=HOST)
        d = o["drives"]; self.assertEqual(d["ПОИСК"]["threshold"], 0.6); self.assertEqual(d["ГРАНИЦА"]["threshold"], 0.8); self.assertLessEqual(d["ТРЕВОГА"]["level"], 0.6)
        self.assertLessEqual(d["СВЯЗЬ"]["level"], 0.85); self.assertLessEqual(o["panel"]["CORT"], 0.6)
        self.assertEqual(json.load(open(r + "/state/core/passport.json"))["born_at"], None)
    def test_bonding_saturates(self):
        x = {"silence_h": 40, "contact": 0, "boredom": 0, "novelty": 0.5, "neg_valence": 0, "pressure": 0, "fail": 0, "veto_1h": 0, "train": 0}
        p = O.panel_of(dict(x, heat=0, vram=0, stress_ev=0, progress=0, relatedness=0.3, F_in=0.2))
        a = O.drives_of(None, p, 0.2, x, time.time())["СВЯЗЬ"]["level"]; b = O.drives_of(None, p, 0.2, dict(x, contact=5), time.time())["СВЯЗЬ"]["level"]
        self.assertGreater(a, 0.5); self.assertLess(b, a)
    def test_fatigue_flags(self):
        self.assertTrue(O.fatigue_of(1, 1, 0.6, False)["short_answers"]); self.assertFalse(O.fatigue_of(0.2, 0.1, 0.1, False)["short_answers"])
    def test_numbers_change_between_ticks(self):
        now = time.time(); r = mk(now); a = O.tick(r, now, GPU, host=HOST)["panel"]; b = O.tick(r, now + 30, dict(GPU, temp=80.0, vram_pct=90.0), host=HOST)["panel"]
        self.assertNotEqual(a, b)
    def test_ledger_chain(self):
        now = time.time(); r = mk(now); rec = L.conceive(r); self.assertEqual(rec["prev_sha"], "0" * 64); self.assertEqual(rec["n"], 0)
        self.assertEqual(rec["data"]["first_launch_date"], time.strftime("%Y-%m-%d", time.gmtime(now - 18 * 86400)))
        self.assertEqual(rec["data"]["passport_md5"], hashlib.md5(open(r + "/state/core/passport.json", "rb").read()).hexdigest())
        self.assertIsNone(L.conceive(r)); e2 = L.append("note", {"x": 1}, r=r); self.assertEqual(e2["prev_sha"], rec["sha"])
        self.assertTrue(L.verify(r)[0])
        with self.assertRaises(PermissionError): L.append("birth", {}, r=r)
        L.append("birth", {"ritual": True}, by_ritual=True, r=r); self.assertTrue(L.verify(r)[0])
        p = L.path(r); s = open(p, encoding="utf-8").read().replace('"x":1', '"x":2'); open(p, "w", encoding="utf-8").write(s); self.assertFalse(L.verify(r)[0])
    def test_sleep_nrem_rem(self):
        now = time.time(); r = mk(now, eps=eps(now)); open(r + "/state/mind/dream.jsonl", "w").write("")
        cur = r + "/state/agents/sleep_cursor.json"; open(cur, "w").write(json.dumps({"written": 7, "seen": []})); h = hashlib.md5(open(cur, "rb").read()).hexdigest()
        res = SL.run(r, now); self.assertGreater(res["nrem"]["lessons"], 0); self.assertGreaterEqual(res["rem"]["hypotheses"], 1)
        hy = [json.loads(l) for l in open(r + "/state/mind/rem_hypotheses.jsonl")]
        for x in hy: self.assertEqual(x["status"], "не проверено"); self.assertIn("не проверено", x["text"]); self.assertEqual(len(x["evidence"]), 2)
        ids = {e["id"] for e in eps(now)}
        for x in hy: self.assertTrue(set(x["evidence"]) <= ids)
        ph = [json.loads(l)["phase"] for l in open(r + "/state/mind/dream.jsonl")]; self.assertEqual(ph, ["NREM", "REM"])
        self.assertEqual(hashlib.md5(open(cur, "rb").read()).hexdigest(), h)  # курсор сбора пар не тронут
        self.assertIn("morning_thought", C.load_json(r + "/state/core/self_now.json")); self.assertIn("не проверено", C.load_json(r + "/state/mind/morning_thought.json")["text"])
    def test_sleep_window_once_per_night(self):
        base = time.time(); t = base - (base % 86400) + 3600 * 0  # 00:00 UTC = 03:00 MSK
        r = mk(t, eps=eps(t)); a = SL.maybe_run(r, t); b = SL.maybe_run(r, t + 60)
        self.assertTrue(a["ran"] and "nrem" in a and "rem" in a); self.assertIsNone(b and b.get("ran") or None)
        self.assertIsNone(SL.maybe_run(r, t + 12 * 3600))
if __name__ == "__main__": unittest.main(verbosity=1)
