import base64
import json
import math
import os
import struct
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CONTROL = os.environ.get("NOX_CONTROL") or "/home/claude/msstxnews/nox-helion-pp-private-build/nox-control"
if not os.path.isdir(os.path.join(CONTROL, "voice")):
    raise unittest.SkipTest("нужен клон nox-control (NOX_CONTROL) с пакетом voice")
os.environ["NOX_CONTROL"] = CONTROL
sys.path.insert(0, HERE)
import voice_server as V  # noqa: E402
from voice import common  # noqa: E402

RATE = V.OUT_RATE


class FakeBackend(V.TTSBackend):
    """Выдаёт синус 0.5 с на фразу; delay имитирует время синтеза."""
    def __init__(self, name="fake", delay=0.0, fail=None, ok=True):
        self.name, self.delay, self.fail, self.ok, self.calls, self.speeds = name, delay, fail, ok, [], []

    def available(self):
        return (True, "") if self.ok else (False, "python package 'torch' not installed (pip install torch)")

    def synth(self, text, lang, voice=None):
        self.calls.append((text, lang, voice))
        self.speeds.append(V.current_speed())
        if self.fail:
            raise V.BackendError(self.fail)
        time.sleep(self.delay)
        n = RATE // 2
        return struct.pack("<%dh" % n, *[int(8000 * math.sin(i / 20.0)) for i in range(n)]), RATE


class FakeStt:
    name = "fake"

    def __init__(self, ready=True):
        self.ready = ready

    def available(self):
        return self.ready

    def deps(self):
        return {"faster_whisper": self.ready}

    def info(self):
        return {"name": "fake"}

    def transcribe(self, pcm, language=None, words=True, prompt=None):
        if not self.ready:
            raise V.TranscribeError("dependencies missing: faster_whisper", 503)
        return {"language": language or "ru", "text": "привет, %d байт" % len(pcm), "segments": []}


def make_service(backend=None, stt=None, **kw):
    b = backend or FakeBackend()
    mgrs = {l: V.BackendManager(backends=[b], cooldown=0.1) for l in ("ru", "es", "en")}
    return V.VoiceService(managers=mgrs, transcriber=stt or FakeStt(), vad_factory=V.EnergyVad), b


class Server:
    def __init__(self, svc):
        self.svc = svc
        self.srv = common.serve(V.make_handler(svc), "127.0.0.1", 0)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = "http://127.0.0.1:%d" % self.srv.server_address[1]

    def req(self, path, body=None, raw=None, ctype="application/json"):
        data = raw if raw is not None else (None if body is None else json.dumps(body).encode())
        r = urllib.request.Request(self.base + path, data=data, method="GET" if data is None else "POST", headers={"Content-Type": ctype})
        try:
            return urllib.request.urlopen(r, timeout=10)
        except urllib.error.HTTPError as e:
            return e

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


def tone(ms, amp=8000, rate=16000):
    n = rate * ms // 1000
    return struct.pack("<%dh" % n, *[int(amp * math.sin(i / 5.0)) for i in range(n)])


def silence(ms, rate=16000):
    return b"\x00\x00" * (rate * ms // 1000)


class Units(unittest.TestCase):
    def test_mood_speed(self):
        self.assertEqual(V.mood_speed(None), 1.0)
        self.assertEqual(V.mood_speed({"p": "x"}), 1.0)
        self.assertGreater(V.mood_speed({"p": 0.5, "a": 0.8}), 1.05)
        self.assertLess(V.mood_speed({"p": -0.8, "a": -0.5}), 0.95)
        self.assertLessEqual(V.mood_speed({"p": 1, "a": 1}), 1.12)
        self.assertGreaterEqual(V.mood_speed({"p": -1, "a": -1}), 0.9)

    def test_to_pcm16(self):
        b = V.to_pcm16([0.0, 1.0, -1.0, 2.0])
        self.assertEqual(struct.unpack("<4h", b), (0, 32767, -32767, 32767))

    def test_energy_vad_and_barge(self):
        det = V.BargeDetector(V.EnergyVad(), min_ms=250)
        sp, br = det.feed(silence(500))
        self.assertFalse(sp or br)
        sp, br = det.feed(tone(100))
        self.assertTrue(sp)
        self.assertFalse(br)                    # 100 мс мало
        sp, br = det.feed(tone(300))
        self.assertTrue(br)

    def test_barge_resets_on_gap_and_cough(self):
        det = V.BargeDetector(V.EnergyVad(), min_ms=250)
        det.feed(silence(300))
        for _ in range(3):                      # короткие всплески по 100 мс с паузами - не перебивание
            self.assertFalse(det.feed(tone(100))[1])
            self.assertFalse(det.feed(silence(200))[1])

    def test_barge_frame_buffering(self):
        det = V.BargeDetector(V.EnergyVad(), min_ms=250)
        det.feed(silence(300))
        data, fired = tone(400), False
        for i in range(0, len(data), 300):      # нестандартные куски по 150 сэмплов
            fired = fired or det.feed(data[i:i + 300])[1]
        self.assertTrue(fired)

    def test_real_backends_report_missing(self):
        s, k = V.SileroBackend(), V.KokoroBackend()
        s.path = "/nonexistent/v5_ru.pt"
        ok, why = s.available()
        self.assertFalse(ok)
        self.assertTrue("torch" in why or "model file" in why, why)
        with self.assertRaises(V.BackendError):
            s.synth("привет", "es")             # не тот язык
        if not common.have_module("kokoro"):
            ok, why = k.available()
            self.assertFalse(ok)
            self.assertIn("kokoro", why)
            with self.assertRaises(V.BackendError):
                k.synth("hola", "es")
        with self.assertRaises(V.BackendError):
            k.synth("привет", "ru")

    def test_build_managers_order(self):
        m = V.build_managers(orders={"ru": "silero,piper", "es": "kokoro", "en": "kokoro"})
        self.assertEqual([b.name for b in m["ru"].backends], ["silero", "piper"])
        self.assertEqual([b.name for b in m["es"].backends], ["kokoro"])
        self.assertIs(m["es"].backends[0], m["en"].backends[0])          # экземпляр общий

    def test_phrases_cleaning(self):
        svc, _ = make_service()
        ph = svc.phrases("Привет, мессир! Вот код:\n```python\nprint(1)\n```\nИ ещё фраза номер два.", "ru")
        self.assertTrue(all("print" not in p and "`" not in p for p in ph))
        self.assertGreaterEqual(len(ph), 2)


class Http(unittest.TestCase):
    def setUp(self):
        self.svc, self.b = make_service()
        self.s = Server(self.svc)

    def tearDown(self):
        self.s.close()

    def test_health(self):
        j = json.loads(self.s.req("/health").read())
        self.assertTrue(j["tts"]["ru"]["ready"])
        self.assertTrue(j["stt"]["ready"])
        self.assertEqual(self.s.req("/nope").code, 404)

    def test_tts_pcm_stream(self):
        r = self.s.req("/tts", {"text": "Привет, мессир. Как ваши дела сегодня?", "lang": "ru", "sid": "a"})
        self.assertEqual(r.status, 200)
        self.assertEqual(r.headers["X-Sample-Rate"], str(RATE))
        data = r.read()
        self.assertEqual(len(data), RATE * len(self.b.calls))              # 0.5 с * 2 байта на фразу
        self.assertGreaterEqual(len(self.b.calls), 1)
        self.assertEqual(self.svc.jobs, {})

    def test_tts_sse_and_mood_speed(self):
        r = self.s.req("/tts", {"text": "Hola, ¿cómo estás hoy? Todo bien por aquí.", "lang": "es", "format": "sse", "mood": {"p": 0.5, "a": 0.8}})
        body = r.read().decode()
        evs = [json.loads(l[5:]) for l in body.split("\n") if l.startswith("data:")]
        self.assertEqual(evs[-1]["type"], "end")
        au = [e for e in evs if e["type"] == "audio"]
        self.assertTrue(au and au[0]["sample_rate"] == RATE and base64.b64decode(au[0]["pcm_b64"]))
        self.assertGreater(self.b.speeds[0], 1.05)
        self.assertEqual(self.b.calls[0][1], "es")

    def test_bad_requests(self):
        self.assertEqual(self.s.req("/tts", {"text": "   ", "lang": "ru"}).code, 400)
        self.assertEqual(self.s.req("/tts", {"text": "Привет", "format": "mp3"}).code, 400)
        self.assertEqual(self.s.req("/tts", raw=b"{oops").code, 400)

    def test_missing_backend_is_clear_503(self):
        svc, _ = make_service(FakeBackend(ok=False))
        s = Server(svc)
        try:
            r = s.req("/tts", {"text": "Привет, мессир.", "lang": "ru"})
            self.assertEqual(r.code, 503)
            j = json.loads(r.read())
            self.assertIn("torch", j["error"])
            self.assertIn("torch", j["missing"])
            self.assertIn("install_voice_s1.sh", j["hint"])
            h = json.loads(s.req("/health").read())
            self.assertFalse(h["tts"]["ru"]["ready"])
        finally:
            s.close()

    def test_backend_failure_503_then_cooldown_text(self):
        svc, _ = make_service(FakeBackend(fail="boom"))
        s = Server(svc)
        try:
            r = s.req("/tts", {"text": "Привет, мессир.", "lang": "ru"})
            self.assertEqual(r.code, 503)
            self.assertIn("boom", json.loads(r.read())["error"])
        finally:
            s.close()

    def test_cancel_midstream(self):
        svc, b = make_service(FakeBackend(delay=0.25))
        s = Server(svc)
        try:
            text = " ".join("Это достаточно длинная фраза номер %d для проверки." % i for i in range(8))
            r = s.req("/tts", {"text": text, "lang": "ru", "sid": "cx"})
            jid = r.headers["X-Voice-Id"]
            got = len(r.read(RATE * 2 // 10))
            self.assertGreater(got, 0)
            self.assertEqual(json.loads(s.req("/cancel", {"id": jid}).read())["cancelled"], [jid])
            rest = r.read()
            self.assertLess(got + len(rest), RATE * 4)                          # из 8 фраз (8*RATE байт) пришло меньше половины
            time.sleep(0.5)
            self.assertLess(len(b.calls), 8)
            self.assertEqual(svc.jobs, {})
        finally:
            s.close()

    def test_client_disconnect_cancels(self):
        svc, b = make_service(FakeBackend(delay=0.1))
        s = Server(svc)
        try:
            text = " ".join("Это достаточно длинная фраза номер %d для проверки." % i for i in range(10))
            r = s.req("/tts", {"text": text, "lang": "ru"})
            r.read(1000)
            r.close()
            for _ in range(40):
                if not svc.jobs:
                    break
                time.sleep(0.1)
            self.assertEqual(svc.jobs, {})
            self.assertLess(len(b.calls), 10)
        finally:
            s.close()

    def test_barge_cancels_speaking_session(self):
        svc, b = make_service(FakeBackend(delay=0.3))
        s = Server(svc)
        try:
            text = " ".join("Это достаточно длинная фраза номер %d для проверки." % i for i in range(8))
            r = s.req("/tts", {"text": text, "lang": "ru", "sid": "u1"})
            r.read(100)
            j = json.loads(s.req("/barge?sid=u1", raw=silence(300), ctype="audio/L16").read())
            self.assertFalse(j["barge"])
            self.assertTrue(j["speaking"])
            j = json.loads(s.req("/barge?sid=u1", raw=tone(400), ctype="audio/L16").read())
            self.assertTrue(j["barge"])
            self.assertEqual(len(j["cancelled"]), 1)
            r.read()
            self.assertLess(len(b.calls), 8)
            # без озвучки перебивание ничего не отменяет
            j = json.loads(s.req("/barge?sid=u2", raw=tone(600), ctype="audio/L16").read())
            self.assertTrue(j["barge"] and j["cancelled"] == [])
        finally:
            s.close()

    def test_stt(self):
        r = self.s.req("/stt?language=es", raw=tone(500), ctype="audio/L16")
        j = json.loads(r.read())
        self.assertEqual((j["language"], r.status), ("es", 200))
        self.assertIn("16000", j["text"])
        self.assertEqual(self.s.req("/stt", raw=b"", ctype="audio/L16").code, 400)

    def test_stt_missing_package(self):
        svc, _ = make_service(stt=FakeStt(ready=False))
        s = Server(svc)
        try:
            r = s.req("/stt", raw=tone(300), ctype="audio/L16")
            self.assertEqual(r.code, 503)
            j = json.loads(r.read())
            self.assertIn("faster-whisper", j["hint"])
            self.assertFalse(json.loads(s.req("/health").read())["stt"]["ready"])
        finally:
            s.close()


if __name__ == "__main__":
    unittest.main()


class Bench(unittest.TestCase):
    def test_bench_against_fake_server(self):
        import voice_bench as B
        svc, _ = make_service(FakeBackend(delay=0.05))
        s = Server(svc)
        try:
            r = B.bench_one(s.base, "Привет, мессир. Как дела сегодня?", "ru")
            self.assertTrue(r["ok"], r)
            self.assertEqual(r["backend"], "fake")
            self.assertGreater(r["audio_s"], 0.4)
            self.assertLess(r["ttfa_s"], r["total_s"] + 1e-6)
            summ = B.summarize([r, dict(r, ttfa_s=0.3, rtf=0.2), {"ok": False, "lang": "ru", "error": "x"}])
            self.assertEqual(summ["ru"]["runs"], 3)
            self.assertEqual(summ["ru"]["errors"], ["x"])
            self.assertEqual(B.main(["--url", s.base, "--repeat", "1"]), 0)
        finally:
            s.close()
        bad = B.bench_one("http://127.0.0.1:1", "Привет", "ru", timeout=2)
        self.assertFalse(bad["ok"])
        svc2, _ = make_service(FakeBackend(ok=False))
        s2 = Server(svc2)
        try:
            e = B.bench_one(s2.base, "Привет, мессир.", "ru")
            self.assertFalse(e["ok"])
            self.assertIn("503", e["error"])
        finally:
            s2.close()
