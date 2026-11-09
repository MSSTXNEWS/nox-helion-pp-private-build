"""No network, no model simulation: tests real temporary transcript bytes."""
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import datetime, timezone
import json
import unittest
from nox_prime_experience_v1 import project


def turn(root, role, content, persona=None, time="2026-11-07T14:00:00Z"):
    path = Path(root)/"brain"/"history"/"unified_chat_v1.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {"role": role, "content": content, "time": time}
    if persona:
        record["persona_id"] = persona
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


class ExperienceTest(unittest.TestCase):
    def test_source_grounding_with_timestamps(self):
        with TemporaryDirectory() as root:
            turn(root, "user", "NOX PowerShell failed because a quote was missing")
            turn(root, "assistant", "We fixed the quote in bootstrap")
            old = (Path(root)/"brain"/"history"/"unified_chat_v1.jsonl").read_bytes()
            result = project(root, "PowerShell quote", datetime(2026, 11, 7, tzinfo=timezone.utc))
            self.assertEqual(result["count"], 1)
            self.assertIn("PowerShell", result["episodes"][0]["user_excerpt"])
            self.assertFalse(result["episodes"][0]["verified"])
            self.assertFalse(result["s03_written"])
            self.assertEqual(old, (Path(root)/"brain"/"history"/"unified_chat_v1.jsonl").read_bytes())

    def test_never_leak_private_persona(self):
        with TemporaryDirectory() as root:
            turn(root, "user", "private KV data", persona="KV")
            turn(root, "assistant", "secret KV response", persona="KV")
            self.assertEqual(project(root, "private")["count"], 0)

    def test_no_doubled_evidence(self):
        with TemporaryDirectory() as root:
            for _ in range(2):
                turn(root, "user", "repeat message")
                turn(root, "assistant", "same answer")
            self.assertEqual(project(root)["count"], 1)

    def test_shared_term_graph_is_not_claimed_knowledge(self):
        with TemporaryDirectory() as root:
            turn(root, "user", "Memory graph has bug", time="2026-11-06T09:00:00Z")
            turn(root, "assistant", "We will test graph", time="2026-11-06T09:00:00Z")
            turn(root, "user", "Graph performance check", time="2026-11-07T09:00:00Z")
            turn(root, "assistant", "Graph test needed", time="2026-11-07T09:00:00Z")
            data = project(root, "graph")
            self.assertEqual(data["count"], 2)
            self.assertTrue(any(e["term"] == "graph" and e["event_count"] == 2
                                for e in data["temporal_entities"]))
            self.assertEqual(data["temporal_entities"][0]["relation"], "SHARED_LEXICAL_TERM")

    def test_invalid_datetime_fails_closed(self):
        with TemporaryDirectory() as root:
            with self.assertRaises(ValueError):
                project(root, now=datetime(2026, 11, 7))


if __name__ == "__main__":
    unittest.main()
