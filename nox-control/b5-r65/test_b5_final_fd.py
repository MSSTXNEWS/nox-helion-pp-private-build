"""R65 regression on exact R64 and candidate, real OS temporary FDs."""
import os
from unittest.mock import patch
from test_b5_retained_ingress import RetainedIngressTests
import b5_retained_ingress as candidate
import b5_retained_ingress_r64 as donor


class FinalValidationDriftTests(RetainedIngressTests):
    def test_drift_during_final_guard_reproduced_and_rejected(self):
        for implementation, rejects in ((donor, False), (candidate, True)):
            with self.subTest(implementation=implementation.__name__):
                pairs = tuple(self.pair(n) for n in (1, 2, 3))
                original = implementation.verify_existing_chain

                def validate(**kwargs):
                    valid = original(**kwargs)
                    self.assertTrue(valid)
                    os.pwrite(pairs[0][0], b"X", 0)
                    return valid

                with patch.object(implementation, "verify_existing_chain", side_effect=validate):
                    if rejects:
                        with self.assertRaisesRegex(ValueError, "CHANGED"):
                            implementation.load_retained_chain(
                                dialog_id=__import__("test_b5_chain_guard").DIALOG,
                                session_id=__import__("test_b5_chain_guard").SESSION,
                                artifacts=pairs)
                    else:
                        chain = implementation.load_retained_chain(
                            dialog_id=__import__("test_b5_chain_guard").DIALOG,
                            session_id=__import__("test_b5_chain_guard").SESSION,
                            artifacts=pairs)
                        self.assertEqual(len(chain), 3)
                for pair in pairs:
                    for fd in pair[:2]:
                        self.assertEqual(os.lseek(fd, 0, os.SEEK_CUR), 1)
