import json
import unittest
from unittest.mock import patch

import owner_native_repair as target
import owner_native_operator as operator


MAIN = b"[supervisord]\n[include]\nfiles=/etc/supervisor/conf.d/*.conf\n"
HOLDER = (b"[program:nox-engram-cold-holder]\nautostart=true\npriority=500\n"
          b"command=/usr/bin/python3 -I -B /root/nox/ops/engram_cold_holder.py\n")
MODEL = b"[program:nox-ds41-8098]\nautostart=true\ncommand=/bin/bash /root/nox/ops/nox_boot_ds41_8098.sh\n"
DISPATCHER = b"[program:nox-dispatcher-t855u]\nautostart=false\ncommand=/bin/bash /root/nox/ops/dispatcher.sh\n"
SAFE = (b"#!/bin/bash\nSUP=/etc/supervisor/supervisord.conf\n"
        b"mkdir -p /etc/supervisor/conf.d\n"
        b'/usr/bin/supervisord --configuration "${SUP}" >> /var/log/supervisord.log 2>&1\n')


class ColdStartup(unittest.TestCase):
    def project(self, script=SAFE, dispatcher=DISPATCHER, model=MODEL, holder=HOLDER):
        files = {target.STARTUP: script, target.MAIN: MAIN, target.HOLDER: holder,
                 target.MODEL: model, target.DISPATCHER: dispatcher,
                 target.MODEL_GUARD: b"guard", target.MODEL_LAUNCHER: b"launcher",
                 target.HOLDER_SOURCE: b"holder"}
        with patch.object(target, "STARTUP_PINS", {k: target.sha(v) for k, v in files.items()}):
            return target.project(files.__getitem__)

    def test_model_and_holder_auto_with_dispatcher_genuinely_missing(self):
        r = self.project()
        self.assertTrue(r["literal_config_references_preserve_pinned_units"])
        self.assertTrue(r["holder_autostart_configured"])
        self.assertTrue(r["model_autostart_configured"])
        self.assertTrue(r["holder_precedes_model_by_priority"])
        self.assertIs(r["dispatcher_autostart_configured"], False)
        self.assertTrue(r["dispatcher_start_route_missing"])
        self.assertFalse(r["runtime_startup_verified"])

    def test_explicit_dispatcher_start_only_counts_as_reference(self):
        r = self.project(SAFE + b"/usr/bin/supervisorctl start nox-dispatcher-t855u\n")
        self.assertTrue(r["dispatcher_onstart_reference"])
        self.assertFalse(r["dispatcher_start_route_missing"])
        self.assertFalse(r["runtime_startup_verified"])

    def test_reports_autostart_separately_from_pinned_start_command(self):
        model = MODEL.replace(b"/bin/bash ", b"/usr/bin/env bash ")
        holder = HOLDER.replace(b"autostart=true", b"autostart=false")
        r = self.project(model=model, holder=holder)
        self.assertIs(r["model_autostart_configured"], True)
        self.assertIs(r["model_command_matches_expected"], False)
        self.assertFalse(r["model_start_route_pinned"])
        self.assertIs(r["holder_autostart_configured"], False)
        self.assertIs(r["holder_command_matches_expected"], True)
        self.assertFalse(r["holder_start_route_pinned"])
        self.assertFalse(r["holder_precedes_model_by_priority"])
        self.assertNotIn("/usr/bin/env", json.dumps(r))

    def test_matches_only_the_exact_owning_stanza_in_a_multi_unit_file(self):
        other = b"[program:unrelated]\nautostart=true\ncommand=/usr/bin/true\n"
        r = self.project(dispatcher=other + DISPATCHER)
        self.assertIs(r["dispatcher_autostart_configured"], False)
        self.assertTrue(r["dispatcher_start_route_missing"])
        for unverified in (other, DISPATCHER + DISPATCHER):
            r = self.project(dispatcher=unverified)
            self.assertIsNone(r["dispatcher_autostart_configured"])
            self.assertFalse(r["dispatcher_start_route_missing"])

    def test_root_startup_preserves_exact_main_template_but_not_changed_bytes(self):
        main = b"cat >/etc/supervisor/supervisord.conf <<'NOXCONF'\n"
        exact = self.project(SAFE + main + MAIN + b"NOXCONF\n")
        self.assertTrue(exact["literal_config_references_preserve_pinned_units"])
        self.assertEqual(exact["supervisor_config_write_risk_count"], 0)
        altered = self.project(SAFE + main + MAIN.replace(b"*.conf", b"other.conf") + b"NOXCONF\n")
        self.assertFalse(altered["literal_config_references_preserve_pinned_units"])
        self.assertEqual(altered["supervisor_config_write_risk_count"], 1)

    def test_literals_and_indirect_operations_are_hash_only(self):
        script = SAFE + (b"cp hidden-credential-source /etc/supervisor/conf.d/nox-t855u.conf\n"
                         b"source /hidden/private-helper\n")
        report = self.project(script)
        self.assertEqual(report["supervisor_config_write_risk_count"], 1)
        self.assertEqual(report["indirect_shell_reference_count"], 1)
        self.assertNotIn("hidden-credential-source", json.dumps(report))
        self.assertNotIn("/hidden/private-helper", json.dumps(report))
        self.assertFalse(report["literal_config_references_preserve_pinned_units"])

    def test_reassigned_config_alias_does_not_attest_exact_main(self):
        r = self.project(SAFE.replace(b"mkdir -p", b"SUP=/tmp/other.conf\nmkdir -p"))
        self.assertFalse(r["supervisor_launches_pinned_main_reference"])
        self.assertGreaterEqual(r["supervisor_reference_unclassified_count"], 1)

    def test_exec_marks_potential_unreachable_dispatcher_after_it(self):
        r = self.project(SAFE.replace(b"/usr/bin/supervisord", b"exec /usr/bin/supervisord")
                         + b"supervisorctl start nox-dispatcher-t855u\n")
        self.assertTrue(r["supervisor_exec_may_replace_onstart"])
        self.assertTrue(r["dispatcher_onstart_reference"])
        self.assertFalse(r["protected_configs_live_verified_after_new_pid1"])

    def test_collector_forbids_a_mixed_pid1_epoch(self):
        with patch.object(target, "generation", side_effect=[10, 11]), \
                patch.object(target, "read_pinned_root_file", side_effect=FileNotFoundError):
            with self.assertRaisesRegex(ValueError, "CHANGED_STARTUP_EPOCH"):
                target.collect()

    def test_collector_rejects_changed_bytes_after_first_read(self):
        path = target.STARTUP
        digest = target.sha(b"pinned")
        with patch.object(target, "generation", return_value=10), \
                patch.object(target, "STARTUP_PINS", {path: digest}), \
                patch.object(target, "read_pinned_root_file", side_effect=[b"pinned", b"changed"]):
            with self.assertRaisesRegex(ValueError, "CHANGED_STARTUP_EPOCH_OR_FILE"):
                target.collect()

    def test_reader_rejects_any_unlisted_path_before_io(self):
        with patch.object(target.os, "open") as opened:
            with self.assertRaisesRegex(ValueError, "PATH_NOT_ALLOWLISTED"):
                target.read_pinned_root_file("/etc/passwd")
            opened.assert_not_called()

    def test_operator_uses_exact_readonly_entry_without_assets(self):
        entry = "nox-control/owner_native_repair.py"
        self.assertEqual(operator.FILES["repair"], entry)
        self.assertEqual(operator.repair_bundle_paths("repair", entry, ("unused.py",)), ())


if __name__ == "__main__":
    unittest.main()
