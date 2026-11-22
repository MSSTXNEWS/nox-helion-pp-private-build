import collections
import json
import os
import random
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import traits as T
import traits_api as API
import nightly
import development as D
import personality as P

DAY = 86400.0
CUR, DIR, LOY = "persona.trait.curiosity", "persona.trait.directness", "persona.trait.music_interest"


class Base(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.t = [1_000_000.0]
        self.clock = lambda: self.t[0]
        self.tr = T.Traits(os.path.join(self.d, "traits.json"), clock=self.clock)
        self.dev = D.Development(os.path.join(self.d, "dev.json"), clock=self.clock)
        self.per = P.Personality(os.path.join(self.d, "per.json"), clock=self.clock, rng=random.Random(1))

    def feed(self, tid, delta, n, prefix="e"):
        for i in range(n):
            self.tr.observe(tid, delta, "эпизод %s %s %d" % (tid, prefix, i), "%s-%s-%d" % (prefix, tid[-6:], i))

    def sleep(self, per=None):
        self.t[0] += DAY
        return self.tr.consolidate(self.dev, per)


class TestCatalog(Base):
    def test_seed_64_in_8_categories(self):
        seed = T.load_seed()
        self.assertEqual(len(seed), 62)
        self.assertEqual(sorted(collections.Counter(s["category"] for s in seed).values()), [6] + [8] * 7)
        self.assertEqual(len(self.tr.traits), 62)
        for t in self.tr.traits.values():
            self.assertEqual((t["minimum"], t["maximum"], t["value"], t["initial_state"], t["mode"]),
                             (1, 10, 5.0, "UNVERIFIED_NEUTRAL", "REVIEW_ONLY" if t["sensitive"] else "AUTO"))

    def test_sensitive_review_only_until_signed(self):
        """Черты 33-48 (ценности/политика, отношения): REVIEW_ONLY до подписи Создателя; значение не двигается, идёт предложение."""
        sens = [t for t in self.tr.traits.values() if t["sensitive"]]
        self.assertEqual(len(sens), 14)
        self.assertTrue(all(t["mode"] == "REVIEW_ONLY" and not t["auto_adjustable"] for t in sens))
        self.assertTrue(all(t["mode"] == "AUTO" for t in self.tr.traits.values() if not t["sensitive"]))
        n = self.tr.sign_sensitive()
        self.assertEqual(n, 14)
        self.assertTrue(all(t["mode"] == "AUTO" for t in self.tr.traits.values()))
        self.assertTrue(self.tr.sensitive_signed)

    def test_base_open_facets_closed(self):
        base = [t for t in self.tr.traits.values() if t["open"]]
        self.assertEqual(len(base), 21)
        self.assertTrue(all(t["category"] in T.BASE_CATS or t["trait_id"][len(T.PREFIX):] in T.BASE_IDS for t in base))
        closed = self.tr.api_list(self.dev)["traits"]
        self.assertTrue(all(r["value"] is None and r["missing"] for r in closed if not r["open"]))
        self.assertEqual(self.tr.traits[CUR]["opened_reason"][:7], "базовая")

    def test_persistence(self):
        self.feed(CUR, 1, 6)
        self.sleep()
        v = self.tr.traits[CUR]["value"]
        tr2 = T.Traits(self.tr.path, clock=self.clock)
        self.assertEqual(tr2.traits[CUR]["value"], v)
        self.assertEqual(len(tr2.traits), 62)


class TestEvidenceAndDrift(Base):
    def test_needs_three_independent_episodes(self):
        self.feed(CUR, 1, 2)
        self.assertEqual(self.sleep()["changes"], [])
        self.assertEqual(self.tr.traits[CUR]["value"], 5.0)
        self.assertEqual(self.tr.traits[CUR]["initial_state"], "UNVERIFIED_NEUTRAL")
        self.tr.observe(CUR, 1, "третий независимый эпизод", "e-third")
        self.assertEqual(len(self.sleep()["changes"]), 1)
        self.assertEqual(self.tr.traits[CUR]["initial_state"], "EARNED")

    def test_duplicates_ignored(self):
        self.assertTrue(self.tr.observe(CUR, 1, "читал про звёзды", "ep1"))
        self.assertFalse(self.tr.observe(CUR, 1, "иной текст", "ep1"))                 # тот же эпизод
        self.assertFalse(self.tr.observe(CUR, 1, "  Читал про ЗВЁЗДЫ ", "ep2"))        # тот же текст
        self.assertEqual(self.tr.traits[CUR]["evidence_count"], 1)
        with self.assertRaises(ValueError):
            self.tr.observe(CUR, 1, "без эпизода", "")

    def test_daily_cap_and_scale(self):
        self.dev.s["phase"] = "childhood"                                   # scale 1.0
        self.feed(CUR, 1, 10)
        self.sleep()
        step = self.tr.traits[CUR]["value"] - 5.0
        self.assertAlmostEqual(step, T.CAP_PTS, places=3)
        self.assertAlmostEqual(T.CAP_PTS / 9, P.DRIFT_CAP)
        self.feed(CUR, 1, 10, "b")
        self.t[0] += 3600
        self.tr.consolidate(self.dev)                                       # в те же сутки бюджета нет
        self.assertAlmostEqual(self.tr.traits[CUR]["value"] - 5.0, T.CAP_PTS, places=3)
        self.sleep()                                                        # новые сутки - сдвиг продолжается
        self.assertGreater(self.tr.traits[CUR]["value"], 5.0 + T.CAP_PTS + 0.1)

    def test_birth_phase_slower(self):
        self.feed(CUR, 1, 10)
        self.sleep()
        self.assertAlmostEqual(self.tr.traits[CUR]["value"] - 5.0, T.CAP_PTS * 0.25, places=3)

    def test_journal_has_why_and_evidence(self):
        self.feed(CUR, 1, 6)
        self.sleep()
        j = [j for j in self.tr.journal if j["kind"] == "drift"][-1]
        self.assertIn("эпизод", j["why"])
        self.assertTrue(self.tr.why(CUR))
        self.assertEqual(self.tr.traits[CUR]["last_reason"], j["why"])


class TestModes(Base):
    def test_manual_lock_never_moves(self):
        self.tr.set_value(CUR, 4, "владелец: слишком много", lock=True)
        self.assertEqual(self.tr.traits[CUR]["mode"], "MANUAL_LOCK")
        self.feed(CUR, 1, 10)
        for _ in range(3):
            self.sleep()
        self.assertEqual(self.tr.traits[CUR]["value"], 4.0)
        self.assertEqual(self.tr.traits[CUR]["evidence_count"], 10)
        self.assertTrue(any(j["kind"] == "lock_skip" for j in self.tr.journal))

    def test_return_to_auto(self):
        self.tr.set_value(CUR, 7, lock=True)
        self.tr.set_mode(CUR, "AUTO")
        self.assertIsNone(self.tr.traits[CUR]["owner_override"])
        self.feed(CUR, -1, 8)
        self.sleep()
        self.assertLess(self.tr.traits[CUR]["value"], 7.0)

    def test_review_only_waits_for_owner(self):
        self.tr.set_mode(CUR, "REVIEW_ONLY")
        self.feed(CUR, 1, 8)
        rep = self.sleep()
        self.assertEqual(rep["proposed"], [CUR])
        self.assertEqual(self.tr.traits[CUR]["value"], 5.0)
        prop = self.tr.traits[CUR]["proposal"]["value"]
        self.assertGreater(prop, 5.0)
        self.tr.approve_change(CUR)
        self.assertEqual(self.tr.traits[CUR]["value"], prop)
        self.feed(CUR, 1, 8, "r")
        self.sleep()
        self.tr.reject_change(CUR)
        self.assertEqual(self.tr.traits[CUR]["value"], prop)
        self.assertIsNone(self.tr.traits[CUR]["proposal"])

    def test_bad_mode(self):
        with self.assertRaises(ValueError):
            self.tr.set_mode(CUR, "WILD")

    def test_undo_returns_previous_state(self):
        self.feed(CUR, 1, 8)
        self.sleep()
        v1 = self.tr.traits[CUR]["value"]
        self.tr.set_value(CUR, 9)
        self.assertEqual(self.tr.undo_last(CUR), v1)
        self.assertEqual(self.tr.traits[CUR]["value"], v1)
        self.assertEqual(self.tr.traits[CUR]["initial_state"], "EARNED")


class TestFacets(Base):
    def test_closed_facet_collects_but_stays_closed(self):
        self.feed(LOY, 1, 4)
        self.assertEqual(self.sleep()["opened"], [])
        self.assertFalse(self.tr.traits[LOY]["open"])
        self.assertIn("фаза", " ".join(self.tr.unlock_missing(self.tr.traits[LOY], self.dev)))

    def test_opens_on_phase_milestone_and_episodes(self):
        self.feed(LOY, 1, 3)
        self.dev.s["phase"] = "youth"
        self.assertEqual(self.sleep()["opened"], [])                         # нет вехи first_taste
        self.dev.milestone("first_taste", "вкус из эксперимента")
        self.dev.s["phase"] = "childhood"
        self.assertEqual(self.sleep()["opened"], [])                         # фаза мала
        self.dev.s["phase"] = "youth"
        rep = self.sleep()
        self.assertEqual(rep["opened"], [LOY])
        self.assertTrue(self.tr.traits[LOY]["open"])
        self.assertIn("first_taste", self.tr.traits[LOY]["opened_reason"])
        self.sleep()                                                         # накопленное применяется после открытия
        self.assertGreater(self.tr.traits[LOY]["value"], 5.0)

    def test_open_limit_per_sleep(self):
        self.dev.s["phase"] = "maturity"
        self.dev.s["milestones"] = {k: {"ts": 0, "detail": ""} for k in D.MILESTONES}
        for t in self.tr.traits.values():
            if not t["open"]:
                self.feed(t["trait_id"], 1, 3, "o")
        self.assertEqual(len(self.sleep()["opened"]), T.MAX_OPEN_PER_SLEEP)

    def test_romance_traits_removed(self):
        for k in ("romantic_expression", "relationship_exclusivity"):
            self.assertNotIn("persona.trait." + k, self.tr.traits)
        t = self.tr.traits["persona.trait.affection_style"]
        self.assertTrue(t["no_vows"] and t["sensitive"])
        self.assertIn("клятв", t["scope_note"])


class TestProposals(Base):
    def eps(self, n=3, tag="x"):
        return [{"id": "%s%d" % (tag, i), "text": "изучал городскую среду %s %d" % (tag, i)} for i in range(n)]

    def card(self, **kw):
        a = dict(label_ru="Интерес к архитектуре городов", definition_ru="изучает устройство и планировку городов",
                 category="Интересы", reason="три независимых исследования урбанистики", episodes=self.eps(), value_hint=8, dev=self.dev)
        a.update(kw)
        return self.tr.propose_trait(**a)

    def test_flow_65_and_66(self):
        self.dev.s["phase"] = "youth"
        r = self.card()
        self.assertEqual(r["status"], "PENDING")
        self.assertEqual(r["trait_id"], "persona.trait.interes_k_arhitekture_gorodov")
        self.assertEqual(len(self.tr.api_list(self.dev)["proposals"]), 1)
        self.assertEqual(self.tr.decide_proposal(r["id"], "approve"), "APPROVED")
        t = self.tr.traits[r["trait_id"]]
        self.assertEqual((t["kind"], t["open"], t["mode"], t["evidence_count"]), ("discovered", True, "AUTO", 3))
        self.assertEqual(set(t["anchors"]), {"1", "5", "10"})
        r2 = self.card(label_ru="Любовь к ночному небу", definition_ru="наблюдает звёзды и планеты", episodes=self.eps(3, "y"),
                       reason="эпизоды про астрономию")
        self.tr.decide_proposal(r2["id"], "approve")
        self.assertEqual(len(self.tr.traits), 64)
        self.sleep()
        self.assertGreater(t["value"], 5.0)
        self.assertEqual(t["initial_state"], "EARNED")

    def test_gates(self):
        self.assertEqual(self.card()["status"], "TOO_EARLY")                     # фаза рождения
        self.dev.s["phase"] = "youth"
        self.assertEqual(self.card(episodes=self.eps(2))["status"], "INSUFFICIENT")
        same = [{"id": "a", "text": "один"}, {"id": "b", "text": "один"}, {"id": "c", "text": "один"}]
        self.assertEqual(self.card(episodes=same)["status"], "INSUFFICIENT")      # один материал трижды

    def test_dedup(self):
        self.dev.s["phase"] = "youth"
        r = self.card(label_ru="Любознательность", definition_ru="повторно изучает неизвестные темы")
        self.assertEqual((r["status"], r["of"]), ("DUPLICATE", CUR))
        self.assertEqual(self.card()["status"], "PENDING")
        self.assertEqual(self.card(definition_ru="планировка городов", episodes=self.eps(3, "q"))["status"], "DUPLICATE")

    def test_block_and_review(self):
        self.dev.s["phase"] = "youth"
        r = self.card()
        self.tr.decide_proposal(r["id"], "review")
        self.assertEqual(self.tr.api_list(self.dev)["proposals"][0]["status"], "REVIEW")
        self.tr.decide_proposal(r["id"], "block")
        self.assertEqual(self.tr.api_list(self.dev)["proposals"], [])
        self.assertEqual(self.card(episodes=self.eps(3, "z"))["status"], "BLOCKED")
        self.assertNotIn("persona.trait.interes_k_arhitekture_gorodov", self.tr.traits)
        with self.assertRaises(KeyError):
            self.tr.decide_proposal(r["id"], "approve")

    def test_weekly_limit(self):
        self.dev.s["phase"] = "youth"
        names = ["Тяга к шахматам", "Любовь к ботанике", "Интерес к картографии", "Склонность к каллиграфии"]
        st = [self.card(label_ru=n, definition_ru="отдельное занятие номер %d" % i, episodes=self.eps(3, "w%d" % i))["status"]
              for i, n in enumerate(names)]
        self.assertEqual(st, ["PENDING"] * 3 + ["LIMIT"])

    def test_autonomous_not_for_sensitive(self):
        self.dev.s["phase"] = "youth"
        self.tr.autonomy = True
        self.assertEqual(self.card()["status"], "AUTO_APPROVED")
        r = self.card(label_ru="Любимый певец", definition_ru="тянется к одному исполнителю", category="Отношения и вкусы",
                      episodes=self.eps(3, "s"), reason="слушал и возвращался")
        self.assertEqual(r["status"], "PENDING")
        r = self.card(label_ru="Взгляд на налоги", definition_ru="позиция по налогам", category="Ценности, философия, политика",
                      episodes=self.eps(3, "p"), reason="прочитал разное")
        self.assertEqual(r["status"], "PENDING")

    def test_archive_discovered_only(self):
        self.dev.s["phase"] = "youth"
        r = self.card()
        self.tr.decide_proposal(r["id"], "approve")
        self.tr.archive(r["trait_id"])
        self.assertNotIn(r["trait_id"], [x["id"] for x in self.tr.api_list(self.dev)["traits"]])
        with self.assertRaises(ValueError):
            self.tr.archive(CUR)


class TestSnapshots(Base):
    def test_rollback_restores_and_removes_new_trait(self):
        self.tr.snapshot("keep")
        self.dev.s["phase"] = "youth"
        r = self.tr.propose_trait("Тяга к картам", "рисует карты местности", "Интересы", "три эпизода",
                                                                       [{"id": str(i), "text": "карта %d" % i} for i in range(3)], dev=self.dev)
        self.tr.decide_proposal(r["id"], "approve")
        self.tr.set_value(CUR, 9, lock=True)
        self.tr.rollback("keep")
        self.assertEqual(self.tr.traits[CUR]["value"], 5.0)
        self.assertEqual(self.tr.traits[CUR]["mode"], "AUTO")
        self.assertNotIn(r["trait_id"], self.tr.traits)
        self.assertTrue(any(j["kind"] == "rollback" for j in self.tr.journal))

    def test_auto_snapshot_each_sleep_and_cap(self):
        for _ in range(T.MAX_SNAPSHOTS + 5):
            self.sleep()
        self.assertEqual(len([k for k in self.tr.snapshots if k.startswith("auto-")]), T.MAX_SNAPSHOTS)


class TestPerLink(Base):
    def test_axes_are_aggregates_of_earned_traits(self):
        self.assertTrue(all(d["target"] is None for d in self.tr.axis_targets().values()))   # 5 без доказательств не в счёт
        self.tr.set_value("persona.trait.humor", 9)
        self.tr.set_value("persona.trait.playfulness", 7)
        tg = self.tr.axis_targets()
        self.assertAlmostEqual(tg["irony"]["target"], round((2 * 8 / 9 + 6 / 9) / 3, 3))
        self.assertIsNone(tg["curiosity"]["target"])

    def test_inverse_weight(self):
        self.tr.set_value("persona.trait.risk_appetite", 10)
        self.assertEqual(self.tr.axis_targets()["caution"]["target"], 0.0)

    def test_sync_goes_through_per_with_cap(self):
        self.dev.s["phase"] = "childhood"
        self.dev.apply_to(self.per)
        for tid in ("persona.trait.self_discipline", "persona.trait.persistence", "persona.trait.focus"):
            self.tr.set_value(tid, 10)
        before = self.per.axes["discipline"]
        rep = self.tr.consolidate(self.dev, self.per)
        self.assertIn("discipline", rep["synced"])
        self.assertEqual(len(self.per.pending["discipline"]), 3)
        self.assertTrue(all(e[2] == "traits" for e in self.per.pending["discipline"]))
        self.t[0] += 3600
        self.per.consolidate()
        self.assertLessEqual(abs(self.per.axes["discipline"] - before), P.DRIFT_CAP + 1e-6)
        self.assertGreater(self.per.axes["discipline"], before)

    def test_static_block_includes_both(self):
        text, h = self.tr.static_block(self.per)
        self.assertIn("Мой характер сейчас", text)
        self.assertEqual(len(h), 8)


class TestSignature(Base):
    def test_unverified_excluded_and_empty_text(self):
        text, h = self.tr.signature()
        self.assertIn("пока нет", text)
        self.assertEqual(self.tr.signature()[1], h)

    def test_hysteresis_stable(self):
        self.tr.set_value(CUR, 8)
        text, h = self.tr.signature()
        self.assertIn("Любознательность: выражено сильно", text)
        for v in (7.4, 7.0, 7.6, 6.9):                  # колебания внутри гистерезиса: хеш неизменен
            self.tr.traits[CUR]["value"] = v
            self.assertEqual(self.tr.signature()[1], h)
        self.tr.traits[CUR]["value"] = 6.5               # ушло за границу
        self.assertNotEqual(self.tr.signature()[1], h)

    def test_low_band_and_lines_cap(self):
        self.tr.set_value(CUR, 2)
        self.assertIn("выражено слабо", self.tr.signature()[0])
        for t in list(self.tr.traits)[:30]:
            self.tr.set_value(t, 10)
        self.assertLessEqual(self.tr.signature()[0].count("\n- "), T.MAX_SIG_LINES)

    def test_hash_stable_100_calls(self):
        self.tr.set_value(CUR, 9)
        hs = {self.tr.signature()[1] for _ in range(100)}
        self.assertEqual(len(hs), 1)


class TestApi(Base):
    def test_list_shape(self):
        d = self.tr.api_list(self.dev, self.per)
        r = next(x for x in d["traits"] if x["id"] == CUR)
        for k in ("id", "name", "category", "value", "mode", "open", "last_reason"):
            self.assertIn(k, r)
        self.assertEqual(d["counts"], {"total": 62, "open": 21, "base": 21, "discovered": 0})
        self.assertEqual(len(d["axes"]), 6)
        json.dumps(d, ensure_ascii=False)

    def test_handle_auth_and_actions(self):
        h = {"X-NOX-Token": "s3"}
        self.assertEqual(API.handle(self.tr, "POST", "/api/traits/action", {"action": "set_value", "id": CUR, "value": 7}, h, token="")[0], 403)
        self.assertEqual(API.handle(self.tr, "POST", "/api/traits/action", {"action": "set_value", "id": CUR, "value": 7}, {}, token="s3")[0], 401)
        self.assertEqual(API.handle(self.tr, "GET", "/api/traits", None, {}, token="s3")[0], 401)
        c, out = API.handle(self.tr, "POST", "/api/traits/action", {"action": "set_value", "id": CUR, "value": 7, "lock": True}, h, token="s3")
        self.assertEqual(c, 200)
        row = next(x for x in out["traits"] if x["id"] == CUR)
        self.assertEqual((row["value"], row["mode"]), (7.0, "MANUAL_LOCK"))
        self.assertEqual(API.handle(self.tr, "POST", "/api/traits/action", {"action": "set_mode", "id": CUR, "mode": "X"}, h, token="s3")[0], 400)
        self.assertEqual(API.handle(self.tr, "GET", "/api/traits/%s/why" % CUR, None, h, token="s3")[0], 200)
        self.assertEqual(API.handle(self.tr, "GET", "/nope", None, h, token="s3")[0], 404)

    def test_proposal_actions_over_api(self):
        self.dev.s["phase"] = "youth"
        r = self.tr.propose_trait("Тяга к шахматам", "разбирает партии", "Интересы", "три эпизода",
                                  [{"id": str(i), "text": "партия %d" % i} for i in range(3)], dev=self.dev)
        h = {"X-NOX-Token": "k"}
        c, out = API.handle(self.tr, "POST", "/api/traits/action", {"action": "proposal", "id": r["id"], "decision": "approve"}, h, token="k")
        self.assertEqual(c, 200)
        self.assertEqual(out["counts"]["discovered"], 1)
        self.assertEqual(out["proposals"], [])


class TestNightly(unittest.TestCase):
    def test_dry_run_changes_nothing(self):
        d = tempfile.mkdtemp()
        env = {"NOX_TRAITS": os.path.join(d, "t.json"), "NOX_PERSONALITY": os.path.join(d, "p.json"), "NOX_DEVELOPMENT": os.path.join(d, "d.json")}
        os.environ.update(env)
        try:
            T.Traits(env["NOX_TRAITS"]).save()
            before = open(env["NOX_TRAITS"], "rb").read()
            r = nightly.run(dry=True)
            self.assertTrue(r["dry_run"])
            self.assertEqual(open(env["NOX_TRAITS"], "rb").read(), before)
            self.assertFalse(os.path.exists(env["NOX_PERSONALITY"]))
            self.assertEqual(nightly.run(dry=False)["phase"], "birth")
            self.assertNotEqual(open(env["NOX_TRAITS"], "rb").read(), before)
        finally:
            for k in env:
                os.environ.pop(k, None)


if __name__ == "__main__":
    unittest.main()
