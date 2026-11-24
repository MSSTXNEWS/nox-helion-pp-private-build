"""B2 R92: require a single physical/retained pair before RU/ES review.
Offline only. Detached pins require independent authenticated orchestration.
Never grants POST, training or native acceptance.
"""
import copy
import json
import subprocess
from pathlib import Path
from distinct_dialog import review_distinct, encode
from s03_identity_join import _pin
from retained_pair import compose_pair
from outcome_review import _hold

NODE = Path(__file__).resolve().parent / "b3_r71_physical_terminal_composition.cjs"

def review_physical_pair(*, outcome, review_inputs=None, failed_attempt=None,
                         provenance=None, physical_receipt_pair=None):
    if outcome != "completed":
        return review_distinct(outcome=outcome, failed_attempt=failed_attempt)
    try:
        if type(provenance) is not dict or type(review_inputs) is not dict:
            raise ValueError("inputs")
        p = copy.deepcopy(provenance)
        inputs = dict(review_inputs)
        descriptors = inputs["descriptor_sets"]
        if type(descriptors) is not tuple or len(descriptors) != 3:
            raise ValueError("chain")
        if type(physical_receipt_pair) is not tuple or len(physical_receipt_pair) != 2:
            raise ValueError("receipts")
        receipts = _pin(*physical_receipt_pair)
        pin = physical_receipt_pair[1]
        pairs = p["transport_pairs"]
        if type(pairs) is not tuple or len(pairs) != 2:
            raise ValueError("transport")
        pins = [p["owner_pair"][1], *(x[1] for x in p["terminal_pairs"]),
                *(x[1] for x in pairs), *(v for d in descriptors for v in d[2:])]
        if pin in pins:
            raise ValueError("pin reuse")
        turns = tuple(_pin(*x) for x in pairs)
        scope = p["expected_scope"]
        packet = compose_pair(dialog_id=scope["s03_dialog_id"],
                              session_id=scope["session_id"],
                              artifacts=descriptors, receipts=receipts, turns=turns)
        raw = subprocess.run(
            ["node", "-e", "const r=require(process.argv[1]);"
             "console.log(JSON.stringify(r.check(JSON.parse(require('node:fs').readFileSync(0,'utf8')))))",
             str(NODE)], input=encode(packet), stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=5, check=True)
        verdict = json.loads(raw.stdout)
        if (verdict.get("status") != "CONSISTENT_COMPOSED_PHYSICAL_ONLY"
            or verdict.get("consistent") is not True
            or verdict.get("readbacks") != 4 or verdict.get("turns") != 2
            or any(verdict.get(k) is not False for k in
                   ("native_accepted", "authentication_verified", "next_post_allowed"))):
            raise ValueError("physical pair")
        result = review_distinct(outcome=outcome, review_inputs=inputs, provenance=p)
        if result.get("route") == "REVIEW_DATA_ONLY":
            if result.get("native_accepted") is not False or result.get("training_admitted") is not False:
                raise ValueError("authority")
            evidence = dict(result["dialog_provenance"], physical_receipt_sha256=pin,
                            physical_readback_sha256=[x["sha256"] for x in receipts["receipt_index"]])
            return dict(result, dialog_provenance=evidence)
        return result
    except (TypeError, ValueError, KeyError, IndexError, AttributeError,
            RuntimeError, OSError, UnicodeError, subprocess.SubprocessError):
        return _hold("HOLD_B2_R92_PHYSICAL_PAIR")
