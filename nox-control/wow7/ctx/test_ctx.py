import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

import ctxcommon as cc
from context_manager import Budgets, ContextManager, ContextOverflow, TurnStore
from idle_precompute import IdleWorker
from loss_eval import auto_qa, evaluate, judge
from summarizer import Summarizer, extractive_digest

FILL = ("Это обычное рассуждение без важных данных, оно только для объёма текста. "
        "Мы немного поговорили о погоде и о том, как идут дела в целом. ")


def turn_text(i):
    return ("Тема %d: обсуждаем сервер Канада. " % i + FILL * 4 +
            "Порт модели 80%02d, файл nox_hot_context.py, баланс 1 %03d рублей." % (i, 100 + i) +
            (" Решили: никогда не включать --mlock для главной модели." if i % 3 == 0 else ""))


def fill_store(store, n):
    for i in range(n):
        store.add("user" if i % 2 == 0 else "assistant", turn_text(i))


def facts_in_prompt(prompt, k="ОБЯЗАТЕЛЬНО сохрани дословно: "):
    for line in prompt.split("\n"):
        if line.startswith(k):
            return [x.strip() for x in line[len(k):].split(";" if "дословно" in k else " | ") if x.strip()]
    return []


class GoodLLM:
    def __init__(self):
        self.calls = 0

    def __call__(self, messages, max_tokens=600):
        self.calls += 1
        u = messages[-1]["content"]
        if "Верни ТОЛЬКО JSON" in messages[0]["content"]:
            return json.dumps({"topic": "сервер Канада", "goals": ["настроить порт"], "decisions": ["не включать --mlock"],
                               "open_questions": [], "keywords": ["сервер", "порт"]}, ensure_ascii=False)
        return ("Итог беседы: обсуждали сервер Канада. Данные: " + "; ".join(facts_in_prompt(u)) + ". " +
                " ".join(facts_in_prompt(u, "Сохрани смысл (имена/решения): ")) + ".")


class LossyThenFixLLM(GoodLLM):
    def __call__(self, messages, max_tokens=600):
        self.calls += 1
        u = messages[-1]["content"]
        if "ПОТЕРЯНО" in u:
            return GoodLLM.__call__(self, messages, max_tokens)
        return "Итог беседы: обсуждали сервер Канада и погоду, баланс обсуждали."


class StubbornLossyLLM(GoodLLM):
    def __call__(self, messages, max_tokens=600):
        self.calls += 1
        return "Итог беседы: обсуждали сервер Канада, порт и баланс. Решили не включать --mlock для главной модели."


class HallucinatingLLM(GoodLLM):
    def __call__(self, messages, max_tokens=600):
        self.calls += 1
        return GoodLLM.__call__(self, messages, max_tokens) + " цена 77777 рублей."


def mk(llm=None, budgets=None, n=0, path=None, state=None):
    store = TurnStore(path or ":memory:")
    sm = Summarizer(llm or GoodLLM())
    cm = ContextManager("Я NOX. Душа.", store, sm, budgets=budgets, state_path=state)
    fill_store(store, n)
    return cm


SMALL = Budgets(n_ctx=8192, reserve_out=512, l0_max=300, l2_max=1500, dyn_max=400, expand_max=700, l1_high=1500, l1_idle=1200,
                l1_low=700, keep_last_turns=4, max_batch_tokens=1500)


class FactsT(unittest.TestCase):
    def test_extract(self):
        f = cc.extract_facts("Порт 8083, баланс 1 500,50 ₽, 22.11.2026 в 14:30, файл s03_store.py, см. https://x.io/a. Решили: берём Qwen3-4B.")
        k = {(x["kind"], x["key"]) for x in f}
        self.assertIn(("number", "8083"), k)
        self.assertIn(("number", "1500.5"), k)
        self.assertIn(("date", "22.11.2026"), k)
        self.assertIn(("date", "14:30"), k)
        self.assertIn(("id", "s03_store.py"), k) if ("id", "s03_store.py") in k else self.assertIn(("id", "s03_store"), k)
        self.assertIn(("url", "https://x.io/a"), k)
        self.assertTrue(any(x["kind"] == "decision" for x in f))

    def test_single_digit_ignored(self):
        self.assertFalse([x for x in cc.extract_facts("Пункт 1. Сделай 2 вещи.") if x["kind"] == "number"])

    def test_check_and_invented(self):
        src = "Порт 8083 и размер 435 ГиБ, файл run_all.sh."
        facts = cc.extract_facts(src)
        self.assertTrue(cc.check_facts(facts, "порт 8083, 435 ГиБ, run_all.sh")["ok"])
        r = cc.check_facts(facts, "порт 8083, run_all.sh")
        self.assertFalse(r["ok"])
        self.assertEqual([f["key"] for f in r["missing_hard"]], ["435"])
        self.assertTrue(cc.unsupported_hard("порт 9999", src))
        self.assertFalse(cc.unsupported_hard("порт 8083 и 435", src))
        self.assertTrue(cc.check_facts(cc.extract_facts("в 1 500 рублей"), "1500 рублей")["ok"])


class SummarizerT(unittest.TestCase):
    def turns(self, n=4):
        s = TurnStore()
        fill_store(s, n)
        return s.after(0)

    def test_good(self):
        r = Summarizer(GoodLLM()).summarize(self.turns())
        self.assertEqual(r["verdict"], "llm")
        self.assertTrue(r["check"]["ok"])
        self.assertLess(r["ratio"], 0.6)

    def test_retry_recovers(self):
        llm = LossyThenFixLLM()
        r = Summarizer(llm).summarize(self.turns())
        self.assertEqual(r["verdict"], "llm")
        self.assertEqual(r["attempts"], 2)

    def test_repair_appends_exact(self):
        r = Summarizer(StubbornLossyLLM()).summarize(self.turns())
        self.assertEqual(r["verdict"], "repaired")
        self.assertIn("Точно:", r["text"])
        self.assertTrue(cc.check_facts(r["facts"], r["text"])["hard_cov"] == 1.0)

    def test_hallucination_rejected(self):
        r = Summarizer(HallucinatingLLM()).summarize(self.turns())
        self.assertEqual(r["verdict"], "extractive")
        self.assertNotIn("77777", r["text"])

    def test_llm_down_falls_back(self):
        def boom(m, t=0):
            raise RuntimeError("down")
        r = Summarizer(boom).summarize(self.turns())
        self.assertEqual(r["verdict"], "extractive")

    def test_verbatim_when_dense_or_tiny(self):
        tiny = [{"id": "t1", "role": "user", "content": "Порт 8083."}]
        self.assertEqual(Summarizer(GoodLLM()).summarize(tiny)["verdict"], "verbatim")
        dense = [{"id": "t%d" % i, "role": "user" if i % 2 == 0 else "assistant",
                  "content": "Порт %d1; файл a_b%d.py; сумма %d77 рублей; дата 2026-11-%02d." % (8000 + i, i, 100 + i, i + 1)} for i in range(8)]
        r = Summarizer(StubbornLossyLLM(), min_tokens=10).summarize(dense)
        self.assertEqual(r["verdict"], "verbatim")

    def test_topic_card_drops_invented(self):
        class L:
            def __call__(s, m, t=0):
                return json.dumps({"topic": "сервер", "goals": ["цена 55555 рублей", "порт 8081"], "decisions": [], "open_questions": [], "keywords": []})
        s = TurnStore()
        s.add("user", "Порт 8081 готов, сервер работает хорошо и стабильно.")
        card = Summarizer(L()).topic_card(s.after(0))
        self.assertEqual(card["goals"], ["порт 8081"])


class ManagerT(unittest.TestCase):
    def test_no_compaction_below_high_and_prefix_stable(self):
        cm = mk(budgets=SMALL)
        prev = None
        for i in range(3):
            cm.commit("вопрос %d про сервер" % i, "ответ %d" % i)
            r = cm.build("следующий вопрос %d" % i)
            self.assertEqual(r["segments"], 0)
            if prev:
                self.assertTrue(r["kv"]["prefix_intact"], r["kv"])
                self.assertEqual(r["kv"]["same_as_prev"], len(prev["messages"]) - 1)
            prev = r
        self.assertEqual(r["messages"][0]["content"], "Я NOX. Душа.")

    def test_compact_hysteresis_and_append_only(self):
        cm = mk(budgets=SMALL, n=12)
        self.assertGreater(cm.l1_tokens(), SMALL.l1_high)
        segs = cm.compact("llm")
        self.assertTrue(segs)
        self.assertLessEqual(cm.l1_tokens(), SMALL.l1_low + 400)
        first_text = cm.segments[0]["text"]
        d1 = cm.digest_text()
        fill_store(cm.store, 14)
        cm.compact("llm")
        self.assertGreaterEqual(len(cm.segments), 2)
        self.assertTrue(cm.digest_text().startswith(d1.split("\n§")[0]))
        self.assertEqual(cm.segments[0]["text"], first_text)   # старые сегменты не переписаны
        # префикс дайджеста: первый сегмент в тексте идентичен
        self.assertIn(cm._render_seg(cm.segments[0]), cm.digest_text())

    def test_build_budget_and_no_llm_in_foreground(self):
        llm = GoodLLM()
        cm = mk(llm, SMALL, n=40)
        r = cm.build("что с портом?")
        self.assertEqual(llm.calls, 0)
        self.assertTrue(r["emergency"])
        self.assertLessEqual(r["tokens"]["total"], SMALL.usable)
        self.assertEqual(r["messages"][-1]["role"], "user")
        self.assertTrue(r["messages"][-1]["content"].endswith("что с портом?"))

    def test_facts_survive_in_prompt(self):
        cm = mk(budgets=SMALL, n=14)
        cm.compact("llm")
        text = cm.digest_text() + " ".join(t["content"] for t in cm.l1_turns())
        orig = [f for t in cm.store.after(0) for f in cc.extract_facts(t["content"]) if f["kind"] in cc.HARD]
        self.assertEqual(cc.check_facts(orig, text, 0)["hard_cov"], 1.0)

    def test_expand_verified_by_query_and_tail_only(self):
        cm = mk(budgets=SMALL, n=14)
        cm.compact("llm")
        sid = cm.segments[0]["id"]
        r = cm.build("а какой был порт 8002 и файл nox_hot_context.py?")
        self.assertIn(sid, r["expanded"])
        self.assertIn("<дословно_из_прошлого>", r["messages"][-1]["content"])
        self.assertNotIn("<дословно_из_прошлого>", "".join(m["content"] for m in r["messages"][:-1]))
        ex = cm.expand(ids=[sid])
        self.assertTrue(ex["verified"])
        self.assertIn("Тема 0:", ex["text"])

    def test_tamper_detected(self):
        cm = mk(budgets=SMALL, n=14)
        cm.compact("llm")
        sid = cm.segments[0]["id"]
        cm.store.db.execute("UPDATE ctx_turns SET content='подделка' WHERE n=1")
        ex = cm.expand(ids=[sid])
        self.assertFalse(ex["verified"])
        self.assertIn("t000001", ex["tampered"])
        self.assertNotIn("подделка", ex["text"])

    def test_s03_resolver_mismatch(self):
        store = TurnStore(s03_sink=lambda t: "e:%s" % t["id"][1:])
        t = store.add("user", "Порт 8083.")
        self.assertEqual(t["s03"], "e:000001")
        self.assertTrue(store.verified(t["id"], resolver=lambda ref: "Порт 8083.")[1])
        self.assertFalse(store.verified(t["id"], resolver=lambda ref: "Порт 9999.")[1])

    def test_reply_marker_queues_expand(self):
        cm = mk(budgets=SMALL, n=14)
        cm.compact("llm")
        sid = cm.segments[0]["id"]
        cm.scan_reply_for_expand("Уточню по §%s" % sid)
        r = cm.build("продолжим")
        self.assertIn(sid, r["expanded"])

    def test_persist_restore_same_prefix(self):
        with tempfile.TemporaryDirectory() as d:
            db, st = os.path.join(d, "t.db"), os.path.join(d, "s.json")
            cm = mk(budgets=SMALL, n=14, path=db, state=st)
            cm.compact("llm")
            a = cm.build("вопрос")["messages"][:-1]
            cm.store.db.close()
            cm2 = ContextManager("Я NOX. Душа.", TurnStore(db), Summarizer(GoodLLM()), budgets=SMALL, state_path=st)
            b = cm2.build("вопрос")["messages"][:-1]
            self.assertEqual(a, b)

    def test_merge_recursive_keeps_facts(self):
        b = Budgets(n_ctx=8192, reserve_out=512, l0_max=300, l2_max=330, dyn_max=400, expand_max=700, l1_high=1500, l1_idle=1200,
                    l1_low=500, keep_last_turns=4, max_batch_tokens=1000)
        cm = mk(budgets=b, n=30)
        for _ in range(5):
            cm.compact("llm")
        self.assertTrue(cm.archive or any(s["paged"] for s in cm.segments))
        self.assertLessEqual(cm.l2_tokens(), b.l2_max + 120)
        live = " ".join(s["text"] for s in cm.segments if not s["paged"])
        merged = [s for s in cm.segments if s["covers"]]
        for s in merged:
            self.assertEqual(cc.check_facts([f for f in s["facts"] if f["kind"] in cc.HARD], s["text"], 0)["hard_cov"], 1.0)
        # развернуть выгруженное можно
        paged = [s for s in cm.segments if s["paged"]]
        if paged:
            self.assertTrue(cm.expand(ids=[paged[0]["id"]])["text"])

    def test_overflow_for_giant_question(self):
        cm = mk(budgets=SMALL)
        with self.assertRaises(ContextOverflow):
            cm.build("слово " * 20000)

    def test_budget_validation(self):
        with self.assertRaises(ValueError):
            Budgets(l1_low=5000, l1_idle=4000).validate()


class IdleT(unittest.TestCase):
    def test_busy_then_idle_jobs(self):
        t = [1000.0]
        llm = GoodLLM()
        cm = mk(llm, SMALL, n=14)
        warmed = []
        with tempfile.TemporaryDirectory() as d:
            kp = os.path.join(d, "k.jsonl")
            w = IdleWorker(cm, cm.sm, warm=lambda m: warmed.append(len(m)), knowledge_path=kp, clock=lambda: t[0], idle_after=45)
            w.touch(1000.0)
            self.assertEqual(w.tick(now=1010.0)["state"], "busy")
            self.assertEqual(llm.calls, 0)
            r = w.tick(now=1100.0, sleep=True)
            self.assertEqual(r["state"], "idle", r)
            self.assertFalse(r["errors"], r)
            self.assertTrue(any(a.startswith("compact") for a in r["actions"]))
            self.assertIn("topic_card", r["actions"])
            self.assertIn("warm", r["actions"])
            self.assertEqual(len(warmed), 1)
            self.assertEqual(cm.topic_card["topic"], "сервер Канада")
            lines = [json.loads(l) for l in open(kp, encoding="utf-8")]
            self.assertTrue(lines and lines[0]["anchors"]["turns"])
            r2 = w.tick(now=1200.0, sleep=True)       # ничего нового: нет повторной работы
            self.assertNotIn("warm", r2["actions"])
            self.assertEqual(len(warmed), 1)
            n_lines = len(lines)
            w.tick(now=1300.0, sleep=True)
            self.assertEqual(len(open(kp, encoding="utf-8").readlines()), n_lines)

    def test_stop_signal(self):
        cm = mk(GoodLLM(), SMALL, n=14)
        w = IdleWorker(cm, cm.sm, clock=lambda: 5000.0, idle_after=1)
        w.last_activity = 0
        r = w.tick(now=5000.0, should_stop=lambda: True)
        self.assertEqual(r["actions"], ["stopped_before:compact"])
        self.assertEqual(len(cm.segments), 0)

    def test_card_in_tail_not_prefix(self):
        cm = mk(GoodLLM(), SMALL, n=6)
        w = IdleWorker(cm, cm.sm, clock=lambda: 9e3, idle_after=1)
        w.last_activity = 0
        w.tick(now=9e3)
        r = cm.build("ну что")
        self.assertIn("[ТЕМА БЕСЕДЫ]", r["messages"][-1]["content"])
        self.assertNotIn("[ТЕМА БЕСЕДЫ]", "".join(m["content"] for m in r["messages"][:-1]))


class LossEvalT(unittest.TestCase):
    @staticmethod
    def reader(messages, max_tokens=60):
        """Идеальный ридер: отвечает золотом, если оно есть в контексте; иначе «нет данных». Проверяет логику харнесса."""
        u = messages[-1]["content"]
        ctx, q = u.split("\n\nВопрос: ", 1)
        for it in LossEvalT.items:
            if it["q"] == q:
                return it["gold"] if it["gold"] in ctx else "нет данных"
        return "нет данных"

    def setUp(self):
        self.cm = mk(budgets=SMALL, n=14)
        LossEvalT.items = auto_qa(self.cm.store.after(0), 30)

    def test_auto_qa_masks(self):
        self.assertTrue(LossEvalT.items)
        for it in LossEvalT.items:
            self.assertIn("___", it["q"])
            self.assertNotIn(it["gold"], it["q"])

    def test_judge(self):
        self.assertTrue(judge("это 1 500", {"gold": "1500", "kind": "number"}))
        self.assertFalse(judge("нет данных", {"gold": "8083", "kind": "number"}))

    def test_lossless_passes(self):
        self.cm.compact("llm")
        rep = evaluate(self.cm, LossEvalT.items, self.reader)
        self.assertTrue(rep["pass"], rep)
        self.assertEqual(rep["fact_retention_static"], 1.0)
        self.assertEqual(rep["delta_compressed"], 0.0)
        self.assertLess(rep["ratio"], 0.8)

    def test_lossy_detected_and_expand_rescues(self):
        self.cm.compact("llm")
        for s in self.cm.segments:                     # имитация плохой выжимки: числа потеряны
            s["text"] = "Обсуждали сервер."
        rep = evaluate(self.cm, LossEvalT.items, self.reader)
        self.assertFalse(rep["pass"])
        self.assertTrue(rep["lost"])
        self.assertLess(rep["delta_compressed"], -0.02)
        self.assertGreater(rep["acc"]["compressed+expand"], rep["acc"]["compressed"])
        self.assertTrue(rep["missing_static"])


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/tokenize":
            out = {"tokens": list(range(len(body["content"].split())))}
        else:
            out = {"choices": [{"message": {"content": "ответ:" + body["messages"][-1]["content"][:5]}}]}
        data = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class HttpT(unittest.TestCase):
    def test_http_clients(self):
        srv = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        url = "http://127.0.0.1:%d" % srv.server_port
        tok = cc.LlamaTokenizer(url)
        self.assertEqual(tok.count_text("раз два три"), 3)
        self.assertEqual(tok([{"role": "user", "content": "раз два"}]), 2 + 6 + 3)
        self.assertEqual(cc.http_llm(url)([{"role": "user", "content": "привет мир"}]), "ответ:приве")
        self.assertTrue(cc.kv_warm_http(url)([{"role": "user", "content": "x"}]))
        srv.shutdown()
        dead = cc.LlamaTokenizer("http://127.0.0.1:9", timeout=0.3)
        self.assertGreater(dead.count_text("текст без сервера"), 0)
        self.assertEqual(dead.failures, 1)


if __name__ == "__main__":
    unittest.main(verbosity=1)
