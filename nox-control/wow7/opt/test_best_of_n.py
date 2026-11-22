import json, threading, unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
import best_of_n_fast_judge as b


def serve(handler):
    srv = HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_port}"


def fast_handler(texts):
    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            i = body["seed"] - 1000
            t = texts[i]
            toks = [{"token": w, "logprob": -0.1 * (i + 1), "top_logprobs": [{"token": w, "logprob": -0.1 * (i + 1)}]}
                    for w in t.split()[:5]]
            out = json.dumps({"content": t, "completion_probabilities": toks}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(out)
        def log_message(self, *a): pass
    return H


def judge_handler(rule, busy=False):
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            out = json.dumps([{"is_processing": busy}]).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(out)
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            assert body["n_predict"] == 1
            p = body["prompt"]
            a = p.split("ОТВЕТ A:\n")[1].split("\n\nОТВЕТ B:")[0]; bb = p.split("ОТВЕТ B:\n")[1].split("\n\nЛучший")[0]
            pick = rule(a, bb)  # "A"/"B"
            lp = {"A": (-0.05, -3.0), "B": (-3.0, -0.05)}[pick]
            toks = [{"token": pick, "logprob": max(lp), "top_logprobs": [{"token": " A", "logprob": lp[0]}, {"token": "B", "logprob": lp[1]}]}]
            out = json.dumps({"content": pick, "completion_probabilities": toks}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(out)
        def log_message(self, *a): pass
    return H


GOOD = "RAID объединяет несколько дисков в один массив для надёжности и скорости чтения данных"
GOOD2 = "RAID объединяет несколько дисков в массив ради надёжности и скорости чтения данных"
ODD = "Погода хорошая и мы пойдём гулять по набережной вечером вместе с друзьями"


class T(unittest.TestCase):
    def test_prefilter(self):
        self.assertEqual(b.prefilter("")[1], "empty")
        self.assertEqual(b.prefilter("The quick brown fox jumps over the lazy dog")[1], "not_russian")
        self.assertEqual(b.prefilter("раз два три четыре пять шесть " * 4)[1], "loop")
        self.assertEqual(b.prefilter("Как языковая модель, я не могу.")[1], "llm_ism")
        self.assertEqual(b.prefilter("Это не баг, а фича. Это не шум, а сигнал. Это не риск, а цена.")[1], "not_x_but_y")
        self.assertEqual(b.prefilter("Ответ готов", validator=lambda t: (False, "json"))[1], "validator:json")
        self.assertEqual(b.prefilter(GOOD), (True, "ok"))

    def test_parse_both_logprob_formats(self):
        new = {"completion_probabilities": [{"token": "A", "logprob": -0.2, "top_logprobs": [{"token": "A", "logprob": -0.2}, {"token": "B", "logprob": -2}]}]}
        old = {"completion_probabilities": [{"content": "A", "probs": [{"tok_str": "A", "prob": 0.8}, {"tok_str": "B", "prob": 0.1}]}]}
        self.assertAlmostEqual(b.parse_tokens(new)[0][2]["B"], -2)
        self.assertAlmostEqual(b.parse_tokens(old)[0][2]["A"], __import__("math").log(0.8))
        self.assertAlmostEqual(b.mean_logprob(new), -0.2)

    def test_support_pessimism_prefers_majority(self):
        cands = [{"text": GOOD, "conf": -0.3}, {"text": GOOD2, "conf": -0.3}, {"text": ODD, "conf": -0.1}]
        s, sup = b.heuristic_scores(cands)
        self.assertLess(s[2], max(s[0], s[1]))

    def test_end_to_end_judge_picks_better_with_swap(self):
        fs, fu = serve(fast_handler([GOOD, GOOD2, ODD, GOOD + " дополнительно про уровни RAID 0 1 5 6 и 10"]))
        js, ju = serve(judge_handler(lambda a, bb: "A" if "уровни RAID" in a else "B"))
        try:
            r = b.best_of_n("Что такое RAID?", "Что такое RAID?", fu, ju, n=4)
            self.assertIn("уровни RAID", r["answer"]); self.assertEqual(r["method"], "judge")
        finally:
            fs.shutdown(); js.shutdown()

    def test_position_biased_judge_is_tie_falls_back_to_heuristic(self):
        fs, fu = serve(fast_handler([GOOD, GOOD2, GOOD + " ещё", GOOD2 + " ещё"]))
        js, ju = serve(judge_handler(lambda a, bb: "A"))  # всегда A = позиционное смещение
        try:
            r = b.best_of_n("Что такое RAID?", "Что такое RAID?", fu, ju, n=4)
            self.assertEqual(r["method"], "heuristic(judge_tie)"); self.assertTrue(r["answer"])
        finally:
            fs.shutdown(); js.shutdown()

    def test_judge_busy_and_down_fallback(self):
        fs, fu = serve(fast_handler([GOOD, GOOD2, ODD, GOOD]))
        js, ju = serve(judge_handler(lambda a, bb: "A", busy=True))
        try:
            self.assertEqual(b.best_of_n("q", "q", fu, ju, n=4)["method"], "heuristic(judge_busy)")
        finally:
            js.shutdown()
        try:
            r = b.best_of_n("q", "q", fu, "http://127.0.0.1:9", n=4)
            self.assertIn(r["method"], ("heuristic(judge_down)", "heuristic"))
            self.assertTrue(r["answer"])
        finally:
            fs.shutdown()

    def test_all_filtered_returns_best_effort(self):
        fs, fu = serve(fast_handler(["English only text here", "More english words again", "third english one", "fourth english"]))
        try:
            r = b.best_of_n("q", "q", fu, None, n=4)
            self.assertEqual(r["note"], "all_filtered"); self.assertTrue(r["answer"])
        finally:
            fs.shutdown()


if __name__ == "__main__":
    unittest.main()
