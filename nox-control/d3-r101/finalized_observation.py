"""R101: offline final-disposition admission before R97.
Detached receipts must be supplied by an independently authenticated host.
This module does not authenticate, reserve, send ACK, POST, train or deploy.
"""
import copy
from browser_projection_gate import review_browser_projection, SCOPE, BIND, HASH, ID
from s03_identity_join import _pin
from outcome_review import _hold

COMMON = SCOPE | BIND | {"observation_id", "observation_sha256",
                        "browser_sha256", "terminal_receipt_sha256"}
RESERVATION = COMMON | {"schema", "reservation_id", "state"}
FINAL = COMMON | {"schema", "disposition_id", "reservation_id",
                  "reservation_sha256", "state", "dom_recheck", "stop_recheck"}

def require(ok):
    if not ok:
        raise ValueError("HOLD_B2_FINAL_BROWSER_DISPOSITION")

def review_finalized_observations(*, disposition_pairs=None, reservation_pairs=None, **kwargs):
    if kwargs.get("outcome") != "completed":
        return review_browser_projection(**kwargs)
    try:
        require(type(disposition_pairs) is tuple and len(disposition_pairs) == 2)
        require(type(reservation_pairs) is tuple and len(reservation_pairs) == 2)
        projections = kwargs["browser_pairs"]
        require(type(projections) is tuple and len(projections) == 2)
        p = kwargs["provenance"]
        seen = {p["owner_pair"][1], kwargs["physical_receipt_pair"][1],
                *(x[1] for x in p["terminal_pairs"]),
                *(x[1] for x in p["transport_pairs"]),
                *(x[1] for x in projections),
                *(v for d in kwargs["review_inputs"]["descriptor_sets"] for v in d[2:])}
        disposition_ids, reservation_ids = set(), set()
        evidence = []
        for turn, projection, reservation, disposition in zip(
                (2, 3), projections, reservation_pairs, disposition_pairs):
            require(type(reservation) is tuple and len(reservation) == 2)
            require(type(disposition) is tuple and len(disposition) == 2)
            require(reservation[1] not in seen)
            seen.add(reservation[1])
            require(disposition[1] not in seen)
            seen.add(disposition[1])
            obs = _pin(*projection)
            res = _pin(*reservation)
            final = _pin(*disposition)
            require(set(res) == RESERVATION and set(final) == FINAL)
            require(type(obs["turn"]) is int and obs["turn"] == turn)
            require(obs["ack_state"] == "NOT_SENT")
            expected = {k: obs[k] for k in COMMON - {"observation_sha256"}}
            expected["observation_sha256"] = projection[1]
            for k, value in expected.items():
                require(type(res[k]) is type(value) and res[k] == value)
                require(type(final[k]) is type(value) and final[k] == value)
            require(res["schema"] == "nox.browser.ack-reservation-readback.v1")
            require(res["state"] == "RESERVED_NOT_SENT")
            require(final["schema"] == "nox.browser.projection-disposition.v1")
            require(final["state"] == "FINALIZED" and final["dom_recheck"] == "MATCHED"
                    and final["stop_recheck"] == "CLEAR")
            require(final["reservation_sha256"] == reservation[1])
            rid, did = res["reservation_id"], final["disposition_id"]
            require(type(rid) is str and ID.fullmatch(rid) and rid not in reservation_ids)
            require(type(did) is str and ID.fullmatch(did) and did not in disposition_ids)
            require(final["reservation_id"] == rid)
            reservation_ids.add(rid)
            disposition_ids.add(did)
            evidence.append(dict(observation_sha256=projection[1],
                                 reservation_sha256=reservation[1],
                                 disposition_sha256=disposition[1]))
        result = review_browser_projection(**kwargs)
        if result.get("route") != "REVIEW_DATA_ONLY":
            return result
        require(all(result[k] is False for k in
                    ("native_accepted", "training_admitted", "next_post_allowed",
                     "retry_allowed", "ack_allowed")))
        return dict(result, dialog_provenance=dict(result["dialog_provenance"],
                    finalized_observation_pairs=evidence,
                    disposition_status="MATCHED_OFFLINE",
                    authentication_verified=False))
    except (TypeError, ValueError, KeyError, IndexError, AttributeError, RuntimeError, OSError):
        return dict(_hold("HOLD_B2_FINAL_BROWSER_DISPOSITION"), ack_allowed=False)
