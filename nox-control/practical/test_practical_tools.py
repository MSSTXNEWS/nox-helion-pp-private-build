import json
import os
import struct
import subprocess
import tempfile
import unittest
import zlib

import practical_tools as pt

HERE = os.path.dirname(os.path.abspath(__file__))


class T(unittest.TestCase):
    def test_manifest_matches_tools(self):
        m = json.load(open(os.path.join(HERE, "practical_tools.json"), encoding="utf-8"))
        self.assertEqual(sorted(t["name"] for t in m["tools"]), sorted(pt.TOOLS))

    def test_contrast_known_values(self):
        self.assertAlmostEqual(pt.contrast_ratio("#000", "#fff"), 21.0, 2)
        self.assertAlmostEqual(pt.contrast_ratio("#777777", "#ffffff"), 4.48, 2)
        self.assertFalse(pt.wcag(pt.contrast_ratio("#777777", "#fff"))["AA_text"])
        self.assertTrue(pt.wcag(pt.contrast_ratio("#767676", "#fff"))["AA_text"])

    def test_palette(self):
        r = pt.palette_gen({"base": "#1a73e8", "scheme": "triad"})
        self.assertTrue(r["ok"]); self.assertEqual(len(r["palette"]), 5)
        for v in r["palette"].values():
            self.assertAlmostEqual(v["ratio"], pt.contrast_ratio(v["on"], v["hex"]), 1)
        self.assertFalse(pt.palette_gen({"base": "zzz"})["ok"])
        self.assertFalse(pt.palette_gen({})["ok"])
        self.assertIn("blocked", pt.palette_gen({"base": "#fff", "scheme": "x"}))

    def test_css_tokens(self):
        r = pt.css_tokens({"palette": {"primary": "#1a73e8"}})
        self.assertIn("--color-primary: #1a73e8;", r["css"]); self.assertIn("--space-1: 4px;", r["css"])
        self.assertIn("--font-size-1: 1.0rem;", r["css"])
        self.assertFalse(pt.css_tokens({"palette": {"a": "red"}})["ok"])

    def test_a11y(self):
        bad = ('<html><body><img src=a.png><h1>x</h1><h3>y</h3><a href="#"></a>'
               '<button style="width:30px;height:30px">ok</button><input type="text">'
               '<p style="color:#777777;background-color:#ffffff">t</p></body></html>')
        codes = {i["code"] for i in pt.a11y_check({"html": bad})["issues"]}
        self.assertEqual(codes, {"html-lang", "img-alt", "heading-order", "empty-control",
                                 "target-size", "form-label", "contrast"})
        good = ('<!doctype html><html lang="ru"><body><img src=a alt="">'
                '<label for=n>N</label><input id=n><button style="height:48px">Go</button>'
                '<p style="color:#111111;background-color:#fff">t</p></body></html>')
        self.assertEqual(pt.a11y_check({"html": good})["violations"], 0)

    def test_lint(self):
        r = pt.html_lint({"html": "<div><span></div><img id=a><p id=a><center>x</center>"})
        codes = {i["code"] for i in r["issues"]}
        self.assertTrue({"no-doctype", "no-title", "unclosed-tag", "duplicate-id", "deprecated-tag"} <= codes)
        ok = pt.html_lint({"html": '<!doctype html><html lang=ru><head><meta charset=utf-8>'
                           '<meta name=viewport content="width=device-width"><title>t</title></head><body><p>x</p></body></html>'})
        self.assertEqual(ok["errors"], 0); self.assertEqual(ok["warnings"], 0)

    def test_img_plan(self):
        d = tempfile.mkdtemp()
        raw = b"\x00" + b"\x00\x00\x00" * 2000
        png = (b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">IIBBBBB", 2000, 1, 8, 2, 0, 0, 0)
               + b"\x00" * 4 + zlib.compress(raw))
        open(os.path.join(d, "a.png"), "wb").write(png)
        r = pt.img_optimize_plan({"dir": d, "max_width": 1200})
        self.assertEqual(r["plan"][0]["dimensions"], (2000, 1))
        self.assertTrue(any("downscale" in x for x in r["plan"][0]["actions"]))
        self.assertFalse(pt.img_optimize_plan({"dir": "/nonexistent"})["ok"])

    def test_screenshot_plan(self):
        r = pt.screenshot_diff_plan({"pages": ["Главная", "О нас"]})
        self.assertEqual(r["count"], 6); self.assertFalse(pt.screenshot_diff_plan({})["ok"])

    def test_copy_ru(self):
        r = pt.copy_ru({"text": 'Он сказал "привет"  и  ушёл - далеко. Цена 5 ₽ , в 2020-2021 году!!'})
        self.assertIn("«привет»", r["text"]); self.assertIn("—", r["text"]); self.assertIn("2020–2021", r["text"])
        self.assertIn("в 2020", r["text"]); self.assertNotIn("  ", r["text"]); self.assertNotIn(" ,", r["text"])
        self.assertTrue(any("!" in i for i in r["issues"]))

    def test_task_to_pr(self):
        r = pt.task_to_pr({"text": "- Сделать кнопку входа\n- Задеплоить на прод\n- Удалить старый файл"})
        self.assertEqual(len(r["steps"]), 3); self.assertTrue(r["needs_owner"]); self.assertEqual(len(r["risks"]), 2)
        self.assertTrue(r["branch"].startswith("task/")); self.assertIn("[ ] тесты зелёные", r["acceptance"])
        self.assertFalse(pt.task_to_pr({"text": ""})["ok"])

    def test_changelog(self):
        d = tempfile.mkdtemp()
        g = lambda *a: subprocess.run(["git", "-C", d, "-c", "user.name=t", "-c", "user.email=t@t", *a],
                                      check=True, capture_output=True)
        g("init", "-q")
        for m in ("c1: first", "fix(ui): button", "plain msg"):
            g("commit", "-q", "--allow-empty", "-m", m)
        r = pt.changelog_gen({"repo": d})
        self.assertEqual(r["commits"], 3); self.assertEqual(set(r["groups"]), {"c1", "fix", "other"})
        self.assertIn("## fix", r["markdown"])
        self.assertFalse(pt.changelog_gen({"repo": tempfile.mkdtemp()})["ok"])

    def test_deploy_checklist(self):
        self.assertTrue(pt.deploy_checklist({"kind": "nox"})["checklist"][0].startswith("[ ]"))
        self.assertFalse(pt.deploy_checklist({"kind": "x"})["ok"])

    def test_server_status(self):
        r = pt.server_status_summary({"ports": {"closed": 1}})
        self.assertTrue(r["ok"]); self.assertFalse(r["ports"]["closed"]); self.assertIn("порт closed", r["summary"])
        self.assertFalse(pt.server_status_summary({"proc": "/nonexistent"})["ok"])

    def test_advisor_review(self):
        r = pt.advisor_review({"task": "t", "acceptance": "a", "answer": "x", "config": "/nonexistent.json"})
        self.assertFalse(r["ok"]); self.assertTrue(r["need"])
        import sys
        sys.path.insert(0, os.path.join(HERE, "..", "advisors"))
        from test_nox_advisors import make_server, chat, url
        s = make_server(chat('{"verdict":"pass","reasons":[]}')); s2 = make_server(chat('{"verdict":"pass","reasons":[]}'))
        cfg = os.path.join(tempfile.mkdtemp(), "c.json")
        json.dump([{"name": "a", "url": url(s), "role": "judge"}, {"name": "b", "url": url(s2), "role": "checker"}], open(cfg, "w"))
        r = pt.advisor_review({"task": "t", "acceptance": "a", "answer": "x", "config": cfg})
        s.shutdown(); s2.shutdown()
        self.assertEqual(r["verdict"], "pass"); self.assertIn("не NOX", r["label"])

    def test_cli_and_unknown(self):
        self.assertFalse(pt.run("nope", {})["ok"])
        p = subprocess.run(["python3", os.path.join(HERE, "practical_tools.py"), "deploy_checklist",
                            "--json", '{"kind":"web"}'], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0); self.assertTrue(json.loads(p.stdout)["ok"])


if __name__ == "__main__":
    unittest.main()
