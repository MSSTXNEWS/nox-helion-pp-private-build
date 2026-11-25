"""B5/B0 exact-source composition rehearsal, fixtures only; never native acceptance."""
import os
import tempfile
import unittest
from contextlib import ExitStack
from b5_r55_pinned import load_pinned_s03_artifacts
from b0_resume_bridge import bind_existing_resume
from b5_browser_prefix_gate import bind_observed_browser_prefix
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

    def test_actual_browser_prefix_before_next_post(self):
        with ExitStack() as stack:
            for n in (1, 2):
                old, pins = self.load(stack, n)
                f = fixture(n)
                f.update(canonical_rows=old, prior_witnesses=pins)
                observed = [{"role": r["role"], "content": r["content"]} for r in old]
                def bind(browser=observed, calls=7):
                    return bind_observed_browser_prefix(
                        observed_browser_rows=browser, observed_browser_calls=calls, **f)
                for wrong in (f["owner_rows"], old, list(f["owner_rows"]), list(old), [], observed[:-1]):
                    with self.assertRaisesRegex(ValueError, "HOLD_ACTUAL_BROWSER_PREFIX"):
                        bind(wrong)
                for count in (True, 6, 8):
                    with self.assertRaisesRegex(ValueError, "HOLD_ACTUAL_BROWSER_PREFIX"):
                        bind(calls=count)
                changed = [dict(r) for r in observed]
                changed[0]["content"] = "Подмена / cambio"
                with self.assertRaisesRegex(ValueError, "HOLD_RESUME_BROWSER_PREFIX"):
                    bind(changed)
                changed = [dict(r) for r in observed]
                changed[-1]["message_id"] = "other"
                with self.assertRaisesRegex(ValueError, "HOLD_RESUME_BROWSER_PREFIX"):
                    bind(changed)
                bridge = bind()
                new, newpins = self.load(stack, n+1, prior_rows=old, prior_witnesses=pins)
                self.assertEqual(bridge.finish(
                    browser_rows=[dict(r) for r in new], canonical_rows=new,
                    witnesses=newpins, browser_calls=8, admitted_calls=8,
                    prompt=new[-2]["content"], stream_answer=new[-1]["content"],
                    terminal_saved=True, dom_matches=True), "RESUME_EVIDENCE_MATCHED")

    def test_exact_single_get_ingress_two_consecutive_turns(self):
        from unittest.mock import patch
        import owner_chat_probe as probe
        from b0_resume_bridge import prepare_existing_resume_from_owner_get
        with ExitStack() as stack:
            old, pins = self.load(stack, 1)
            for n in (1, 2):
                f = fixture(n)
                f.update(canonical_rows=old, prior_witnesses=pins,
                         browser_calls=6+n, admitted_calls=6+n)
                observed = [dict(r) for r in old]
                history = dict(dialog_id=f["dialog_id"], messages=f["owner_rows"])
                kwargs = {k: v for k, v in f.items() if k not in ("preflight", "owner_rows")}
                kwargs.update(client="fixture-client", row_count=2*n,
                              observed_browser_rows=observed, observed_browser_calls=6+n)
                # Actual B0 snapshot path; only the authenticated transport is mocked.
                with patch.object(probe, "require_preturn_owner_binding") as before, \
                     patch.object(probe, "owner_readback_json", return_value=history) as get, \
                     patch.object(probe, "require_postturn_owner_binding") as after:
                    bridge = prepare_existing_resume_from_owner_get(**kwargs)
                    before.assert_called_once_with("fixture-client")
                    after.assert_called_once_with("fixture-client")
                    get.assert_called_once_with("fixture-client",
                        "/api/ui/memory/dialogs/history?dialog_id="+f["dialog_id"]+"&limit=8")
                new, newpins = self.load(stack, n+1, prior_rows=old, prior_witnesses=pins)
                args = dict(browser_rows=[dict(r) for r in new], canonical_rows=new,
                            witnesses=newpins, browser_calls=7+n, admitted_calls=7+n,
                            prompt=new[-2]["content"], stream_answer=new[-1]["content"],
                            terminal_saved=True, dom_matches=True)
                self.assertEqual(bridge.finish(**args), "RESUME_EVIDENCE_MATCHED")
                self.assertEqual(bridge.finish(**args), "HOLD_RESUME_ALREADY_CONSUMED")
                self.assertEqual(new[:len(old)], old)
                old, pins = new, newpins
            self.assertEqual(len(old), 6)

    def test_r57_pinned_fd_prefix_drift_during_single_get(self):
        from unittest.mock import patch
        import owner_chat_probe as probe
        from b0_resume_bridge import prepare_existing_resume_from_owner_get
        with ExitStack() as stack:
            for n in (1, 2):
                old, pins = self.load(stack, n)
                for mode in ("shallow_alias", "stale_to_matching", "matching_to_stale"):
                    f = fixture(n)
                    f.update(canonical_rows=old, prior_witnesses=pins)
                    observed = list(old) if mode == "shallow_alias" else [dict(r) for r in old]
                    if mode == "stale_to_matching":
                        observed[-1]["content"] = "Старое / anterior"
                    history = dict(dialog_id=f["dialog_id"], messages=f["owner_rows"])
                    kwargs = {k: v for k, v in f.items() if k not in ("preflight", "owner_rows")}
                    kwargs.update(client="fixture-client", row_count=2*n,
                                  observed_browser_rows=observed, observed_browser_calls=7)
                    def get_history(*_):
                        if mode == "stale_to_matching":
                            observed[-1]["content"] = old[-1]["content"]
                        elif mode == "matching_to_stale":
                            observed[-1]["content"] = "Подмена / cambiado"
                        return history
                    with self.subTest(turn=n+1, mode=mode), \
                         patch.object(probe, "require_preturn_owner_binding"), \
                         patch.object(probe, "owner_readback_json", side_effect=get_history) as get, \
                         patch.object(probe, "require_postturn_owner_binding"):
                        with self.assertRaisesRegex(ValueError, "HOLD_ACTUAL_BROWSER_PREFIX"):
                            prepare_existing_resume_from_owner_get(**kwargs)
                        get.assert_called_once()
                self.assertEqual(old, rows(n))

    def test_r58_terminal_independence_with_pinned_fd_readback(self):
        from unittest.mock import patch
        import owner_chat_probe as probe
        from b0_resume_bridge import prepare_existing_resume_from_owner_get
        with ExitStack() as stack:
            for n in (1, 2):
                old, pins = self.load(stack, n)
                new, newpins = self.load(stack, n+1, prior_rows=old, prior_witnesses=pins)
                for mode in ("same_list", "shallow_alias", "mixed_alias", "independent"):
                    f = fixture(n)
                    f.update(canonical_rows=old, prior_witnesses=pins)
                    kwargs = {k: v for k, v in f.items() if k not in ("preflight", "owner_rows")}
                    kwargs.update(client="fixture-client", row_count=2*n,
                                  observed_browser_rows=[dict(r) for r in old],
                                  observed_browser_calls=7)
                    with self.subTest(turn=n+1, mode=mode), \
                         patch.object(probe, "require_preturn_owner_binding"), \
                         patch.object(probe, "owner_readback_json", return_value=dict(
                             dialog_id=f["dialog_id"], messages=f["owner_rows"])) as get, \
                         patch.object(probe, "require_postturn_owner_binding"):
                        bridge = prepare_existing_resume_from_owner_get(**kwargs)
                        get.assert_called_once()
                        independent = [dict(r) for r in new]
                        browser = {"same_list": new, "shallow_alias": list(new),
                                   "mixed_alias": independent[:-1]+[new[-1]],
                                   "independent": independent}[mode]
                        args = dict(browser_rows=browser, canonical_rows=new,
                                    witnesses=newpins, browser_calls=8, admitted_calls=8,
                                    prompt=new[-2]["content"], stream_answer=new[-1]["content"],
                                    terminal_saved=True, dom_matches=True)
                        self.assertEqual(bridge.finish(**args),
                            "RESUME_EVIDENCE_MATCHED" if mode == "independent"
                            else "HOLD_ACTUAL_BROWSER_POSTTURN")
                        args["browser_rows"] = independent
                        self.assertEqual(bridge.finish(**args), "HOLD_RESUME_ALREADY_CONSUMED")
                self.assertEqual(new[:len(old)], old)
                self.assertEqual(new, rows(n+1))

if __name__ == "__main__":
    unittest.main(verbosity=2)
