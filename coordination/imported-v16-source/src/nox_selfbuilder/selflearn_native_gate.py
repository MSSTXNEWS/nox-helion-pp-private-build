"""Self-learn proceeds only with a native ACK. No ACK means HOLD."""

def require_selflearn_ack(receipt: dict) -> dict:
    if not isinstance(receipt, dict):
        return {"status": "HOLD", "code": "SELFLEARN_ACK_MISSING"}
    if receipt.get("status") != "SELFLEARN_ACK":
        return {"status": "HOLD", "code": "SELFLEARN_ACK_DENIED"}
    if receipt.get("epoch") is None:
        return {"status": "HOLD", "code": "SELFLEARN_EPOCH_MISSING"}
    return {"status": "READY", "code": "SELFLEARN_ACK_OK"}
