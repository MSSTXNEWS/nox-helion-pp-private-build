"""R65 final validation drift must fail at the existing R62 terminal."""
import os
from unittest.mock import patch
import test_owner_fd_turn3 as base
import b5_retained_ingress as ingress


class R65TerminalTest(base.OwnerFDCompositionTest):
    def test_final_validation_drift_blocks_terminal(self):
        evidence = self.prepare()
        original = ingress.verify_existing_chain

        def validate(**kwargs):
            valid = original(**kwargs)
            self.assertTrue(valid)
            os.pwrite(self.pairs[0][0], b"X", 0)
            return valid

        with patch.object(ingress, "verify_existing_chain", side_effect=validate):
            self.assertEqual(evidence.finish(artifacts=self.pairs, **self.args()),
                             "HOLD_B0_TERMINAL_FD_CHAIN")
        self.assertEqual(evidence.finish(artifacts=self.pairs, **self.args()),
                         "HOLD_RESUME_ALREADY_CONSUMED")
