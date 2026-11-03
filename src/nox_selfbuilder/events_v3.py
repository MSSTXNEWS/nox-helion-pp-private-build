"""events.v3 emitter. Live sensors are HOLD without a host."""
from datetime import datetime, timezone

def emit(kind: str, payload: dict) -> dict:
    return {
        "schema": "NOX-INSTALLER-EVENT-v3",
        "kind": kind,
        "at": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
        "live": False,
    }
