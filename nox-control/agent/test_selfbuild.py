import json, os, tempfile, unittest
from ._testutil import FakeGateway, mkcfg, make_repo, tool_resp, text_resp, sh, touch
from .selfbuild import SelfBuild, judge, is_code_task, danger_kinds, task_text
from .tools.approvals import Approvals

FEATURE = "def double(x):\n    return x * 2\n"
TEST = "import unittest\nfrom agent.feature import double\nclass T(unittest.TestCase):\n    def test_d(self):\n        self.assertEqual(double(2), 4)\n"


class SB(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.repo = make_repo(os.path.join(self.tmp, "repo"))
        self.steps = []
        self.verdict = {"ok": True, "reasons": ["диф по задаче"], "risks": []}

        def handler(body):
            if body.get("nox_mode") == "fast":
                self.judge_prompt = body["messages"][0]["content"]
                return text_resp("Вердикт:\n```json\n%s\n```" % json.dumps(self.verdict, ensure_ascii=False))
            return self.steps.pop(0) if self.steps else text_resp("(нет шагов)")
        self.gw = FakeGateway(default=handler)
        self.cfg = mkcfg(self.tmp, NOX_AGENT_GATEWAY=self.gw.url, NOX_AGENT_HEALTH_URL=self.gw.url + "/v1/nox/stats", NOX_AGENT_MAX_STEPS="12")
        self.sb = SelfBuild(self.cfg)
        self.inbox([{"id": "t1", "class": "owner_order", "handler": "selfbuild", "title": "код: добавить функцию double", "status": "pending", "ts": "2026-11-22T10:00:00"}])

    def tearDown(self):
        self.gw.close()

    def inbox(self, rows):
        with open(self.cfg.inbox, "w", encoding="utf-8") as f:
            for r in rows: f.write(json.dumps(r, ensure_ascii=False) + "\n")

    def good_steps(self):
        return [tool_resp([("write_file", {"path": "nox-control/agent/feature.py", "content": FEATURE})]),
                tool_resp([("write_file", {"path": "nox-control/agent/test_feature.py", "content": TEST})]),
                tool_resp([("run_tests", {})]),
                tool_resp([("git", {"action": "commit", "message": "feat: double"})]),
                tool_resp([("finish", {"summary": "добавлена double и тест", "success": True})])]

    def head(self): return sh(self.repo, "git", "rev-parse", "HEAD")


class TestHelpers(unittest.TestCase):
    def test_task_filters(self):
        self.assertTrue(is_code_task({"handler": "selfbuild"})); self.assertTrue(is_code_task({"title": "Код: x"})); self.assertTrue(is_code_task({"title": "selfbuild: x"}))
        self.assertFalse(is_code_task({"handler": "track", "title": "Бэкап"}))
        self.assertEqual(task_text({"title": "код: сделать", "body": "детали"}), "сделать\nдетали")

    def test_danger(self):
        for t, k in [("удалить логи", "удаление"), ("оплатить счёт", "деньги"), ("выдать доступ", "доступы"), ("перенести на S2", "S2"), ("запустить Vast инстанс", "Vast"), ("останови инстанс", "Vast")]:
            self.assertIn(k, danger_kinds(t), t)
        self.assertEqual(danger_kinds("добавить функцию double"), [])


class TestJudge(SB):
    def test_judge_parses_and_fails_closed(self):
        t = {"title": "x"}
        green = {"ok": True, "ran": 3, "failures": 0, "errors": 0}
        v = judge(t, "diff --git a b", green, self.cfg)
        self.assertTrue(v["ok"]); self.assertIn("диф по задаче", v["reasons"])
        self.assertIn("diff --git", self.judge_prompt)
        self.assertEqual(self.gw.requests[-1]["nox_mode"], "fast")              # быстрый тир
        self.assertFalse(judge(t, "d", {"ok": False}, self.cfg)["ok"])           # красные тесты: модель не нужна
        self.assertFalse(judge(t, "  ", green, self.cfg)["ok"])
        self.gw.default = lambda b: text_resp("ну вроде нормально")
        self.assertFalse(judge(t, "d", green, self.cfg)["ok"])                   # не JSON
        self.gw.default = lambda b: text_resp('{"ok": "true"}')
        self.assertFalse(judge(t, "d", green, self.cfg)["ok"])                   # строка не True
        self.gw.default = lambda b: text_resp('{"verdict": "pass", "reasons": []}')
        self.assertTrue(judge(t, "d", green, self.cfg)["ok"])
        self.gw.close(); self.assertFalse(judge(t, "d", green, self.cfg)["ok"])  # шлюз недоступен


class TestSelfBuild(SB):
    def test_full_cycle_merges_and_saves_skill(self):
        self.steps = self.good_steps()
        before = self.head()
        r = self.sb.run_next()
        self.assertEqual(r["status"], "merged", r)
        self.assertNotEqual(self.head(), before)
        self.assertTrue(os.path.exists(os.path.join(self.repo, "nox-control/agent/feature.py")))
        self.assertTrue(r["judge"]["ok"]); self.assertTrue(r["tests"]["ok"]); self.assertGreaterEqual(r["tests"]["ran"], 2)
        self.assertEqual(self.sb.planner.state()["t1"]["status"], "done")
        self.assertIn("Итог: merged", r["report"])
        self.assertTrue(r["skill_id"]); self.assertEqual(self.sb.skills.search("добавить функцию double")[0]["id"], r["skill_id"])
        self.assertIsNone(self.sb.planner.next(accept=is_code_task))           # задача закрыта
        # судья видел диф с кодом
        self.assertIn("def double", self.judge_prompt)
        # журнал каждого шага
        self.assertTrue(os.path.exists(r["workdir"]) is False)

    def test_judge_rejects_no_merge(self):
        self.steps = self.good_steps(); self.verdict = {"ok": False, "reasons": ["лишнее"], "risks": []}
        before = self.head()
        r = self.sb.run_next()
        self.assertEqual(r["status"], "rejected"); self.assertEqual(self.head(), before)
        self.assertEqual(self.sb.planner.state()["t1"]["status"], "failed"); self.assertIn("лишнее", r["report"])

    def test_loop_failure_leaves_main_untouched(self):
        self.steps = [text_resp("не знаю как")] * 1
        self.sb.cfg.verify_retries = 0
        before = self.head()
        r = self.sb.run_next()
        self.assertNotEqual(r["status"], "merged"); self.assertEqual(self.head(), before)

    def test_danger_task_stops_at_owner_then_resumes(self):
        self.inbox([{"id": "t2", "handler": "selfbuild", "title": "код: удалить устаревший файл README", "status": "pending", "ts": 1}])
        r = self.sb.run_next()
        self.assertEqual(r["status"], "awaiting_owner"); self.assertEqual(self.gw.requests, [])          # модель не вызывалась
        self.assertFalse(os.path.exists(self.cfg.work_root))
        ap = Approvals(self.cfg.approvals_file)
        self.assertEqual(len(ap.pending()), 1)
        self.assertEqual(self.sb.planner.state()["t2"]["status"], "awaiting_owner")
        self.assertEqual(self.sb.run_next()["status"], "idle")
        ap.decide(r["approval_id"], "approved")
        self.steps = [tool_resp([("write_file", {"path": "nox-control/agent/feature.py", "content": FEATURE})]),
                      tool_resp([("write_file", {"path": "nox-control/agent/test_feature.py", "content": TEST})]),
                      tool_resp([("git", {"action": "commit", "message": "x"})]), tool_resp([("finish", {"summary": "ok", "success": True})])]
        r2 = self.sb.run_next()
        self.assertEqual(r2["status"], "merged", r2)

    def test_denied_by_owner_closes_task(self):
        self.inbox([{"id": "t3", "handler": "selfbuild", "title": "код: оплатить хостинг", "status": "pending", "ts": 1}])
        r = self.sb.run_next()
        Approvals(self.cfg.approvals_file).decide(r["approval_id"], "denied")
        self.assertEqual(self.sb.run_next()["status"], "idle")
        self.assertEqual(self.sb.planner.state()["t3"]["status"], "failed")

    def test_shell_delete_inside_loop_stops_on_owner(self):
        self.steps = [tool_resp([("write_file", {"path": "junk.txt", "content": "j"})]), tool_resp([("shell", {"cmd": "rm junk.txt"})]), text_resp("не должно дойти")]
        r = self.sb.run_next()
        self.assertEqual(r["status"], "awaiting_owner", r)
        self.assertEqual(self.sb.planner.state()["t1"]["status"], "awaiting_owner")
        self.assertEqual(len(Approvals(self.cfg.approvals_file).pending()), 1)

    def test_deletion_in_patch_requires_owner_at_merge(self):
        touch(os.path.join(self.repo, "old.txt"), "o"); sh(self.repo, "git", "add", "-A"); sh(self.repo, "git", "commit", "-q", "-m", "old")
        self.steps = [tool_resp([("shell", {"cmd": "git status"})]), tool_resp([("finish", {"summary": "ничего", "success": True})])]
        # агент через git-инструмент удаляет файл только через shell rm (подтверждение), поэтому моделируем удаление прямо в ветке
        orig = self.sb.sandbox.create
        def create(title, tid=""):
            s = orig(title, tid)
            os.remove(os.path.join(s["path"], "old.txt")); sh(s["path"], "git", "add", "-A"); sh(s["path"], "git", "commit", "-q", "-m", "rm old")
            return s
        self.sb.sandbox.create = create
        r = self.sb.run_next()
        self.assertEqual(r["status"], "awaiting_owner", r); self.assertEqual(r["stage"], "release")
        self.assertTrue(os.path.exists(os.path.join(self.repo, "old.txt")))

    def test_stop_flag(self):
        touch(self.cfg.stop_file)
        self.assertEqual(self.sb.run_next()["status"], "stopped")
        self.assertEqual(self.gw.requests, [])

    def test_only_code_tasks(self):
        self.inbox([{"id": "hb-1", "class": "owner_order", "handler": "track", "title": "Напомнить про бэкап", "status": "pending", "ts": 1}])
        self.assertEqual(self.sb.run_next()["status"], "idle")


if __name__ == "__main__":
    unittest.main()
