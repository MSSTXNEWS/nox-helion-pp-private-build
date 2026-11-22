import json, os, subprocess, sys, tempfile, threading, time, unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ["V7_STATE"] = tempfile.mkdtemp()
import gw_env  # noqa: E402
WOW = os.environ.get("NOX_WOW_SRC", os.path.join(HERE, "..", ".."))


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self): self.send_response(200); self.end_headers(); self.wfile.write(b"ok")


class T(unittest.TestCase):
    def test_flags_roundtrip(self):
        gw_env.main(["flags", "set", "NOX_PRIME=1", "NOX_CORE=0"]); gw_env.main(["flags", "unset", "NOX_CORE"])
        self.assertEqual(gw_env.load(gw_env.FLAGS, {}), {"NOX_PRIME": "1"})
        gw_env.save(gw_env.FLAGS, {})

    def test_local_json_merge_and_unapply(self):
        reg = {"services": [{"name": "gateway", "env": {"NOX_SOUL": "1", "NOX_MODEL": "модель с пробелами"}}]}
        loc0 = {"policy": {"tick_s": 20}, "services": {"web": {"prio": 41}}}
        loc = gw_env.merge_local(reg["services"], loc0, {"NOX_PRIME": "1"})
        self.assertEqual(loc["services"]["gateway"]["env"]["NOX_PRIME"], "1"); self.assertEqual(loc["services"]["gateway"]["env"]["NOX_SOUL"], "1")
        self.assertEqual(loc["policy"], {"tick_s": 20}); self.assertEqual([s["name"] for s in loc["add_services"]], ["core"])
        again = gw_env.merge_local(reg["services"], loc, {"NOX_PRIME": "1", "NOX_CORE": "1"})
        self.assertEqual(len(again["add_services"]), 1); self.assertEqual(again["services"]["gateway"]["env"]["NOX_CORE"], "1")
        self.assertEqual(gw_env.merge_local(reg["services"], again, {}, unapply=True), loc0)

    def test_local_env(self):
        loc = gw_env.local_env({"policy": {"a": 1}}, "glm", {"GGML_OP_OFFLOAD_MIN_BATCH": "512"})
        self.assertEqual(loc["services"]["glm"]["env"], {"GGML_OP_OFFLOAD_MIN_BATCH": "512"})
        self.assertEqual(gw_env.local_env(loc, "glm", {}, clear=True), {"policy": {"a": 1}})

    def test_core_service_valid_for_dsp_registry(self):
        dsp = os.path.join(WOW, "DSP")
        if not os.path.exists(os.path.join(dsp, "nox_dispatcher.py")):
            self.skipTest("нет DSP рядом")
        sys.path.insert(0, dsp)
        import nox_dispatcher as nd
        reg_path = os.path.join(dsp, "services.json")
        raw = json.load(open(reg_path, encoding="utf-8"))
        d = tempfile.mkdtemp(); lp = os.path.join(d, "local.json")
        gw_env.save(lp, gw_env.merge_local(raw["services"], {}, {"NOX_PRIME": "1"}))
        reg = nd.Registry.load(path=reg_path, local_path=lp, home=d)
        self.assertIn("core", reg.services); self.assertEqual(reg.services["core"]["port"], 8090)
        order = reg.order(); self.assertLess(order.index("recall"), order.index("core"))
        self.assertEqual(reg.services["gateway"]["env"]["NOX_PRIME"], "1")

    def test_capture_and_restart(self):
        srv = HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
        port = srv.server_port; d = tempfile.mkdtemp()
        code = "import os,sys,http.server\nclass H(http.server.BaseHTTPRequestHandler):\n def log_message(s,*a):pass\n def do_GET(s):\n  s.send_response(200);s.end_headers();s.wfile.write(os.environ.get('NOX_PRIME','-').encode())\nhttp.server.HTTPServer(('127.0.0.1',int(sys.argv[1])),H).serve_forever()\n# gwtest_marker"
        script = os.path.join(d, "fakegw.py"); open(script, "w").write(code)
        srv.shutdown(); srv.server_close()
        env = dict(os.environ, NOX_UPSTREAM="http://x", NOX_MODEL="быстрый ответ — тест")
        p = subprocess.Popen([sys.executable, script, str(port)], env=env, start_new_session=True)
        time.sleep(0.6)
        try:
            cap = gw_env.capture(r"fakegw\.py")
            self.assertEqual(cap["pid"], p.pid); self.assertEqual(cap["env"]["NOX_MODEL"], "быстрый ответ — тест")
            gw_env.save(gw_env.FLAGS, {"NOX_PRIME": "1"})
            res = gw_env.restart(r"fakegw\.py", d, os.path.join(d, "log"), [sys.executable, script, str(port)], {}, "http://127.0.0.1:%d/" % port, 15)
            self.assertTrue(res["healthy"]); self.assertTrue(res["had_old_env"])
            import urllib.request
            self.assertEqual(urllib.request.urlopen("http://127.0.0.1:%d/" % port, timeout=3).read(), b"1")
            p.wait(timeout=5)
            res2 = gw_env.restart(r"fakegw\.py", None, os.path.join(d, "log"), [], {}, "http://127.0.0.1:%d/" % port, 15, {"NOX_X": "d"})
            self.assertTrue(res2["healthy"] and res2["had_old_env"])      # без argv: повтор прежней командной строки
            self.assertEqual(gw_env.restart(r"no_such_proc_xyz", None, os.path.join(d, "log"), [], {}, None, 1)["healthy"], False)
        finally:
            for pid in gw_env.pids(r"fakegw\.py"):
                os.kill(pid, 9)
            gw_env.save(gw_env.FLAGS, {})


if __name__ == "__main__":
    unittest.main()
