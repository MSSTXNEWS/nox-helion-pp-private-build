"""Offline owner-command scope and exact pinned-source safety for NOX six-lane repair."""
from __future__ import annotations
import ast
import hashlib
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).parent

def module(name):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + ".py"))
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded

class ReviewedRepairTests(unittest.TestCase):
    def test_exact_native_preimages_bind_live_owner_inspect(self):
        entry = module("owner_sixlane_memory_repair_entry")
        self.assertEqual(entry.OLD[entry.CONFIG],
            "92fba9eb3bf76c8e06de37e4d57877d9ea754f577cdea49d8ec80bb85dcd774d")
        self.assertEqual(entry.OLD[entry.REFILL],
            "06bb8ec21607f09a5703e3f1b7d8694bbc120485e80c14058128902c6d9959ba")
        self.assertEqual(entry.CURRENT_DIRECTOR_SHA,
            "eac3ce9e2d8c862d1a7917ec447ea72e84454b7775a4260ad1e72e59de96fe11")
        self.assertEqual(entry.ROOT.as_posix(), "/root/nox")

    def test_operator_selects_only_current_repair_and_two_reviewed_assets(self):
        operator = module("owner_native_operator")
        entry = "nox-control/owner_sixlane_memory_repair_entry.py"
        self.assertEqual(operator.FILES["repair"], entry)
        paths = operator.repair_bundle_paths("repair", entry, ())
        self.assertEqual(paths, (
            "nox-control/systemic_relay_20261118/runtime/owner_systemic_refill.py",
            "nox-control/continuous_executor_20261118/assets/continuous_transaction_helpers.py"))
        self.assertEqual({Path(path).name for path in paths},
                         {"owner_systemic_refill.py","continuous_transaction_helpers.py"})
        self.assertEqual(operator.FILES["inspect"], "nox-control/owner_native_inspect.py")

    def test_bundle_helper_sha_is_frozen_and_all_python_compiles(self):
        entry = module("owner_sixlane_memory_repair_entry")
        helper = ROOT / "nox-control/continuous_executor_20261118/assets/continuous_transaction_helpers.py"
        self.assertEqual(hashlib.sha256(helper.read_bytes()).hexdigest(),
                         entry.HELPER_SHA)
        script = ROOT / "nox-control/systemic_relay_20261118/runtime/owner_systemic_refill.py"
        source = script.read_text()
        tree = ast.parse(source)
        funcs = {f.name for f in tree.body if isinstance(f, ast.FunctionDef)}
        self.assertTrue({"memory_governor_projection","_reflex_cycle","select_next"} <= funcs)
        self.assertIn("INSPECT_UNREPRESENTED_ORIGINAL", source)
        self.assertIn("reclaimable_estimate_is_not_a_guaranteed_allocation",source)
        compile(source, str(script), "exec")

    def test_no_arbitrary_service_or_model_mutation_in_installer_scope(self):
        entry = (HERE / "owner_sixlane_memory_repair_entry.py").read_text()
        self.assertIn("queue_before, active = h.queue_idle(ROOT)", entry)
        self.assertIn("require(not active, 'ACTIVE_QUEUE_CLAIM')", entry)
        self.assertIn("h.stop_checked()", entry)
        self.assertIn("h.start_checked(ROOT, require_native_status=True)", entry)
        self.assertIn("require(h.stop_clear(ROOT)", entry)
        for operation in ("os.system(", "shell=True", "nox-ds41-8098', 'stop'",
                          "drop_caches", "memory.reclaim", "shutil.rmtree",
                          "nox_proxy restart", "os.kill("):
            self.assertNotIn(operation, entry)
        self.assertIn("original_295_accepted':0", entry)

if __name__ == "__main__":
    unittest.main()
