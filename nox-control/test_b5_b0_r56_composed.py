"""B5/B0 exact-source composition rehearsal, fixtures only; never native acceptance."""
import os
import tempfile
import unittest
from contextlib import ExitStack
from b5_r55_pinned import load_pinned_s03_artifacts
from b0_resume_bridge import bind_existing_resume
from test_b0_resume_bridge import fixture, rows, witnesses

class ComposedIngressTests(unittest.TestCase):
    def load(self, stack, n, **overrides):
        w, r, wp, rp = witnesses(rows(n))
        def fd(raw):
            f = stack.enter_context(tempfile.TemporaryFile())
            f.write(raw)
            f.flush()
            f.seek(1)
            return f.fileno()
        args = dict(writer_fd=fd(w), readback_fd=fd(r), writer_sha256=wp,
                    readback_sha256=rp, dialog_id="a"*32, session_id="fixture-owner",
                    sequence=n)
        args.update(overrides)
        result = load_pinned_s03_artifacts(**args)
        self.assertEqual(os.lseek(args["writer_fd"], 0, os.SEEK_CUR), 1)
        self.assertEqual(os.lseek(args["readback_fd"], 0, os.SEEK_CUR), 1)
        return result

    def test_same_dialog_turn2_then_turn3(self):
        with ExitStack() as stack:
            old, pins = self.load(stack, 1)
            for n in (1, 2):
                f = fixture(n)
                f.update(canonical_rows=old, prior_witnesses=pins,
                         browser_calls=7+n-1, admitted_calls=7+n-1)
                bridge = bind_existing_resume(**f)
                new, newpins = self.load(stack, n+1, prior_rows=old, prior_witnesses=pins)
                args = dict(browser_rows=new, canonical_rows=new, witnesses=newpins,
                            browser_calls=7+n, admitted_calls=7+n,
                            prompt=new[-2]["content"], stream_answer=new[-1]["content"],
                            terminal_saved=True, dom_matches=True)
                self.assertEqual(bridge.finish(**args), "RESUME_EVIDENCE_MATCHED")
                self.assertEqual(bridge.finish(**args), "HOLD_RESUME_ALREADY_CONSUMED")
                self.assertEqual(new[:len(old)], old)
                old, pins = new, newpins
            self.assertEqual(len(old), 6)

    def test_foreign_pin_and_owner_drift_hold(self):
        with ExitStack() as stack:
            with self.assertRaisesRegex(ValueError, "HOLD_S03_ARTIFACT_PIN"):
                self.load(stack, 1, writer_sha256="0"*64)
            old, pins = self.load(stack, 1)
            f = fixture(1)
            f.update(canonical_rows=old, prior_witnesses=pins)
            f["owner_rows"][0]["owner_metadata"] = "drift"
            with self.assertRaisesRegex(ValueError, "HOLD_B0_RESUME_OWNER_PIN"):
                bind_existing_resume(**f)

    def test_no_extra_post_or_uncertain_replay(self):
        with ExitStack() as stack:
            old, pins = self.load(stack, 1)
            f = fixture(1)
            f.update(canonical_rows=old, prior_witnesses=pins)
            bridge = bind_existing_resume(**f)
            new, newpins = self.load(stack, 2, prior_rows=old, prior_witnesses=pins)
            args = dict(browser_rows=new, canonical_rows=new, witnesses=newpins,
                        browser_calls=9, admitted_calls=8, prompt=new[-2]["content"],
                        stream_answer=new[-1]["content"], terminal_saved=True, dom_matches=True)
            self.assertEqual(bridge.finish(**args), "HOLD_RESUME_POST_OR_STREAM")
            args["browser_calls"] = 8
            self.assertEqual(bridge.finish(**args), "HOLD_RESUME_ALREADY_CONSUMED")

if __name__ == "__main__":
    unittest.main(verbosity=2)
