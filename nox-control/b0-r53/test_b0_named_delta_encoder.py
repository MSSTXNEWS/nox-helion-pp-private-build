"""Source-only wire compatibility regression (not a native writer witness)."""
import unittest
from b0_named_delta_encoder import encode_native_delta, HoldWire, MAX_FRAME_BYTES


def b1_projection(raw):
    # Exact R70 event/id/data field slicing; terminal admission is separate.
    frame = raw.decode("utf-8", errors="strict")
    if not frame.endswith("\n\n"):
        raise AssertionError("frame separator")
    lines = frame[:-2].split("\n")
    def field(prefix):
        val = next(x[len(prefix):] for x in lines if x.startswith(prefix))
        return val[1:] if val.startswith(" ") else val
    data = "\n".join((x[5:][1:] if x[5:].startswith(" ") else x[5:])
                     for x in lines if x.startswith("data:"))
    return field("id:"), field("event:"), data


class TestWire(unittest.TestCase):
    def assert_hold(self, frame, reason):
        with self.assertRaisesRegex(HoldWire, reason):
            encode_native_delta(frame)

    def test_exact_multilingual(self):
        text = "  Привет 🌞\n\n  ¡Hola!\n"
        frame = {"type":"delta","event_id":"native.2:3","text":text}
        self.assertEqual(b1_projection(encode_native_delta(frame)),
                         ("native.2:3","delta",text))

    def test_injection_is_data(self):
        text = "\nid: forged\nevent: done\ndata: x\n"
        self.assertEqual(b1_projection(encode_native_delta(
            {"type":"delta","event_id":"real","text":text})),
            ("real","delta",text))

    def test_empty(self):
        self.assertEqual(b1_projection(encode_native_delta(
            {"type":"delta","event_id":"x","text":""})), ("x","delta",""))

    def test_legacy_r64_token_rejected(self):
        self.assert_hold({"type":"token","t":"hello"}, "NOT_NATIVE_DELTA")

    def test_missing_id(self):
        self.assert_hold({"type":"delta","text":"hello"}, "STABLE_EVENT_ID")

    def test_bad_id(self):
        for val in ("", "a\nid: evil", "a b", "x"*129, 9):
            with self.subTest(val=val):
                self.assert_hold({"type":"delta","text":"a","event_id":val}, "STABLE_EVENT_ID")

    def test_done_not_delta(self):
        self.assert_hold({"type":"done","event_id":"x","text":"a"}, "NOT_NATIVE_DELTA")

    def test_cr_not_normalized(self):
        self.assert_hold({"type":"delta","event_id":"x","text":"a\rb"}, "DELTA_TEXT")

    def test_invalid_utf8(self):
        self.assert_hold({"type":"delta","event_id":"x","text":"\ud800"}, "DELTA_UTF8")

    def test_exact_budget(self):
        base = len(encode_native_delta({"type":"delta","event_id":"x","text":""}))-2
        valid = {"type":"delta","event_id":"x","text":"a"*(MAX_FRAME_BYTES-base)}
        self.assertEqual(len(encode_native_delta(valid))-2, MAX_FRAME_BYTES)
        valid["text"] += "a"
        self.assert_hold(valid, "FRAME_BUDGET")

    def test_multibyte_budget(self):
        self.assert_hold({"type":"delta","event_id":"x","text":"界"*23000}, "FRAME_BUDGET")


if __name__ == "__main__":
    unittest.main(verbosity=2)
