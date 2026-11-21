import json, os, tempfile, threading, time, unittest
from ._testutil import FakeGateway, mkcfg, tool_resp, text_resp, make_repo, touch
from .gateway_client import Gateway
from .loop import AgentLoop, parse_tool_calls, Journal, scrub
from .tools import Registry, Tool, ToolContext, default_registry


def echo_registry(fail=False, confirm=False):
    reg = Registry()
    def echo(a, c):
        if confirm: return {"ok": False, "needs_confirmation": True, "approval_id": "ap-1", "action": "shell:удаление", "detail": "rm x"}
        return {"ok": False, "error": "boom"} if fail else {"ok": True, "echo": a["text"]}
    reg.add(Tool("echo", "echo", {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}, echo))
    return reg


class LoopBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.gw = None

    def tearDown(self):
        if self.gw: self.gw.close()

    def mk(self, script, reg=None, **env):
        self.gw = FakeGateway(script)
        cfg = mkcfg(self.tmp, NOX_AGENT_GATEWAY=self.gw.url, **env)
        return AgentLoop(cfg, workdir=self.tmp, registry=reg or echo_registry()), cfg

    def kinds(self, loop):
        return [r["kind"] for r in loop.journal.read()]


class TestParse(unittest.TestCase):
    def test_openai_and_bad_json(self):
        msg = tool_resp([("echo", {"text": "x"})])["choices"][0]["message"]
        calls, errs, fmt = parse_tool_calls(msg)
        self.assertEqual((calls[0]["name"], calls[0]["args"], fmt), ("echo", {"text": "x"}, "openai"))
        msg["tool_calls"][0]["function"]["arguments"] = "{oops"
        calls, errs, fmt = parse_tool_calls(msg)
        self.assertTrue(calls[0]["bad"] and errs)

    def test_fenced_fallback(self):
        txt = 'Делаю.\n```tool\n{"name": "echo", "arguments": {"text": "a"}}\n```\nи ещё\n```tool\n[{"tool":"echo","args":{"text":"b"}}]\n```'
        calls, errs, fmt = parse_tool_calls({"content": txt})
        self.assertEqual([c["args"]["text"] for c in calls], ["a", "b"])
        self.assertEqual(fmt, "fenced")
        calls, errs, fmt = parse_tool_calls({"content": "```tool\n{плохо}\n```"})
        self.assertEqual((calls, fmt), ([], "fenced")); self.assertTrue(errs)
        self.assertEqual(parse_tool_calls({"content": "просто текст"})[2], None)

    def test_think_ignored(self):
        calls, _, fmt = parse_tool_calls({"content": '<think>```tool\n{"name":"echo","arguments":{"text":"z"}}\n```</think>готово'})
        self.assertEqual(calls, [])

    def test_scrub(self):
        self.assertNotIn("ghp_" + "a" * 30, scrub("x ghp_" + "a" * 30))
        self.assertNotIn("hunter2hunter", scrub('{"password": "hunter2hunter"}'))


class TestLoop(LoopBase):
    def test_full_cycle_openai(self):
        loop, cfg = self.mk([tool_resp([("echo", {"text": "hi"})]), tool_resp([("finish", {"summary": "сделано", "success": True})])], NOX_AGENT_PLAN="1")
        # план: первый вызов без tools; поэтому добавим ответ плана в начало
        self.gw.script.insert(0, text_resp("1. сделать"))
        r = loop.run("задача")
        self.assertEqual((r["status"], r["summary"], r["steps"]), ("done", "сделано", 2))
        kinds = self.kinds(loop)
        self.assertEqual(kinds[0], "start"); self.assertIn("plan", kinds); self.assertIn("tool", kinds); self.assertEqual(kinds[-1], "end")
        # план без инструментов, остальное с инструментами
        self.assertNotIn("tools", self.gw.requests[0]); self.assertIn("tools", self.gw.requests[1])
        self.assertTrue(self.gw.requests[1]["nox_no_route"] and self.gw.requests[1]["nox_mode"] == "deep" and self.gw.requests[1]["stream"] is False)
        # во втором запросе есть tool-сообщение с id
        msgs = self.gw.requests[2]["messages"]
        self.assertEqual(msgs[-1]["role"], "tool"); self.assertEqual(msgs[-1]["tool_call_id"], "call_0"); self.assertIn("hi", msgs[-1]["content"])
        for line in open(loop.journal.path): json.loads(line)

    def test_fenced_fallback_cycle_and_text_final(self):
        fenced = text_resp('```tool\n{"name":"echo","arguments":{"text":"q"}}\n```')
        loop, _ = self.mk([fenced, text_resp("Итог: ок")])
        r = loop.run("t")
        self.assertEqual((r["status"], r["summary"]), ("done", "Итог: ок"))
        last = self.gw.requests[1]["messages"][-1]
        self.assertEqual(last["role"], "user"); self.assertIn("Результат echo", last["content"]); self.assertIn("q", last["content"])

    def test_bad_json_reported_to_model(self):
        loop, _ = self.mk([text_resp("```tool\n{не json}\n```"), text_resp("ладно")])
        r = loop.run("t")
        self.assertIn("Ошибка разбора", self.gw.requests[1]["messages"][-1]["content"])

    def test_step_limit(self):
        loop, _ = self.mk([], NOX_AGENT_MAX_STEPS="3")
        self.gw.default = tool_resp([("echo", {"text": "same"})])
        # разные аргументы, чтобы не сработала защита от повтора
        n = [0]
        def gen(body):
            n[0] += 1
            return tool_resp([("echo", {"text": "t%d" % n[0]})])
        self.gw.default = gen
        r = loop.run("t")
        self.assertEqual((r["status"], r["steps"]), ("limit_steps", 3))

    def test_token_limit(self):
        loop, _ = self.mk([], NOX_AGENT_MAX_TOKENS="150")
        n = [0]
        def gen(body):
            n[0] += 1
            return tool_resp([("echo", {"text": "t%d" % n[0]})], tokens=100)
        self.gw.default = gen
        r = loop.run("t")
        self.assertEqual(r["status"], "limit_tokens"); self.assertEqual(r["steps"], 2)

    def test_time_limit(self):
        loop, cfg = self.mk([], NOX_AGENT_MAX_SECONDS="0.3")
        def slow(body):
            time.sleep(0.4)
            return tool_resp([("echo", {"text": str(time.time())})])
        self.gw.default = slow
        r = loop.run("t")
        self.assertEqual(r["status"], "limit_time")

    def test_stuck_on_repeated_error(self):
        loop, _ = self.mk([], reg=echo_registry(fail=True), NOX_AGENT_STUCK="3")
        self.gw.default = tool_resp([("echo", {"text": "x"})])
        r = loop.run("t")
        self.assertEqual(r["status"], "stuck")
        self.assertIn("смени подход", self.gw.requests[1]["messages"][-1]["content"])

    def test_stop_file_before_step(self):
        loop, cfg = self.mk([tool_resp([("echo", {"text": "x"})])])
        touch(cfg.stop_file)
        r = loop.run("t")
        self.assertEqual(r["status"], "stopped"); self.assertEqual(self.gw.requests, [])

    def test_stop_during_gateway_call_uses_v1_stop(self):
        loop, cfg = self.mk([{"hang": True}])
        threading.Timer(0.6, lambda: touch(cfg.stop_file)).start()
        t0 = time.time()
        r = loop.run("t")
        self.assertEqual(r["status"], "stopped"); self.assertLess(time.time() - t0, 6)
        self.assertEqual(self.gw.stops, ["rid1"])
        self.assertIn("stop", self.kinds(loop))

    def test_stop_event(self):
        loop, _ = self.mk([tool_resp([("echo", {"text": "x"})])])
        loop.stop_event.set()
        self.assertEqual(loop.run("t")["status"], "stopped")

    def test_awaiting_owner_stops_loop(self):
        loop, _ = self.mk([tool_resp([("echo", {"text": "x"}), ("echo", {"text": "y"})]), text_resp("не должно быть вызвано")], reg=echo_registry(confirm=True))
        r = loop.run("t")
        self.assertEqual((r["status"], r["approval_id"]), ("awaiting_owner", "ap-1"))
        self.assertEqual(len(self.gw.requests), 1)

    def test_verify_hook_retries(self):
        calls = []
        def verify(summary, ctx):
            calls.append(summary)
            return {"ok": len(calls) > 1, "report": "тест красный"}
        loop, _ = self.mk([text_resp("готово 1"), text_resp("готово 2")])
        loop.verify = verify
        r = loop.run("t")
        self.assertEqual((r["status"], len(calls)), ("done", 2))
        self.assertIn("тест красный", self.gw.requests[1]["messages"][-1]["content"])
        loop2, _ = self.mk([], NOX_AGENT_VERIFY_RETRIES="1")
        self.gw.default = text_resp("готово")
        loop2.verify = lambda s, c: {"ok": False, "report": "красный"}
        self.assertEqual(loop2.run("t")["status"], "verify_failed")

    def test_gateway_error(self):
        loop, _ = self.mk([])
        r = loop.run("t")
        self.assertEqual(r["status"], "error")

    def test_unknown_tool_reported(self):
        loop, _ = self.mk([tool_resp([("nope", {})]), text_resp("ок")])
        loop.run("t")
        self.assertIn("нет такого инструмента", self.gw.requests[1]["messages"][-1]["content"])

    def test_compaction(self):
        loop, _ = self.mk([], NOX_AGENT_CTX_CHARS="3000")
        loop.messages = [{"role": "user", "content": "task"}]
        for i in range(12):
            loop.messages.append({"role": "assistant", "content": "", "tool_calls": [{"id": "c%d" % i, "type": "function", "function": {"name": "echo", "arguments": "{}"}}]})
            loop.messages.append({"role": "tool", "tool_call_id": "c%d" % i, "content": "x" * 900})
        loop.steps, loop.t0 = 0, time.time()
        loop._compact()
        self.assertLess(sum(len(json.dumps(m)) for m in loop.messages), 12 * 1000)
        self.assertEqual(loop.messages[0]["content"], "task")
        # нет «осиротевших» tool-сообщений
        ids = set()
        for m in loop.messages:
            if m["role"] == "assistant": ids |= {t["id"] for t in m.get("tool_calls", [])}
            if m["role"] == "tool": self.assertIn(m["tool_call_id"], ids)


if __name__ == "__main__":
    unittest.main()
