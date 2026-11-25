"""Offline-only packet assembly from the actual R104 -> R101 -> R97 chain.

No host authentication is implemented here. The receiving R103 adapter still
requires its independently configured verifier. No production samples or
native/ACK/POST/training authority are returned.
"""
import json
from receipt_id_fence import review_unique_receipt_ids

def _result(status, packet=None):
    return dict(status=status, packet=packet, native_accepted=False,
                training_admitted=False, ack_allowed=False, next_post_allowed=False,
                quality_sample=None, metrics=None)

def prepare_joint_packet(*, timing, browser_pairs, reservation_pairs,
                         disposition_pairs, **kwargs):
    try:
        result = review_unique_receipt_ids(browser_pairs=browser_pairs,
            reservation_pairs=reservation_pairs, disposition_pairs=disposition_pairs,
            **kwargs)
        if result.get("route") != "REVIEW_DATA_ONLY":
            return _result(result.get("reason", "HOLD_QUALITY"))
        if kwargs.get("outcome") != "completed" or type(timing) is not tuple or len(timing) != 2:
            return _result("HOLD_JOINT_INPUT")
        if any(result.get(k) is not False for k in ("native_accepted", "training_admitted",
                "ack_allowed", "next_post_allowed", "retry_allowed")):
            return _result("HOLD_JOINT_AUTHORITY")
        provenance = result["dialog_provenance"]
        if provenance["authentication_verified"] is not False or provenance["disposition_status"] != "MATCHED_OFFLINE":
            return _result("HOLD_JOINT_AUTHORITY")
        turns = []
        for i, (sample, proof) in enumerate(timing):
            if type(sample) is not dict or type(proof) is not dict:
                return _result("HOLD_JOINT_INPUT")
            row = {"sample": sample, "proof": {k:v for k,v in proof.items() if k != "verified"}}
            for name, pairs in (("observation", browser_pairs), ("reservation", reservation_pairs),
                                ("disposition", disposition_pairs)):
                raw, pin = pairs[i]
                if type(raw) is not bytes:
                    return _result("HOLD_JOINT_INPUT")
                if provenance["finalized_observation_pairs"][i][name+"_sha256"] != pin:
                    return _result("HOLD_JOINT_PIN")
                row[name] = [raw.decode("utf-8", errors="strict"), pin]
            turns.append(row)
        packet = json.dumps({"review": result, "turns": turns}, ensure_ascii=False,
                            allow_nan=False, separators=(",", ":"))
        return _result("OFFLINE_PACKET_READY", packet)
    except (TypeError, ValueError, KeyError, IndexError, AttributeError, RuntimeError, OSError):
        return _result("HOLD_JOINT_PACKET")
