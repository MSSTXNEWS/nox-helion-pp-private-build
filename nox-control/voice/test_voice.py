"""Тесты voice без сети (только localhost) и без тяжёлых моделей: поддельные транскрайбер/бэкенды/чат."""
import json
import math
import os
import queue
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from voice import common, stt_server, tts_server, voice_loop  # noqa: E402
from voice.textproc import SentenceSegmenter, clean_for_tts, es_int, ru_int, split_text  # noqa: E402

SR = 16000


def tone(sec, f=220.0, amp=8000):
    return common.from_samples([int(amp * math.sin(2 * math.pi * f * i / SR) * (0.6 + 0.4 * math.sin(2 * math.pi * 4 * i / SR)))
                                for i in range(int(sec * SR))])


def silence(sec):
    return b"\x00\x00" * int(sec * SR)


def chunks(pcm, ms=200):
    n = SR * ms // 1000 * 2
    return [pcm[i:i + n] for i in range(0, len(pcm), n)]


def stream_segment(text, step):
    s = SentenceSegmenter()
    out = []
    for i in range(0, len(text), step):
        out += s.feed(text[i:i + step])
    return out + s.flush()


class TextTests(unittest.TestCase):
    def test_numbers(self):
        self.assertEqual(ru_int(21), "двадцать один")
        self.assertEqual(ru_int(2025), "две тысячи двадцать пять")
        self.assertEqual(ru_int(1000000), "один миллион")
        self.assertEqual(es_int(21345), "veintiún mil trescientos cuarenta y cinco".replace("veintiún", "veintiun"))
        self.assertEqual(es_int(100), "cien")

    def test_clean_markdown_emoji_urls(self):
        t = clean_for_tts("## Заголовок\n- **Важно**: см. https://example.com 😀 `код`\n```py\nprint(1)\n```\nГотово")
        self.assertNotIn("*", t)
        self.assertNotIn("#", t)
        self.assertNotIn("http", t)
        self.assertNotIn("print", t)
        self.assertNotIn("😀", t)
        self.assertIn("ссылка", t)
        self.assertIn("Важно", t)

    def test_clean_numbers_ru_es(self):
        self.assertEqual(clean_for_tts("5% от 16 ГБ", "ru"), "пять процентов от шестнадцать гигабайт")
        self.assertIn("три запятая пять", clean_for_tts("версия 3,5", "ru"))
        self.assertIn("и так далее", clean_for_tts("яблоки, груши и т.д.", "ru"))
        self.assertEqual(clean_for_tts("Tengo 3 gatos y el 25%", "es"), "Tengo tres gatos y el veinticinco por ciento")
        self.assertIn("por ejemplo", clean_for_tts("p. ej. esto", "es"))
        self.assertIn("минус пять", clean_for_tts("температура -5", "ru"))

    def test_segmenter_sentences_and_abbr(self):
        out = split_text("Привет! Как дела? Всё хорошо, т.е. почти. Версия 3.5 вышла.")
        self.assertEqual(out[0], "Привет! Как дела?")
        self.assertIn("Всё хорошо, т.е. почти.", out)
        self.assertTrue(any("3.5" in x for x in out))

    def test_segmenter_streaming_equals_batch(self):
        text = "Первое предложение здесь. Второе предложение тоже длинное! А третье? Да, четвёртое тоже есть. Конец истории."
        ref = split_text(text)
        for step in (1, 3, 7, 50):
            self.assertEqual(stream_segment(text, step), ref, step)

    def test_segmenter_emits_before_end(self):
        s = SentenceSegmenter()
        got = s.feed("Это первое предложение. А это второе, ещё не ")
        self.assertEqual(got, ["Это первое предложение."])
        self.assertEqual(s.flush(), ["А это второе, ещё не"])

    def test_segmenter_early_first_split_on_comma(self):
        s = SentenceSegmenter(first_min_chars=20)
        got = s.feed("Это довольно длинное начало ответа, и продолжение без точки")
        self.assertEqual(got, ["Это довольно длинное начало ответа,"])

    def test_segmenter_long_split_and_merge_short(self):
        s = SentenceSegmenter(max_chars=50, early_first=False)
        got = s.feed("слово " * 30)
        self.assertTrue(got and all(len(x) <= 50 for x in got))
        self.assertEqual(split_text("Да. Нет. Конечно, согласен с этим."), ["Да. Нет. Конечно, согласен с этим."])

    def test_segmenter_skips_code_fence(self):
        out = stream_segment("Смотри пример.\n```python\nprint('x. y')\n```\nГотово и закончено.", 4)
        self.assertFalse(any("print" in x for x in out))
        self.assertTrue(any("Готово" in x for x in out))

    def test_segmenter_newline_and_list(self):
        out = split_text("Список покупок:\n1. хлеб белый\n2. молоко свежее\nВсё.")
        self.assertGreaterEqual(len(out), 2)


class FakeTranscriber:
    name, device, compute = "fake", "cpu", "int8"

    def __init__(self):
        self.calls = []

    def deps(self):
        return {"faster_whisper": True, "numpy": True}

    def available(self):
        return True

    def info(self):
        return {"name": "fake", "loaded": True}

    def transcribe(self, pcm, language=None, words=True, prompt=None):
        d = len(pcm) / 2.0 / SR
        self.calls.append((d, language))
        return {"language": language or "ru", "language_probability": 0.99, "text": "речь %.1f" % d if d > 0.3 else "",
                "segments": [{"start": 0.0, "end": d, "text": "речь", "words": [{"word": "речь", "start": 0.0, "end": d, "probability": 0.9}]}],
                "duration": d}


def run_server(handler_cls, svc):
    srv = common.serve(handler_cls, "127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, "http://127.0.0.1:%d" % srv.server_address[1]


def post(url, body=b"", ctype="application/json", timeout=30):
    if isinstance(body, (dict, list)):
        body = json.dumps(body).encode()
    req = urllib.request.Request(url, body, {"Content-Type": ctype})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode())


class SttTests(unittest.TestCase):
    def setUp(self):
        self.tr = FakeTranscriber()
        self.svc = stt_server.SttService(self.tr)
        self.srv, self.url = run_server(stt_server.make_handler(self.svc), self.svc)

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def feed_all(self, sid, pcm):
        evs = []
        for c in chunks(pcm):
            evs += post("%s/stream/%s/chunk" % (self.url, sid), c, "audio/L16; rate=16000")["events"]
        return evs

    def test_health_honest(self):
        h = get(self.url + "/health")
        self.assertTrue(h["ok"])
        self.assertIn("ffmpeg", h["deps"])
        self.assertIn(h["smart_turn"]["backend"], ("heuristic", "onnx"))
        self.assertEqual(h["smart_turn"]["config"]["min_trailing"], stt_server.TurnConfig().min_trailing)

    def test_real_transcriber_health_matches_imports(self):
        t = stt_server.FasterWhisperTranscriber()
        d = t.deps()
        self.assertEqual(d["faster_whisper"], common.have_module("faster_whisper"))
        if not t.available():
            with self.assertRaises(stt_server.TranscribeError) as cm:
                t.transcribe(tone(0.5))
            self.assertEqual(cm.exception.code, 503)

    def test_end_of_turn_on_synthetic_audio(self):
        sid = post(self.url + "/stream/start", {"language": "ru"})["id"]
        evs = self.feed_all(sid, silence(0.5) + tone(1.5) + silence(1.5))
        types = [e["type"] for e in evs]
        self.assertIn("speech_start", types)
        self.assertEqual(types.count("end_of_turn"), 1)
        self.assertLess(types.index("final"), types.index("end_of_turn"))
        fin = [e for e in evs if e["type"] == "final"][0]
        self.assertTrue(fin["text"].startswith("речь"))
        self.assertEqual(fin["segments"][0]["words"][0]["word"], "речь")
        self.assertEqual(fin["language"], "ru")
        eot = [e for e in evs if e["type"] == "end_of_turn"][0]
        self.assertEqual(eot["reason"], "smart_turn")
        self.assertGreaterEqual(eot["turn"]["trailing_silence"], 0.3)

    def test_no_end_of_turn_mid_speech_or_short_pause(self):
        sid = post(self.url + "/stream/start", {})["id"]
        evs = self.feed_all(sid, tone(1.0) + silence(0.2) + tone(1.0))
        self.assertNotIn("end_of_turn", [e["type"] for e in evs])
        self.assertEqual(self.tr.calls, [])      # partial выключены по умолчанию? нет - но interval 1.5 с не достигнут за миллисекунды

    def test_two_turns_in_one_session(self):
        sid = post(self.url + "/stream/start", {})["id"]
        evs = self.feed_all(sid, tone(1.0) + silence(1.5) + tone(1.0) + silence(1.5))
        self.assertEqual([e["type"] for e in evs].count("end_of_turn"), 2)

    def test_silence_only_no_events_and_bounded_buffer(self):
        sid = post(self.url + "/stream/start", {})["id"]
        evs = self.feed_all(sid, silence(5.0))
        self.assertEqual(evs, [])
        self.assertLess(self.svc.get(sid).state()["buffered_s"], 1.0)

    def test_thresholds_configurable(self):
        # длинная требуемая пауза: через 1.0 с тишины конец ещё не наступил
        sid = post(self.url + "/stream/start", {"turn": {"base_pause": 1.5, "min_trailing": 1.4}})["id"]
        evs = self.feed_all(sid, tone(1.0) + silence(1.0))
        self.assertNotIn("end_of_turn", [e["type"] for e in evs])
        evs = self.feed_all(sid, silence(1.0))
        self.assertIn("end_of_turn", [e["type"] for e in evs])

    def test_partial_events(self):
        sid = post(self.url + "/stream/start", {"partial": 0.0001})["id"]
        evs = self.feed_all(sid, tone(1.5))
        self.assertTrue([e for e in evs if e["type"] == "partial"])

    def test_max_len_forces_final(self):
        sid = post(self.url + "/stream/start", {"turn": {"max_utterance": 2.0}, "partial": 0})["id"]
        evs = self.feed_all(sid, tone(3.0))
        self.assertTrue([e for e in evs if e["type"] == "end_of_turn" and e["reason"] == "max_len"])

    def test_finish_and_events_endpoint(self):
        sid = post(self.url + "/stream/start", {})["id"]
        self.feed_all(sid, tone(1.0))
        r = post("%s/stream/%s/finish" % (self.url, sid), {})
        self.assertEqual([e["type"] for e in r["events"]], ["final", "end_of_turn"])
        ev = get("%s/stream/%s/events?after=0" % (self.url, sid))["events"]
        self.assertIn("end_of_turn", [e["type"] for e in ev])
        self.assertEqual(get("%s/stream/%s/events?after=%d" % (self.url, sid, ev[-1]["id"]))["events"], [])

    def test_transcribe_wav_and_errors(self):
        r = post(self.url + "/transcribe?language=es", common.make_wav(tone(1.0), SR), "audio/wav")
        self.assertEqual(r["language"], "es")
        self.assertTrue(r["text"])
        r = post(self.url + "/transcribe", tone(1.0), "audio/L16; rate=16000")
        self.assertAlmostEqual(r["duration"], 1.0, places=1)
        with self.assertRaises(urllib.error.HTTPError) as cm:
            post(self.url + "/transcribe", b"", "audio/wav")
        self.assertEqual(cm.exception.code, 400)
        with self.assertRaises(urllib.error.HTTPError) as cm:
            post(self.url + "/stream/nope/chunk", b"\x00\x00")
        self.assertEqual(cm.exception.code, 404)

    def test_wav_resample_and_stereo(self):
        import io
        import wave
        bio = io.BytesIO()
        with wave.open(bio, "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(8000)
            w.writeframes(b"\x10\x00\x10\x00" * 8000)
        pcm = common.decode_audio(bio.getvalue())
        self.assertAlmostEqual(len(pcm) / 2.0 / SR, 1.0, places=2)


class FakeBackend(tts_server.TTSBackend):
    def __init__(self, name, rate=22050, fail=False, avail=True, ms=100):
        self.name, self.rate, self.fail, self.avail, self.ms = name, rate, fail, avail, ms
        self.calls = []

    def available(self):
        return (self.avail, "" if self.avail else "not installed")

    def synth(self, text, lang, voice=None):
        self.calls.append((text, lang))
        if self.fail:
            raise tts_server.BackendError("boom")
        return b"\x01\x00" * int(self.rate * self.ms / 1000), self.rate


class BackendTests(unittest.TestCase):
    def test_fallback_to_piper_on_error_and_cooldown(self):
        x, p = FakeBackend("xtts", 24000, fail=True), FakeBackend("piper", 22050)
        m = tts_server.BackendManager([x, p], cooldown=60)
        pcm, name = m.synth("привет", "ru")
        self.assertEqual(name, "piper")
        self.assertEqual(len(pcm), int(0.1 * tts_server.OUT_RATE) * 2, "ресемплинг к OUT_RATE")
        m.synth("ещё", "ru")
        self.assertEqual(len(x.calls), 1, "xtts на cooldown не вызывается повторно")
        self.assertTrue(m.health()["backends"][0]["cooling_down"])
        self.assertEqual(m.stats["xtts_errors"], 1)

    def test_unavailable_skipped_and_all_fail(self):
        x, p = FakeBackend("xtts", avail=False), FakeBackend("piper")
        m = tts_server.BackendManager([x, p])
        self.assertEqual(m.synth("a", "es")[1], "piper")
        self.assertEqual(x.calls, [])
        m2 = tts_server.BackendManager([FakeBackend("xtts", avail=False), FakeBackend("piper", fail=True)])
        with self.assertRaises(tts_server.BackendError) as cm:
            m2.synth("a", "ru")
        self.assertIn("xtts: not installed", str(cm.exception))

    def test_real_backends_report_unavailable_honestly(self):
        os.environ.pop("NOX_PIPER_MODEL", None)
        h = tts_server.BackendManager([tts_server.XttsBackend(), tts_server.PiperBackend()]).health()
        for b in h["backends"]:
            self.assertEqual(b["available"], b["reason"] is None)
        self.assertEqual(h["ready"], any(b["available"] for b in h["backends"]))


def iter_sse(url, method="GET", body=None):
    req = urllib.request.Request(url, body, {"Content-Type": "application/json"}, method=method)
    with urllib.request.urlopen(req, timeout=30) as r:
        for raw in r:
            ln = raw.decode().strip()
            if ln.startswith("data:"):
                e = json.loads(ln[5:])
                yield e
                if e["type"] in ("end", "cancelled"):
                    return


def read_sse(url, method="GET", body=None):
    return list(iter_sse(url, method, body))


class TtsHttpTests(unittest.TestCase):
    def setUp(self):
        self.x, self.p = FakeBackend("xtts", 24000, fail=True), FakeBackend("piper", 22050, ms=50)
        self.svc = tts_server.TtsService(tts_server.BackendManager([self.x, self.p], cooldown=60))
        self.srv, self.url = run_server(tts_server.make_handler(self.svc), self.svc)

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def test_health(self):
        h = get(self.url + "/health")
        self.assertTrue(h["ready"])
        self.assertEqual([b["name"] for b in h["backends"]], ["xtts", "piper"])

    def test_synth_sse_by_phrases_with_cleaning(self):
        evs = read_sse(self.url + "/synth", "POST", json.dumps({"text": "Привет! У меня **5** новостей. Вот ссылка https://a.b/c 😀", "lang": "ru"}).encode())
        audio = [e for e in evs if e["type"] == "audio"]
        self.assertGreaterEqual(len(audio), 2)
        self.assertEqual(evs[-1]["type"], "end")
        self.assertTrue(all(e["backend"] == "piper" for e in audio))
        self.assertEqual([e["seq"] for e in audio], list(range(1, len(audio) + 1)))
        import base64
        self.assertGreater(len(base64.b64decode(audio[0]["pcm_b64"])), 100)
        joined = " ".join(e["text"] for e in audio)
        self.assertIn("пять", joined)
        self.assertNotIn("http", joined)
        self.assertNotIn("*", joined)

    def test_streaming_text_audio_before_final(self):
        sid = post(self.url + "/session", {"lang": "ru"})["id"]
        post("%s/session/%s/text" % (self.url, sid), {"text": "Первая фраза готова. Вторая начинается"})
        got = queue.Queue()

        def reader():
            for e in iter_sse("%s/session/%s/audio?format=sse" % (self.url, sid)):
                got.put(e)
        threading.Thread(target=reader, daemon=True).start()
        e = got.get(timeout=10)                    # пришло ДО final=True
        self.assertEqual(e["type"], "audio")
        self.assertEqual(e["text"], "Первая фраза готова.")
        post("%s/session/%s/text" % (self.url, sid), {"text": " и заканчивается здесь.", "final": True})
        types = []
        while not types or types[-1] != "end":
            types.append(got.get(timeout=10)["type"])
        self.assertEqual(types, ["audio", "end"])

    def test_pcm_and_wav_formats(self):
        for fmt in ("pcm", "wav"):
            req = urllib.request.Request(self.url + "/synth", json.dumps({"text": "Короткая фраза для проверки.", "format": fmt}).encode(),
                                         {"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
                self.assertEqual(r.headers["X-Sample-Rate"], str(tts_server.OUT_RATE))
            if fmt == "wav":
                self.assertEqual(data[:4], b"RIFF")
                self.assertEqual(data[36:40], b"data")
                data = data[44:]
            self.assertAlmostEqual(len(data) / 2.0 / tts_server.OUT_RATE, 0.05, places=2)

    def test_stop_cancels(self):
        slow = FakeBackend("piper", ms=10)
        orig = slow.synth

        def slow_synth(*a, **k):
            time.sleep(0.3)
            return orig(*a, **k)
        slow.synth = slow_synth
        svc = tts_server.TtsService(tts_server.BackendManager([slow]))
        srv, url = run_server(tts_server.make_handler(svc), svc)
        try:
            sid = post(url + "/session", {"lang": "ru"})["id"]
            post("%s/session/%s/text" % (url, sid), {"text": "Одна фраза. Вторая фраза. Третья фраза. Четвёртая фраза.", "final": True})
            time.sleep(0.1)
            self.assertEqual(post("%s/stop" % url, {"session": sid})["stopped"], 1)
            evs = read_sse("%s/session/%s/audio" % (url, sid))
            self.assertEqual(evs[-1]["type"], "cancelled")
            time.sleep(0.8)
            self.assertLessEqual(len(slow.calls), 1, "после STOP новые фразы не синтезируются")
            with self.assertRaises(urllib.error.HTTPError) as cm:
                post("%s/session/%s/text" % (url, sid), {"text": "ещё"})
            self.assertEqual(cm.exception.code, 409)
        finally:
            srv.shutdown()
            srv.server_close()

    def test_all_backends_fail_reports_error_event(self):
        svc = tts_server.TtsService(tts_server.BackendManager([FakeBackend("xtts", avail=False), FakeBackend("piper", avail=False)]))
        srv, url = run_server(tts_server.make_handler(svc), svc)
        try:
            evs = read_sse(url + "/synth", "POST", json.dumps({"text": "Привет, мир."}).encode())
            self.assertEqual(evs[0]["type"], "error")
            self.assertIn("not installed", evs[0]["message"])
            self.assertEqual(evs[-1]["type"], "end")
            self.assertFalse(get(url + "/health")["ready"])
        finally:
            srv.shutdown()
            srv.server_close()


# ---------------- барж-ин и цикл ----------------
class FakeStt:
    def __init__(self, script):
        self.script, self.n = script, 0

    def start(self):
        return "s"

    def chunk(self, pcm):
        self.n += 1
        return {"events": self.script.get(self.n, [])}

    def finish(self):
        return {"events": []}

    def close(self):
        pass


class FakeTts:
    def __init__(self):
        self.q = {}
        self.pushed = []
        self.stopped = []
        self.n = 0

    def start(self):
        self.n += 1
        sid = "t%d" % self.n
        self.q[sid] = queue.Queue()
        return sid

    def push(self, sid, text, final=False):
        self.pushed.append((sid, text, final))
        if text.strip():
            self.q[sid].put({"type": "audio", "seq": 1, "text": text, "backend": "fake", "sample_rate": 24000, "pcm": b"\x01\x00" * 2400})
        if final:
            self.q[sid].put({"type": "end"})

    def stop(self, sid):
        self.stopped.append(sid)
        self.q[sid].put({"type": "cancelled"})

    def events(self, sid):
        while True:
            e = self.q[sid].get(timeout=10)
            yield e
            if e["type"] in ("end", "cancelled"):
                return


class FakeChat:
    def __init__(self, words=60, delay=0.03):
        self.words, self.delay, self.calls, self.emitted = words, delay, [], []

    def stream(self, messages, cancel=None):
        self.calls.append(messages)
        self.emitted.append(0)
        idx = len(self.emitted) - 1
        for i in range(self.words):
            if cancel is not None and cancel.is_set():
                break
            time.sleep(self.delay)
            self.emitted[idx] += 1
            yield "слово%d. " % i


EOT = [{"type": "final", "text": "привет", "language": "ru"}, {"type": "end_of_turn", "reason": "smart_turn"}]


class SlowSource:
    def __init__(self, n, pause_at=None, pause=0.0):
        self.n, self.pause_at, self.pause = n, pause_at or {}, 0

    def __iter__(self):
        for i in range(1, self.n + 1):
            time.sleep(self.pause_at.get(i, 0.0))
            yield b"\x00\x00" * 3200


class BargeInTests(unittest.TestCase):
    def test_barge_in_stops_tts_chat_and_sink(self):
        tts, chat, sink = FakeTts(), FakeChat(words=100), voice_loop.MemorySink()
        stt = FakeStt({1: EOT, 3: [{"type": "speech_start", "speech_ms": 400}], 5: [{"type": "final", "text": "стоп хватит"}, {"type": "end_of_turn"}]})
        loop = voice_loop.VoiceLoop(SlowSource(6, {3: 0.6, 5: 0.6}), sink, stt, tts, chat, barge_in=True, barge_min_ms=300)
        res = loop.run(drain_timeout=20)
        self.assertEqual(res["barge_ins"], 1)
        self.assertTrue(res["turns"][0]["barged_in"])
        self.assertGreaterEqual(sink.stopped_count, 1)
        self.assertIn("t1", tts.stopped)
        self.assertLess(chat.emitted[0], 100, "ответ чата прерван")
        self.assertEqual([t["user"] for t in res["turns"] if t["id"] == 2], ["стоп хватит"])   # новая реплика после перебивания
        self.assertEqual(chat.calls[1][-1], {"role": "user", "content": "стоп хватит"})

    def test_short_noise_does_not_barge_in(self):
        tts, chat, sink = FakeTts(), FakeChat(words=10), voice_loop.MemorySink()
        stt = FakeStt({1: EOT, 3: [{"type": "speech_start", "speech_ms": 100}]})
        loop = voice_loop.VoiceLoop(SlowSource(4, {3: 0.2}), sink, stt, tts, chat, barge_in=True, barge_min_ms=300)
        res = loop.run(drain_timeout=20)
        self.assertEqual(res["barge_ins"], 0)
        self.assertFalse(res["turns"][0]["barged_in"])
        self.assertEqual(chat.emitted, [10])

    def test_half_duplex_drops_mic_while_speaking(self):
        tts, chat, sink = FakeTts(), FakeChat(words=10, delay=0.05), voice_loop.MemorySink()
        stt = FakeStt({1: EOT})
        loop = voice_loop.VoiceLoop(SlowSource(8, {i: 0.1 for i in range(2, 9)}), sink, stt, tts, chat, barge_in=False)
        loop.run(drain_timeout=20)
        self.assertLess(stt.n, 8)

    def test_empty_final_is_ignored(self):
        tts, chat, sink = FakeTts(), FakeChat(), voice_loop.MemorySink()
        stt = FakeStt({1: [{"type": "final", "text": "  "}, {"type": "end_of_turn"}]})
        res = voice_loop.VoiceLoop(SlowSource(2), sink, stt, tts, chat).run(drain_timeout=5)
        self.assertEqual(res["turns"], [])
        self.assertEqual(chat.calls, [])

    def test_chat_error_recorded_and_tts_closed(self):
        class Bad:
            def stream(self, m, cancel=None):
                raise RuntimeError("chat down")
                yield
        tts = FakeTts()
        res = voice_loop.VoiceLoop(SlowSource(2), voice_loop.MemorySink(), FakeStt({1: EOT}), tts, Bad()).run(drain_timeout=10)
        self.assertTrue(any("chat down" in e for e in res["errors"]))
        self.assertTrue(tts.pushed[-1][2])


class ChatServer:
    """Мини-чат по HTTP: nox-формат SSE."""

    def __init__(self, fmt="nox"):
        outer = self

        class H(common.JsonHandler):
            def do_POST(self):
                self.read_body()
                self.start_chunked("text/event-stream")
                for w in ["Здравствуйте. ", "Меня зовут Нокс, ", "я готов помочь. ", "Сегодня 5 задач."]:
                    o = {"type": "token", "text": w} if fmt == "nox" else {"choices": [{"delta": {"content": w}}]}
                    self.write_chunk(("data: %s\n\n" % json.dumps(o, ensure_ascii=False)).encode())
                self.write_chunk(b"data: " + (b'{"type":"done"}' if fmt == "nox" else b"[DONE]") + b"\n\n")
                self.end_chunked()
        self.srv, self.url = run_server(H, None)


class IntegrationTests(unittest.TestCase):
    def test_full_loop_over_http(self):
        import tempfile
        tr = FakeTranscriber()
        stt_svc = stt_server.SttService(tr)
        s1, stt_url = run_server(stt_server.make_handler(stt_svc), stt_svc)
        tts_svc = tts_server.TtsService(tts_server.BackendManager([FakeBackend("xtts", fail=True), FakeBackend("piper", 22050, ms=30)]))
        s2, tts_url = run_server(tts_server.make_handler(tts_svc), tts_svc)
        try:
            for fmt in ("nox", "openai"):
                chat = ChatServer(fmt)
                d = tempfile.mkdtemp()
                sink = voice_loop.FileSink(d)
                src = voice_loop.ListSource(chunks(silence(0.3) + tone(1.2) + silence(2.0)))
                loop = voice_loop.VoiceLoop(src, sink, voice_loop.SttClient(stt_url, "ru"), voice_loop.TtsClient(tts_url, "ru"),
                                            voice_loop.ChatClient(chat.url + "/x", fmt), system_prompt="кратко")
                res = loop.run(drain_timeout=30)
                chat.srv.shutdown()
                chat.srv.server_close()
                self.assertEqual(len(res["turns"]), 1, res)
                t = res["turns"][0]
                self.assertTrue(t["user"].startswith("речь"))
                self.assertIn("Нокс", t["reply"])
                self.assertGreaterEqual(t["phrases_spoken"], 2)
                self.assertEqual(len(sink.files), 1)
                self.assertGreater(os.path.getsize(sink.files[0]), 1000)
                self.assertEqual(res["errors"], [])
        finally:
            for s in (s1, s2):
                s.shutdown()
                s.server_close()

    def test_file_source_adds_tail_silence(self):
        import tempfile
        p = os.path.join(tempfile.mkdtemp(), "q.wav")
        with open(p, "wb") as f:
            f.write(common.make_wav(tone(1.0), SR))
        src = voice_loop.FileSource(p, tail_silence=2.0)
        self.assertAlmostEqual(len(src.pcm) / 2.0 / SR, 3.0, places=2)
        self.assertEqual(b"".join(src), src.pcm)

    def test_mic_source_honest_error(self):
        if not (voice_loop.shutil.which("arecord") or common.ffmpeg_path()):
            with self.assertRaises(RuntimeError):
                voice_loop.MicSource()


if __name__ == "__main__":
    unittest.main()
