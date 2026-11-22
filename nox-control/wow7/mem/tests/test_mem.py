"""Тесты MEM на ВРЕМЕННОЙ файловой SQLite через настоящие qs6.s03_store.Store / recall_api.Recall / memory_search.
Путь к клону: NOX_REPO (по умолчанию клон на этой машине); без него тесты пропускаются. В клон ничего не пишется."""
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
REPO = os.environ.get("NOX_REPO", "/home/claude/msstxnews/nox-helion-pp-private-build/nox-control")
if os.path.isdir(os.path.join(REPO, "qs6")):
    sys.path.insert(0, REPO)
try:
    from qs6.s03_store import Store
    from qs6.memory_search import MemorySearch
    from qs6.recall_api import Recall
    HAVE = True
except Exception as _e:  # pragma: no cover
    HAVE = False

import autobio
import consolidate
import correction
import provenance
from memcommon import DAY, day_of

NOW = 1_795_000_000.0  # фиксированный "сейчас" (ноябрь 2026)


def mk(td, name="s03.sqlite"):
    st = Store(os.path.join(td, name))
    rc = Recall(st, MemorySearch(st, use_env_embedder=False))
    return st, rc


@unittest.skipUnless(HAVE, "нет клона qs6 (NOX_REPO)")
class Base(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.td, True)
        self.s, self.rc = mk(self.td)
        self.addCleanup(self.s.close)
        self.c = correction.Corrector(self.s, self.rc)


class CorrectionT(Base):
    def test_correct_is_verified_by_fresh_read(self):
        fid = self.s.add_fact("Порт recall равен 8788")
        ref = "f:%d" % fid
        self.s.db.execute("INSERT INTO mem_vectors(ref,model,dim,vec,text_key) VALUES(?,?,?,?,?)", (ref, "m", 1, b"\0\0\0\0", "x"))
        self.s.db.commit()
        rev0 = correction.revision(self.s)
        r = self.c.correct(ref, "Порт recall равен 8095", reason="тест")
        self.assertTrue(r["ok"] and r["verified"], r)
        self.assertEqual(r["readback"]["text"], "Порт recall равен 8095")
        self.assertTrue(r["invalidated"]["vector_dropped"] and r["invalidated"]["fts_current"])
        self.assertNotEqual(correction.revision(self.s), rev0)
        # другое соединение (как новая сессия) видит то же
        s2, rc2 = mk(self.td)
        self.addCleanup(s2.close)
        self.assertEqual(s2.get_fact(fid)["text"], "Порт recall равен 8095")
        hits = [h["text"] for h in rc2.search.search("порт recall", k=5)["hits"]]
        self.assertIn("Порт recall равен 8095", hits)
        self.assertNotIn("Порт recall равен 8788", hits)

    def test_correct_rejections_return_ok_false_and_change_nothing(self):
        a = "f:%d" % self.s.add_fact("Факт номер один про сервер")
        self.s.add_fact("Факт номер два про сервер")
        for ref, txt in ((a, ""), (a, "пароль: supersecret123"), ("f:999", "что-то"), (a, "Факт номер два про сервер")):
            r = self.c.correct(ref, txt)
            self.assertFalse(r["ok"], (ref, txt))
            self.assertFalse(r["verified"])
        self.assertEqual(self.c.readback(a)["text"], "Факт номер один про сервер")

    def test_lying_backend_is_detected_and_rolled_back(self):
        fid = self.s.add_fact("Исходный текст факта для проверки")
        ref = "f:%d" % fid
        orig = self.rc.correct
        calls = []

        def liar(r, text, actor="owner", reason=None):   # «ok», но в S03 ничего не меняет (как UI при ok:false/потере записи)
            calls.append(text)
            return self.s.get(r)
        self.rc.correct = liar
        r = self.c.correct(ref, "Совсем другой текст факта")
        self.assertFalse(r["ok"] or r["verified"])
        self.assertEqual(self.c.readback(ref)["text"], "Исходный текст факта для проверки")
        self.assertEqual(len(calls), 2)       # правка + попытка автооткатa

    def test_revoke_verified_and_not_resurrected(self):
        fid = self.s.add_fact("Мессир пьёт зелёный чай по утрам", kind="owner", pinned=True)
        ref = "f:%d" % fid
        self.s.add_episode("Запомни, что Мессир пьёт зелёный чай по утрам", ts=NOW, session="2026-11-20")
        r = self.c.revoke(ref, "неверно")
        self.assertTrue(r["ok"] and r["verified"], r)
        self.assertTrue(all(r["checks"].values()))
        self.assertEqual(len(r["traces"]), 1)          # эпизод со следом найден
        # новый диалог: ни ядро, ни поиск не отдают
        out = self.rc.recall_for_reply("что пьёт мессир по утрам чай", turn_id="new1")
        self.assertNotIn(ref, out["core"]["items"])
        self.assertNotIn(ref, [h["ref"] for h in out["search"]["hits"]])
        # голый add_fact воскрешает (риск лестницы), guarded - нет
        self.assertIsNone(correction.guarded_add_fact(self.s, "Мессир пьёт зелёный чай по утрам"))
        self.assertEqual(self.s.db.execute("SELECT COUNT(*) FROM mem_changes WHERE action='blocked_revoked'").fetchone()[0], 1)

    def test_cascade_archives_traces(self):
        ref = "f:%d" % self.s.add_fact("Секретная кличка кота Барсик")
        self.s.add_episode("Секретная кличка кота Барсик, запомни", ts=NOW)
        r = self.c.revoke(ref, "приватно", cascade_episodes=True)
        self.assertTrue(r["ok"])
        self.assertEqual(r["traces"], [])
        self.assertEqual(len(r["archived_traces"]), 1)
        self.assertEqual(self.s.db.execute("SELECT COUNT(*) FROM mem_fts WHERE body LIKE '%Барсик%'").fetchone()[0], 0)

    def test_restore_reverts_and_unblocks(self):
        ref = "f:%d" % self.s.add_fact("Сервер S1 стоит в Канаде")
        r = self.c.revoke(ref, "ошибка")
        back = self.c.restore(r["change_id"])
        self.assertTrue(back["ok"], back)
        self.assertIsNotNone(correction.guarded_add_fact(self.s, "Сервер S1 стоит в Канаде"))

    def test_api_wrapper(self):
        api = correction.CorrectionAPI(self.rc)
        fid = self.s.add_fact("Мессир живёт в Москве")
        ref = "f:%d" % fid
        self.assertEqual(api.handle({"op": "get", "id": ref})["item"]["status"], "active")
        bad = api.handle({"op": "correct", "id": ref, "text": ""})
        self.assertFalse(bad["ok"])
        good = api.handle({"op": "correct", "id": ref, "text": "Мессир живёт в Казани"})
        self.assertTrue(good["ok"] and good["item"]["text"] == "Мессир живёт в Казани")
        d = api.handle({"op": "delete", "id": ref})
        self.assertTrue(d["ok"])
        self.assertEqual(api.handle({"op": "get", "id": ref})["item"]["status"], "deleted")
        self.assertFalse(api.handle({"op": "get", "id": "f:12345"})["ok"])
        self.assertTrue(api.handle({"op": "list"})["ok"])           # делегирование прежних операций
        self.assertEqual(len(api.handle({"op": "revision"})["revision"]), 64)


class HttpT(Base):
    def test_serve_with_correction_api_end_to_end(self):
        import json
        import threading
        import urllib.request
        from qs6.recall_api import serve
        fid = self.s.add_fact("Тестовый факт для сети")
        srv = serve(correction.CorrectionAPI(self.rc), port=0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        url = "http://127.0.0.1:%d/api" % srv.server_address[1]

        def post(o):
            rq = urllib.request.Request(url, json.dumps(o).encode(), {"Content-Type": "application/json"})
            return json.loads(urllib.request.urlopen(rq, timeout=5).read())
        self.assertFalse(post({"op": "correct", "id": "f:%d" % fid, "text": ""})["ok"])         # ok:false приходит как есть
        self.assertTrue(post({"op": "correct", "id": "f:%d" % fid, "text": "Новый тестовый факт"})["ok"])
        self.assertEqual(post({"op": "get", "id": "f:%d" % fid})["item"]["text"], "Новый тестовый факт")
        self.assertTrue(post({"op": "delete", "id": "f:%d" % fid})["verified"])


class ProvenanceT(Base):
    def test_turn_explained_with_sources_and_changes(self):
        fid = self.s.add_fact("Сервер S1 работает на порту 8080", source="chat:2026-11-20", ts=NOW - 2 * DAY)
        self.s.add_fact("Сервер S1 работает на порту 8080", source="chat:2026-11-21", ts=NOW - DAY)
        self.s.set_profile("имя", "NOX HELION", "persona")
        self.s.add_episode("Давай проверим на каком порту сервер S1 работает", ts=NOW - 2 * DAY, session="2026-11-20")
        out = provenance.recall_with_provenance(self.rc, "на каком порту сервер", turn_id="t1")
        ex = provenance.explain_turn(self.s, "t1", reply_text="Сервер S1 работает на порту 8080, мессир.")
        byref = {i["ref"]: i for i in ex["items"]}
        it = byref["f:%d" % fid]
        self.assertEqual(it["via"], "search")
        self.assertEqual(len([e for e in it["evidence"] if e["polarity"] > 0]), 2)
        self.assertEqual({e["source"] for e in it["evidence"]}, {"chat:2026-11-20", "chat:2026-11-21"})
        self.assertTrue(it["probably_in_reply"])
        self.assertEqual(byref["p:имя"]["via"], "core")
        self.assertFalse(byref["p:имя"]["probably_in_reply"])
        # правка после ответа: слепок хранит текст на момент ответа
        self.c.correct("f:%d" % fid, "Сервер S1 работает на порту 9090")
        ex2 = provenance.explain_turn(self.s, "t1")
        it2 = {i["ref"]: i for i in ex2["items"]}["f:%d" % fid]
        self.assertTrue(it2["changed_since"])
        self.assertIn("8080", it2["text_at_use"])
        self.assertIn("9090", it2["text"])
        txt = provenance.render_ru(ex2)
        self.assertIn("ИЗМЕНЕНО с тех пор", txt)
        self.assertTrue(any(j["action"] == "correct" for j in it2["journal"]))
        # отзыв
        self.c.revoke("f:%d" % fid, "x")
        it3 = {i["ref"]: i for i in provenance.explain_turn(self.s, "t1")["items"]}["f:%d" % fid]
        self.assertTrue(it3["revoked"])
        self.assertIn("ОТОЗВАНО", provenance.render_ru(provenance.explain_turn(self.s, "t1")))

    def test_install_hook_snapshots_every_turn_once(self):
        self.s.add_fact("Сервер S1 работает на порту 8080")
        provenance.install_hook(self.rc)
        provenance.install_hook(self.rc)                     # повторная установка не плодит обёртки
        self.rc.recall_for_reply("порт сервера", turn_id="h1")
        n = self.s.db.execute("SELECT COUNT(*) FROM mem_usage_snap WHERE turn_id='h1'").fetchone()[0]
        self.assertGreaterEqual(n, 1)
        self.assertEqual(n, self.s.db.execute("SELECT COUNT(DISTINCT ref) FROM mem_usage WHERE turn_id='h1'").fetchone()[0])

    def test_origin_episodes_and_empty_turn(self):
        fid = self.s.add_fact("Мессир предпочитает чёрный кофе", source="chat:2026-11-20")
        self.s.add_episode("Я предпочитаю чёрный кофе без сахара", ts=NOW, session="2026-11-20")
        self.s.add_episode("Погода сегодня хорошая", ts=NOW + 1, session="2026-11-20")
        e = provenance.explain_item(self.s, "f:%d" % fid)
        self.assertEqual(len(e["origin_episodes"]), 1)
        self.assertEqual(provenance.render_ru(provenance.explain_turn(self.s, "нет-такого")), "В этот ход ничего из памяти не попало.")


def fake_extract(text):
    m = text.lower().startswith("запомни, что ")
    return [{"text": text[13:].strip(), "kind": "fact", "source_kind": "direct", "rule": "t"}] if m else []


class ConsolidateT(Base):
    def mkc(self, **kw):
        return consolidate.Consolidator(self.s, self.c, extractor=fake_extract, clock=lambda: NOW, **kw)

    def test_episodes_to_facts_idempotent_and_no_inflation(self):
        self.s.add_episode("Запомни, что Мессир любит чёрный кофе", ts=NOW - DAY, session="2026-11-21")
        self.s.add_episode("просто болтовня без фактов", ts=NOW - DAY + 5, session="2026-11-21")
        c = self.mkc()
        dry = c.consolidate_episodes(apply=False)
        self.assertEqual(len(dry["facts"]), 1)
        self.assertEqual(self.s.stats()["facts"], 0)                       # сухой прогон ничего не пишет
        r = c.consolidate_episodes(apply=True)
        self.assertEqual(self.s.stats()["facts"], 1)
        fid = int(r["facts"][0]["ref"][2:])
        # то же свидетельство, что и у after_reply (chat:<сессия>) -> повтор не накручивает уверенность
        self.s.add_fact("Мессир любит чёрный кофе", source="chat:2026-11-21", source_kind="direct")
        self.assertEqual(self.s.ladder.evidence_count(self.s.get_fact(fid)["ladder_id"]), 1)
        self.assertEqual(c.consolidate_episodes(apply=True)["episodes"], 0)

    def test_revoked_not_reconsolidated(self):
        ref = "f:%d" % self.s.add_fact("Мессир любит чёрный кофе")
        self.c.revoke(ref, "нет")
        self.s.add_episode("Запомни, что Мессир любит чёрный кофе", ts=NOW, session="s")
        r = self.mkc().consolidate_episodes(apply=True)
        self.assertEqual(r["facts"], [])
        self.assertEqual(len(r["blocked_revoked"]), 1)
        self.assertEqual(self.s.stats()["facts"], 0)

    def test_real_extractor_integration(self):
        self.s.add_episode("Я живу в Казани", ts=NOW - DAY, session="2026-11-21")
        c = consolidate.Consolidator(self.s, self.c, clock=lambda: NOW)     # extractor по умолчанию = qs6.fact_extract
        r = c.consolidate_episodes(apply=True)
        self.assertEqual([f["text"] for f in r["facts"]], ["Владелец живёт в Казани"])

    def test_beliefs_from_recurring_topics(self):
        for d in range(4):
            self.s.add_episode("Хочу обсудить запуск ракеты и орбиту", ts=NOW - (d + 1) * DAY, session="d%d" % d)
        self.s.add_episode("Привет, как дела", ts=NOW - DAY + 9, session="d0")
        c = self.mkc()
        res = c.beliefs(apply=True)
        self.assertTrue(res and all(r["days"] >= 3 for r in res))
        txts = [r["text"] for r in res]
        self.assertTrue(any("ракет" in t and "запус" in t for t in txts), txts)
        f = self.s.get_fact(int(res[0]["ref"][2:]))
        self.assertLessEqual(f["level"], 1)                               # без подтверждения владельца - только гипотеза
        n = self.s.stats()["facts"]
        c.beliefs(apply=True)
        self.assertEqual(self.s.stats()["facts"], n)                       # стабильный текст: дублей нет

    def test_forgetting_by_decay_protects_important(self):
        old = NOW - 400 * DAY
        weak = self.s.add_fact("Мимолётное наблюдение про погоду", ts=old, importance=0.1)
        weak2 = self.s.add_fact("Забытая мелочь про курс", ts=old, importance=0.2)
        pinned = self.s.add_fact("Важное закреплённое про семью", ts=old, pinned=True)
        owner = self.s.add_fact("Имя жены мессира Анна", kind="owner", ts=old)
        fresh = self.s.add_fact("Свежее наблюдение про сеть", ts=NOW - DAY, importance=0.1)
        used = self.s.add_fact("Часто вспоминаемое про сервер", ts=old, importance=0.1)
        for _ in range(30):
            self.s.touch("f:%d" % used, NOW - 5 * DAY)
        c = self.mkc()
        cand = {x["ref"] for x in c.forget_candidates()}
        self.assertEqual(cand, {"f:%d" % weak, "f:%d" % weak2})
        self.assertEqual(c.forget(apply=False)["applied"], False)
        self.assertEqual(self.s.stats()["facts"], 6)
        c.forget(apply=True)
        self.assertEqual(self.s.stats()["facts"], 4)
        self.assertEqual(self.s.get_fact(weak)["status"], "archived")
        self.assertEqual(self.s.db.execute("SELECT COUNT(*) FROM mem_fts WHERE ref=?", ("f:%d" % weak,)).fetchone()[0], 0)
        self.assertTrue(c.restore_archived("f:%d" % weak))
        self.assertEqual(self.s.get_fact(weak)["status"], "active")
        # монотонность: удержание падает со временем и растёт с обращениями
        f = self.s.get_fact(weak)
        self.assertGreater(c.retention(f, NOW - 399 * DAY), c.retention(f, NOW))

    def test_forget_cap_per_run(self):
        for i in range(30):
            self.s.add_fact("Мимолётное наблюдение номер %d про шум" % i, ts=NOW - 400 * DAY, importance=0.1)
        c = self.mkc(max_forget_ratio=0.1, min_forget_cap=5)
        rep = c.forget(apply=True)
        self.assertEqual(len(rep["facts"]), 5)
        self.assertEqual(rep["deferred_by_cap"], 25)
        self.assertEqual(self.s.stats()["facts"], 25)

    def test_old_consolidated_episodes_archived(self):
        e1 = self.s.add_episode("Запомни, что Мессир любит чай", ts=NOW - 200 * DAY, session="a")
        e2 = self.s.add_episode("Новая реплика недавно", ts=NOW - DAY, session="b")
        e3 = self.s.add_episode("Старая но не обработанная реплика", ts=NOW - 300 * DAY, session="c")
        c = self.mkc()
        self.s.db.execute("INSERT INTO mem_consolidated(episode_id,ts) VALUES(?,?)", (e1, NOW))
        self.s.db.commit()
        rep = c.forget(apply=True)
        self.assertEqual([x["ref"] for x in rep["episodes"]], ["e:%d" % e1])
        self.assertEqual(self.s.get_episode(e3)["status"], "active")
        self.assertEqual(self.s.get_episode(e2)["status"], "active")

    def test_conflicts_to_question_and_owner_answer(self):
        a = self.s.add_fact("Порт сервера recall 8788", ts=NOW - 5 * DAY)
        b = self.s.add_fact("Порт сервера recall 8095", ts=NOW - DAY)
        n1 = self.s.add_fact("Мессир любит чёрный кофе")
        n2 = self.s.add_fact("Мессир не любит чёрный кофе")
        self.s.add_fact("Мессир любит зелёный чай")          # не конфликт: просто другое предпочтение
        c = self.mkc(max_open_questions=2)
        kinds = sorted(x["kind"] for x in c.detect_conflicts())
        self.assertEqual(kinds, ["negation", "value"])
        made = c.ask_conflicts(apply=True)
        self.assertEqual(len(made), 2)
        self.assertIn("Какое верно", made[0]["question"])
        self.assertEqual(c.ask_conflicts(apply=True), [])                  # дубликатов и лишних открытых нет
        qv = [q for q in c.open_questions() if q["kind"] == "value"][0]
        self.assertEqual(self.s.get_fact(a)["status"], "active")           # сам не решает
        res = c.answer(qv["id"], "2")
        self.assertTrue(res["ok"], res)
        self.assertEqual(self.s.get_fact(b)["owner_confirmed"], 1)
        self.assertEqual(self.s.get_fact(a)["status"], "deleted")
        self.assertEqual(len(c.open_questions()), 1)
        self.assertFalse(c.answer(qv["id"], "1")["ok"])                    # закрытый вопрос не переоткрыть
        self.assertFalse(c.answer(c.open_questions()[0]["id"], "ой")["ok"])

    def test_run_dry_vs_apply(self):
        self.s.add_episode("Запомни, что Мессир любит чай", ts=NOW - DAY, session="x")
        c = self.mkc()
        before = self.s.db.execute("SELECT COUNT(*) FROM mem_changes").fetchone()[0]
        rep = c.run(apply=False)
        self.assertFalse(rep["applied"])
        self.assertEqual(self.s.db.execute("SELECT COUNT(*) FROM mem_changes").fetchone()[0], before)
        c.run(apply=True)
        self.assertEqual(self.s.stats()["facts"], 1)


class AutobioT(Base):
    def test_days_story_privacy_and_idempotence(self):
        t1, t2 = NOW - 3 * DAY, NOW - 2 * DAY
        for i, t in enumerate((t1, t1 + 60, t1 + 120)):
            self.s.add_episode("Давай обсудим запуск ракеты с орбитой %d" % i, role="user", ts=t, session="a")
        self.s.add_episode("Принял, запуск ракеты разберём", role="assistant", ts=t1 + 5, session="a")
        self.s.add_fact("Мессир интересуется ракетами", ts=t1 + 10)
        secret = self.s.add_fact("Закрытая тайна про мессира", ts=t1 + 20)
        self.s.add_episode("Привет", ts=t2, session="b")
        self.c.revoke("f:%d" % secret, "приватно")
        self.c.correct("f:1", "Мессир увлечён ракетами")
        out = autobio.write_missing(self.s, clock=lambda: NOW)
        days = [o["day"] for o in out]
        self.assertEqual(days, sorted({day_of(t1), day_of(t2)}))
        self.assertNotIn(day_of(NOW), days)                                # сегодняшний день ещё не закрыт
        d1 = [o for o in out if o["day"] == day_of(t1)][0]
        self.assertEqual((d1["data"]["heard"], d1["data"]["said"]), (3, 1))
        self.assertIn("3 реплики", d1["text"])
        self.assertNotIn("тайна", d1["text"].casefold())                   # отозванное не пересказывается
        self.assertEqual(d1["data"]["revoked_new"], 1)
        self.assertIn("ракет", " ".join(d1["data"]["topics"]) + d1["text"])
        self.assertEqual(autobio.write_missing(self.s, clock=lambda: NOW), [])   # идемпотентно
        md = autobio.render_markdown(self.s)
        self.assertTrue(md.startswith("# Моя история") and day_of(t1) in md)

    def test_narrator_guard(self):
        t = NOW - DAY
        self.s.add_episode("Привет", ts=t, session="a")
        day = day_of(t)
        liar = lambda prompt, d: "Сегодня я услышал 777 реплик и очень радовался."
        r = autobio.write_day(self.s, day, narrator=liar)
        self.assertNotIn("777", r["text"])
        ok = lambda prompt, d: "%s: мессир сказал мне %d реплику, и я её записал." % (day, d["heard"])
        r2 = autobio.write_day(self.s, day, narrator=ok)
        self.assertIn("я её записал", r2["text"])
        boom = lambda prompt, d: 1 / 0
        self.assertIn("Это сводка по журналу", autobio.write_day(self.s, day, narrator=boom)["text"])

    def test_plural(self):
        self.assertEqual([autobio._num(n, "а", "б", "в") for n in (1, 2, 5, 11, 21, 22, 12)], ["а", "б", "в", "в", "а", "б", "в"])


class JsUiT(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node") and os.path.isdir("/opt/node22/lib/node_modules/playwright"), "нет node/playwright")
    def test_ok_false_does_not_change_ui(self):
        p = subprocess.run(["node", os.path.join(HERE, "js_ui_test.js")], capture_output=True, text=True, timeout=120)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("PASS", p.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
