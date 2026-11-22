"""Тесты bash-скриптов SPD (soul_kv_warm.sh, start_glm_best.sh, recon_s1.sh) на локальном фейковом сервере.
Запуск: python3 -m unittest test_scripts -v"""
import json
import os
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def make_server(slot_dir):
    state = {"saved": set(), "restored": False, "calls": []}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass

        def _send(self, obj):
            b = json.dumps(obj).encode()
            self.send_response(200); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

        def do_GET(self):
            self._send({"status": "ok"})

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])) or b"{}")
            state["calls"].append(self.path)
            if self.path.startswith("/slots/0?action=save"):
                open(os.path.join(slot_dir, body["filename"]), "wb").write(b"KV" * 10)
                state["saved"].add(body["filename"]); self._send({"n_saved": 500, "n_written": 20})
            elif self.path.startswith("/slots/0?action=restore"):
                state["restored"] = True; self._send({"n_restored": 500})
            else:  # chat probe
                cached = 500 if state["restored"] else 0
                self._send({"timings": {"cache_n": cached, "prompt_n": 8 if cached else 508}})
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, state


class T(unittest.TestCase):
    def test_bash_syntax(self):
        for s in ("recon_s1.sh", "soul_kv_warm.sh", "start_glm_best.sh"):
            self.assertEqual(subprocess.run(["bash", "-n", os.path.join(HERE, s)]).returncode, 0, s)

    def test_soul_kv_warm_warm_then_restore(self):
        tmp = tempfile.mkdtemp(); d = os.path.join(tmp, "kv"); os.makedirs(d)
        soul = os.path.join(tmp, "soul.txt"); open(soul, "w").write("Ты NOX. Душа.")
        srv, st = make_server(d); port = srv.server_address[1]
        env = dict(os.environ, RECEIPTS=os.path.join(tmp, "rc"))
        cmd = ["bash", os.path.join(HERE, "soul_kv_warm.sh"), "--port", str(port), "--soul", soul, "--dir", d, "--keep", "1"]
        r1 = subprocess.run(cmd + ["auto"], env=env, capture_output=True, text=True)
        self.assertEqual(r1.returncode, 0, r1.stderr + r1.stdout)
        rec = json.load(open(os.path.join(tmp, "rc", "SPD-04.json")))
        self.assertEqual(rec["used"], "warm+save"); self.assertEqual(rec["warm_prompt_n"], 508)
        files = [f for f in os.listdir(d) if f.startswith("soul_")]
        self.assertEqual(len(files), 1)
        r2 = subprocess.run(cmd + ["auto"], env=env, capture_output=True, text=True)
        self.assertEqual(r2.returncode, 0, r2.stderr)
        rec = json.load(open(os.path.join(tmp, "rc", "SPD-04.json")))
        self.assertEqual(rec["used"], "restore"); self.assertEqual(rec["restore_probe_cache_n"], 500)
        self.assertEqual(rec["restore_probe_prompt_n"], 8)
        # другая душа -> другой файл, старый вытесняется (keep=1)
        open(soul, "w").write("Ты NOX. Душа v3.")
        st["restored"] = False
        r3 = subprocess.run(cmd + ["auto"], env=env, capture_output=True, text=True)
        self.assertEqual(r3.returncode, 0, r3.stderr)
        self.assertEqual(len([f for f in os.listdir(d) if f.startswith("soul_")]), 1)
        self.assertNotIn(files[0], os.listdir(d))
        srv.shutdown()

    def test_soul_kv_warm_dead_server_and_dry(self):
        tmp = tempfile.mkdtemp(); soul = os.path.join(tmp, "s.txt"); open(soul, "w").write("x")
        env = dict(os.environ, RECEIPTS=os.path.join(tmp, "rc"))
        r = subprocess.run(["bash", os.path.join(HERE, "soul_kv_warm.sh"), "--port", str(free_port()), "--soul", soul, "--dir", tmp], env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 4)
        r = subprocess.run(["bash", os.path.join(HERE, "soul_kv_warm.sh"), "--dry-run", "--soul", soul], env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0); self.assertIn("soul_", r.stdout)

    def test_start_glm_best_bans_and_real_launch(self):
        tmp = tempfile.mkdtemp()
        fake = os.path.join(tmp, "llama-server")
        open(fake, "w").write('''#!%s
import sys, json
from http.server import BaseHTTPRequestHandler, HTTPServer
A = sys.argv[1:]
if "--help" in A:
    print("--slot-save-path PATH\\n--cache-reuse N"); sys.exit(0)
port = int(A[A.index("--port") + 1])
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b'{"status":"ok"}')
HTTPServer(("127.0.0.1", port), H).serve_forever()
''' % sys.executable)
        os.chmod(fake, os.stat(fake).st_mode | stat.S_IEXEC)
        port = free_port()
        bad = os.path.join(tmp, "bad.json"); json.dump({"args": ["-c", "16384", "--mlock"], "env": {}}, open(bad, "w"))
        env = dict(os.environ, LLAMA_BIN=fake, WIN=bad, SLOTDIR=os.path.join(tmp, "kv"), RECEIPTS=os.path.join(tmp, "rc"), LOGDIR=os.path.join(tmp, "lg"))
        r = subprocess.run(["bash", os.path.join(HERE, "start_glm_best.sh"), "--port", str(port), "--no-warm"], env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 6); self.assertIn("--mlock", r.stderr)
        self.assertFalse(os.path.exists(os.path.join(tmp, "rc", "SPD-03.json")))
        good = os.path.join(tmp, "good.json"); json.dump({"args": ["-c", "16384", "-ub", "1024"], "env": {"GGML_OP_OFFLOAD_MIN_BATCH": "512"}}, open(good, "w"))
        env["WIN"] = good
        try:
            r = subprocess.run(["bash", os.path.join(HERE, "start_glm_best.sh"), "--port", str(port), "--no-warm"], env=env, capture_output=True, text=True, timeout=120)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            rec = json.load(open(os.path.join(tmp, "rc", "SPD-03.json")))
            self.assertTrue(rec["healthy"]); self.assertTrue(rec["bans_checked"])
            self.assertIn("--slot-save-path", rec["args"]); self.assertIn("--cache-reuse 256", rec["args"])
            self.assertIn("GGML_OP_OFFLOAD_MIN_BATCH=512", rec["env"])
        finally:
            subprocess.run(["pkill", "-f", "--", "--port %d" % port])

    def test_recon_writes_receipt(self):
        tmp = tempfile.mkdtemp()
        r = subprocess.run(["bash", os.path.join(HERE, "recon_s1.sh"), "--bin", "/nonexistent"], env=dict(os.environ, RECEIPTS=tmp), capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        rec = json.load(open(os.path.join(tmp, "SPD-01.json")))
        self.assertEqual(rec["id"], "SPD-01"); self.assertIn("draft_mtp", rec["llama"]); self.assertGreater(rec["ram"]["copy_bw_gbs_1thread"], 0)


if __name__ == "__main__":
    unittest.main()
