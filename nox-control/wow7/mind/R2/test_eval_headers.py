"""Тесты патча BRAIN/nox_core.py: X-NOX-Eval (метка [EVAL], очистка, ничему не учит) и X-NOX-Ablate (абляция эпизода). Запуск: cd MIND/R2 && python3 -m unittest test_eval_headers"""
import asyncio, os, sys, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
BRAIN = os.path.abspath(os.path.join(HERE, "..", "..", "BRAIN"))
sys.path.insert(0, BRAIN)
import test_core as T
import netio


class Rec:
    def __init__(self):
        self.observed, self.late, self.pred, self.obs, self.after, self.forgot = [], [], [], [], [], []

    # solver
    def run(self, text, ctx, turn_id=None):
        return None

    def observe(self, tid, oc):
        self.observed.append(tid)

    def observe_late(self, tid, oc):
        self.late.append(tid)

    # predictive
    def predict(self, tid, ctx, text):
        self.pred.append(tid)
        return None

    def post_to_workspace(self, ws):
        return 0


def last_answer_req(fast, marker):
    """Последний запрос к быстрой модели, где в реплике стоит marker (отсекает переписывания Совести)."""
    return [r for r in fast.reqs if marker in r["user"] and "Перепиши" not in r["system"]][-1]


class EvalBase(T.Base):
    fast_fn = staticmethod(lambda s, u, n: "Ответ готов, мессир, номер %d." % n)

    async def asyncSetUp(self):
        self.rec = Rec()
        self.mem_calls = []
        rec = self.rec

        def memory(text, tid):
            self.mem_calls.append(tid)
            return {"core": "Создатель любит чай\nЭПИЗОД-ep1 слово ЯНТАРЬ", "recalled": ["факт про ЭПИЗОД-ep1: ЯНТАРЬ-77", "общий факт", {"turn_id": "ep1", "text": "запись"}]}

        def after(u, r, tid):
            rec.after.append((u, r, tid))

        def forget(ids):
            rec.forgot.extend(ids)
            return {"ok": True, "forgotten": len(ids)}
        self.organs_parts = {"workspace": T.FakeWS(), "affect": T.FakeAffect(), "solver": rec, "predictive": rec, "memory": memory, "after": after, "forget": forget}
        await super().asyncSetUp()

    async def purge(self, **body):
        st, obj = await netio.json_call("POST", "http://127.0.0.1:%d/v1/core/eval/purge" % self.port, body, 5.0)
        return obj


class TestEval(EvalBase):
    async def test_eval_turn_marked_and_teaches_nobody(self):
        r = await self.post("как устроена твоя память", headers={"X-NOX-Eval": "1", "X-NOX-Bench": "mind"})
        tid = r["nox"]["turn_id"]
        await self.chron(tid)
        self.assertEqual(self.rec.observed, [])
        self.assertEqual(self.rec.pred, [])
        self.assertTrue(self.rec.after[0][0].startswith("[EVAL] ") and self.rec.after[0][1].startswith("[EVAL] "))
        _, tr = await self.get("/v1/core/trace/" + tid)
        self.assertEqual(tr["eval"], {"bench": "mind"})
        self.assertEqual(tr["chronicler"]["mind"], {"skipped": "eval"})

    async def test_normal_turn_learns_and_is_not_marked(self):
        r = await self.post("как устроена твоя память")
        tid = r["nox"]["turn_id"]
        await self.chron(tid)
        self.assertEqual(self.rec.observed, [tid])
        self.assertEqual(self.rec.pred, [tid])
        self.assertFalse(self.rec.after[0][0].startswith("[EVAL]"))
        _, tr = await self.get("/v1/core/trace/" + tid)
        self.assertNotIn("eval", tr)

    async def test_purge_removes_only_eval(self):
        e = await self.post("как устроена твоя память", conv="bench-1", headers={"X-NOX-Eval": "1", "X-NOX-Bench": "mind"})
        live = await self.post("как устроена твоя память", conv="live-1")
        await self.chron(e["nox"]["turn_id"])
        res = await self.purge(bench="mind")
        self.assertEqual(res["purged_turns"], 1)
        self.assertEqual(self.rec.forgot, [e["nox"]["turn_id"]])
        self.assertNotIn("bench-1", self.core.convs)
        self.assertIn("live-1", self.core.convs)
        self.assertEqual((await self.purge(bench="mind"))["purged_turns"], 0)       # повтор безопасен

    async def test_session_header_separates_conversations(self):
        await self.post("запомни слово ЯНТАРЬ", conv=None, headers={"X-NOX-Session": "A"})
        await self.post("привет снова", conv=None, headers={"X-NOX-Session": "B"})
        self.assertIn("A", self.core.convs)
        self.assertIn("B", self.core.convs)


class TestAblate(EvalBase):
    async def test_ablate_episode_from_history_and_memory(self):
        await self.post("запомни кодовое слово ЯНТАРЬ-55", conv="c", nox_turn_id="ep1")
        # контроль: без заголовка эпизод виден и в истории, и в памяти
        await self.post("какое кодовое слово?", conv="c")
        ctl = last_answer_req(self.fast, "какое кодовое слово")
        self.assertIn("ЯНТАРЬ-55", " ".join(m["content"] for m in ctl["all"]))
        self.assertIn("ЭПИЗОД-ep1", ctl["user"])
        # с абляцией: ни история хода ep1, ни записи памяти с ep1
        r = await self.post("какое кодовое слово?", conv="c", headers={"X-NOX-Ablate": "episode:ep1"})
        ab = last_answer_req(self.fast, "какое кодовое слово")
        self.assertNotIn("ЯНТАРЬ-55", " ".join(m["content"] for m in ab["all"]))
        self.assertNotIn("ЭПИЗОД-ep1", ab["user"])
        self.assertIn("Создатель любит чай", ab["user"])                           # остальная память цела
        _, tr = await self.get("/v1/core/trace/" + r["nox"]["turn_id"])
        self.assertEqual(tr["ablate"]["episodes"], ["ep1"])
        self.assertEqual(tr["ablate"]["dropped_history"], 2)
        self.assertEqual(tr["ablate"]["dropped_recalled"], 3)                       # 2 записи recalled + строка core

    async def test_ablate_is_per_request_and_garbage_ignored(self):
        await self.post("запомни кодовое слово ЯНТАРЬ-55", conv="c", nox_turn_id="ep1")
        await self.post("а теперь?", conv="c", headers={"X-NOX-Ablate": "episode:ep1"})
        await self.post("и снова?", conv="c")
        self.assertIn("ЯНТАРЬ-55", " ".join(m["content"] for m in last_answer_req(self.fast, "и снова")["all"]))      # абляция не стёрла историю насовсем
        self.assertEqual(self.core.parse_ablate("мусор; episode:; episode:a b"), [])
        self.assertEqual(self.core.parse_ablate("episode:t-1, episode:t-2"), ["t-1", "t-2"])


class TestBridgeInCore(EvalBase):
    async def asyncSetUp(self):
        import tempfile
        sys.path.insert(0, HERE)
        import mind_bridge as MBR, curiosity as CU
        await super().asyncSetUp()
        self.td = tempfile.mkdtemp()
        self.ib = CU.GrowthInbox(os.path.join(self.td, "inbox.jsonl"))
        self.core.organs.parts["bridge"] = MBR.MindBridge(self.rec, self.rec, None, None, self.ib)

    async def test_chronicler_goes_through_bridge(self):
        r = await self.post("как устроена твоя память")
        tid = r["nox"]["turn_id"]
        await self.chron(tid)
        _, tr = await self.get("/v1/core/trace/" + tid)
        self.assertEqual(tr["chronicler"]["mind"]["growth"], "queued")
        self.assertEqual(self.ib.pending(), 1)
        await self.post("нет, не так, ты ошибся")
        self.assertEqual(self.rec.late, [tid])
        e = await self.post("как устроена память", headers={"X-NOX-Eval": "1"})
        await self.chron(e["nox"]["turn_id"])
        await self.chron(self.core.turns and list(self.core.turns)[-2])
        n = self.ib.pending()
        self.assertEqual(n, 3)                                      # ход1 + поправка Создателя + ход2; eval-ход в рост не попал


if __name__ == "__main__":
    unittest.main()
