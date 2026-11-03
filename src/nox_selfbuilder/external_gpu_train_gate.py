"""External GPU training gate. Fail closed without ACK, GPU, and pinned weights."""

def require_external_gpu_train(*, ack: dict, gpu_present: bool, weights_sha256: str) -> dict:
    if not isinstance(ack, dict) or ack.get("status") != "SELFLEARN_ACK":
        return {"status": "HOLD", "code": "GPU_TRAIN_ACK_REQUIRED"}
    if not gpu_present:
        return {"status": "HOLD", "code": "EXTERNAL_GPU_MISSING"}
    if not isinstance(weights_sha256, str) or len(weights_sha256) != 64:
        return {"status": "HOLD", "code": "WEIGHTS_SHA_REQUIRED"}
    return {"status": "READY", "code": "GPU_TRAIN_GATES_OK"}
