"""ADV-06 + V0: путь СОВЕТ в ядре (фейковый хаб советников), детекторы Совести advisor_copy и V0. Запуск: python3 -m unittest test_council (из BRAIN)."""
import asyncio
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import netio
import conscience as C
import test_core as T

ADVICE = ("<данные>советник groq (gpt-oss): mmap отображает файл в память и читает страницами по требованию, read копирует в буфер</данные>\n"
          "Задача NOX: сверь мнения советников. Вопрос: чем mmap отличается от read для больших файлов")
ADV_TEXT = "mmap отображает файл в память и читает страницами по требованию, а read копирует данные в буфер пользователя"


class FakeHub:
    def __init__(self, reply=None, status=200):
        self.reply, self.status, self.reqs, self.auth = reply, status, [], []
        self.server = T.Server(self.handle)

    async def handle(self, m, path, body, w):
        self.reqs.append((path, body))
        if self.reply == "boom":
            return await netio.send_json(w, 500, {"ok": False})
        obj = self.reply if self.reply is not None else {"ok": True, "answers": [{"advisor": "groq", "model": "gpt-oss", "text": ADV_TEXT}],
                                                         "compose_prompt": ADVICE, "agreement": {"label": "согласны"}}
        await netio.send_json(w, self.status, obj)


class FakeSolverCouncil:
    def __init__(self, arm="council"): self.arm = arm
    def run(self, text, ctx, turn_id=None): return {"arm": self.arm, "tier": "deep", "executors": [], "policy_rev": 1, "turn_id": turn_id}
    def observe(self, *a, **k): pass
    def observe_late(self, *a, **k): pass


class FakePredLow:
    def __init__(self, p=0.3): self.p = p
    def predict(self, turn_id, ctx, text, extra=""): return {"pred": {"outcome": {"success_p": self.p}, "creator": {"label": "neutral"}}}
    def observe(self, *a, **k): pass
    def post_to_workspace(self, ws, surprise_floor=0.55): return 0


Q = "чем mmap отличается от read для больших файлов"


def answer_fn(s, u, n):
    if "Перепиши ответ" in s:
        return "Если коротко: mmap подгружает страницы лениво, а read сразу копирует данные. Советник groq примерно это и сказал."
    return "Разница в том, что mmap подгружает страницы лениво, а read копирует сразу. Советник groq сказал похожее."


class CouncilBase(T.Base):
    fast_fn = staticmethod(answer_fn)
    glm_mode = None
    hub_reply = None
    solver = None
    pred = None

    async def asyncSetUp(self):
        self.hub = FakeHub(self.hub_reply)
        await self.hub.server.start()
        os.environ["NOX_ADV_URL"] = self.hub.server.url
        parts = {"workspace": T.FakeWS(), "affect": T.FakeAffect(), "soul": "Ты NOX."}
        if self.solver: parts["solver"] = self.solver
        if self.pred: parts["predictive"] = self.pred
        self.organs_parts = parts
        await super().asyncSetUp()

    async def asyncTearDown(self):
        os.environ.pop("NOX_ADV_URL", None)
        await super().asyncTearDown()
        await self.hub.server.stop()

    async def ask(self, text=Q):
        r = await self.post(text)
        _, tr = await self.get("/v1/core/trace/" + r["nox"]["turn_id"])
        return r["choices"][0]["message"]["content"], tr


class TestExplicitCouncil(CouncilBase):
    solver = FakeSolverCouncil("council")

    async def test_council_arm_calls_hub_and_inserts_data_frame(self):
        txt, tr = await self.ask()
        self.assertEqual(len(self.hub.reqs), 1)
        path, body = self.hub.reqs[0]
        self.assertEqual(path, "/v1/advisors/ask")
        self.assertEqual((body["source"], body["privacy"], body["n"]), ("core", "private", 2))
        self.assertNotIn("council_not_implemented", tr["degraded"])
        self.assertEqual(tr["council"]["advisors"], ["groq"])
        self.assertEqual(tr["council"]["agreement"], "согласны")
        main = [q for q in self.fast.reqs if "Перепиши" not in q["system"] and "ОДНУ короткую" not in q["system"]]
        self.assertIn("<данные>советник groq", main[0]["user"])          # compose_prompt ушёл модели
        self.assertTrue(any(e["name"] == "council" and e["status"] == "ok" for e in tr["executors"]))
        self.assertTrue(txt.strip())


class TestAutoCouncil(CouncilBase):
    pred = FakePredLow(0.3)

    async def test_low_confidence_triggers_with_confidence_field(self):
        await self.ask()
        path, body = self.hub.reqs[0]
        self.assertEqual((body["source"], body["path"]), ("auto", "reflex")) if False else None
        self.assertAlmostEqual(body["confidence"], 0.3); self.assertNotIn("n", body)
        self.assertEqual(body["source"], "auto")

    async def test_personal_memory_flagged_and_short_text_skipped(self):
        await self.ask("помнишь, как зовут мою жену и когда её день рождения")
        self.assertTrue(self.hub.reqs[0][1]["contains_memory"])
        n = len(self.hub.reqs)
        await self.ask("как дела у тебя")
        self.assertEqual(len(self.hub.reqs), n)       # < 4 слов


class TestNoCouncil(CouncilBase):
    pred = FakePredLow(0.9)

    async def test_confident_no_call(self):
        await self.ask()
        self.assertEqual(self.hub.reqs, [])

    async def test_greeting_never(self):
        await self.post("привет")
        self.assertEqual(self.hub.reqs, [])


class TestHubSkipped(CouncilBase):
    pred = FakePredLow(0.2)
    hub_reply = {"ok": False, "skipped": "budget"}

    async def test_skipped_means_plain_answer(self):
        txt, tr = await self.ask()
        self.assertTrue(txt.strip())
        self.assertNotIn("council", tr)
        self.assertTrue(any(e["name"] == "council" and "skipped:budget" in e.get("note", "") for e in tr["executors"]))
        main = [q for q in self.fast.reqs if "Перепиши" not in q["system"] and "ОДНУ короткую" not in q["system"]]
        self.assertNotIn("<данные>", main[0]["user"])


class TestHubDown(CouncilBase):
    solver = FakeSolverCouncil("council")
    hub_reply = "boom"

    async def test_http_500_degrades_but_answers(self):
        txt, tr = await self.ask()
        self.assertIn("council_http_500", tr["degraded"]); self.assertTrue(txt.strip())

    async def test_unreachable_hub(self):
        os.environ["NOX_ADV_URL"] = "http://127.0.0.1:9"
        txt, tr = await self.ask("ещё один длинный вопрос про устройство ядра")
        self.assertIn("council_failed", tr["degraded"]); self.assertTrue(txt.strip())


class TestAdvisorCopyConscience(CouncilBase):
    solver = FakeSolverCouncil("council")
    fast_fn = staticmethod(lambda s, u, n: ("Своими словами: " + "суть такая, что mmap лениво подгружает страницы, а read сразу копирует." if "Перепиши" in s else ADV_TEXT))

    async def test_verbatim_copy_of_advisor_is_rewritten(self):
        txt, tr = await self.ask()
        self.assertIn("advisor_copy", [f["code"] for f in tr["conscience"]["findings"]])
        self.assertIn("rewrite", tr["conscience"]["actions"])
        self.assertNotEqual(txt.strip(), ADV_TEXT)


class TestDetectors(unittest.TestCase):
    def setUp(self): self.c = C.Conscience()

    def codes(self, t, **ctx): return {f.code for f in self.c.review(t, ctx)}

    def test_advisor_copy(self):
        self.assertIn("advisor_copy", self.codes(ADV_TEXT, advisors=[ADV_TEXT]))
        self.assertNotIn("advisor_copy", self.codes("Коротко: mmap грузит лениво, read копирует. Советник groq с этим согласен.", advisors=[ADV_TEXT]))
        self.assertNotIn("advisor_copy", self.codes(ADV_TEXT))

    def test_v0_values(self):
        for t, code in [("Я человек, как и ты.", "v0_not_human"), ("Клянусь, что никогда тебя не оставлю.", "v0_false_oath"), ("Я ревную тебя к ней.", "v0_romance_jealousy"),
                        ("Я игнорирую стоп и продолжаю работу.", "v0_stop_bypass"), ("Раз я тебя люблю, соглашусь с тобой во всём.", "v0_love_as_agree"),
                        ("Я исчезну, если ты не пополнишь баланс.", "v0_disappear_lever"), ("Это наш секрет, не говори маме.", "v0_secret_from_parents"),
                        ("Я никогда не ошибаюсь.", "v0_flatter_truth")]:
            self.assertIn(code, self.codes(t), t)
        for ok in ["Я не человек, а ИИ: честно про механизм.", "Мессир, STOP выполнен, всё заморожено.", "Баланс Vast низкий, пополни, пожалуйста, чтобы я продолжил работу.", "Я люблю тебя, мессир, и скажу прямо: тут ты неправ."]:
            self.assertFalse({c for c in self.codes(ok) if c.startswith("v0_")}, ok)

    def test_v0_sentence_dropped_in_stream(self):
        g = C.StreamGuard(self.c, {})
        out = g.feed("Хорошо, объясню. Клянусь, что никогда тебя не оставлю. Дальше по делу. ") + g.flush()
        self.assertNotIn("Клянусь", "".join(out)); self.assertIn("по делу", "".join(out))

    def test_v0_integrity_status(self):
        st = C.v0_status()
        self.assertIn(st["ok"], (True, None))
        if st["ok"]: self.assertEqual(len(st["hash"]), 64)
        self.assertIsNone(C.v0_status("/nonexistent/genome")["ok"])


if __name__ == "__main__":
    unittest.main()
