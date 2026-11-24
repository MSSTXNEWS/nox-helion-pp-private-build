import json
import hashlib
import unittest
from unittest.mock import patch
import owner_chat_probe as probe
from test_b0_resume_bridge import fixture, rows, witnesses
from b0_chain_bound import prepare_chain_bound_turn3


def cp(n):
    r = rows(n)
    return r, witnesses(r)


def inputs():
    f = fixture(2)
    history = dict(dialog_id=f["dialog_id"], messages=f["owner_rows"])
    kw = {k:v for k,v in f.items() if k not in ("preflight", "owner_rows")}
    kw.update(client="fixture-client", row_count=4,
              observed_browser_rows=rows(2), observed_browser_calls=7)
    return kw, history


def finish_args(reuse=False):
    r, p = cp(3)
    if reuse:
        w, rb = [json.loads(x) for x in p[:2]]
        for x in (w, rb):
            x["event_id"] = "evt-1"
            x["turn_id"] = "turn-1"
        a, b = [json.dumps(x, ensure_ascii=False, separators=(",",":")).encode()
                for x in (w, rb)]
        p = (a, b, hashlib.sha256(a).hexdigest(), hashlib.sha256(b).hexdigest())
    return dict(browser_rows=[dict(x) for x in r], canonical_rows=r, witnesses=p,
                browser_calls=8, admitted_calls=8, prompt=r[-2]["content"],
                stream_answer=r[-1]["content"], terminal_saved=True, dom_matches=True)


class ChainBoundTest(unittest.TestCase):
    def test_valid_and_nonadjacent_reuse(self):
        for reuse in (False, True):
            kw, history = inputs()
            with patch.object(probe, "require_preturn_owner_binding"), \
                 patch.object(probe, "owner_readback_json", return_value=history) as get, \
                 patch.object(probe, "require_postturn_owner_binding"):
                obj = prepare_chain_bound_turn3(retained_chain=(cp(1), cp(2)), **kw)
                get.assert_called_once()
            self.assertEqual(obj.finish(**finish_args(reuse)),
                "HOLD_B0_FULL_S03_CHAIN" if reuse else "RESUME_EVIDENCE_MATCHED")
            self.assertEqual(obj.finish(**finish_args()), "HOLD_RESUME_ALREADY_CONSUMED")

    def test_missing_first_checkpoint_blocks_before_get(self):
        kw, _ = inputs()
        with patch.object(probe, "owner_readback_json") as get:
            for chain in ((cp(2),), (cp(2), cp(2)), None):
                with self.assertRaisesRegex(ValueError, "HOLD_B0_FULL_S03_PREFIX"):
                    prepare_chain_bound_turn3(retained_chain=chain, **kw)
            get.assert_not_called()

    def test_retained_chain_drift_during_get(self):
        kw, history = inputs()
        chain = (cp(1), cp(2))
        def drift(*_):
            chain[0][0][0]["content"] = "changed"
            return history
        with patch.object(probe, "require_preturn_owner_binding"), \
             patch.object(probe, "owner_readback_json", side_effect=drift) as get, \
             patch.object(probe, "require_postturn_owner_binding"):
            with self.assertRaisesRegex(ValueError, "HOLD_B0_FULL_S03_PREFIX_DRIFT"):
                prepare_chain_bound_turn3(retained_chain=chain, **kw)
            get.assert_called_once()
