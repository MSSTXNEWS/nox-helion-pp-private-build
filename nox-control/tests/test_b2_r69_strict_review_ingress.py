"""Run against exact B5 and D3/B2 sources; synthetic data only."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from b2_r69_strict_review_ingress import prepare_strict_review, verify_strict_reviews
from test_d3_r68_review_binding import actual_b4_pair, digest, fixture, raw, DIALOG, SESSION
from b5_s03_verifier_r54 import multiturn_transcript_sha256


def witness(rows, seq):
    history = multiturn_transcript_sha256(
        rows, expected_sequence=seq, _prefix_only=(seq == 1))
    identities = digest(json.dumps([x["message_id"] for x in rows],
                        ensure_ascii=False, separators=(",", ":")).encode())
    common = dict(source="canonical_s03", dialog_id=DIALOG, session_id=SESSION,
                  sequence=seq, event_id=f"event-{seq}", turn_id=f"turn-{seq}",
                  full_transcript_sha256=history, message_ids_sha256=identities)
    writer = raw(dict(common, verified=True, durable=True))
    reader = raw(dict(common, independent=True, messages=rows,
                      full_answer_sha256=digest(rows[-1]["content"].encode())))
    return writer, reader, digest(writer), digest(reader)


def inputs():
    base = fixture()
    r2 = json.loads(base["turn2_raw"])["messages"]
    r3 = json.loads(base["turn3_raw"])["messages"]
    r1 = copy.deepcopy(r2[:2])
    pair = actual_b4_pair()
    return dict(dialog_id=DIALOG, session_id=SESSION, prior_rows=r1,
                turn2_rows=r2, turn3_rows=r3, prior_witnesses=witness(r1, 1),
                turn2_witnesses=witness(r2, 2), turn3_witnesses=witness(r3, 3),
                rubric_raw=base["rubric_raw"], rubric_pin=base["rubric_pin"],
                pair_raw=pair, pair_pin=digest(pair))


def mutate(witnesses, side, **fields):
    a = list(witnesses)
    doc = json.loads(a[side])
    doc.update(fields)
    a[side] = raw(doc)
    a[side+2] = digest(a[side])
    return tuple(a)


class StrictComposition(unittest.TestCase):
    def test_review_and_closure_with_real_b5_contract(self):
        kwargs = inputs()
        result = prepare_strict_review(**kwargs)
        self.assertEqual(result["native_acceptance"], "HOLD_EXTERNAL_OWNER_BROWSER_S03_REVIEW")
        self.assertEqual(result["review_packet"]["readback_sha256"],
                         [kwargs["turn2_witnesses"][3], kwargs["turn3_witnesses"][3]])
        submissions = {}
        for side in ("a", "b"):
            doc = copy.deepcopy(result["review_packet"]["submission"])
            doc["reviewer_id"] = "fixture-reviewer-" + side
            for row in doc["decisions"]:
                row.update(verdict="correct", reason="Synthetic fixture only")
            data = raw(doc)
            submissions.update({f"submission_{side}_raw": data,
                                f"submission_{side}_pin": digest(data)})
        final = verify_strict_reviews(**kwargs, **submissions)
        self.assertEqual(final["review_summary"]["decisions_bound"], 4)
        self.assertFalse(final["review_summary"]["reviewer_identity_verified"])
        self.assertTrue(final["native_acceptance"].startswith("HOLD"))
        kwargs["turn3_witnesses"] = mutate(kwargs["turn3_witnesses"], 0,
                                           full_transcript_sha256="0"*64)
        with self.assertRaisesRegex(ValueError, "CANONICAL_TURN3"):
            verify_strict_reviews(**kwargs, **submissions)

    def test_same_answer_wrong_history_or_ids_never_reviewed(self):
        for side, field in ((0, "full_transcript_sha256"), (1, "message_ids_sha256")):
            kwargs = inputs()
            kwargs["turn2_witnesses"] = mutate(kwargs["turn2_witnesses"], side,
                                               **{field:"0"*64})
            with self.subTest(side=side, field=field), self.assertRaisesRegex(
                    ValueError, "CANONICAL_TURN2"):
                prepare_strict_review(**kwargs)

    def test_existing_first_turn_required_and_no_alias(self):
        kwargs = inputs()
        kwargs["prior_witnesses"] = kwargs["turn2_witnesses"]
        with self.assertRaisesRegex(ValueError, "CANONICAL_TURN2"):
            prepare_strict_review(**kwargs)
        kwargs = inputs()
        kwargs["turn3_witnesses"] = mutate(kwargs["turn3_witnesses"], 0, event_id="event-2")
        with self.assertRaisesRegex(ValueError, "CANONICAL_TURN3"):
            prepare_strict_review(**kwargs)

    def test_strict_s03_does_not_replace_browser_binding(self):
        kwargs = inputs()
        pair = actual_b4_pair(("Different visible answer", "Respuesta en español"))
        kwargs.update(pair_raw=pair, pair_pin=digest(pair))
        with self.assertRaisesRegex(ValueError, "BROWSER_S03_ANSWER_MISMATCH"):
            prepare_strict_review(**kwargs)


if __name__ == "__main__":
    unittest.main(verbosity=2)
