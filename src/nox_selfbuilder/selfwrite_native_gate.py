"""Self-write proceeds only with a native ACK. No ACK means HOLD."""

def require_selfwrite_ack(receipt: dict) -> dict:
    if not isinstance(receipt, dict):
        return {"status": "HOLD", "code": "SELFWRITE_ACK_MISSING"}
    if receipt.get("status") != "SELFWRITE_ACK":
        return {"status": "HOLD", "code": "SELFWRITE_ACK_DENIED"}
    if receipt.get("epoch") is None:
        return {"status": "HOLD", "code": "SELFWRITE_EPOCH_MISSING"}
    return {"status": "READY", "code": "SELFWRITE_ACK_OK"}
