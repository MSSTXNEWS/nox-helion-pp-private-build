"""Offline validation of controlled V63 recovery source, never touch Vast."""
import ast
import unittest
from nox_runpod.teacher_mesh.v63 import recover_agent_tuner


def remote_python():
    script=recover_agent_tuner.REMOTE
    begin="python3 - <<'PYREMOTE'\n"
    end="\nPYREMOTE"
    assert script.count(begin)==1 and script.count(end)==1
    return script.split(begin,1)[1].split(end,1)[0]


class TestTunerAdmission(unittest.TestCase):
    def test_embedded_remote_syntax(self):
        ast.parse(remote_python())

    def test_fixed_target_and_source_sha(self):
        text=remote_python()
        self.assertIn("TARGET='nox-agent-tuner-t858u'",text)
        self.assertIn("77f01625f1a05425080808f9ce377fb4e4253f45d3ce19892e80aaceebf4c9eb",text)
        self.assertIn("f9ec50e6feb5b39307666b109623234624c30e5c3dd8ec496d7f5d51a69f41b5",text)

    def test_single_targeted_start_only(self):
        text=remote_python()
        self.assertEqual(text.count("['supervisorctl','start',TARGET]"),1)
        self.assertNotIn("['supervisorctl','restart'",text)
        self.assertNotIn("['supervisorctl','start','all'",text)
        self.assertIn("['supervisorctl','stop',TARGET]",text)

    def test_fail_closed_on_low_disk_stop_and_source(self):
        text=remote_python()
        for marker in ("16_000_000_000","HOLD_GLOBAL_STOP_SIGNAL",
                       "HOLD_SCRIPT_SHA_CHANGED","HOLD_CONFIG_SHA_CHANGED",
                       "HOLD_GPU_TRAINER_IMPORT","HOLD_TUNER_MUTATION_RISK",
                       "HOLD_GPU_TELEMETRY_MISSING"):
            self.assertIn(marker,text)

    def test_result_is_not_fake_pass_on_remote_hold(self):
        main=recover_agent_tuner.main.__code__
        self.assertTrue(any(isinstance(x,str) and "HOLD_NOT_ACCEPTED_OR_UNVERIFIED" in x for x in main.co_consts))
        self.assertTrue(any(isinstance(x,tuple) and "NATIVE_TUNER_RUNNING_VERIFIED" in x and "ALREADY_RUNNING" in x for x in main.co_consts))


if __name__=="__main__":
    unittest.main()
