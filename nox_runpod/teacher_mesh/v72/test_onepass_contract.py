"""Compile and contract tests for V72 ONEPASS. No GPU or network required."""
from __future__ import annotations

import ast
import unittest

from nox_runpod.teacher_mesh.v72 import onepass_live as run

class OnePassContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        start="python3 - <<'PYREMOTE'\n"
        command=run.REMOTE.lstrip("\n")
        assert command.startswith("set -euo pipefail\n"+start)
        assert command.rstrip().endswith("PYREMOTE")
        cls.body=command.split(start,1)[1].rsplit("\nPYREMOTE",1)[0]
        cls.ast=ast.parse(cls.body)

    def test_embedded_python_syntax(self):
        self.assertTrue(self.ast.body)

    def test_one_remote_apply_only_with_existing_vast_key(self):
        src=ast.unparse(ast.parse(run.__loader__.get_source(run.__name__)))
        self.assertIn("NOX2",src)
        self.assertIn("live_direct_route",src)
        self.assertIn("attach_temporary_key",src)
        self.assertIn("temp_ssh_key_revoked",src)

    def test_no_host_reboot_or_process_terminate(self):
        source=self.body
        for bad in ("os.kill(","systemctl stop","supervisorctl stop",
                    "os.unlink(","shutil.rmtree(","subprocess.Popen(",
                    "rm -rf","apt-get","pip install","huggingface_hub",
                    "force_download","DROP TABLE","CREATE DATABASE"):
            self.assertNotIn(bad,source)

    def test_preserves_canonical_s03_and_no_model_switch(self):
        t=self.body
        self.assertIn("sqlite3.connect(':memory:')",t)
        self.assertIn("src.backup(dst",t)
        self.assertIn("PRAGMA quick_check",t)
        self.assertIn('"active_student_switched":False',t)
        self.assertIn('"checkpoint_changed":False',t)
        self.assertIn('"onehost_scheduler_replaced":False',t)

    def test_priority_is_only_allowlisted_existing_pids(self):
        t=self.body
        self.assertIn("chat_proxy.py",t)
        self.assertIn("llama-server",t)
        self.assertIn("os.getpriority(os.PRIO_PROCESS,pid)",t)
        self.assertIn("os.setpriority(os.PRIO_PROCESS,pid,target)",t)
        self.assertIn("os.setpriority(os.PRIO_PROCESS,pids[label],orig[label])",t)

    def test_native_receipt_reports_non_activation_honestly(self):
        self.assertIn('"native_oneprime_bound":False',self.body)
        self.assertIn('"authenticated_end_to_end_tested":False',self.body)
        self.assertIn('"new_optimizer_steps_verified":False',self.body)
        self.assertIn("HOLD_CONTAINER_CAP_SYS_NICE",self.body)

if __name__=="__main__":
    unittest.main()
