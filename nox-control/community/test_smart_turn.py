import math, os, random, struct, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from community import smart_turn as st

SR = 16000


def sine(sec, f=220.0, amp=8000):
    return [int(amp * math.sin(2 * math.pi * f * i / SR) * (0.6 + 0.4 * math.sin(2 * math.pi * 4 * i / SR))) for i in range(int(sec * SR))]


def silence(sec, noise=0, seed=1):
    r = random.Random(seed)
    return [r.randint(-noise, noise) if noise else 0 for _ in range(int(sec * SR))]


def pcm(*parts):
    xs = [x for p in parts for x in p]
    return struct.pack("<%dh" % len(xs), *xs)


class T(unittest.TestCase):
    def test_backend_default_heuristic(self):
        st.load_onnx("/nonexistent/model.onnx")
        self.assertEqual(st.backend(), "heuristic")
        self.assertIn("not found", st.onnx_error())

    def test_pure_silence_no_speech(self):
        r = st.analyze(pcm(silence(2.0, noise=30)))
        self.assertFalse(r["speech"]); self.assertFalse(r["complete"])

    def test_speech_then_long_silence_complete(self):
        r = st.analyze(pcm(silence(0.3, 30), sine(1.5), silence(1.2, 30)))
        self.assertTrue(r["speech"]); self.assertTrue(r["complete"], r)
        self.assertAlmostEqual(r["speech_ms"], 1500, delta=250)

    def test_speech_without_pause_not_complete(self):
        r = st.analyze(pcm(silence(0.3, 30), sine(1.5)))
        self.assertFalse(r["complete"], r)

    def test_short_pause_mid_sentence_not_complete(self):
        r = st.analyze(pcm(sine(1.0), silence(0.25, 30)))
        self.assertFalse(r["complete"], r)

    def test_adaptive_pause_slow_speaker(self):
        # говорящий делает внутреннюю паузу 0.7 с -> нужная пауза растёт (>=0.9)
        a = st.analyze(pcm(sine(0.8), silence(0.7, 30), sine(0.8), silence(0.7, 30)))
        self.assertGreater(a["required_silence"], 0.8)
        self.assertFalse(a["complete"], a)
        b = st.analyze(pcm(sine(0.8), silence(0.7, 30), sine(0.8), silence(1.6, 30)))
        self.assertTrue(b["complete"], b)

    def test_adaptive_threshold_noisy_room(self):
        noise = 400
        r = st.analyze(pcm(silence(0.5, noise), sine(1.5, amp=9000), silence(1.3, noise)))
        self.assertTrue(r["complete"], r)
        r2 = st.analyze(pcm(silence(3.0, noise)))
        self.assertFalse(r2["speech"])

    def test_odd_bytes_and_empty(self):
        self.assertFalse(st.analyze(b"")["complete"])
        self.assertFalse(st.analyze(b"\x01")["complete"])
        b = pcm(sine(1.0), silence(1.2, 30)) + b"\x00"
        self.assertTrue(st.is_turn_complete(b))

    def test_streaming_detector(self):
        d = st.TurnDetector()
        data = pcm(sine(1.0), silence(1.2, 30))
        res = None
        for i in range(0, len(data), 3200):
            res = d.feed(data[i:i + 3200])
        self.assertTrue(res["complete"])
        d.reset(); self.assertEqual(len(d.buf), 0)

    def test_onnx_failure_falls_back(self):
        class Bad:
            def get_inputs(self): raise RuntimeError("boom")
        st._ONNX.update(session=Bad(), np=object())
        try:
            r = st.analyze(pcm(sine(1.0), silence(1.2, 30)))
            self.assertEqual(r["backend"], "heuristic"); self.assertEqual(st.backend(), "heuristic")
            self.assertIn("inference failed", st.onnx_error())
        finally:
            st._ONNX.update(session=None)

    def test_log_mel_shape_if_numpy(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest("numpy not installed")
        f = st._log_mel(np, np.zeros(16000, dtype=np.float32))
        self.assertEqual(f.shape, (80, 800))


if __name__ == "__main__":
    unittest.main()
