"""External GPU training gate. Fail closed without ACK, GPU, and pinned weights."""

import re

def require_external_gpu_train(*, ack: dict, gpu_present: bool, weights_sha256: str) -> dict:
    if not isinstance(ack, dict) or ack.get("status") != "SELFLEARN_ACK":
        return {"status": "HOLD", "code": "GPU_TRAIN_ACK_REQUIRED"}
    if gpu_present is not True:
        return {"status": "HOLD", "code": "EXTERNAL_GPU_MISSING"}
    if not isinstance(weights_sha256, str) or re.fullmatch(r"[0-9a-f]{64}", weights_sha256) is None:
        return {"status": "HOLD", "code": "WEIGHTS_SHA_REQUIRED"}
    return {"status": "READY", "code": "GPU_TRAIN_GATES_OK"}
