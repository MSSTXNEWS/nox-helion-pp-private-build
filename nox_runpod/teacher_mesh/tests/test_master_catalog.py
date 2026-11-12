#!/usr/bin/env python3
"""Verify immutable catalog shape and non-destructive download policy."""
import json
from pathlib import Path
from urllib.parse import urlsplit
import unittest
ROOT=Path(__file__).resolve().parent.parent

class MasterCatalogTests(unittest.TestCase):
    def test_exact_100_unique_engines(self):
        catalog=json.loads((ROOT/"NOX_MASTER_CATALOG_100.json").read_text())
        self.assertEqual(catalog["schema"],"nox-helion-master-tools-100-v1")
        rows=catalog["entries"]
        self.assertEqual(len(rows),100)
        self.assertEqual([r["number"] for r in rows],list(range(1,101)))
        norm=lambda url:url.rstrip("/").removesuffix(".git").lower()
        self.assertEqual(len({norm(r["url"]) for r in rows}),100)
        self.assertTrue(all(urlsplit(r["url"]).scheme=="https" for r in rows))
        self.assertTrue(all(r["state"]=="CANDIDATE_NOT_INSTALLED" for r in rows))
        self.assertEqual(len(catalog["teachers"]),15)
        self.assertEqual(len(catalog["worms"]),20)
        self.assertFalse(catalog["policy"]["no_auto_install"] is False)
    def test_documentation_has_all_components(self):
        catalog=json.loads((ROOT/"NOX_MASTER_CATALOG_100.json").read_text())
        md=(ROOT/"NOX_MASTER_CATALOG_100.md").read_text()
        for r in catalog["entries"]:
            self.assertIn(r["url"],md)
        for teacher in catalog["teachers"]:
            self.assertIn(teacher["url"],md)
        self.assertIn("WormAutopilot",md)
        self.assertIn("WormSwarm",md)
        self.assertIn("STOP",md)
    def test_only_one_canonical_memory(self):
        catalog=json.loads((ROOT/"NOX_MASTER_CATALOG_100.json").read_text())
        self.assertEqual(catalog["policy"]["one_memory"],"S03")
        self.assertEqual(catalog["policy"]["one_identity"],"NOX")
        self.assertTrue(catalog["policy"]["stop_fail_closed"])
        self.assertTrue(catalog["policy"]["do_not_restart_live_training"])

if __name__=="__main__":
    unittest.main()
