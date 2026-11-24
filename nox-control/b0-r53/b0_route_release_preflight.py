"""Offline B0 release-route veto, not a native admission authority.

The R63 frozen B1/B3 direct composition is incompatible. This checker is
intentionally negative-only: a different pair requires independent review.
No network, generation, STOP, replay, or service state access.
"""
import hashlib
import json
from pathlib import Path
import sys

PINS = ("f6147e511fcb9683f0da0457460da4fe4b998e38",
        "8fbd18f35c96924f9330622a8148b273f6199f31",
        "66595eac01c562aff4daae68f5d146aaed64cbbe")
TASK = "B0-R64-FROZEN-RELEASE-WIRE-PREADMISSION-HOLD-20261124"


def blob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def inspect(manifest, browser, bridge):
    inputs = (manifest, browser, bridge)
    receipt = {"task_id": TASK, "decision": "HOLD_UNREVIEWED_RELEASE_WIRE",
               "native_accepted": False, "post_authorized": False}
    if any(type(raw) is not bytes for raw in inputs):
        return receipt
    receipt["git_blobs"] = [blob(raw) for raw in inputs]
    receipt["sha256"] = [hashlib.sha256(raw).hexdigest() for raw in inputs]
    if tuple(receipt["git_blobs"]) != PINS:
        return receipt
    # Immutable source anchors: producer emits default JSON SSE, consumer
    # projects only named delta events. No claim that either is installed.
    producer = (b"controller.enqueue(enc.encode('data: '+JSON.stringify(payload)+'\\n\\n'));" in bridge
                and b"event({type:'token',t:parts[index]});" in bridge)
    consumer = (b"if(event==='delta'){" in browser and b"s,data,ctrl.signal,eventId" in browser)
    if producer and consumer:
        receipt["decision"] = "HOLD_R63_DIRECT_WIRE_INCOMPATIBLE_BEFORE_POST"
        receipt["producer"] = "default JSON SSE token without stable event ID"
        receipt["consumer"] = "named delta projection"
    return receipt


def require_reviewed_wire(manifest, browser, bridge):
    """Fail before dispatch. This frozen-input veto never issues permission."""
    raise RuntimeError(inspect(manifest, browser, bridge)["decision"])


def selftest(manifest, browser, bridge):
    exact = inspect(manifest, browser, bridge)
    assert exact["decision"] == "HOLD_R63_DIRECT_WIRE_INCOMPATIBLE_BEFORE_POST", exact
    cases = [(manifest, browser, bridge),
             (manifest+b" ", browser, bridge),
             (manifest, browser+b" ", bridge),
             (manifest, browser, bridge+b" "),
             (None, browser, bridge)]
    posts = stops = 0
    for i, args in enumerate(cases):
        try:
            require_reviewed_wire(*args)
        except RuntimeError as exc:
            expected = exact["decision"] if i == 0 else "HOLD_UNREVIEWED_RELEASE_WIRE"
            assert str(exc) == expected
        else:
            posts += 1
            raise AssertionError("unexpected dispatch permission")
    print(json.dumps({"exact": exact, "cases": len(cases),
                      "fixture_post_calls": posts, "fixture_stop_calls": stops,
                      "native_accepted": False}, sort_keys=True))


if __name__ == "__main__":
    if len(sys.argv) != 5 or sys.argv[1] not in ("check", "selftest"):
        raise SystemExit("usage: check|selftest MANIFEST BROWSER BRIDGE")
    args = tuple(Path(p).read_bytes() for p in sys.argv[2:])
    if sys.argv[1] == "selftest":
        selftest(*args)
    else:
        print(json.dumps(inspect(*args), sort_keys=True))
        raise SystemExit(2)
