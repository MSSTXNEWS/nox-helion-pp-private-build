"""Full existing-dialog S03 chain guard. Pure evidence only, no native admission.
The owner must retain independently pinned writer/readback pairs from turn 1
and turn 2 BEFORE the next POST; never reconstruct either from turn 3.
"""
from b5_r55_pinned import (
    canonical_s03_firstturn_prefix_valid,
    canonical_s03_resumed_second_turn_valid,
    canonical_s03_pinned_evidence_valid,
    strict_owner_json_bytes,
)


def verify_existing_chain(*, dialog_id, session_id, chain):
    """Validate two or three immutable (rows, witness_tuple) checkpoints.

    Two checkpoints: pre-turn-3 guard. Three: terminal guard before acceptance.
    The caller obtains all pins independently, not from candidate receipts.
    """
    if type(chain) is not tuple or len(chain) not in (2, 3):
        return False
    try:
        events, turns = set(), set()
        previous = None
        for sequence, checkpoint in enumerate(chain, 1):
            if type(checkpoint) is not tuple or len(checkpoint) != 2:
                return False
            rows, pins = checkpoint
            if type(rows) is not list or len(rows) != 2 * sequence:
                return False
            if type(pins) is not tuple or len(pins) != 4:
                return False
            scope = dict(expected_session_id=session_id)
            if sequence == 1:
                valid = canonical_s03_firstturn_prefix_valid(
                    *pins, dialog_id, rows, **scope)
            elif sequence == 2:
                valid = canonical_s03_resumed_second_turn_valid(
                    *pins, dialog_id, rows, prior_messages=previous[0],
                    prior_witnesses=previous[1], **scope)
            else:
                valid = canonical_s03_pinned_evidence_valid(
                    *pins, dialog_id, rows, expected_sequence=3,
                    expected_prior_messages=previous[0],
                    prior_witnesses=previous[1], **scope)
            if not valid:
                return False
            writer = strict_owner_json_bytes(pins[0])
            event, turn = writer["event_id"], writer["turn_id"]
            if event in events or turn in turns:
                return False
            events.add(event)
            turns.add(turn)
            previous = checkpoint
        return True
    except (TypeError, ValueError, RuntimeError, KeyError, UnicodeError, RecursionError):
        return False
