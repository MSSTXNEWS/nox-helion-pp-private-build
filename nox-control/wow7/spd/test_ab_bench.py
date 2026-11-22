"""Тесты ab_bench на локальном фейковом llama-server (HTTP, без LLM). Запуск: python3 -m unittest test_ab_bench -v"""
import json
import os
import socket
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ab_bench as ab  # noqa: E402

FAKE = r'''#!%(py)s
import json, sys, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
A = sys.argv[1:]
if "--help" in A:
    print("--spec-type draft-mtp|ngram-map-k\n--cache-reuse N\n--numa TYPE\n--moe-cache-mib N")
    sys.exit(0)
def val(k, d=None):
    return A[A.index(k) + 1] if k in A else d
port = int(val("--port"))
ngl = int(val("-ngl", "0")); ub = int(val("-ub", "256")); thr = int(val("-t", "24"))
if ngl >= 30:
    sys.stderr.write("CUDA out of memory\n"); sys.exit(1)
tg = 5.0 + (0.1 if thr != 24 else 0)
if val("--spec-type") == "draft-mtp":
    tg *= 1.8
pp = 20.0 * (ub / 256.0) ** 0.5
if "--moe-cache-mib" in A:
    tg *= 0.5
bad_text = val("--spec-type") == "ngram-map-k"
cache_reuse = "--cache-reuse" in A
last = [""]
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b'{"status":"ok"}')
    def do_POST(self):
        b = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        p = b["prompt"]; n = b.get("n_predict", 8)
        cache_n = 0
        if b.get("cache_prompt"):
            q = last[0]
            while cache_n < min(len(p), len(q)) and p[cache_n] == q[cache_n]:
                cache_n += 1
            if cache_reuse and cache_n < len(p) and cache_n > 0 and p.endswith(q[-30:]) is False:
                cache_n = max(cache_n, len(p) - 20)
            last[0] = p
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
        text = "2, 3, 5, 7, 11, 13" if not bad_text else "ъъъ хзх qqq 999 !!!"
        self.wfile.write(("data: " + json.dumps({"content": text[:6], "stop": False}) + "\n\n").encode())
        self.wfile.write(("data: " + json.dumps({"content": text[6:], "stop": True, "timings": {
            "prompt_n": max(len(p) - cache_n, 1), "cache_n": cache_n, "prompt_per_second": pp,
            "predicted_n": n, "predicted_per_second": tg}}) + "\n\n").encode())
ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
'''


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


class T(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.bin = os.path.join(cls.tmp, "fake-llama-server")
        with open(cls.bin, "w") as f:
            f.write(FAKE % {"py": sys.executable})
        os.chmod(cls.bin, os.stat(cls.bin).st_mode | stat.S_IEXEC)
        cls.matrix = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "matrix.json")))
        cls.matrix["bench"].update({"repeats": 1, "health_timeout_s": 20, "long_repeat": 3})

    def test_apply_lever_replaces_and_drops(self):
        lv = {"set": {"-ub": "1024", "--new": ""}, "drop": ["--no-op-offload"]}
        out = ab.apply_lever(["-ub", "256", "--no-op-offload", "-c", "16384"], lv)
        self.assertEqual(ab.get_flag(out, "-ub"), "1024")
        self.assertNotIn("--no-op-offload", out)
        self.assertIn("--new", out)
        self.assertEqual(ab.get_flag(out, "-c"), "16384")

    def test_bans(self):
        bans = self.matrix["bans"]
        self.assertTrue(ab.check_bans(["--no-mmap"], bans))
        self.assertTrue(ab.check_bans(["--mlock"], bans))
        self.assertTrue(ab.check_bans(["-ctk", "q8_0"], bans))
        self.assertFalse(ab.check_bans(["-ctk", "f16", "-c", "16384"], bans))
        self.assertTrue(ab.check_bans(["-c", "8192"], bans))
        self.assertFalse(ab.check_bans(["-ctk", "q8_0"], bans, allow_kv_quant=True))
        self.assertFalse(ab.check_bans(self.matrix["base"], bans))

    def test_plan_blocks_forbidden_and_missing_support(self):
        steps = {s["id"]: s for s in ab.plan(self.matrix, help_txt="--spec-type draft-mtp --cache-reuse")}
        self.assertIn("ЗАПРЕТ", steps["X01_kv_q8_QUALITY_ONLY"]["skip"])
        self.assertIn("не поддерживает", steps["L09_cache_ram"]["skip"])
        self.assertIsNone(steps["L05_mtp_n2"]["skip"])
        self.assertIsNone(steps["L02_ub1024_opoffload"]["skip"])
        self.assertEqual(steps["L02_ub1024_opoffload"]["env"]["GGML_OP_OFFLOAD_MIN_BATCH"], "512")
        # исходная база не мутирует
        self.assertIn("--no-op-offload", self.matrix["base"])

    def test_full_run_picks_winner(self):
        out = os.path.join(self.tmp, "out")
        m = json.loads(json.dumps(self.matrix))
        m["base"] = ["-c", "16384", "-ngl", "24", "-t", "24", "-ub", "256", "--jinja"]
        m["levers"] = [lv for lv in m["levers"] if lv["id"] in (
            "L02_ub1024_opoffload", "L04_moe_cache_4g", "L05_mtp_n2", "L07_ngram", "L09_cache_ram",
            "L11_ngl_up", "X01_kv_q8_QUALITY_ONLY")]
        mp = os.path.join(self.tmp, "m.json")
        json.dump(m, open(mp, "w"))
        rc = ab.main(["--matrix", mp, "--bin", self.bin, "--model", "x.gguf", "--port", str(free_port()),
                      "--out", out, "--accumulate"])
        self.assertEqual(rc, 0)
        res = {r["id"]: r for r in json.load(open(os.path.join(out, "results.json")))["results"]}
        win = json.load(open(os.path.join(out, "winner.json")))
        self.assertTrue(res["base"]["ok"])
        self.assertTrue(res["L02_ub1024_opoffload"]["verdict"]["accepted"])   # pp x2
        self.assertTrue(res["L05_mtp_n2"]["verdict"]["accepted"])             # tg x1.8
        self.assertFalse(res["L04_moe_cache_4g"]["verdict"]["accepted"])      # tg просел
        self.assertFalse(res["L07_ngram"]["verdict"]["accepted"])             # качество
        self.assertIn("качество", " ".join(res["L07_ngram"]["verdict"]["reasons"]))
        self.assertIn("CUDA out of memory", open(os.path.join(out, "server_L11_ngl_up.log")).read())
        self.assertFalse(res["L11_ngl_up"]["ok"])                              # OOM = результат
        self.assertIn("ЗАПРЕТ", res["X01_kv_q8_QUALITY_ONLY"]["skip"])
        self.assertIn("не поддерживает", res["L09_cache_ram"]["skip"])
        # накопление: у победителя и ub1024, и MTP
        self.assertEqual(win["id"], "L05_mtp_n2")
        self.assertEqual(ab.get_flag(win["args"], "-ub"), "1024")
        self.assertEqual(ab.get_flag(win["args"], "--spec-type"), "draft-mtp")
        self.assertEqual(win["env"]["GGML_OP_OFFLOAD_MIN_BATCH"], "512")
        self.assertGreater(win["metrics"]["tg"], win["base_metrics"]["tg"] * 1.5)
        # кэш-тест: повтор почти целиком из кэша
        c = res["base"]["metrics"]["cache"]
        self.assertGreater(c["repeat_cache_n"], 100)
        self.assertLessEqual(c["repeat_prompt_n"], 2)
        csv_text = open(os.path.join(out, "results.csv"), encoding="utf-8").read()
        self.assertIn("L05_mtp_n2", csv_text)
        self.assertIn("skip", csv_text)

    def test_single_lever_mode_not_accumulated(self):
        out = os.path.join(self.tmp, "out2")
        m = json.loads(json.dumps(self.matrix))
        m["base"] = ["-c", "16384", "-ngl", "24", "-t", "24", "-ub", "256"]
        m["levers"] = [lv for lv in m["levers"] if lv["id"] in ("L02_ub1024_opoffload", "L05_mtp_n2")]
        mp = os.path.join(self.tmp, "m2.json")
        json.dump(m, open(mp, "w"))
        self.assertEqual(ab.main(["--matrix", mp, "--bin", self.bin, "--model", "x.gguf",
                                  "--port", str(free_port()), "--out", out]), 0)
        res = {r["id"]: r for r in json.load(open(os.path.join(out, "results.json")))["results"]}
        self.assertEqual(ab.get_flag(res["L05_mtp_n2"]["args"], "-ub"), "256")  # один рычаг за раз

    def test_refuses_busy_port(self):
        import subprocess
        port = free_port()
        p = subprocess.Popen([self.bin, "-m", "x", "--port", str(port), "-ngl", "1"])
        try:
            for _ in range(50):
                if ab.healthy("http://127.0.0.1:%d" % port):
                    break
                import time; time.sleep(0.1)
            rc = ab.main(["--bin", self.bin, "--port", str(port), "--out", os.path.join(self.tmp, "o3")])
            self.assertEqual(rc, 3)
        finally:
            p.terminate(); p.wait()

    def test_attach_and_dry_run(self):
        import subprocess, io, contextlib
        port = free_port()
        p = subprocess.Popen([self.bin, "-m", "x", "--port", str(port), "-ngl", "1"])
        try:
            for _ in range(50):
                if ab.healthy("http://127.0.0.1:%d" % port):
                    break
                import time; time.sleep(0.1)
            mp = os.path.join(self.tmp, "m3.json")
            m = json.loads(json.dumps(self.matrix)); m["bench"]["long_repeat"] = 2
            json.dump(m, open(mp, "w"))
            self.assertEqual(ab.main(["--matrix", mp, "--attach", "http://127.0.0.1:%d" % port,
                                      "--out", os.path.join(self.tmp, "o4")]), 0)
            w = json.load(open(os.path.join(self.tmp, "o4", "winner.json")))
            self.assertAlmostEqual(w["metrics"]["tg"], 5.0, places=1)
        finally:
            p.terminate(); p.wait()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(ab.main(["--dry-run"]), 0)
        self.assertIn("L05_mtp_n2", buf.getvalue())
        self.assertIn("ЗАПРЕТ", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
