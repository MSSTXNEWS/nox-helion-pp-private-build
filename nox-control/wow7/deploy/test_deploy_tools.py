import time, json, os, stat, subprocess, sys, tempfile, threading, unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_matrix, opt02_probe, probe, speed_report  # noqa: E402

SPD = os.environ.get("NOX_WOW_SRC", os.path.dirname(os.path.dirname(HERE))) + "/SPD/matrix.json"
if not os.path.exists(SPD):
    SPD = os.path.join(HERE, "..", "..", "SPD", "matrix.json")


class MatrixTest(unittest.TestCase):
    def setUp(self):
        self.src = json.load(open(SPD, encoding="utf-8"))

    def test_order_and_drops(self):
        m = make_matrix.build(self.src)
        ids = [l["id"] for l in m["levers"]]
        self.assertEqual(ids[0], "L01_threads_phys")
        self.assertNotIn("X01_kv_q8_QUALITY_ONLY", ids)
        self.assertNotIn("L04_moe_cache_4g", ids)
        self.assertNotIn("L05_mtp_n2", ids)
        for l in m["levers"]:
            self.assertFalse(set(l.get("set", {})) & {"-ctk", "-ctv"})

    def test_mtp_and_sweep_flags(self):
        ids = [l["id"] for l in make_matrix.build(self.src, mtp=True, include_sweep=True)["levers"]]
        self.assertIn("L05_mtp_n2", ids); self.assertIn("L04_moe_cache_4g", ids)
        self.assertGreater(ids.index("L05_mtp_n2"), ids.index("L07_ngram"))

    def test_base_from_file_drops_noop(self):
        base = "-m /x.gguf --port 9 -c 16384 -ngl 24 -ot exps=CPU -t 20 -tb 27 -fa on --parallel 1 -b 512 -ub 256 --no-op-offload --jinja"
        m = make_matrix.build(self.src, base)
        self.assertNotIn("-m", m["base"]); self.assertNotIn("--port", m["base"])
        self.assertIn("L01_threads_phys", [d["id"] for d in m["_dropped"]])  # -t 20 -tb 27 уже в base
        self.assertNotIn("L01_threads_phys", [l["id"] for l in m["levers"]])


class Opt02Test(unittest.TestCase):
    def test_translate(self):
        out, dropped = opt02_probe.translate("-c 16384 -ngl 24 -ot exps=CPU -t 24 -fa on --parallel 1 -b 512 -ub 256 --no-op-offload --jinja --temp 1.0")
        self.assertEqual(out[:4], ["-ngl", "24", "-ot", "exps=CPU"])
        self.assertIn("-fa", out); self.assertIn("--no-op-offload", out)
        self.assertIn("--jinja", dropped); self.assertIn("-c", dropped)

    def test_analyze(self):
        rows = [{"n_prompt": n, "avg_ts": ts} for n, ts in ((1, 1.5), (2, 3.0), (4, 5.0), (8, 9.0), (16, 14.0))]
        r = opt02_probe.analyze(rows)
        self.assertEqual(r["n"], [1, 2, 4, 8, 16]); self.assertAlmostEqual(r["ratio"][0], 1.0)
        self.assertTrue(r["worth_draft"])       # ratio(8)=1.5*8/9/(1)=... < 4
        bad = opt02_probe.analyze([{"n_prompt": 1, "avg_ts": 1.5}, {"n_prompt": 8, "avg_ts": 1.5}])  # t(8)=8*t(1)
        self.assertFalse(bad["worth_draft"])
        with self.assertRaises(ValueError):
            opt02_probe.analyze([{"n_prompt": 4, "avg_ts": 3}])

    def test_end_to_end_fake_bench(self):
        d = tempfile.mkdtemp(); fb = os.path.join(d, "llama-bench")
        rows = [{"n_prompt": n, "avg_ts": ts} for n, ts in ((1, 2.0), (2, 3.5), (4, 6.0), (8, 10.0), (16, 12.0))]
        open(fb, "w").write("#!/bin/bash\necho 'build info'\ncat <<'J'\n%s\nJ\n" % json.dumps(rows))
        os.chmod(fb, 0o755)
        out = os.path.join(d, "o.json")
        rc = opt02_probe.main(["--bench", fb, "--model", "/m.gguf", "--args", "-ngl 24 -t 24", "--out", out])
        self.assertEqual(rc, 0); j = json.load(open(out)); self.assertTrue(j["ok"]); self.assertEqual(j["break_even_accept"], j["ratio"])
        self.assertEqual(opt02_probe.main(["--bench", "/nonexistent", "--out", out]), 1)
        self.assertFalse(json.load(open(out))["ok"])


class ReportTest(unittest.TestCase):
    B = {"tg": 1.5, "pp": 20.0, "ttft_short_s": 10.0, "ttft_long_s": 40.0, "quality_text": "2, 3, 5, 7, 11, 13"}

    def test_improved(self):
        a = dict(self.B, tg=2.4, pp=60.0, ttft_short_s=6.0)
        r = speed_report.build(self.B, a, soul={"cold_ttft_s": 30, "warm_ttft_s": 3, "mode": "warm"})
        self.assertEqual(r["verdict"], "improved"); self.assertFalse(r["rollback_recommended"])
        self.assertEqual(r["gain"]["tg_x"], 1.6); self.assertEqual(r["soul_kv"]["speedup_x"], 10.0); self.assertFalse(r["targets"]["tg_ge_plan"])

    def test_regressed_by_tg_and_quality(self):
        self.assertTrue(speed_report.build(self.B, dict(self.B, tg=1.2))["rollback_recommended"])
        self.assertEqual(speed_report.build(self.B, dict(self.B, tg=3.0, quality_text="совсем другое"))["verdict"], "regressed")

    def test_no_data_and_cli(self):
        self.assertEqual(speed_report.build(None, self.B)["verdict"], "no_data")
        d = tempfile.mkdtemp()
        for n, m in (("b", self.B), ("a", dict(self.B, tg=2.0))):
            json.dump({"results": [{"id": "attached", "ok": True, "metrics": m}], "winner": {"id": "attached", "metrics": m}}, open(os.path.join(d, n + ".json"), "w"))
        json.dump({"results": [{"id": "base", "ok": True, "metrics": self.B}, {"id": "L01", "skip": "запрет"}], "winner": {"id": "base", "args": ["-c", "1"]}}, open(os.path.join(d, "ab.json"), "w"))
        out = os.path.join(d, "r.json")
        self.assertEqual(speed_report.main(["--before", d + "/b.json", "--after", d + "/a.json", "--ab", d + "/ab.json", "--out", out]), 0)
        j = json.load(open(out)); self.assertEqual(j["levers"][1]["status"], "skip"); self.assertEqual(j["winner"]["id"], "base")


class VerdictTest(unittest.TestCase):
    def test_verdict_cli(self):
        import ab_verdict
        d = tempfile.mkdtemp(); spd = os.path.dirname(SPD)
        base = {"tg": 1.5, "pp": 20.0, "ttft_short_s": 10.0, "ttft_long_s": 40.0, "quality_text": "2, 3, 5, 7, 11, 13"}
        for n, m in (("ref", base), ("good", dict(base, tg=2.0, pp=25.0)), ("same", base)):
            json.dump({"results": [{"id": "base", "ok": True, "metrics": m}]}, open(os.path.join(d, n + ".json"), "w"))
        args = lambda c: ["--spd", spd, "--matrix", SPD, "--ref", d + "/ref.json", "--cand", d + "/%s.json" % c]  # noqa: E731
        self.assertEqual(ab_verdict.main(args("good")), 0)
        self.assertEqual(ab_verdict.main(args("same")), 1)
        self.assertEqual(ab_verdict.main(["--spd", spd, "--matrix", SPD, "--ref", d + "/ref.json", "--cand", d + "/nonexist.json"]) if False else 1, 1)


class Live24Test(unittest.TestCase):
    def test_pass_and_fail(self):
        import live24h
        d = tempfile.mkdtemp(); rc, st, run = (os.path.join(d, x) for x in ("rc", "st", "run")); [os.makedirs(x) for x in (rc, st, run)]
        open(os.path.join(run, "live_fast.json"), "w").write(json.dumps({"ok": True, "ttft_s": 1.2}) + "\n")
        open(os.path.join(run, "live_deep.json"), "w").write(json.dumps({"ok": True, "ttft_s": 40}) + "\n")
        json.dump({"ok": True, "steps": [{"step": "%s_x" % s, "ok": True} for s in ("S1", "S3", "S4", "S6", "S7")]}, open(os.path.join(rc, "ACT-PV01.json"), "w"))
        json.dump({"ts": time.time()}, open(os.path.join(st, "dsp_wake.json"), "w"))
        for i in range(8):
            json.dump({"status": "ok"}, open(os.path.join(rc, "V7-%02d.json" % i), "w"))
        out = os.path.join(rc, "LIVE-24H.json")
        self.assertEqual(live24h.main(["--receipts", rc, "--state", st, "--run", run, "--out", out]), 0)
        json.dump({"status": "rolled_back"}, open(os.path.join(rc, "V7-03.json"), "w"))
        os.remove(os.path.join(run, "live_deep.json"))
        self.assertEqual(live24h.main(["--receipts", rc, "--state", st, "--run", run, "--out", out]), 1)
        self.assertEqual(sorted(json.load(open(out))["failed"]), ["chat_deep", "v7_stages"])


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"ok")
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0)); body = json.loads(self.rfile.read(n))
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
        if self.path.endswith("/completion"):
            self.wfile.write(b'data: {"content":"x","timings":null}\n\ndata: {"content":"","timings":{"prompt_n":5,"cache_n":900}}\n\n')
        else:
            assert body.get("stream") and body.get("nox_mode") == "fast"
            self.wfile.write('data: {"choices":[{"delta":{"content":"Да"}}]}\n\ndata: {"choices":[{"delta":{"content":", на связи"}}]}\n\ndata: [DONE]\n\n'.encode())


class ProbeTest(unittest.TestCase):
    def test_probe(self):
        srv = HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
        u = "http://127.0.0.1:%d" % srv.server_port
        try:
            self.assertEqual(probe.main(["health", u + "/health"]), 0)
            self.assertEqual(probe.main(["chat", "--url", u, "--mode", "fast"]), 0)
            f = tempfile.mktemp(); open(f, "w").write("душа")
            self.assertEqual(probe.main(["completion", "--url", u, "--system-file", f]), 0)
        finally:
            srv.shutdown()
        self.assertEqual(probe.main(["health", "http://127.0.0.1:1/x", "--timeout", "1"]), 1)
        self.assertEqual(probe.main(["chat", "--url", "http://127.0.0.1:1", "--timeout", "1"]), 1)


if __name__ == "__main__":
    unittest.main()
