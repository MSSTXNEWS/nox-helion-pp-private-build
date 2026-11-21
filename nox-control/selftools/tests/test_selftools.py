import http.server
import json
import os
import sys
import tempfile
import threading
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
TMP = tempfile.mkdtemp(prefix="nox_st_")
os.environ["NOX_ALLOW_ROOTS"] = os.pathsep.join([TMP, os.path.dirname(os.path.dirname(HERE)), os.path.dirname(os.path.dirname(os.path.dirname(HERE)))])
os.environ["NOX_AUDIT_LOG"] = os.path.join(TMP, "audit.jsonl")
os.environ["NOX_DISPATCH_DIR"] = os.path.join(TMP, "disp")
os.environ["NOX_TRAIN_DIR"] = os.path.join(TMP, "train")
os.environ["NOX_WEB_ALLOW"] = "127.0.0.1"
os.environ["NOX_WEB_ALLOW_HTTP"] = "1"
import registry as R  # noqa: E402

R.load_all()
call = R.call


def w(name, text):
    p = os.path.join(TMP, name)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w", encoding="utf-8").write(text)
    return p


class Srv:
    """Mock OpenAI-compatible + file server."""
    def __init__(self, handler):
        self.s = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.url = "http://127.0.0.1:%d" % self.s.server_port
        threading.Thread(target=self.s.serve_forever, daemon=True).start()

    def close(self):
        self.s.shutdown()
        self.s.server_close()


def chat_handler(reply, stream_tokens=6):
    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            body = b"ok"
            if self.path == "/blob":
                body = b"model-bytes" * 100
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            n = int(self.headers["Content-Length"])
            req = json.loads(self.rfile.read(n))
            self.send_response(200)
            if self.path.endswith("/embeddings"):
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                ins = req["input"]
                vecs = [[1.0 if "alpha" in t else 0.0, 1.0 if "beta" in t else 0.0] for t in ins]
                self.wfile.write(json.dumps({"data": [{"embedding": v} for v in vecs]}).encode())
            elif req.get("stream"):
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                for i in range(stream_tokens):
                    self.wfile.write(("data: " + json.dumps({"choices": [{"delta": {"content": "t%d " % i}}]}) + "\n\n").encode())
                    self.wfile.flush()
                self.wfile.write(b"data: [DONE]\n\n")
            else:
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"choices": [{"message": {"content": reply}}]}).encode())
    return H


class TestRegistry(unittest.TestCase):
    def test_thirty_tools(self):
        self.assertEqual(len(R.TOOLS), 30)
        for t in R.TOOLS.values():
            self.assertIn(t["mode"], ("read", "write", "danger"))
            self.assertTrue(t["doc"])

    def test_validation_and_unknown(self):
        self.assertFalse(call("repo_read", {})["ok"])
        self.assertIn("unknown arg", call("repo_read", {"path": "x", "zzz": 1})["error"])
        self.assertIn("unknown tool", call("nope")["error"])

    def test_path_allowlist(self):
        r = call("repo_read", {"path": "/etc/passwd"})
        self.assertFalse(r["ok"])
        self.assertTrue(r.get("denied"))
        r = call("repo_read", {"path": TMP + "/../../etc/passwd"})
        self.assertTrue(r.get("denied"))

    def test_command_allowlist(self):
        with self.assertRaises(R.Denied):
            R.run(["rm", "-rf", "/"])

    def test_danger_needs_confirm(self):
        r = call("sandbox_run", {"cmd": ["python3", "-c", "print(1)"]})
        self.assertIn("blocked", r)
        r = call("sandbox_run", {"cmd": ["python3", "-c", "print(1)"]}, confirm=True)
        self.assertTrue(r["ok"]) 
        self.assertEqual(r["stdout"].strip(), "1")

    def test_audit_written(self):
        call("repo_read", {"path": TMP})
        lines = open(os.environ["NOX_AUDIT_LOG"]).read().splitlines()
        self.assertTrue(any(json.loads(l)["tool"] == "repo_read" for l in lines))

    def test_cli_describe(self):
        self.assertEqual(len(R.describe()), 30)


class TestReadTools(unittest.TestCase):
    def test_repo_read_grep_map(self):
        p = w("a/x.py", "import os\n\ndef foo():\n    '''d'''\n    return 1\n")
        r = call("repo_read", {"path": p, "start": 3, "end": 4})
        self.assertIn("3\tdef foo", r["text"])
        self.assertEqual(call("repo_read", {"path": os.path.dirname(p)})["entries"], ["x.py"])
        g = call("repo_grep", {"pattern": r"def \w+", "path": TMP + "/a"})
        self.assertEqual(g["hits"][0]["line"], 3)
        self.assertFalse(call("repo_grep", {"pattern": "("})["ok"])
        m = call("self_map", {"path": TMP + "/a"})
        self.assertEqual(m["files"][0]["functions"], ["foo"])

    def test_log_tail(self):
        p = w("l/log.txt", "".join("line%d %s\n" % (i, "ERR" if i % 100 == 0 else "ok") for i in range(1, 5001)))
        r = call("log_tail", {"path": p, "lines": 3})
        self.assertEqual(r["lines"][-1], "line5000 ERR")
        self.assertEqual(len(r["lines"]), 3)
        r = call("log_tail", {"path": p, "lines": 2, "grep": "ERR"})
        self.assertEqual(r["lines"], ["line4900 ERR", "line5000 ERR"])

    def test_lint(self):
        good = w("lint/g.py", "x = 1\n")
        bad = w("lint/b.py", "def (:\n")
        sh = w("lint/s.sh", "echo hi\n")
        r = call("lint_syntax", {"paths": [good, bad, sh]})
        self.assertFalse(r["ok"])
        self.assertEqual([f["ok"] for f in r["files"]], [True, False, True])
        js = w("lint/j.js", "let x = ;\n")
        rj = call("lint_syntax", {"paths": [js]})
        self.assertFalse(rj["ok"])  # node missing -> blocked, node present -> syntax error

    def test_gpu_mem_plan(self):
        r = call("gpu_alloc", {"gpus": [{"index": 0, "free_mb": 24000}, {"index": 1, "free_mb": 8000}],
                               "jobs": [{"name": "llm", "vram_mb": 20000}, {"name": "emb", "vram_mb": 4000}, {"name": "big", "vram_mb": 30000}]})
        self.assertEqual({p["name"]: p["gpu"] for p in r["placed"]}, {"llm": 0, "emb": 1})
        self.assertEqual(r["unplaced"], ["big"])
        m = call("mem_alloc", {"components": [{"name": "a", "mb": 5000}], "available_mb": 8000})
        self.assertTrue(m["fits"])
        m = call("mem_alloc", {"components": [{"name": "a", "mb": 9000}], "available_mb": 8000})
        self.assertFalse(m["ok"])

    def test_gpu_blocked_without_smi(self):
        with mock.patch("gpu_alloc.R.run", return_value={"rc": 127, "out": "", "err": "not installed", "missing": True}):
            r = call("gpu_alloc", {})
        self.assertIn("blocked", r)
        self.assertIn("need", r)

    def test_inspector_hook(self):
        d = os.path.join(TMP, "insp")
        w("insp/INSPECTOR.md", "# insp\n")
        w("insp/HISTORY.jsonl", json.dumps({"ts": "2020-01-01T00:00:00Z", "note": "a"}) + "\nbad\n")
        r = call("inspector_hook", {"dir": d})
        self.assertEqual(r["count"], 1)
        self.assertEqual(r["bad_lines"], 1)
        self.assertTrue(r["stale"])
        real = call("inspector_hook", {})
        self.assertTrue(real["ok"])

    def test_test_runner(self):
        w("tr/test_a.py", "import unittest\nclass T(unittest.TestCase):\n    def test_a(self): self.assertTrue(1)\n")
        r = call("test_runner", {"start_dir": TMP + "/tr"})
        self.assertTrue(r["ok"])
        self.assertEqual(r["ran"], 1)
        w("tr2/test_b.py", "import unittest\nclass T(unittest.TestCase):\n    def test_b(self): self.assertTrue(0)\n")
        r = call("test_runner", {"start_dir": TMP + "/tr2"})
        self.assertFalse(r["ok"])
        self.assertEqual(r["failures"], 1)

    def test_health_probe(self):
        s = Srv(chat_handler("x"))
        try:
            r = call("health_probe", {"targets": [{"name": "up", "url": s.url + "/health"}, {"name": "down", "url": "http://127.0.0.1:1/health"}]})
        finally:
            s.close()
        self.assertFalse(r["ok"])
        self.assertEqual([t["up"] for t in r["targets"]], [True, False])

    def test_speed_bench(self):
        s = Srv(chat_handler("x", stream_tokens=8))
        try:
            r = call("speed_bench", {"endpoint": s.url, "runs": 2})
            self.assertTrue(r["ok"])
            self.assertEqual(r["runs"][0]["tokens"], 8)
            self.assertGreater(r["avg_tok_s"], 0)
        finally:
            s.close()
        r = call("speed_bench", {"endpoint": "http://127.0.0.1:1", "runs": 1})
        self.assertIn("blocked", r)

    def test_judge_and_eval(self):
        s = Srv(chat_handler('noise {"verdict":"pass","score":0.9,"reasons":["ok"]} tail'))
        try:
            r = call("judge_run", {"task": "t", "answer": "a", "criteria": "c", "endpoint": s.url})
            self.assertEqual(r["verdict"], "pass")
            h = w("ev/hold.jsonl", json.dumps({"prompt": "q", "contains": "verdict"}) + "\n" + json.dumps({"prompt": "q2", "exact": "zzz"}) + "\n")
            e = call("eval_gate", {"action": "score", "holdout": h, "endpoint": s.url})
            self.assertEqual(e["score"], 0.5)
        finally:
            s.close()
        self.assertIn("blocked", call("judge_run", {"task": "t", "answer": "a", "criteria": "c", "endpoint": "http://127.0.0.1:1"}))
        self.assertIn("blocked", call("eval_gate", {"action": "score", "holdout": h}))
        a = w("ev/ans.jsonl", json.dumps({"answer": "x verdict"}) + "\n" + json.dumps({"answer": "zzz"}) + "\n")
        self.assertEqual(call("eval_gate", {"action": "score", "holdout": h, "answers": a})["score"], 1.0)
        self.assertTrue(call("eval_gate", {"action": "gate", "baseline": 0.8, "candidate": 0.79})["pass"])
        self.assertFalse(call("eval_gate", {"action": "gate", "baseline": 0.8, "candidate": 0.7})["pass"])

    def test_rag(self):
        w("rag/root/a.md", "alpha topic about cats and kittens\n" * 3)
        w("rag/root/b.md", "beta topic about rockets and engines\n" * 3)
        idx = os.path.join(TMP, "rag/index.json")
        self.assertFalse(os.path.exists(idx))
        d = call("rag_index", {"action": "build", "root": TMP + "/rag/root", "index": idx})
        self.assertTrue(d["dry_run"])
        self.assertFalse(os.path.exists(idx))
        b = call("rag_index", {"action": "build", "root": TMP + "/rag/root", "index": idx, "dry_run": False})
        self.assertEqual(b["chunks"], 2)
        q = call("rag_index", {"action": "query", "index": idx, "query": "rockets", "embed_url": "http://127.0.0.1:1"})
        self.assertEqual(q["mode"], "bm25")
        self.assertEqual(q["results"][0]["file"], "b.md")
        s = Srv(chat_handler("x"))
        try:
            q = call("rag_index", {"action": "query", "index": idx, "query": "alpha kittens", "embed_url": s.url})
        finally:
            s.close()
        self.assertEqual(q["mode"], "bm25+bge-m3")
        self.assertEqual(q["results"][0]["file"], "a.md")

    def test_web_fetch_allowlist(self):
        s = Srv(chat_handler("x"))
        try:
            r = call("web_fetch", {"url": s.url + "/blob"})
            self.assertTrue(r["ok"])
            self.assertTrue(r["text"].startswith("model-bytes"))
        finally:
            s.close()
        os.environ["NOX_WEB_ALLOW"] = "example.org"
        try:
            self.assertTrue(call("web_fetch", {"url": "https://evil.test/x"}).get("denied"))
        finally:
            os.environ["NOX_WEB_ALLOW"] = "127.0.0.1"

    def test_advisor_blocked_without_config(self):
        self.assertIn("blocked", call("advisor_ask", {"question": "hi", "config": TMP + "/none.json"}))

    def test_advisor_ask_real_module(self):
        cfgp = w("adv/a.json", json.dumps([{"name": "x", "url": "http://127.0.0.1:1", "timeout_s": 1}]))
        self.assertIn("blocked", call("advisor_ask", {"question": "hi", "config": cfgp}))
        s = Srv(chat_handler("advice"))
        try:
            cfgp = w("adv/b.json", json.dumps([{"name": "x", "url": s.url, "timeout_s": 5}]))
            r = call("advisor_ask", {"question": "hi", "config": cfgp})
        finally:
            s.close()
        self.assertEqual(r["advisors"][0]["answer"], "advice")


class TestWriteTools(unittest.TestCase):
    DIFF = "--- a/f.txt\n+++ b/f.txt\n@@ -1,3 +1,3 @@\n one\n-two\n+TWO\n three\n"

    def test_patch_dry_then_real_with_backup_and_rollback(self):
        p = w("pt/f.txt", "one\ntwo\nthree\n")
        r = call("patch_apply", {"diff": self.DIFF, "root": TMP + "/pt"})
        self.assertTrue(r["dry_run"])
        self.assertEqual(open(p).read(), "one\ntwo\nthree\n")
        r = call("patch_apply", {"diff": self.DIFF, "root": TMP + "/pt", "dry_run": False})
        self.assertTrue(r["ok"])
        self.assertEqual(open(p).read(), "one\nTWO\nthree\n")
        self.assertTrue(os.path.exists(r["changed"][0]["backup"]))
        r = call("patch_apply", {"diff": self.DIFF, "root": TMP + "/pt", "dry_run": False})
        self.assertFalse(r["ok"])  # already applied: context mismatch
        rb = call("rollback", {"path": p})
        self.assertTrue(rb["dry_run"])
        rb = call("rollback", {"path": p, "dry_run": False})
        self.assertEqual(open(p).read(), "one\ntwo\nthree\n")
        self.assertTrue(rb["backup_of_current"])

    def test_patch_offset_and_create(self):
        p = w("pt2/g.txt", "x\nx\none\ntwo\nthree\n")
        r = call("patch_apply", {"diff": self.DIFF.replace("f.txt", "g.txt"), "root": TMP + "/pt2", "dry_run": False})
        self.assertTrue(r["ok"], r)
        self.assertIn("TWO", open(p).read())
        newd = "--- /dev/null\n+++ b/new.txt\n@@ -0,0 +1,2 @@\n+a\n+b\n"
        r = call("patch_apply", {"diff": newd, "root": TMP + "/pt2", "dry_run": False})
        self.assertTrue(r["ok"], r)
        self.assertEqual(open(TMP + "/pt2/new.txt").read(), "a\nb\n")

    def test_patch_path_escape(self):
        d = "--- a/../../../etc/x\n+++ b/../../../etc/x\n@@ -1 +1 @@\n-a\n+b\n"
        self.assertTrue(call("patch_apply", {"diff": d, "root": TMP}).get("denied"))

    def test_backup(self):
        p = w("bk/f.txt", "hello")
        self.assertNotIn("backup", call("backup_before_edit", {"path": p}))
        r = call("backup_before_edit", {"path": p, "dry_run": False})
        self.assertEqual(open(r["backup"]).read(), "hello")

    def test_task_board(self):
        self.assertIn("blocked", call("task_board", {"action": "list"}))
        os.makedirs(os.environ["NOX_DISPATCH_DIR"])
        r = call("task_board", {"action": "add", "task": {"id": "t1", "title": "x"}})
        self.assertTrue(r["dry_run"])
        self.assertEqual(call("task_board", {"action": "list"})["tasks"], [])
        call("task_board", {"action": "add", "task": {"id": "t1"}, "dry_run": False})
        call("task_board", {"action": "add", "task": {"id": "t2"}, "dry_run": False})
        self.assertFalse(call("task_board", {"action": "add", "task": {"id": "t2"}, "dry_run": False})["ok"])
        self.assertEqual(call("task_board", {"action": "pop", "dry_run": False})["task"]["id"], "t1")
        call("task_board", {"action": "update", "id": "t2", "fields": {"status": "done"}, "dry_run": False})
        self.assertEqual(call("task_board", {"action": "get", "id": "t2"})["task"]["status"], "done")
        call("task_board", {"action": "set_state", "key": "paused", "value": True, "dry_run": False})
        self.assertTrue(call("task_board", {"action": "list"})["state"]["paused"])

    def test_task_board_concurrent_locking(self):
        d = os.environ["NOX_DISPATCH_DIR"]
        os.makedirs(d, exist_ok=True)
        ts = [threading.Thread(target=lambda i=i: call("task_board", {"action": "add", "task": {"id": "c%d" % i}, "dry_run": False})) for i in range(20)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        ids = [t["id"] for t in call("task_board", {"action": "list"})["tasks"]]
        self.assertEqual(len([i for i in ids if i.startswith("c")]), 20)

    def test_svc_ctl(self):
        self.assertTrue(call("svc_ctl", {"action": "restart", "name": "nox-web"})["dry_run"])
        self.assertTrue(call("svc_ctl", {"action": "restart", "name": "sshd"}).get("denied"))
        self.assertIn("blocked", call("svc_ctl", {"action": "stop", "name": "nox-web"}))  # danger needs confirm
        with mock.patch("svc_ctl.R.run", return_value={"rc": 127, "out": "", "err": "", "missing": True}):
            self.assertIn("blocked", call("svc_ctl", {"action": "restart", "name": "nox-web", "dry_run": False}))
        with mock.patch("svc_ctl.R.run", return_value={"rc": 0, "out": "nox-web RUNNING", "err": ""}) as m:
            r = call("svc_ctl", {"action": "restart", "name": "nox-web", "dry_run": False})
        self.assertTrue(r["ok"])
        self.assertEqual(m.call_args[0][0], ["supervisorctl", "restart", "nox-web"])

    def test_disk_guard(self):
        old = w("dg/x.bak", "zz")
        os.utime(old, (1, 1))
        keep = w("dg/keep.txt", "k")
        os.utime(keep, (1, 1))
        os.environ["NOX_CLEAN_ROOTS"] = TMP + "/dg"
        try:
            self.assertTrue(call("disk_guard", {"action": "report", "paths": [TMP]})["ok"])
            pl = call("disk_guard", {"action": "plan_clean"})
            self.assertEqual(pl["count"], 1)
            self.assertIn("blocked", call("disk_guard", {"action": "clean"}))
            self.assertTrue(os.path.exists(old))
            r = call("disk_guard", {"action": "clean"}, confirm=True)
            self.assertEqual(r["removed"], 1)
            self.assertFalse(os.path.exists(old))
            self.assertTrue(os.path.exists(keep))
        finally:
            del os.environ["NOX_CLEAN_ROOTS"]

    def test_priority_ctl(self):
        pid = os.getpid()
        cur = call("priority_ctl", {"pid": pid})["current"]["nice"]
        r = call("priority_ctl", {"pid": pid, "nice": min(19, cur + 1)})
        self.assertTrue(r["dry_run"])
        self.assertEqual(call("priority_ctl", {"pid": pid})["current"]["nice"], cur)
        self.assertTrue(call("priority_ctl", {"pid": 1, "nice": 5}).get("denied"))
        r = call("priority_ctl", {"pid": pid, "nice": min(19, cur + 1), "dry_run": False})
        self.assertTrue(r["ok"], r)
        self.assertFalse(call("priority_ctl", {"pid": pid, "nice": 99})["ok"])

    def test_corpus_build_dedup(self):
        w("cb/c1.md", "| A1 | Do thing | It passes | TODO |\n| A2 | Other | Works | TODO |\n|---|---|---|---|\n")
        w("cb/c2.md", "| A1 | Do thing | It passes | TODO |\n")
        out = os.path.join(TMP, "cb/out.jsonl")
        with mock.patch("corpus_build.R.safe_path", side_effect=lambda p, **k: out if p == out else os.path.join(TMP, "cb")):
            r = call("corpus_build", {"cards_glob": "*.md", "out": out, "include_commits": False, "dry_run": False})
            self.assertEqual((r["new"], r["duplicates"]), (2, 1))
            r = call("corpus_build", {"cards_glob": "*.md", "out": out, "include_commits": False, "dry_run": False})
            self.assertEqual(r["new"], 0)
        rows = [json.loads(l) for l in open(out)]
        self.assertEqual(sorted(x["instruction"] for x in rows), ["Do thing", "Other"])

    def test_train_ctl(self):
        td = os.environ["NOX_TRAIN_DIR"]
        self.assertIn("blocked", call("train_ctl", {"action": "start", "dry_run": False}))
        os.makedirs(td, exist_ok=True)
        w("train/train.json", json.dumps({"cmd": ["python3", "-c", "import time; time.sleep(30)"], "cwd": td}))
        self.assertEqual(call("train_ctl", {"action": "start"})["would_run"][0], "python3")
        call("train_ctl", {"action": "set_stop_flag", "dry_run": False})
        self.assertIn("blocked", call("train_ctl", {"action": "start", "dry_run": False}))
        call("train_ctl", {"action": "clear_stop_flag", "dry_run": False})
        r = call("train_ctl", {"action": "start", "dry_run": False})
        self.assertTrue(r["ok"], r)
        self.assertTrue(call("train_ctl", {"action": "status"})["running"])
        self.assertIn("blocked", call("train_ctl", {"action": "stop"}))
        st = call("train_ctl", {"action": "stop"}, confirm=True)
        self.assertEqual(st["stopped_pid"], r["pid"])
        import time
        time.sleep(0.5)
        try:
            os.waitpid(r["pid"], os.WNOHANG)
        except ChildProcessError:
            pass
        self.assertFalse(call("train_ctl", {"action": "status"})["running"])

    def test_branch_pr(self):
        r = call("branch_pr", {"action": "open_pr", "repo": "o/r", "head": "b", "title": "T", "body": "B"})
        self.assertTrue(r["dry_run"])
        self.assertTrue(r["payload"]["body"].endswith("https://claude.com/claude-code)"))
        self.assertEqual(r["would_call"], ["POST", "https://api.github.com/repos/o/r/pulls"])
        c = call("branch_pr", {"action": "commit", "message": "m", "paths": ["a"]})
        self.assertIn("Claude-Session:", c["would_run"][1][-1])
        self.assertTrue(call("branch_pr", {"action": "push", "branch": "x; rm -rf"}) ["ok"] is False)
        with mock.patch("branch_pr._token", return_value=None):
            self.assertIn("blocked", call("branch_pr", {"action": "merge_pr", "repo": "o/r", "pr": 5, "dry_run": False}))
        with mock.patch("branch_pr._token", return_value="tok"), mock.patch("branch_pr._http", return_value=(200, {"merged": True})) as h:
            r = call("branch_pr", {"action": "merge_pr", "repo": "o/r", "pr": 5, "dry_run": False})
        self.assertTrue(r["merged"])
        self.assertEqual(h.call_args[0][:2], ("PUT", "https://api.github.com/repos/o/r/pulls/5/merge"))
        self.assertEqual(h.call_args[0][3], {"merge_method": "squash"})

    def test_branch_pr_real_git(self):
        d = os.path.join(TMP, "gitr")
        os.makedirs(d)
        import subprocess
        for c in (["init", "-q", "-b", "main"], ["config", "user.email", "a@b"], ["config", "user.name", "n"]):
            subprocess.run(["git"] + c, cwd=d, check=True)
        w("gitr/f", "1")
        r = call("branch_pr", {"action": "commit", "message": "first", "paths": ["f"], "cwd": d, "dry_run": False})
        self.assertTrue(r["ok"], r)
        self.assertIn("Claude-Session", subprocess.run(["git", "log", "-1", "--format=%B"], cwd=d, capture_output=True, text=True).stdout)
        self.assertEqual(call("branch_pr", {"action": "status", "cwd": d})["branch"], "main")

    def test_lora_swap_with_rollback(self):
        d = os.path.join(TMP, "lora")
        os.makedirs(d)
        a1, a2 = w("lora/a1.gguf", "1"), w("lora/a2.gguf", "2")
        link = os.path.join(d, "current.gguf")
        os.symlink(a1, link)
        ok = {"rc": 0, "out": "", "err": ""}
        self.assertTrue(call("lora_swap", {"action": "swap", "link": link, "adapter": a2, "service": "llama-main"})["dry_run"])
        self.assertEqual(os.readlink(link), a1)
        with mock.patch("lora_swap._restart", return_value=ok), mock.patch("lora_swap._healthy", return_value=True):
            r = call("lora_swap", {"action": "swap", "link": link, "adapter": a2, "service": "llama-main", "dry_run": False})
        self.assertTrue(r["ok"])
        self.assertEqual(os.readlink(link), a2)
        health = iter([False, True])
        with mock.patch("lora_swap._restart", return_value=ok), mock.patch("lora_swap._healthy", side_effect=lambda *a, **k: next(health)):
            r = call("lora_swap", {"action": "swap", "link": link, "adapter": a1, "service": "llama-main", "dry_run": False})
        self.assertFalse(r["ok"])
        self.assertTrue(r["rolled_back"])
        self.assertEqual(os.readlink(link), a2)  # restored to previous
        self.assertTrue(call("lora_swap", {"action": "swap", "link": link, "adapter": a1, "service": "sshd"}).get("denied"))

    def test_pc_pull(self):
        dest = TMP + "/pcdest"
        fail = {"rc": 255, "out": "", "err": "Connection timed out", "missing": False}
        with mock.patch("pc_pull.R.run", return_value=fail):
            r = call("pc_pull", {"remote_path": "/home/u/data", "dest": dest, "user": "u"})
        self.assertIn("blocked", r)
        self.assertIn("need", r)
        calls = []

        def fake(argv, **k):
            calls.append(argv)
            return {"rc": 0, "out": "ok", "err": ""}
        with mock.patch("pc_pull.R.run", side_effect=fake):
            r = call("pc_pull", {"remote_path": "/home/u/data", "dest": dest, "user": "u"})
        self.assertTrue(r["dry_run"])
        self.assertIn("-n", calls[1])
        self.assertIn("u@100.84.111.36:/home/u/data", calls[1])
        self.assertTrue(call("pc_pull", {"remote_path": "/a; rm -rf /", "dest": dest, "user": "u"}).get("denied"))

    def test_model_dl(self):
        s = Srv(chat_handler("x"))
        dest = TMP + "/models/m.bin"
        import hashlib
        good = hashlib.sha256(b"model-bytes" * 100).hexdigest()
        try:
            self.assertIn("blocked", call("model_dl", {"url": s.url + "/blob", "dest": dest, "sha256": good}))
            r = call("model_dl", {"url": s.url + "/blob", "dest": dest, "sha256": "0" * 64}, confirm=True)
            self.assertEqual(r["error"], "sha256 mismatch")
            self.assertFalse(os.path.exists(dest) or os.path.exists(dest + ".part"))
            r = call("model_dl", {"url": s.url + "/blob", "dest": dest, "sha256": good}, confirm=True)
            self.assertTrue(r["ok"], r)
            self.assertEqual(R.sha256_file(dest), good)
            self.assertFalse(call("model_dl", {"url": s.url + "/blob", "dest": dest, "sha256": good}, confirm=True)["ok"])
        finally:
            s.close()
        os.environ["NOX_WEB_ALLOW"] = "huggingface.co"
        try:
            self.assertTrue(call("model_dl", {"url": "http://127.0.0.1:1/x", "dest": TMP + "/q", "sha256": good}, confirm=True).get("denied"))
        finally:
            os.environ["NOX_WEB_ALLOW"] = "127.0.0.1"


if __name__ == "__main__":
    unittest.main()
