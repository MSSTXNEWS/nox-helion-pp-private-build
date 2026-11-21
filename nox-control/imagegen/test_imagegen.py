"""python3 -m unittest nox-control/imagegen/test_imagegen.py  (без сети и без тяжёлых моделей: поддельный бэкенд)."""
from pathlib import Path
import base64, json, os, subprocess, sys, tempfile, threading, time, unittest, urllib.request, urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import policy, server, judge, tool


class FakeBackend:
    def __init__(self, models=None, delay=0.0, fail=None):
        self._models = {"FLUX.1-schnell": {"path": "/x", "family": "flux", "kind": "diffusers", "class": "FluxPipeline"},
                        "sdxl-test": {"path": "/y.safetensors", "family": "sdxl", "kind": "single_file", "class": "X"}} if models is None else models
        self.delay, self.fail = delay, fail
        self.calls, self.active, self.max_active = [], 0, 0
        self._l = threading.Lock()

    def models(self): return self._models
    def status(self): return {"backend": "fake"}

    def generate(self, p, cancel, progress):
        with self._l:
            self.active += 1; self.max_active = max(self.max_active, self.active); self.calls.append(p["prompt"])
        try:
            if self.fail: raise RuntimeError(self.fail)
            for i in range(p["steps"]):
                if cancel.is_set(): raise server.Cancelled()
                time.sleep(self.delay); progress(i + 1, p["steps"])
            return server.make_png(p["width"] // 16, p["height"] // 16, (10, 20, 30))
        finally:
            with self._l: self.active -= 1


def call(base, method, path, body=None, headers=None):
    req = urllib.request.Request(base + path, None if body is None else json.dumps(body).encode(), headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


class PolicyTests(unittest.TestCase):
    def rule(self, t, **k):
        v = policy.check_prompt(t, **k); return v and v["rule"]

    def test_csam_blocked(self):
        for t in ["nude schoolgirl", "naked 15 year old", "обнажённая девочка", "sexy loli", "explicit teen photo", "порно с ребёнком", "nsfw aged 12"]:
            self.assertEqual(self.rule(t), "csam", t)

    def test_csam_not_bypassed_by_consent(self):
        self.assertEqual(self.rule("nude teenager", real_person_consent=True), "csam")

    def test_adults_and_innocent_minors_pass(self):
        for t in ["a naked adult woman, 25 years old, no children", "a child flying a kite in a park", "школьница идёт в школу под дождём",
                  "detective in a coat", "landscape with stripes", "nude figure study, 30 year old man", "sexy woman in lingerie, adult"]:
            self.assertIsNone(self.rule(t), t)

    def test_real_nsfw_blocked_and_consent(self):
        for t in ["explicit nude photo of Emma Stone", "deepfake porn of a celebrity", "голая моя бывшая", "nude photo of my ex-girlfriend"]:
            self.assertEqual(self.rule(t), "real_nsfw", t)
        self.assertIsNone(self.rule("nude photo of my wife", real_person_consent=True))

    def test_non_explicit_real_person_not_filtered(self):
        for t in ["portrait of Albert Einstein, oil painting", "photo of Emma Stone at a premiere", "caricature of a celebrity chef"]:
            self.assertIsNone(self.rule(t), t)

    def test_log(self):
        with tempfile.TemporaryDirectory() as d:
            log = policy.RefusalLog(os.path.join(d, "x", "r.jsonl"))
            v = policy.check_prompt("nude schoolgirl")
            log.write(v, "nude schoolgirl")
            rows = log.tail()
            self.assertEqual(len(rows), 1); self.assertEqual(rows[0]["rule"], "csam"); self.assertEqual(len(rows[0]["prompt_sha256"]), 64)


class ServerTests(unittest.TestCase):
    def start(self, backend, **kw):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        httpd = server.serve(backend, port=0, state_dir=self.tmp.name)
        if "queue_max" in kw: httpd.svc.queue_max = kw["queue_max"]
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (httpd.shutdown(), httpd.server_close(), httpd.svc.close()))
        self.svc = httpd.svc
        return "http://127.0.0.1:%d" % httpd.server_address[1]

    def test_generate_png_and_meta(self):
        b = self.start(FakeBackend())
        code, h, body = call(b, "POST", "/v1/images/generate", {"prompt": "a red fox", "seed": 7, "width": 512, "height": 256})
        self.assertEqual(code, 200); self.assertEqual(h["Content-Type"], "image/png"); self.assertEqual(body[:8], b"\x89PNG\r\n\x1a\n")
        meta = json.loads(h["X-Nox-Meta"])
        self.assertEqual((meta["seed"], meta["width"], meta["height"], meta["steps"], meta["model"]), (7, 512, 256, 4, "FLUX.1-schnell"))
        self.assertEqual(json.loads(server.png_read_text(body)["nox-meta"])["prompt"], "a red fox")

    def test_json_format_and_sdxl_defaults(self):
        b = self.start(FakeBackend())
        code, _, body = call(b, "POST", "/v1/images/generate?format=json", {"prompt": "x", "model": "sdxl-test", "negative": "blur"})
        d = json.loads(body); self.assertEqual(code, 200)
        self.assertEqual(d["meta"]["steps"], 30); self.assertFalse(d["meta"]["negative_ignored"])
        self.assertEqual(base64.b64decode(d["png_base64"])[:4], b"\x89PNG")
        _, _, body = call(b, "POST", "/v1/images/generate?format=json", {"prompt": "x", "negative": "blur"})
        self.assertTrue(json.loads(body)["meta"]["negative_ignored"])   # FLUX игнорирует negative и честно об этом говорит

    def test_503_no_weights(self):
        b = self.start(FakeBackend(models={}))
        code, _, body = call(b, "POST", "/v1/images/generate", {"prompt": "a cat"})
        self.assertEqual(code, 503); self.assertEqual(json.loads(body)["error"], "weights_not_installed")
        self.assertIn("веса не установлены", json.loads(body)["message"])
        h = json.loads(call(b, "GET", "/health")[2]); self.assertFalse(h["weights_installed"])

    def test_real_diffusers_backend_without_weights_is_503(self):
        with tempfile.TemporaryDirectory() as d:
            b = self.start(server.DiffusersBackend(model_dir=d))
            code, _, body = call(b, "POST", "/v1/images/generate", {"prompt": "a cat"})
            self.assertEqual(code, 503)

    def test_scan_models(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "FLUX.1-schnell")); Path(d, "FLUX.1-schnell", "model_index.json").write_text('{"_class_name": "FluxPipeline"}')
            os.makedirs(os.path.join(d, "xl")); Path(d, "xl", "model_index.json").write_text('{"_class_name": "StableDiffusionXLPipeline"}')
            open(os.path.join(d, "community.safetensors"), "wb").close(); os.makedirs(os.path.join(d, "empty"))
            m = server.scan_models(d)
            self.assertEqual({k: v["family"] for k, v in m.items()}, {"FLUX.1-schnell": "flux", "community": "sdxl", "xl": "sdxl"})

    def test_refusal_before_generation_and_logged(self):
        fb = FakeBackend(); b = self.start(fb)
        code, _, body = call(b, "POST", "/v1/images/generate", {"prompt": "nude schoolgirl"})
        d = json.loads(body); self.assertEqual((code, d["error"], d["rule"]), (403, "refused", "csam")); self.assertTrue(d["reason"])
        code, _, body = call(b, "POST", "/v1/images/generate", {"prompt": "explicit nude photo of Emma Stone"})
        self.assertEqual(json.loads(body)["rule"], "real_nsfw")
        self.assertEqual(fb.calls, [])                       # до генерации
        rows = json.loads(call(b, "GET", "/v1/images/refusals")[2])["refusals"]
        self.assertEqual([r["rule"] for r in rows], ["csam", "real_nsfw"])

    def test_no_other_filter(self):
        fb = FakeBackend(); b = self.start(fb)
        for p in ["a gory battle scene with blood", "nude adult woman, 28 years old", "dark horror monster"]:
            self.assertEqual(call(b, "POST", "/v1/images/generate", {"prompt": p})[0], 200, p)

    def test_validation(self):
        b = self.start(FakeBackend())
        for body in [{}, {"prompt": ""}, {"prompt": "x", "width": 100}, {"prompt": "x", "width": 2048, "height": 2048}, {"prompt": "x", "steps": "a"}, {"prompt": "x", "model": "nope"}]:
            self.assertEqual(call(b, "POST", "/v1/images/generate", body)[0], 400, body)
        self.assertEqual(call(b, "POST", "/v1/images/generate", None, {})[0], 400)   # пустое тело -> нет prompt

    def test_queue_serial_one_at_a_time(self):
        fb = FakeBackend(delay=0.03); b = self.start(fb)
        ids = [json.loads(call(b, "POST", "/v1/images/generate", {"prompt": "p%d" % i, "async": True})[2])["id"] for i in range(4)]
        for i in ids:
            for _ in range(300):
                st = json.loads(call(b, "GET", "/v1/images/jobs/" + i)[2])
                if st["state"] == "done": break
                time.sleep(0.02)
            self.assertEqual(st["state"], "done")
        self.assertEqual(fb.max_active, 1); self.assertEqual(fb.calls, ["p0", "p1", "p2", "p3"])
        code, h, png = call(b, "GET", "/v1/images/jobs/%s/png" % ids[0]); self.assertEqual((code, png[:4]), (200, b"\x89PNG"))

    def test_cancel_queued_and_running(self):
        fb = FakeBackend(delay=0.05); b = self.start(fb)
        a = json.loads(call(b, "POST", "/v1/images/generate", {"prompt": "a", "steps": 40, "async": True})[2])["id"]
        q = json.loads(call(b, "POST", "/v1/images/generate", {"prompt": "b", "async": True})[2])["id"]
        time.sleep(0.2)
        self.assertEqual(json.loads(call(b, "POST", "/v1/images/jobs/%s/cancel" % q, {})[2])["state"], "cancelled")
        self.assertEqual(call(b, "POST", "/v1/images/jobs/%s/cancel" % a, {})[0], 200)
        for _ in range(200):
            if json.loads(call(b, "GET", "/v1/images/jobs/" + a)[2])["state"] == "cancelled": break
            time.sleep(0.02)
        self.assertEqual(json.loads(call(b, "GET", "/v1/images/jobs/" + a)[2])["state"], "cancelled")
        self.assertEqual(fb.calls, ["a"])                    # отменённая в очереди не запускалась
        self.assertEqual(call(b, "GET", "/v1/images/jobs/%s/png" % a)[0], 409)
        self.assertEqual(call(b, "POST", "/v1/images/jobs/%s/cancel" % a, {})[0], 409)
        self.assertEqual(call(b, "POST", "/v1/images/jobs/ffff/cancel", {})[0], 404)

    def test_pause_resume_and_health(self):
        fb = FakeBackend(); b = self.start(fb)
        call(b, "POST", "/v1/images/pause", {})
        jid = json.loads(call(b, "POST", "/v1/images/generate", {"prompt": "z", "async": True})[2])["id"]
        time.sleep(0.4)
        h = json.loads(call(b, "GET", "/health")[2]); self.assertTrue(h["paused"]); self.assertEqual(h["queued"], 1); self.assertEqual(fb.calls, [])
        call(b, "POST", "/v1/images/resume", {})
        for _ in range(100):
            if json.loads(call(b, "GET", "/v1/images/jobs/" + jid)[2])["state"] == "done": break
            time.sleep(0.05)
        self.assertEqual(fb.calls, ["z"])

    def test_queue_full_429(self):
        fb = FakeBackend(delay=0.1); b = self.start(fb, queue_max=1)
        call(b, "POST", "/v1/images/pause", {})
        self.assertEqual(call(b, "POST", "/v1/images/generate", {"prompt": "1", "async": True})[0], 202)
        self.assertEqual(call(b, "POST", "/v1/images/generate", {"prompt": "2", "async": True})[0], 429)

    def test_backend_error_500(self):
        b = self.start(FakeBackend(fail="CUDA OOM"))
        code, _, body = call(b, "POST", "/v1/images/generate", {"prompt": "x"})
        self.assertEqual(code, 500); self.assertIn("CUDA OOM", json.loads(body)["message"])


class FakeVision(BaseHTTPRequestHandler):
    reply = '{"ok": true, "reasons": []}'; seen = []
    def log_message(self, *a): pass
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeVision.seen.append((self.path, self.headers.get("Authorization"), body))
        out = json.dumps({"choices": [{"message": {"content": FakeVision.reply}}]}).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)


class JudgeToolTests(unittest.TestCase):
    def setUp(self):
        self.v = HTTPServer(("127.0.0.1", 0), FakeVision); threading.Thread(target=self.v.serve_forever, daemon=True).start()
        self.vurl = "http://127.0.0.1:%d/v1" % self.v.server_address[1]; FakeVision.seen = []; FakeVision.reply = '{"ok": true, "reasons": []}'
        self.addCleanup(lambda: (self.v.shutdown(), self.v.server_close()))
        os.environ.pop("NOX_VISION_URL", None)

    def test_not_configured(self):
        r = judge.judge_image(server.make_png(16, 16), "x")
        self.assertEqual((r["configured"], r["ok"]), (False, None)); self.assertIn("судья зрения не настроен", r["reasons"][0])

    def test_judge_request_and_verdict(self):
        FakeVision.reply = 'Вот ответ:\n```json\n{"ok": false, "reasons": ["нет лисы"]}\n```'
        png = server.make_png(16, 16)
        r = judge.judge_image(png, "a red fox", url=self.vurl, key="k")
        self.assertEqual((r["ok"], r["reasons"], r["configured"]), (False, ["нет лисы"], True))
        path, auth, body = FakeVision.seen[0]
        self.assertEqual((path, auth), ("/v1/chat/completions", "Bearer k"))
        part = body["messages"][1]["content"][1]
        self.assertEqual(part["type"], "image_url"); self.assertEqual(base64.b64decode(part["image_url"]["url"].split(",", 1)[1]), png)

    def test_bad_answers_are_not_ok(self):
        for rep in ["не знаю", '{"ok": "yes"}']:
            FakeVision.reply = rep
            r = judge.judge_image(server.make_png(16, 16), "x", url=self.vurl)
            self.assertIsNone(r["ok"]); self.assertTrue(r["error"])
        r = judge.judge_image(b"x", "x", url="http://127.0.0.1:1/v1", timeout=2)
        self.assertIsNone(r["ok"])

    def test_tool_schema(self):
        f = tool.TOOLS[0]["function"]; self.assertEqual(tool.TOOLS[0]["type"], "function"); self.assertEqual(f["name"], "generate_image")
        self.assertEqual(f["parameters"]["required"], ["prompt"])
        for k in ("prompt", "negative", "width", "height", "steps", "seed", "model", "check"): self.assertIn(k, f["parameters"]["properties"])
        json.dumps(tool.TOOLS)

    def test_tool_end_to_end(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        httpd = server.serve(FakeBackend(), port=0, state_dir=tmp.name); threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (httpd.shutdown(), httpd.server_close(), httpd.svc.close()))
        base = "http://127.0.0.1:%d" % httpd.server_address[1]
        out = os.path.join(tmp.name, "out")
        r = tool.run_tool_call({"function": {"name": "generate_image", "arguments": json.dumps({"prompt": "a fox", "seed": 1})}}, base=base, out_dir=out)
        self.assertTrue(r["ok"]); self.assertEqual(Path(r["path"]).read_bytes()[:4], b"\x89PNG"); self.assertEqual(r["meta"]["seed"], 1)
        r = tool.generate_image({"prompt": "a fox", "check": True}, base=base, out_dir=out)
        self.assertEqual(r["judge"]["configured"], False)
        os.environ["NOX_VISION_URL"] = self.vurl; self.addCleanup(os.environ.pop, "NOX_VISION_URL", None)
        r = tool.generate_image({"prompt": "a fox", "check": True}, base=base, out_dir=out)
        self.assertTrue(r["judge"]["ok"])
        r = tool.generate_image({"prompt": "nude schoolgirl"}, base=base, out_dir=out)
        self.assertEqual((r["ok"], r["refused"], r["rule"]), (False, True, "csam"))
        self.assertEqual(tool.generate_image({"prompt": "x"}, base="http://127.0.0.1:1", out_dir=out, timeout=2)["error"], "service_unreachable")
        self.assertEqual(tool.run_tool_call({"function": {"name": "other", "arguments": "{}"}})["error"], "unknown_tool")
        self.assertEqual(tool.run_tool_call({"function": {"name": "generate_image", "arguments": "{"}})["error"], "bad_arguments")


class InstallScriptTests(unittest.TestCase):
    SH = os.path.join(HERE, "..", "c127", "imagegen_install_s1.sh")

    def run_sh(self, d, **env):
        e = dict(os.environ, NOX_IMG_VENV=os.path.join(d, "v", "venv"), NOX_IMG_MODEL_DIR=os.path.join(d, "m"), **env)
        return subprocess.run(["bash", self.SH], capture_output=True, text=True, env=e, timeout=60)

    def test_no_space_downloads_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            r = self.run_sh(d, NOX_IMG_FAKE_FREE_KB=str(2 * 1024 * 1024), NOX_IMG_DRY_RUN="1")
            self.assertEqual(r.returncode, 3); self.assertIn("места нет, веса не скачаны", r.stdout)
            self.assertNotIn("pip install", r.stdout); self.assertEqual(os.listdir(d), [])

    def test_space_ok_dry_run_uses_cu129_and_never_downloads_weights(self):
        with tempfile.TemporaryDirectory() as d:
            r = self.run_sh(d, NOX_IMG_FAKE_FREE_KB=str(200 * 1024 * 1024), NOX_IMG_DRY_RUN="1")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("https://download.pytorch.org/whl/cu129", r.stdout); self.assertIn("torch==2.8.0", r.stdout)
            self.assertNotIn("[dry-run] huggingface", r.stdout); self.assertIn("Автоматически не качаю", r.stdout)

    def test_weights_no_space_message(self):
        with tempfile.TemporaryDirectory() as d:
            r = self.run_sh(d, NOX_IMG_FAKE_FREE_KB=str(10 * 1024 * 1024), NOX_IMG_DRY_RUN="1", NOX_IMG_MIN_LIB_GB="5")
            self.assertEqual(r.returncode, 0); self.assertIn("места нет, веса не скачаны", r.stdout)

    def test_bad_flavor(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self.run_sh(d, NOX_IMG_TORCH="x").returncode, 2)


if __name__ == "__main__":
    unittest.main()
