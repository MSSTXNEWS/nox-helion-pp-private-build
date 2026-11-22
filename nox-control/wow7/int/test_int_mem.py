"""MEM-02/03 + PER-02 на КОПИИ qs6: mem_patch.diff и per_memory_layer.diff применяются к оригиналу, recall_server отдаёт CorrectionAPI,
отозванный факт не воскресает, NOX_PERSONA управляет личностью, без флага отчёт прежний."""
import http.client, json, os, shutil, subprocess, sys, tempfile, threading, unittest
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.environ.get("NOX_REPO", "/home/claude/msstxnews/nox-helion-pp-private-build/nox-control")
WOW = os.environ.get("NOX_WOW_SRC", "/home/claude/nox_wow")
os.environ["NOX_WOW_SRC"] = WOW


class T(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.pop("NOX_WOW7_MEM", None); os.environ.pop("NOX_WOW7_PER", None)   # тесты используют свои копии модулей
        cls.root = tempfile.mkdtemp(); q = os.path.join(cls.root, "qs6")
        for pkg in ("qs6", "community"):
            shutil.copytree(os.path.join(REPO, pkg), os.path.join(cls.root, pkg), ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        for d in ("mem_patch.diff", "per_memory_layer.diff"):
            r = subprocess.run(["patch", "-p3", "-d", q, "-i", os.path.join(HERE, d)], capture_output=True, text=True)
            assert r.returncode == 0, r.stdout + r.stderr
        cls.mem_dir = os.path.join(cls.root, "wow7", "mem"); cls.per_dir = os.path.join(cls.root, "wow7", "per")
        os.makedirs(cls.mem_dir); os.makedirs(cls.per_dir)
        for f in ("memcommon", "correction", "provenance", "consolidate", "autobio"): shutil.copy(os.path.join(WOW, "MEM", f + ".py"), cls.mem_dir)
        for f in ("perpath", "per_wire"): shutil.copy(os.path.join(HERE, "per", f + ".py"), cls.per_dir)
        sys.path.insert(0, cls.root)
        import qs6.memory_layer as ML, qs6.recall_server as RS, qs6.s03_store as S
        cls.ML, cls.RS, cls.S = ML, RS, S

    def db(self):
        d = tempfile.mkdtemp(); p = os.path.join(d, "s03.db"); s = self.S.Store(p); s.add_fact("Мессир работает по ночам", kind="owner", pinned=True); s.close(); return p

    def layer(self, db, **env):
        e = dict({"NOX_SOUL": "1", "NOX_MEMORY_DB": db, "NOX_STATE": tempfile.mkdtemp()}, **env)
        return self.ML.MemoryLayer(env=e, log=lambda m: None)

    def api(self, db):
        os.environ.update(NOX_MEMORY_DB=db, NOX_RECALL_PORT="0"); srv = self.RS.build()
        threading.Thread(target=srv.serve_forever, daemon=True).start(); self.addCleanup(srv.shutdown); port = srv.server_address[1]
        def call(req):
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=10); c.request("POST", "/api", json.dumps(req), {"Content-Type": "application/json"})
            r = json.loads(c.getresponse().read()); c.close(); return r
        return call

    def test_recall_server_serves_correction_api(self):
        db = self.db(); call = self.api(db)
        rev = call({"op": "revision"}); self.assertTrue(rev["ok"]); self.assertEqual(len(rev["revision"]), 64)
        st = self.S.Store(db); fid = "f:%d" % st.add_fact("Порт шлюза NOX равен 8082", kind="fact"); st.close()
        self.assertEqual(call({"op": "get", "id": fid})["item"]["status"], "active")
        self.assertFalse(call({"op": "correct", "id": fid, "text": ""})["ok"])
        r = call({"op": "delete", "id": fid}); self.assertTrue(r["ok"]); self.assertTrue(r["verified"]); self.assertTrue(all(r["checks"].values()), r["checks"])
        self.assertTrue(call({"op": "stats"}) is not None)      # прежние op делегируются Recall

    def test_revoked_fact_not_resurrected_by_after_reply(self):
        db = self.db(); m = self.layer(db)
        rep = m.after_reply("Меня зовут Игорь", "Рад знакомству", "t1", [], "s")
        self.assertEqual([f["text"] for f in rep["facts"]], ["Владельца зовут Игорь"]); self.assertNotIn("blocked", rep)
        call = self.api(db); r = call({"op": "revoke", "id": rep["facts"][0]["ref"]}); self.assertTrue(r["verified"])
        rep2 = m.after_reply("Меня зовут Игорь", "ок", "t2", [], "s")
        self.assertEqual(rep2["facts"], []); self.assertEqual(rep2["blocked"], ["Владельца зовут Игорь"])
        st = self.S.Store(db)
        try:
            self.assertNotIn("Владельца зовут Игорь", [f["text"] for f in st.active_facts()])
            self.assertTrue(st.db.execute("SELECT 1 FROM mem_changes WHERE action='blocked_revoked'").fetchone() or
                            st.db.execute("SELECT 1 FROM mem_changes WHERE op='blocked_revoked'").fetchone())
        finally: st.close()
        m2 = self.layer(db); r3 = m2.after_reply("Я живу в Риге", "ок", "t3", [], "s"); self.assertEqual(r3["facts"][0]["text"], "Владелец живёт в Риге")

    def test_without_mem_modules_old_behaviour(self):
        db = self.db(); os.environ["NOX_WOW7_MEM"] = "/нет/такого"
        saved = [p for p in sys.path if p == self.mem_dir]; sys.path[:] = [p for p in sys.path if p != self.mem_dir]; sys.modules.pop("correction", None); sys.modules.pop("memcommon", None)
        try:
            logs = []; m = self.ML.MemoryLayer(env={"NOX_SOUL": "1", "NOX_MEMORY_DB": db}, log=logs.append)
            self.assertIsNone(m._guard); self.assertTrue(any("MEM-03" in l for l in logs))
            self.assertEqual(m.after_reply("Я живу в Риге", "ок", "t", [], "s")["facts"][0]["text"], "Владелец живёт в Риге")
        finally:
            os.environ.pop("NOX_WOW7_MEM", None); sys.path.extend(saved)

    def test_persona_flag(self):
        db = self.db(); off = self.layer(db); self.assertIsNone(off.per)
        self.assertNotIn("persona", off.after_reply("привет", "ок", "t", [], "s"))                   # флаг выключен -> отчёт прежний
        st = tempfile.mkdtemp(); on = self.layer(db, NOX_PERSONA="1", NOX_EMOTION="1", NOX_STATE=st); self.assertIsNotNone(on.per)
        for i in range(3): rep = on.after_reply("Слишком длинно, будь короче", "...", "t%d" % i, [], "s")
        self.assertIn(("directness", 0.5), rep["persona"]["corrections"])
        self.assertEqual(json.load(open(os.path.join(st, "development.json")))["counts"]["turn"], 3)
        self.assertEqual(len(on.per.pers.pending["directness"]), 3)

    def test_persona_broken_module_is_logged_not_fatal(self):
        logs = []; os.environ["NOX_WOW7_PER"] = "/нет/такого"
        saved = [p for p in sys.path if p == self.per_dir]; sys.path[:] = [p for p in sys.path if p != self.per_dir]; sys.modules.pop("per_wire", None)
        try:
            m = self.ML.MemoryLayer(env={"NOX_PERSONA": "1", "NOX_MEMORY_DB": self.db()}, log=logs.append)
            self.assertIsNone(m.per); self.assertTrue(any("per_wire не загружен" in l for l in logs)); m.after_reply("привет", "ок", "t", [], "s")
        finally:
            os.environ.pop("NOX_WOW7_PER", None); sys.path.extend(saved)


if __name__ == "__main__": unittest.main()
