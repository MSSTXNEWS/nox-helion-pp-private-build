import json
import unittest
from pathlib import Path

P = Path(__file__).resolve().parents[1]/"catalog_acquisition_final_20261112.json"

class CatalogReconciliationTests(unittest.TestCase):
    def test_consistent_200_without_fictional_installs(self):
        d=json.loads(P.read_text(encoding="utf-8"))
        self.assertEqual(d["outcome"]["unique_catalog_entries"],200)
        self.assertEqual(len(d["entries"]),200)
        self.assertEqual({x["number"] for x in d["entries"]},set(range(1,201)))
        self.assertEqual(sum(x["status"] != "SERVICE_REFERENCE_VERIFIED_NOT_INSTALLABLE" for x in d["entries"]),199)
        self.assertEqual(d["outcome"]["verified_source_artifacts"],199)
        self.assertEqual(d["outcome"]["verified_service_reference"],1)
        self.assertEqual(d["outcome"]["installed_engine_count"],"UNKNOWN")
        self.assertEqual(d["outcome"]["live_nox_acceptance"],"HOLD")
    def test_old_failures_reconciled_but_old_receipt_preserved(self):
        d=json.loads(P.read_text(encoding="utf-8"))
        self.assertEqual(d["base_report"]["downloaded_verified"],182)
        self.assertEqual(d["base_report"]["failed"],18)
        recovered=set(d["recovery_runs"]["alternative_sources"]["numbers"])
        completion=set(d["recovery_runs"]["completion"]["numbers"])
        self.assertEqual(recovered|completion,{6,10,20,25,32,33,34,46,59,70,74,77,78,105,108,110,111,115})
        self.assertEqual(len(recovered|completion),18)
        self.assertEqual([x["number"] for x in d["entries"] if x["status"]=="SERVICE_REFERENCE_VERIFIED_NOT_INSTALLABLE"],[6])
        self.assertTrue(all(x["evidence"].startswith("https://") for x in d["entries"]))
