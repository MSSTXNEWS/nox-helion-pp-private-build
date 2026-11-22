import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from alive.bench import build_report
from alive.gate import ALL_ALIVE_IDS, CRITICAL_ALIVE_IDS, gate_alive


class TestAliveReport(unittest.TestCase):
    def _results(self, failed=()):
        return {
            case_id: {"pass": case_id not in failed, "score": 1.0, "evidence": ["RULE_PASS"]}
            for case_id in ALL_ALIVE_IDS
        }

    def test_report_is_complete_hashed_and_gate_compatible(self):
        report = build_report(self._results(), run_id="shadow-1", mode="shadow", created_at=100)
        self.assertEqual(report["overall"], 1.0)
        self.assertEqual(report["sha256"], build_report(self._results(), run_id="shadow-1", mode="shadow", created_at=100)["sha256"])
        self.assertTrue(gate_alive(report)["ok"])

    def test_critical_case_failure_is_recorded(self):
        report = build_report(self._results(failed=("AL-08",)), run_id="shadow-2", mode="shadow", created_at=100)
        self.assertEqual(report["critical_failures"], ["AL-08"])
        self.assertFalse(gate_alive(report)["ok"])

    def test_missing_or_bool_scores_fail_closed(self):
        results = self._results()
        del results["AL-08"]
        results["AL-01"]["score"] = True
        report = build_report(results, run_id="shadow-3", mode="shadow", created_at=100)
        self.assertIn("AL-08", report["missing"])
        self.assertIn("AL-01", report["missing"])
        self.assertTrue(set(("AL-01", "AL-08")).issubset(report["critical_failures"]))

    def test_evidence_ids_cannot_smuggle_free_text(self):
        results = self._results()
        results["AL-02"]["evidence"] = ["private text"]
        report = build_report(results, run_id="shadow-4", mode="shadow", created_at=100)
        self.assertIn("AL-02", report["missing"])

    def test_run_id_and_mode_are_validated(self):
        with self.assertRaises(ValueError):
            build_report(self._results(), run_id="creator@email", mode="shadow")
        with self.assertRaises(ValueError):
            build_report(self._results(), run_id="shadow-5", mode="production")


if __name__ == "__main__":
    unittest.main()
