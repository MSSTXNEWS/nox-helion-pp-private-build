"""C34-derived source-only anti-regression learning for the active E07 pipeline.
This validates QA process; never assert physical installed EXE or model training.
"""
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]
CURRENT=ROOT/".github/workflows/nox-express-independent-e07-current-d02.yml"
LEGACY=(
 ".github/workflows/nox-express-independent-e07-candidate.yml",
 ".github/workflows/nox-express-independent-e07-nav-a2.yml",
 ".github/workflows/nox-f842-fast-visual.yml",
)
class C34FeedbackFastpath(unittest.TestCase):
 def test_knowledge_is_scoped_and_evidence_bound(self):
  lessons=json.loads((ROOT/"coordination/e07/c34_feedback_rules.json").read_text(encoding="utf-8"))
  self.assertEqual(lessons["schema"],"NOX-EXPRESS-C34-LEARNING-v1")
  self.assertFalse(lessons["release_accepted"])
  self.assertEqual(lessons["instructions_version"],"0.0.6")
  rules=lessons["rules"]
  self.assertEqual(len(rules),len({r["id"] for r in rules}))
  self.assertGreaterEqual(len(rules),6)
  for r in rules:
   self.assertTrue(all(r.get(k) for k in ("symptom","cause","action","prevention","evidence")))
   self.assertTrue(r["evidence"].startswith("https://github.com/MSSTXNEWS/"))
 def test_historical_sha_pins_remain_manual_repro_only(self):
  for relative in LEGACY:
   with self.subTest(path=relative):
    source=(ROOT/relative).read_text(encoding="utf-8")
    header=source.split("\npermissions:",1)[0]
    self.assertIn("  workflow_dispatch:",header)
    self.assertNotIn("  push:",header)
    self.assertIn("NOT RELEASE" if relative.endswith("visual.yml") else "independent E07",source)
 def test_current_sha_has_one_live_fast_fail_gate(self):
  source=CURRENT.read_text(encoding="utf-8")
  header=source.split("\npermissions:",1)[0]
  self.assertIn("  push:",header)
  self.assertIn("  workflow_dispatch:",header)
  for item in ("coordination/e07/probe_final_same_setup.py",
               "tests/e07/test_final_primary_dispatch_u18.py",
               "tests/e07/test_c34_feedback_fastpath_u24.py",
               "coordination/e07/c34_feedback_rules.json"):
   self.assertIn("      - "+item,header)
  front=source.index("      - name: Fast source regression gate before heavy artifacts")
  heavy=source.index("      - name: Download immutable candidate",front)
  section=source[front:heavy]
  calls=section.splitlines()
  for i,line in enumerate(calls):
   if "python -B -m unittest discover" in line or "python -B -m py_compile " in line or 'python -B -c "' in line:
    self.assertLess(i+1,len(calls))
    self.assertIn("if ($LASTEXITCODE -ne 0)",calls[i+1],
                  "uncaught CI exit after: "+line.strip())
  self.assertIn("E07_C34_RECURRING_FAILURE_PREVENTION_HOLD",section)
 def test_observations_cannot_grant_physical_release(self):
  independent=(ROOT/"coordination/e07/independent_setup_e07.py").read_text(encoding="utf-8")
  physical=(ROOT/"coordination/e07/probe_final_same_setup.py").read_text(encoding="utf-8")
  self.assertIn('item.get("permissions_verified") == "PASS"',independent)
  self.assertIn('item.get("function_verified") == "PASS"',independent)
  self.assertIn('visual.get("reduced_motion") == "PASS"',independent)
  self.assertIn('"reduced_motion":"HOLD"',physical)
  self.assertIn('"webview2_media_query":',physical)
  self.assertIn("OBSERVED_NOT_RELEASE",independent)

if __name__=="__main__":
 unittest.main()
