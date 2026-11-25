"""B0 proxy-side named SSE delta encoder; never creates event identities.

Only for an independently authenticated native writer supplying a stable
event_id for each original delta. The caller owns route admission, scope,
replay protection, STOP, terminal EOF and independent S03 readback.
No live route is selected or installed by this module.
"""
import re

MAX_FRAME_BYTES = 65536  # Exact B1 R70 parser budget, excluding blank separator.
EVENT_ID = re.compile(r"[A-Za-z0-9._:-]{1,128}")


class HoldWire(ValueError):
    pass


def encode_native_delta(frame):
    """Preserve upstream identity and text; reject unrepresentable input."""
    if type(frame) is not dict or frame.get("type") != "delta":
        raise HoldWire("HOLD_PROXY_NOT_NATIVE_DELTA")
    event_id = frame.get("event_id")
    if type(event_id) is not str or not EVENT_ID.fullmatch(event_id):
        raise HoldWire("HOLD_PROXY_STABLE_EVENT_ID_REQUIRED")
    text = frame.get("text")
    if type(text) is not str or "\r" in text:
        # SSE treats CR as a line delimiter; never silently normalize it.
        raise HoldWire("HOLD_PROXY_DELTA_TEXT")
    if len(text) > MAX_FRAME_BYTES:
        raise HoldWire("HOLD_PROXY_FRAME_BUDGET")
    # A separate data field for each LF preserves leading/trailing spaces,
    # empty text, and trailing LF under the B1 exact data projection.
    body = "id: " + event_id + "\nevent: delta\n" + "\n".join(
        "data: " + line for line in text.split("\n"))
    try:
        raw = body.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        raise HoldWire("HOLD_PROXY_DELTA_UTF8") from None
    if len(raw) > MAX_FRAME_BYTES:
        raise HoldWire("HOLD_PROXY_FRAME_BUDGET")
    return raw + b"\n\n"
