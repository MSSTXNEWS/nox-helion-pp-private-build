import os, subprocess, sys, tempfile, unittest, json
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import rag_stub


class T(unittest.TestCase):
    def test_bash_syntax(self):
        for s in ("resource_plan.sh", "disk_report.sh"):
            self.assertEqual(subprocess.run(["bash", "-n", os.path.join(HERE, s)]).returncode, 0)

    def test_sampling(self):
        d = json.load(open(os.path.join(HERE, "sampling.json")))
        self.assertEqual(d["modes"]["fast"]["temperature"], 0.55)
        self.assertEqual(d["common"]["top_p"], 0.9)
        self.assertEqual(d["common"]["repeat_penalty"], 1.05)
        self.assertIn("precise", d["modes"])

    def test_prompt_nonempty(self):
        self.assertGreater(len(open(os.path.join(HERE, "system_prompt_ru.txt"), encoding="utf-8").read()), 200)

    def test_rag_bm25_fallback(self):
        with tempfile.TemporaryDirectory() as t:
            os.makedirs(t + "/coordination")
            open(t + "/coordination/a.md", "w").write("# GPU\nобучение на видеокарте V100 память\n")
            open(t + "/coordination/b.md", "w").write("# Диск\nочистка диска и логи\n")
            idx = rag_stub.build_index(t, use_embed=False)
            self.assertEqual(idx["mode"], "bm25")
            r = rag_stub.search(idx, "очистка диска", 1, use_embed=False)
            self.assertEqual(r[0]["src"], "coordination/b.md")

    def test_embed_down_falls_back(self):
        rag_stub.EMBED_URL = "http://127.0.0.1:1/x"
        self.assertIsNone(rag_stub.embed(["x"], url="http://127.0.0.1:1/x", timeout=1))

    def test_resource_plan_dry_run_readonly(self):
        r = subprocess.run(["bash", os.path.join(HERE, "resource_plan.sh")], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0)
        self.assertIn("dry-run only", r.stdout)

    def test_disk_report(self):
        with tempfile.TemporaryDirectory() as t:
            r = subprocess.run(["bash", os.path.join(HERE, "disk_report.sh"), t], capture_output=True, text=True, timeout=60)
            self.assertEqual(r.returncode, 0)
            self.assertIn("read-only", r.stdout)


if __name__ == "__main__":
    unittest.main()
