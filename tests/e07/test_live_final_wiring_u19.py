"""E07 source-only structural regression for live same-Setup physical proof.

This cannot substitute for Windows UIA or approve a release.
"""
from pathlib import Path
import ast
import unittest

ROOT=Path(__file__).resolve().parents[2]
E07=ROOT/"coordination/e07/independent_setup_e07.py"

class LiveEvidenceWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=E07.read_text(encoding="utf-8")
        cls.tree=ast.parse(cls.source)
        cls.funcs={x.name:x for x in cls.tree.body if isinstance(x,ast.FunctionDef)}

    def test_wpf_alive_probe_precedes_finally_termination(self):
        func=self.funcs["gui_hwnd"]
        self.assertIn("final_probe", [x.arg for x in func.args.kwonlyargs])
        body=ast.get_source_segment(self.source,func)
        self.assertIn("final_probe(handle)",body)
        self.assertIn('"final_physical_witness":final_witness',body)
        self.assertIn("proc.terminate()",body)
        self.assertLess(body.index("final_probe(handle)"),body.index("proc.terminate()"))

    def test_installed_lifecycle_runs_probe_before_update(self):
        body=ast.get_source_segment(self.source,self.funcs["lifecycle"])
        self.assertIn("probe_run(hwnd, install, local",body)
        self.assertIn("setup_sha=sha256(setup)",body)
        self.assertIn("final_probe=physical_final_probe",body)
        self.assertIn('"installed_final_physical"',body)
        self.assertLess(body.index("final_probe=physical_final_probe"),body.index('"/ROLLBACK"'))

    def test_final_gate_requires_original_witness(self):
        body=ast.get_source_segment(self.source,self.funcs["main"])
        self.assertIn('witness.get("status") == "PASS"',body)
        self.assertIn('witness.get("setup_sha256") == setup_sha',body)
        self.assertIn('witness.get("source_sha") == source_sha',body)
        self.assertLess(body.index("evaluate_final_acceptance("),body.index('result["release_accepted"] = True'))

if __name__=="__main__":
    unittest.main()
