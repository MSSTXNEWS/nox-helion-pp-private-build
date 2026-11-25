"""Focused differential: real R101 module with lower-chain fixture stubs."""
import hashlib
import json
import re
import sys
import types
import unittest
from unittest.mock import patch


def pair(doc):
    raw = json.dumps(doc, sort_keys=True, ensure_ascii=False).encode()
    return raw, hashlib.sha256(raw).hexdigest()


def pin(raw, sha):
    if hashlib.sha256(raw).hexdigest() != sha:
        raise ValueError("bad digest")
    return json.loads(raw)


def hold(reason):
    return dict(route="HOLD", reason=reason, quality_sample=None, native_accepted=False,
                training_admitted=False, next_post_allowed=False, retry_allowed=False, ack_allowed=False)


def lower(**kwargs):
    if kwargs.get("outcome") != "completed":
        return hold("fixture noncompleted")
    return dict(hold("fixture"), route="REVIEW_DATA_ONLY", quality_sample={"fixture": True}, dialog_provenance={})


class FenceTest(unittest.TestCase):
    def test_cross_kind(self):
        fake = {
            "browser_projection_gate": types.SimpleNamespace(review_browser_projection=lower,
                SCOPE={"conversation_id"}, BIND={"turn"}, HASH=re.compile(r"[a-f0-9]{64}"), ID=re.compile(r"[A-Za-z0-9._:-]{1,128}")),
            "s03_identity_join": types.SimpleNamespace(_pin=pin),
            "outcome_review": types.SimpleNamespace(_hold=hold),
        }
        with patch.dict(sys.modules, fake):
            from finalized_observation import review_finalized_observations
            from receipt_id_fence import review_unique_receipt_ids, REASON
            def inputs(ids):
                obs, res, finals = [], [], []
                for n, (oid, rid, did) in enumerate(ids, 2):
                    common = dict(turn=n, conversation_id="conv", observation_id=oid,
                        browser_sha256="b"*64, terminal_receipt_sha256=str(n)*64)
                    o = pair(dict(common, ack_state="NOT_SENT", visible_text="ответ" if n == 2 else "respuesta"))
                    common["observation_sha256"] = o[1]
                    r = pair(dict(common, schema="nox.browser.ack-reservation-readback.v1", reservation_id=rid, state="RESERVED_NOT_SENT"))
                    d = pair(dict(common, schema="nox.browser.projection-disposition.v1", reservation_id=rid,
                        disposition_id=did, reservation_sha256=r[1], state="FINALIZED", dom_recheck="MATCHED", stop_recheck="CLEAR"))
                    obs.append(o); res.append(r); finals.append(d)
                return dict(outcome="completed", browser_pairs=tuple(obs), reservation_pairs=tuple(res), disposition_pairs=tuple(finals),
                    provenance=dict(owner_pair=(b"", "owner"), terminal_pairs=(), transport_pairs=()),
                    physical_receipt_pair=(b"", "physical"), review_inputs=dict(descriptor_sets=()))
            valid = [("o2", "r2", "d2"), ("o3", "r3", "d3")]
            self.assertEqual(review_unique_receipt_ids(**inputs(valid))["route"], "REVIEW_DATA_ONLY")
            cases = 0
            for a in range(6):
                for b in range(a+1, 6):
                    if a % 3 == b % 3:
                        continue
                    flat = [x for row in valid for x in row]
                    flat[b] = flat[a]
                    args = inputs([flat[:3], flat[3:]])
                    self.assertEqual(review_finalized_observations(**args)["route"], "REVIEW_DATA_ONLY")
                    result = review_unique_receipt_ids(**args)
                    self.assertEqual(result["reason"], REASON)
                    self.assertIsNone(result["quality_sample"])
                    self.assertFalse(result["native_accepted"])
                    self.assertFalse(result["ack_allowed"])
                    cases += 1
            self.assertEqual(cases, 12)
            self.assertEqual(review_unique_receipt_ids(outcome="interrupted"), hold("fixture noncompleted"))
            print("B2_R104: 12 cross-kind baseline review -> 12 HOLD; positive and noncompleted preserved; lower-chain fixture")
