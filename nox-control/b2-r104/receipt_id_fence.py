"""B2 source-only quality admission; no runtime or ACK authority."""
from finalized_observation import review_finalized_observations, ID, _pin, _hold

REASON = "HOLD_B2_CROSS_KIND_RECEIPT_ID"


def review_unique_receipt_ids(*, browser_pairs=None, reservation_pairs=None,
                              disposition_pairs=None, **kwargs):
    if kwargs.get("outcome") == "completed":
        try:
            seen = set()
            for pairs, key in ((browser_pairs, "observation_id"),
                               (reservation_pairs, "reservation_id"),
                               (disposition_pairs, "disposition_id")):
                if type(pairs) is not tuple or len(pairs) != 2:
                    raise ValueError(REASON)
                for pair in pairs:
                    if type(pair) is not tuple or len(pair) != 2:
                        raise ValueError(REASON)
                    ident = _pin(*pair)[key]
                    if type(ident) is not str or not ID.fullmatch(ident) or ident in seen:
                        raise ValueError(REASON)
                    seen.add(ident)
        except (TypeError, ValueError, KeyError, IndexError, AttributeError, RuntimeError, OSError):
            return dict(_hold(REASON), ack_allowed=False)
    return review_finalized_observations(browser_pairs=browser_pairs,
        reservation_pairs=reservation_pairs, disposition_pairs=disposition_pairs, **kwargs)
