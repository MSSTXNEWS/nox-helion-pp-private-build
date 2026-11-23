"""Non-native source contract tests for B2 RU/ES 3-turn holdout capture."""
import copy
import importlib.util
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "b2_ru_es_3turn_holdout.py"
spec = importlib.util.spec_from_file_location("nox_b2_holdout", SOURCE)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def fixture():
    sessions = []
    for i, (case_id, spec) in enumerate(probe.CASES.items()):
        history, turns = [], []
        for j, prompt in enumerate(spec["prompts"]):
            history.append({"role": "user", "content": prompt})
            answer = f"Тестовый ответ {i}-{j} / respuesta: ✓"
            turns.append({
                "messages": copy.deepcopy(history),
                "requested_locale": spec["locale"][j],
                "browser_session_id": f"browser-{i}",
                "stream_id": f"stream-{i}-{j}",
                "sse_deltas": [answer[:9], answer[9:]],
                "sse_done": True,
                "answer": answer,
                "s03_record_id": f"s03-{i}-{j}",
            })
            history.append({"role": "assistant", "content": answer})
        sessions.append({"case_id": case_id,
                         "browser_session_id": f"browser-{i}", "turns": turns})
    return {"schema": probe.SCHEMA, "origin": "offline_fixture", "sessions": sessions}


class ThreeTurnHoldoutContract(unittest.TestCase):
    def test_complete_ru_es_correction_and_calibration_trace_never_claims_native(self):
        result = probe.verify_capture(fixture())
        self.assertEqual(result["turns"], 12)
        self.assertEqual(result["cases"], 4)
        self.assertEqual(result["trace_structure"], "PASS")
        self.assertEqual(result["quality_grade"], "NOT_MEASURED")
        self.assertEqual(result["native_acceptance"], probe.HOLD)

    def test_second_turn_context_loss_is_hold(self):
        example = fixture()
        example["sessions"][0]["turns"][1]["messages"] = [
            example["sessions"][0]["turns"][1]["messages"][-1]
        ]
        with self.assertRaisesRegex(probe.CaptureHold,
                                    "HOLD_B2_HISTORY_LOST_OR_TRUNCATED"):
            probe.verify_capture(example)

    def test_third_turn_replayed_stream_and_missing_done_are_holds(self):
        example = fixture()
        example["sessions"][1]["turns"][2]["stream_id"] = (
            example["sessions"][0]["turns"][0]["stream_id"]
        )
        with self.assertRaisesRegex(probe.CaptureHold, "HOLD_B2_SSE_STREAM_ID"):
            probe.verify_capture(example)
        example = fixture()
        example["sessions"][1]["turns"][2]["sse_done"] = False
        with self.assertRaisesRegex(probe.CaptureHold, "HOLD_B2_SSE_INCOMPLETE"):
            probe.verify_capture(example)

    def test_cross_language_locale_and_independent_s03_ids(self):
        example = fixture()
        example["sessions"][3]["turns"][2]["requested_locale"] = "es"
        with self.assertRaisesRegex(probe.CaptureHold, "HOLD_B2_LOCALE_REQUEST"):
            probe.verify_capture(example)
        example = fixture()
        example["sessions"][2]["turns"][2]["s03_record_id"] = (
            example["sessions"][0]["turns"][1]["s03_record_id"]
        )
        with self.assertRaisesRegex(probe.CaptureHold, "HOLD_B2_S03_RECORD_ID"):
            probe.verify_capture(example)

    def test_unverified_native_origin_cannot_fake_verified_provenance(self):
        example = fixture()
        example["origin"] = "native_browser"
        with self.assertRaisesRegex(probe.CaptureHold,
                                    "HOLD_B2_NATIVE_PROVENANCE_MISSING"):
            probe.verify_capture(example)
        for name in ("installed_sha256", "served_sha256", "browser_capture_sha256"):
            example[name] = "a" * 64
        self.assertEqual(probe.verify_capture(example)["native_acceptance"], probe.HOLD)


if __name__ == "__main__":
    unittest.main()
