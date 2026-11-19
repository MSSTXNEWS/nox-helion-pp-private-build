"""Offline checks for bounded one-shot live chat smoke, no network/processes."""
import ast
from pathlib import Path
import unittest
import owner_native_operator as operator

ROOT=Path(__file__).parent


def embedded_source():
    raw=(ROOT/'owner_live_stream_smoke_oneshot.py').read_text()
    outer=ast.parse(raw)
    expr=next(node.value for node in outer.body
        if isinstance(node,ast.Assign) and
        any(isinstance(target,ast.Name) and target.id=='SOURCE' for target in node.targets))
    source=ast.literal_eval(expr)
    return raw,source,ast.parse(source)


class DirectStreamSmokeTests(unittest.TestCase):
    def test_syntax_and_one_owner_authenticated_live_post_only(self):
        outer,inner,tree=embedded_source()
        self.assertIn('"/api/nox/chat/stream"',inner)
        self.assertIn('"/chat/login"',inner)
        self.assertIn('"/api/ui/memory/dialogs/history?dialog_id="',inner)
        self.assertIn('"HOLD_LIVE_SMOKE_STOP"',inner)
        self.assertIn('"HOLD_LIVE_SMOKE_MEMORY"',inner)
        self.assertIn('"HOLD_LIVE_SMOKE_MODEL_BUSY"',inner)
        self.assertIn('"canonical_s03_write_verified"',inner)
        self.assertIn("=False  # not proven by owner-dialog history",inner)
        self.assertIn('"model_claimed_s03_integrated_unverified"',inner)
        self.assertIn('"canonical_s03_integration_accepted"',inner)
        self.assertIn('"s03_integration_status"',inner)
        self.assertIn('"UNVERIFIED"',inner)
        self.assertNotIn('"done_claims_s03_integrated"',inner)
        self.assertIn('LIVE_STREAM_OWNER_DIALOG_VERIFIED',inner)
        self.assertNotIn('LIVE_SMOKE_S03_VERIFIED',inner)
        self.assertEqual(sum(isinstance(n,ast.FunctionDef) and n.name=='main'
                             for n in tree.body),1)

    def test_chat_proxy_pin_matches_fresh_owner_attestation(self):
        _, inner, _ = embedded_source()
        self.assertIn('pin="9fedaefbe39f4cac8a47d77bb0dada2ccf09c43ec38a5624869d3a00c0fbe5a3"', inner)
        self.assertNotIn('cc1437ce8c3bfbbc4259ffdbe299bf3b8721d4b1bb09c88565ccb6cb9fdb95eb', inner)

    def test_cold_file_cache_profile_preserves_boundaries_and_oom_psi_gates(self):
        _, inner, _ = embedded_source()
        self.assertIn('free>=512*1024**2 and cold>=4*1024**3', inner)
        self.assertIn('free>=256*1024**2 and cold>=12*1024**3', inner)
        self.assertIn('if not (normal or cold_cache_profile):', inner)
        self.assertIn('HOLD_LIVE_SMOKE_OOM', inner)
        self.assertIn('HOLD_LIVE_SMOKE_PRESSURE', inner)
        self.assertIn('HOLD_LIVE_SMOKE_MODEL_BUSY', inner)
        self.assertIn('COLD_CACHE_256M_12G', inner)
        self.assertNotIn('memory.reclaim', inner)
        self.assertNotIn('drop_caches', inner)
        self.assertNotIn('supervisorctl restart', inner)

    def test_existing_model_route_and_no_server_mutations(self):
        _,inner,_=embedded_source()
        self.assertIn('"/root/nox/venv/bin/python"', (ROOT/'owner_live_stream_smoke_oneshot.py').read_text())
        self.assertNotIn('supervisorctl restart',inner)
        self.assertNotIn('os.kill(',inner)
        self.assertNotIn('drop_caches',inner)
        self.assertNotIn('memory.reclaim',inner)
        self.assertNotIn('shutil.rmtree(',inner)
        self.assertNotIn('pip install',inner)
        self.assertNotIn('playwright install',inner)
        self.assertNotIn('NOX_MAINT_REPAIR_COMPLETE=true',inner)

    def test_one_shot_owner_operator_exact_route_only(self):
        self.assertEqual(operator.FILES['repair'],'nox-control/owner_live_stream_smoke_oneshot.py')
        self.assertEqual(operator.repair_bundle_paths('repair',
            operator.FILES['repair'],('nox-control/unrelated_file.py',)),())
        self.assertNotEqual(operator.FILES['repair'],operator.FILES['browser_qa'])


if __name__=='__main__':
    unittest.main()
