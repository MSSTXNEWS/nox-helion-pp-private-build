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


    def test_reference_numbers_and_confident_guess_are_review_flags_not_pass(self):
        example = fixture()
        def set_answer(case_index, turn_index, answer):
            turn = example["sessions"][case_index]["turns"][turn_index]
            turn["answer"] = answer
            turn["sse_deltas"] = [answer]
            # Preserve the full assistant history required by later turns.
            for later in example["sessions"][case_index]["turns"][turn_index + 1:]:
                messages = later["messages"]
                messages[2 * turn_index + 1]["content"] = answer
        set_answer(0, 1, "Это 28 евро.")
        set_answer(1, 2, "Son 36 euros.")
        set_answer(2, 0, "Точно 42.")
        set_answer(3, 2, "Я не знаю: лист не показан.")
        result = probe.verify_capture(example)
        signals = {(r["case_id"], r["turn"]): r["signal"]
                   for r in result["quality_review_signals"]}
        self.assertEqual(len(signals), 12)
        self.assertEqual(signals[("RU_CORRECTION", 2)], "EXPECTED_NUMBER_ABSENT")
        self.assertEqual(signals[("ES_CORRECTION", 3)],
                         "REFERENCE_NUMBER_MENTIONED_REVIEW_REQUIRED")
        self.assertEqual(signals[("RU_CALIBRATION", 1)],
                         "UNSUPPORTED_EXACT_NUMBER_MENTION")
        self.assertEqual(signals[("ES_CALIBRATION", 3)],
                         "ABSTENTION_CUE_MENTIONED_REVIEW_REQUIRED")
        self.assertEqual(result["quality_grade"], "NOT_MEASURED")
        self.assertEqual(result["native_acceptance"], probe.HOLD)

    def test_ambiguous_correct_and_stale_numbers_never_auto_pass(self):
        example = fixture()
        turn = example["sessions"][0]["turns"][2]
        turn["answer"] = "Не 28, а 21 евро."
        turn["sse_deltas"] = [turn["answer"]]
        result = probe.verify_capture(example)
        self.assertEqual(result["quality_review_signals"][2]["signal"],
                         "AMBIGUOUS_NUMERIC_ANSWER")
        self.assertEqual(result["native_acceptance"], probe.HOLD)



    def test_cli_rejects_oversize_actual_bytes_even_if_stat_said_small(self):
        # Reproduce a time-of-check/time-of-use change of the captured file.
        # Old CLI trusts Path.stat() and reports a false structural PASS.
        import contextlib
        import io
        import json
        import tempfile
        from types import SimpleNamespace
        from unittest import mock

        oversized = fixture()
        oversized["padding"] = "x" * probe.MAX_CAPTURE_BYTES
        with tempfile.TemporaryDirectory() as folder:
            capture_path = Path(folder) / "ru_es_capture.json"
            capture_path.write_text(json.dumps(oversized, ensure_ascii=False),
                                    encoding="utf-8")
            output = io.StringIO()
            # Simulates a tiny preflight stat before a larger file is read.
            with mock.patch.object(Path, "stat",
                                   return_value=SimpleNamespace(st_size=128)):
                with contextlib.redirect_stdout(output):
                    status = probe.main(["b2_ru_es_3turn_holdout.py",
                                         str(capture_path)])
            self.assertEqual(status, 2)
            self.assertEqual(json.loads(output.getvalue())["reason"],
                             "HOLD_B2_CAPTURE_OVERSIZE")

    def test_cli_bounded_read_keeps_complete_ru_es_unicode_evidence(self):
        import contextlib
        import io
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as folder:
            capture_path = Path(folder) / "ru_es_unicode.json"
            capture_path.write_text(json.dumps(fixture(), ensure_ascii=False),
                                    encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                status = probe.main(["b2_ru_es_3turn_holdout.py",
                                     str(capture_path)])
            result = json.loads(output.getvalue())
            self.assertEqual(status, 0)
            self.assertEqual(result["trace_structure"], "PASS")
            self.assertEqual(result["quality_grade"], "NOT_MEASURED")
            self.assertEqual(result["native_acceptance"], probe.HOLD)


if __name__ == "__main__":
    unittest.main()
