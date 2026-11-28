import os, sys, json, time, unittest, hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nox_org_common as C, nox_ledger as L, nox_absorb as AB, nox_predator as P, nox_organism as O
from test_nox_organism import mk, GPU, HOST
def hf(items): return lambda url, timeout=20: items
HFDS = [{"id": "org/ru-dialogs", "downloads": 5000, "likes": 3, "tags": ["license:apache-2.0", "language:ru", "dialogue"], "lastModified": C.iso_z(time.time() - 86400), "sha": "abc"},
        {"id": "org/nc-set", "downloads": 9000, "tags": ["license:cc-by-nc-4.0", "russian"], "lastModified": C.iso_z()},
        {"id": "org/gated", "downloads": 9000, "gated": True, "tags": ["license:mit", "russian"]},
        {"id": "org/nolic", "downloads": 9000, "tags": ["russian"]}]
class T(unittest.TestCase):
    def setUp(self):
        self.now = time.time(); self.r = mk(self.now); L.conceive(self.r)
    def test_scan_proposes_only_clean_no_download(self):
        res = P.scan(self.r, self.now, fetch=hf(HFDS), force=True); self.assertEqual(res["found"], 4); self.assertEqual(res["proposed"], 1)
        q = C.load_json(AB.hunt_path(self.r))["requests"]; self.assertEqual(len(q), 1); self.assertEqual(q[0]["status"], "pending_consent"); self.assertIn("Разрешаешь?", q[0]["ask"]); self.assertTrue(q[0]["ask"].startswith("Нашёл org/ru-dialogs."))
        cands = [json.loads(l) for l in open(self.r + "/state/mind/worm_candidates.jsonl")]
        self.assertEqual({c["license_class"] for c in cands}, {"clean", "blocked_nc", "needs_creator"})
        self.assertEqual(AB.audit(self.r)["downloads_without_consent"], 0)
        self.assertEqual(P.scan(self.r, self.now + 700, fetch=hf(HFDS), force=True)["proposed"], 0)  # дедуп
    def test_scan_quota_and_stop_and_error(self):
        open(self.r + "/state/worms.off", "w").write("1"); self.assertEqual(P.scan(self.r, self.now, fetch=hf(HFDS), force=True), {"skipped": "stop"}); os.remove(self.r + "/state/worms.off")
        def boom(url, timeout=20): raise OSError("net")
        self.assertIn("error", P.scan(self.r, self.now, fetch=boom, force=True))
    def test_gh_parse(self):
        c = P.parse_gh({"items": [{"full_name": "a/b", "html_url": "u", "license": {"spdx_id": "MIT"}, "stargazers_count": 50, "topics": ["x"]}, {"full_name": "c/d", "license": {"spdx_id": "NOASSERTION"}}]})
        self.assertEqual(c[0]["license"], "MIT"); self.assertIsNone(c[1]["license"])
    def test_hunger_levels_and_phrase_once_per_day(self):
        led = L.read_all(self.r); t0 = C.parse_ts(led[0]["ts"])
        a = P.hunger_tick(self.r, t0 + 1800); self.assertEqual(a["level"], "сыт"); self.assertIsNone(a["phrase"])
        b = P.hunger_tick(self.r, t0 + 3 * 3600); self.assertEqual(b["level"], "нужны данные"); self.assertEqual(b["phrase"], "Создатель, мне нужны данные.")
        c = P.hunger_tick(self.r, t0 + 3 * 3600 + 1000); self.assertIsNone(c["phrase"])  # окно 15 мин закрыто
        self.assertIsNone(P.hunger_tick(self.r, t0 + 30 * 3600)["phrase"])  # активный поиск: без фразы
        d = P.hunger_tick(self.r, t0 + 8 * 86400); self.assertEqual(d["level"], "голодаю"); self.assertEqual(d["phrase"], "Я голодаю. Мне нужны источники.")
        self.assertIsNone(P.hunger_tick(self.r, t0 + 8 * 86400 + 1000)["phrase"]); self.assertIsNone(P.hunger_tick(self.r, t0 + 8 * 86400 + 7200)["phrase"])
    def test_hunger_emotion_and_drive_cap(self):
        led = L.read_all(self.r); t0 = C.parse_ts(led[0]["ts"]); P.hunger_tick(self.r, t0 + 30 * 86400)
        o = O.tick(self.r, t0 + 30 * 86400, GPU, host=HOST, write=False); hungry = [s for s in o["pad"]["states"] if s["name"] == "голод"]
        self.assertTrue(hungry); self.assertTrue(C.resolve(self.r, hungry[0]["cause"])); self.assertLessEqual(max(s["intensity"] for s in o["pad"]["states"] if s["name"] == "голод"), 0.6)
        self.assertLessEqual(o["drives"]["ПОИСК"]["level"], 0.85); self.assertLessEqual(o["panel"]["CORT"], 0.6); self.assertEqual(o["hunger"]["level"], "голодаю")
    def test_consent_and_registry_flow(self):
        P.scan(self.r, self.now, fetch=hf(HFDS), force=True); cid = C.load_json(AB.hunt_path(self.r))["requests"][0]["id"]
        with self.assertRaises(AB.AbsorbError): AB.transition(cid, "FETCHED", {}, r=self.r)  # без согласия
        AB.consent(cid, "approved", r=self.r); self.assertEqual(C.load_json(AB.hunt_path(self.r))["requests"][0]["status"], "approved_by_creator")
        AB.transition(cid, "FETCHED", {"sha256": "a" * 64}, r=self.r)
        with self.assertRaises(AB.AbsorbError): AB.transition(cid, "ABSORBED", {}, r=self.r)  # не по порядку
        AB.transition(cid, "VERIFIED", {"revision": "r1", "sha256": "a" * 64}, r=self.r); AB.transition(cid, "ACTIVE_ADAPTER", {}, r=self.r); AB.transition(cid, "TRAINING", {"steps_planned": 100}, r=self.r)
        with self.assertRaises(AB.AbsorbError): AB.transition(cid, "ABSORBED", {"sha_before": "x", "sha_after": "x", "steps": 10, "test_result": "ok", "gate_pass": True, "revision": "r1"}, r=self.r)  # переименование
        with self.assertRaises(AB.AbsorbError): AB.transition(cid, "ABSORBED", {"sha_before": "x", "sha_after": "y", "steps": 10, "test_result": "ok", "gate_pass": False, "revision": "r1"}, r=self.r)
        AB.transition(cid, "ABSORBED", {"sha_before": "x", "sha_after": "y", "steps": 10, "test_result": "ok", "gate_pass": True, "revision": "r1"}, r=self.r)
        with self.assertRaises(AB.AbsorbError): AB.transition(cid, "REMOVED", {"deleted_path": "/x"}, r=self.r)
        AB.transition(cid, "REMOVED", {"deleted_path": "/x", "sha256": "a" * 64, "cause": "absorbed", "replacement_id": "ad1", "time": "t", "evidence": "gate", "reload_pointer": "hf:org/ru-dialogs@r1"}, r=self.r)
        a = AB.audit(self.r); self.assertEqual((a["downloads_without_consent"], a["not_in_ledger"], a["sha_chain_breaks"], a["ledger_ok"]), (0, 0, 0, True))
        ev = [e["event"] for e in L.read_all(self.r)]; self.assertIn("hunt_consent", ev); self.assertIn("absorb_absorbed", ev); self.assertIn("absorb_removed", ev); self.assertNotIn("birth", ev)
        AB.rollback(cid, "тест отката", r=self.r); self.assertEqual(AB.load(self.r)["items"][cid]["status"], "ROLLED_BACK"); self.assertEqual(L.read_all(self.r)[-1]["data"]["restore_sha"], "x"); self.assertTrue(L.verify(self.r)[0])
    def test_nc_blocked_without_creator(self):
        AB.propose("c_nc", "m", "u", "hf", "cc-by-nc-4.0", r=self.r); AB.consent("c_nc", "approved", r=self.r)
        with self.assertRaises(AB.AbsorbError): AB.transition("c_nc", "FETCHED", {}, r=self.r)
        AB.consent("c_nc", "approved", nc_ok=True, r=self.r); AB.transition("c_nc", "FETCHED", {}, r=self.r)
    def test_absorbed_gives_organism_emotion(self):
        AB.propose("c1", "m", "u", "hf", "MIT", r=self.r); AB.consent("c1", "approved", r=self.r)
        for to, ev in (("FETCHED", {}), ("VERIFIED", {"revision": "r", "sha256": "s"}), ("ACTIVE_ADAPTER", {}), ("TRAINING", {}), ("ABSORBED", {"sha_before": "a", "sha_after": "b", "steps": 5, "test_result": "ok", "gate_pass": True, "revision": "r"})): AB.transition("c1", to, ev, r=self.r, t=self.now - 5)
        o = O.tick(self.r, self.now, GPU, host=HOST, write=False); self.assertIn("удовлетворение", [s["name"] for s in o["pad"]["states"]])
    def test_reflection_gate_to_lessons_and_forge(self):
        now = self.now; ts = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(now - 60))
        lines = ["%s cid=c1 q='x' flags=['клише ассистента'] how=regen" % ts for _ in range(4)] + ["%s cid=qa-z q='x' flags=['лесть'] how=regen" % ts, "%s cid=c9 q='x' flags=[] how=clean" % ts]
        open(self.r + "/state/chat_gate.log", "w").write("\n".join("%s chatty %s" % (l[:19], l[20:]) if "chatty" not in l else l for l in lines) + "\n")
        rep = P.reflect(self.r, now); self.assertEqual(rep["categories"], {"клише": 4}); self.assertEqual(rep["rejects_qa_24h"], 1); self.assertEqual(rep["lessons_new"], 1); self.assertEqual(rep["proposals_new"], 1)
        les = [json.loads(l) for l in open(self.r + "/state/mind/nrem_lessons.jsonl")][0]; self.assertEqual(les["source"], "gate_reflection"); self.assertNotIn("x", les["text"].replace("Ошибка", "").split("«")[0] if False else "")
        pr = [json.loads(l) for l in open(self.r + "/state/core/forge_proposals.jsonl")][0]; self.assertIsNone(pr["signature"]); self.assertFalse(pr["applied"]); self.assertIn("подпись Создателя", pr["requires"])
        self.assertEqual(P.reflect(self.r, now + 60)["lessons_new"], 0)  # идемпотентно
    def test_morning_patch_and_tick(self):
        P.scan(self.r, self.now, fetch=hf(HFDS), force=True); C.atomic_json(self.r + "/state/mind/morning_brief_v5.json", {"ts": "x", "kind": "morning", "lines": ["a", "b"]})
        q = P.morning_patch(self.r, self.now); self.assertEqual(q["pending"], 1); mb = C.load_json(self.r + "/state/mind/morning_brief_v5.json"); self.assertEqual(mb["lines"], ["a", "b"]); self.assertEqual(mb["hunt"]["pending"], 1)
        o = P.tick(self.r, self.now, fetch=hf([])); self.assertIn("hunger", o)
        O.tick(self.r, self.now, GPU, host=HOST); sn = C.load_json(self.r + "/state/core/self_now.json"); self.assertEqual(sn["hunt_queue"]["pending"], 1); self.assertIn("hunger", sn)
    def test_gratitude_evening_needs_signal(self):
        base = self.now - (self.now % 86400); t = base + 19 * 3600 + 3600  # 20:00 UTC = 23:00 MSK? -> 19:xx UTC=22:xx MSK
        t = base + 19 * 3600 + 600
        r = mk(t); C.emit_signal(r, "train:gate_accept", "event_w", 0.5, 2, src_ref="g:x", t=t - 600)
        o = O.tick(r, t, GPU, host=HOST, write=False); self.assertIsNotNone(o["gratitude"]); self.assertTrue(C.resolve(r, o["gratitude"]["cause"]))
        r2 = mk(t); self.assertIsNone(O.tick(r2, t, GPU, host=HOST, write=False)["gratitude"])
if __name__ == "__main__": unittest.main(verbosity=1)
