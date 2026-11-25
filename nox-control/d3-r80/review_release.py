"""Isolated release entrypoint: R65 loader + R79 closure; no native authority."""
import hashlib
from pathlib import Path
import b5_retained_ingress as ingress
import retained_snapshot_review as r78
import quality_closure as r79

def _require_exact_composition():
    # Resolve the actual imported file, not a caller-supplied version string.
    raw = Path(ingress.__file__).read_bytes()
    if hashlib.sha256(raw).hexdigest() != "fbab0f88cfbcb11c7fa8a5781e535faa3eeba52e2074c5b5029740420ce1a13b":
        raise ValueError("HOLD_D3_R80_LOADER_PIN")
    if r78.load_retained_chain is not ingress.load_retained_chain or r79.r78 is not r78:
        raise ValueError("HOLD_D3_R80_IMPORT_ALIAS")

def prepare_joint_review(**inputs):
    _require_exact_composition()
    return r79.prepare_joint_review(**inputs)

def verify_joint_reviews(**inputs):
    _require_exact_composition()
    return r79.verify_joint_reviews(**inputs)
