import json
import queue
import unittest
from unittest.mock import Mock, patch

import qs6_core as core


def frame(delta=None, finish=None, timings=None, usage=None):
    payload = {"choices": [{"delta": delta or {}, "finish_reason": finish}]}
    if timings is not None:
        payload["timings"] = timings
    if usage is not None:
        payload["usage"] = usage
    return json.dumps(payload)


class StreamPhaseMetricsTest(unittest.TestCase):
    def run_frames(self, frames, *, max_sentences=None):
        meter, cache, conn = Mock(), Mock(), Mock()
        events, request = queue.Queue(), core.Req()
        with patch.object(core, "open_upstream", return_value=(conn, None)),                 patch.object(core, "iter_sse", return_value=iter(frames)),                 patch.object(core.time, "monotonic", side_effect=[10.0, 11.25, 13.75, 15.0]):
            core.pump(core.Cfg(), meter, cache, "deep", "http://127.0.0.1:8081",
                      {}, request, events, max_sentences)
        conn.close.assert_called()
        return list(events.queue), meter, cache

    def test_reports_visible_and_native_phase_times_separately(self):
        metrics = {"prompt_n": 915, "prompt_ms": 338_888, "cache_n": 80,
                   "predicted_n": 32, "predicted_ms": 27_120}
        events, meter, cache = self.run_frames([
            frame({"reasoning_content": "reasoning"}),
            frame({"content": "Ответ."}),
            frame(finish="stop", timings=metrics),
            "[DONE]",
        ])
        result = events[-1][2]
        self.assertEqual(events[0], ("deep", "delta", "Ответ."))
        self.assertEqual(result["ttft_s"], 3.75)
        self.assertEqual(result["first_generated_s"], 1.25)
        self.assertEqual(result["timings"]["prefill"]["tokens"], 915)
        self.assertAlmostEqual(result["timings"]["prefill"]["tokens_per_second"], 2.7)
        self.assertAlmostEqual(result["timings"]["decode"]["tokens_per_second"], 1.18)
        meter.record.assert_called_once_with("deep", 32, 27.12)
        cache.record.assert_called_once_with(80, 995)

    def test_usage_without_engine_timings_never_produces_measured_rate(self):
        events, meter, _ = self.run_frames([
            frame({"content": "Ответ"}),
            frame(finish="stop", usage={"completion_tokens": 5}),
            "[DONE]",
        ])
        self.assertEqual(events[-1][2]["tokens"], 5)
        self.assertEqual(events[-1][2]["timings"], {})
        meter.record.assert_not_called()

    def test_incomplete_stream_is_error_even_after_visible_text(self):
        for tail in ([], ["[DONE]"], [frame(finish="stop")]):
            with self.subTest(tail=tail):
                events, meter, cache = self.run_frames([frame({"content": "Часть"}), *tail])
                self.assertEqual(events[-1][1], "error")
                self.assertTrue(events[-1][2][1])
                meter.record.assert_not_called()
                cache.record.assert_not_called()

    def test_error_payload_cannot_become_success(self):
        events, meter, _ = self.run_frames([
            frame({"content": "Часть"}),
            json.dumps({"error": {"message": "busy"}}),
            "[DONE]",
        ])
        self.assertEqual(events[-1], ("deep", "error", ("busy", True, "Часть")))
        meter.record.assert_not_called()

    def test_reasoning_only_completion_is_not_a_visible_answer(self):
        events, meter, _ = self.run_frames([
            frame({"reasoning_content": "reasoning"}), frame(finish="stop"), "[DONE]"
        ])
        self.assertEqual(events[-1][1], "error")
        self.assertFalse(events[-1][2][1])
        meter.record.assert_not_called()

    def test_intentional_preview_limit_is_valid_without_upstream_terminal(self):
        events, meter, _ = self.run_frames([frame({"content": "Привет. Как помочь?"})], max_sentences=1)
        self.assertEqual(events[-1][1], "end")
        self.assertEqual(events[-1][2]["finish"], "nox_sentence_limit")
        meter.record.assert_not_called()


if __name__ == "__main__":
    unittest.main()
