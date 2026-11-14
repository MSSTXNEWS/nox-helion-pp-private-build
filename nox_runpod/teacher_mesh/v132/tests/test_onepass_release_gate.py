"""NOX ONEPASS V132: source snapshot and independent release proof tests."""
from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path

from nox_runpod.teacher_mesh.v132 import onepass_release_gate as gate

class OnepassV132Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=gate.source_report(Path("."))
        cls.manifest=json.loads(gate.MATRIX.read_text(encoding="utf8"))

    def test_original_frozen_route_count_and_host_boundaries(self):
        m=self.source["web_baseline"]
        self.assertEqual(m["expected_exact_paths"],92)
        self.assertEqual(m["last_observed_exact_registered"],23)
        self.assertEqual(m["last_observed_unmapped"],69)
        self.assertEqual(m["frozen_zip_sha256"],gate.FROZEN_SHA)
        self.assertEqual(sum(m["last_observed_host_partition"].values()),92)
        self.assertEqual(m["last_observed_host_partition"][gate.OWNER_PC],16)
        self.assertEqual(m["last_observed_host_partition"][gate.EXTERNAL],12)
        self.assertFalse(m["current_runtime_recounted_by_this_job"])
        self.assertEqual(self.source['live_runtime']['state'],'HOLD_NOX2_AUTH_ERROR')
        self.assertTrue(self.source['live_runtime']['instance_existence_not_inferred_from_404'])

    def test_real_source_files_hashed_without_embedded_credentials(self):
        self.assertEqual(len(self.source["sources_sha256"]),len(gate.REQUIRED_SOURCE))
        self.assertTrue(all(gate._valid_hash(v) for v in self.source["sources_sha256"].values()))
        self.assertEqual(self.source["v130"]["state"],"SOURCE_STAGED_NOT_LIVE_VERIFIED")
        self.assertFalse(self.source["v130"]["real_s03_mutated_by_this_gate"])
        self.assertFalse(self.source["safety"]["no_new_server"] is False)

    def test_no_falsely_advertised_gpu_or_windows_release(self):
        report=self.source
        self.assertEqual(report["release"]["state"],"HOLD_REQUIRED_LIVE_ACCEPTANCE")
        self.assertFalse(report["release"]["full_parameter_optimizer_steps_verified"])
        self.assertFalse(report["release"]["windows_pc_physical_restore_proven"])
        self.assertFalse(report["release"]["checkpoint_external_restore_proven"])
        self.assertFalse(report["release"]["full_92_route_functional_e2e"])

    def test_native_no_access_holds_instead_of_starting_server(self):
        decision=gate.admission(self.source,{})
        self.assertEqual(decision["state"],"HOLD")
        self.assertIn("HOLD_OWNER_AUTH_OR_API",decision["reasons"])
        self.assertFalse(decision["performed"])

    def test_owner_approval_required_with_all_other_evidence(self):
        names=("owner_access_is_verified","same_instance_60509551","existing_proxy_and_model_healthy",
               "original_s03_quick_check","owner_stop_inactive","source_sha_pins_current",
               "no_active_model_generation","source_ci_passed","code_backup_rollback_available",
               "manual_owner_install_approved")
        checks={key:True for key in names}
        checks["manual_owner_install_approved"]=False
        held=gate.admission(self.source,checks)
        self.assertEqual(held["state"],"HOLD")
        self.assertIn("HOLD_EXPLICIT_OWNER_GATE",held["reasons"])
        checks["manual_owner_install_approved"]=True
        ready=gate.admission(self.source,checks)
        self.assertEqual(ready["state"],"READY_FOR_ONE_NATIVE_INSTALL")
        self.assertFalse(ready["performed"])

    def test_missing_unverified_dependent_stages_remain_hold(self):
        res=gate.release_acceptance(v132=self.source,web_routes=None,training=None,windows=None)
        self.assertEqual(res["state"],"HOLD")
        self.assertEqual(len(res["reasons"]),3)
        self.assertFalse(res["production_promoted"])

    def test_all_evidence_still_requires_owner_review_not_fake_promote(self):
        web={"expected":92,"functional_e2e_verified_count":92,"signed_owner_native_e2e":True}
        train={key:True for key in ("full_parameter_no_adapter_verified","optimizer_delta_verified",
          "candidate_checkpoint_sha_verified","checkpoint_reload_verified",
          "independent_holdout_passed","offsite_checkpoint_restore_verified",
          "s03_external_restore_verified","native_stop_verified")}
        windows={key:True for key in ("real_owner_pc_file_sha_verified",
          "owner_key_decryption_proven","complete_restore_replay_verified",
          "installer_no_loss_windows_accepted")}
        result=gate.release_acceptance(v132=self.source,web_routes=web,training=train,windows=windows)
        self.assertEqual(result["state"],"READY_FOR_OWNER_RELEASE_REVIEW")
        self.assertFalse(result["production_promoted"])

    def test_changed_web_baseline_fails_closed(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            for f in gate.REQUIRED_SOURCE:
                p=root/f
                p.parent.mkdir(parents=True,exist_ok=True)
                p.write_bytes((Path(".")/f).read_bytes())
            m=root/gate.MATRIX
            m.parent.mkdir(parents=True,exist_ok=True)
            doc=json.loads(json.dumps(self.manifest))
            doc["functions"].pop()
            m.write_text(json.dumps(doc),encoding="utf8")
            with self.assertRaisesRegex(ValueError,"HOLD_92_ROUTE_MATRIX"):
                gate.source_report(root)

    def test_auth_only_cannot_authorize_release(self):
        observed={"owner_access_is_verified":True,"manual_owner_install_approved":True}
        self.assertEqual(gate.admission(self.source,observed)["state"],"HOLD")

if __name__=="__main__":
    unittest.main()
