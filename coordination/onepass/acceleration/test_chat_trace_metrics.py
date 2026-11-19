import json
import tempfile
import unittest
from pathlib import Path

import chat_trace_metrics as metrics


SHA = "a" * 64


def write_trace(lines):
    temporary = tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False)
    temporary.write("\n".join(json.dumps(row) for row in lines) + "\n")
    temporary.close()
    return Path(temporary.name)


def header():
    return {
        "schema": metrics.SCHEMA,
        "scenario_id": "owner-two-turn-v1",
        "route_id": "proxy-web-model-s03",
        "served_sha256": SHA,
        "capture_clock": "monotonic_ns",
    }


def sample(sample_id, base, ttft_ms=100, stream_ms=500, persist_ms=20):
    return [
        {"sample_id": sample_id, "event": "request_started", "monotonic_ns": base},
        {"sample_id": sample_id, "event": "first_token", "monotonic_ns": base + ttft_ms * 1_000_000},
        {"sample_id": sample_id, "event": "terminal_received", "monotonic_ns": base + stream_ms * 1_000_000},
        {"sample_id": sample_id, "event": "s03_readback_completed", "monotonic_ns": base + (stream_ms + persist_ms) * 1_000_000},
    ]


class ChatTraceMetricsTests(unittest.TestCase):
    def test_twenty_samples_produce_p50_p95_and_privacy_safe_summary(self):
        rows = [header()]
        for index in range(1, 21):
            rows.extend(sample(f"turn-{index}", index * 1_000_000_000, 100 + index))
        path = write_trace(rows)
        try:
            report = metrics.summarize(path)
        finally:
            path.unlink()
        self.assertEqual(report["sample_count"], 20)
        self.assertEqual(report["incomplete_sample_count"], 0)
        self.assertEqual(report["percentile_quality"], "20_PLUS_SAMPLES")
        self.assertEqual(report["metrics"]["ttft"]["p50_ms"], 110)
        self.assertEqual(report["metrics"]["ttft"]["p95_ms"], 119)
        self.assertFalse(report["live_request_sent_by_harness"])
        self.assertFalse(report["model_or_cache_touched_by_harness"])
        self.assertNotIn("turn-1", json.dumps(report))

    def test_incomplete_sample_is_counted_not_silently_discarded(self):
        rows = [header(), *sample("complete", 1_000_000_000),
                {"sample_id": "partial", "event": "request_started", "monotonic_ns": 5_000_000_000}]
        path = write_trace(rows)
        try:
            report = metrics.summarize(path)
        finally:
            path.unlink()
        self.assertEqual(report["sample_count"], 1)
        self.assertEqual(report["incomplete_sample_count"], 1)
        self.assertEqual(report["percentile_quality"], "DESCRIPTIVE_ONLY_LT_20_SAMPLES")

    def test_dialogue_payload_fields_are_rejected(self):
        rows = [header(), *sample("turn-1", 1_000_000_000)]
        rows[1]["content"] = "private dialogue"
        path = write_trace(rows)
        try:
            with self.assertRaisesRegex(ValueError, "only sample_id"):
                metrics.summarize(path)
        finally:
            path.unlink()

    def test_out_of_order_events_are_rejected(self):
        rows = [header(), *sample("turn-1", 1_000_000_000)]
        rows[2]["monotonic_ns"] = 999
        path = write_trace(rows)
        try:
            with self.assertRaisesRegex(ValueError, "out of order"):
                metrics.summarize(path)
        finally:
            path.unlink()

    def test_exact_served_sha_is_required(self):
        rows = [header(), *sample("turn-1", 1_000_000_000)]
        rows[0]["served_sha256"] = "unknown"
        path = write_trace(rows)
        try:
            with self.assertRaisesRegex(ValueError, "exact served_sha256"):
                metrics.summarize(path)
        finally:
            path.unlink()


if __name__ == "__main__":
    unittest.main()
