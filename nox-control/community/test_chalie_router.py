import os, sys, time, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from community.chalie_router import route, route_text


def U(t): return {"role": "user", "content": t}
def A(t): return {"role": "assistant", "content": t}


class T(unittest.TestCase):
    def a(self, text, exp, hist=None):
        d = route_text(text, hist)
        self.assertEqual(d.action, exp, "%r -> %s (%s)" % (text, d.action, d.reason))
        self.assertTrue(0 <= d.confidence <= 1); self.assertTrue(d.reason)

    def test_answer(self):
        for t in ["Как настроить nginx?", "почему небо синее", "What is the capital of France", "привет", "hello",
                  "Расскажи про Python", "Is it going to rain tomorrow", "Я не понимаю, как работает этот цикл в коде"]:
            self.a(t, "answer")

    def test_act(self):
        for t in ["открой терминал", "Запусти тесты пожалуйста", "please restart nginx", "Можешь открыть файл?",
                  "Run the backup now", "напомни мне завтра про отчёт", "could you delete the old logs"]:
            self.a(t, "act")

    def test_clarify(self):
        for t in ["я думаю что", "и ещё, а", "сделай это", "thinking about the", "ладно, но", "?"]:
            self.a(t, "clarify")
        self.a("холодильник", "clarify")

    def test_ignore(self):
        for t in ["", "   ", "...", "👍", "ага", "ok", "угу", "!!!"]:
            self.a(t, "ignore")

    def test_echo_and_repeat(self):
        self.a("Всё готово, файл сохранён", "ignore", [U("сохрани"), A("Всё готово, файл сохранён")])
        self.a("какая погода сегодня", "ignore", [U("какая погода сегодня"), A("Солнечно")])

    def test_ack_after_question_is_answer(self):
        self.a("да", "answer", [U("удали файл"), A("Точно удалить?")])

    def test_deictic_with_history_ok(self):
        self.a("сделай это", "act", [U("вот скрипт"), A("Вижу")])

    def test_no_user(self):
        self.assertEqual(route([]).action, "ignore")
        self.assertEqual(route([A("hi")]).action, "ignore")
        self.assertEqual(route(None).action, "ignore")

    def test_list_content(self):
        d = route([{"role": "user", "content": [{"type": "text", "text": "открой файл"}]}])
        self.assertEqual(d.action, "act")

    def test_to_dict(self):
        d = route_text("как дела?").to_dict()
        self.assertEqual(set(d), {"action", "reason", "confidence", "features"})

    def test_speed_under_5ms(self):
        samples = ["Как настроить nginx?", "открой терминал", "я думаю что", "ага", "Расскажи мне подробно про устройство сети " * 20,
                   "what is going on here and why"]
        hist = [U("привет"), A("Здравствуйте")] * 20
        n = 0
        worst = 0.0
        for _ in range(200):
            for s in samples:
                t0 = time.perf_counter()
                route(hist + [U(s)])
                worst = max(worst, time.perf_counter() - t0); n += 1
        t0 = time.perf_counter()
        for _ in range(200):
            for s in samples:
                route(hist + [U(s)])
        avg = (time.perf_counter() - t0) / (200 * len(samples))
        self.assertLess(avg, 0.005, "avg %.3f ms" % (avg * 1000))
        self.assertLess(worst, 0.05)


if __name__ == "__main__":
    unittest.main()
