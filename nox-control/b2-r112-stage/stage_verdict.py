"""Add the exact B2 verdict entrypoint to an already verified R111 extraction."""
import hashlib
from pathlib import Path

HERE=Path(__file__).resolve().parent
SOURCE=HERE.parent/"b2-r112/verdict_consistency.cjs"
DEST="nox-control/b2-r112/verdict_consistency.cjs"
PINS={
    "nox-control/d3-r111/release.json":"fd6b4dd58465de1b7874c36f292acd98be7bb6c5",
    "nox-control/b2-r110/reported_review.cjs":"ea2a46f68770ae613ae6645ddb48de52d37eb9b7",
    "nox-control/a3-r109-r80/joint_frozen.cjs":"8ccc4877f610e6ba32f0bf19efdd7105b6fdedf9",
    "nox-control/b2-r108/atomic_ordered_quality.cjs":"2bd2efcaea708498871b6f913e4b28d5bb8ca90e",
    "nox-control/a3-r109-r80/frozen/b3_r80_frozen_byte_ingress.cjs":"8a95bf6eef67b92964f9a77c54ba71822bdb4b4d",
    "nox-control/a6-r109-r80-release/release.json":"513f61f098574f438b8f9974cfd7ca5f7002428d",
}
SOURCE_PIN="727600ede64523c899680dec84f2edc1ec4d2d2e"

def blob(b):
    return hashlib.sha1(b"blob "+str(len(b)).encode()+b"\0"+b).hexdigest()

def stage_verdict(root):
    # Caller must have verified the original archive and R111 overlay.
    root=Path(root).resolve(strict=True)
    for p,pin in PINS.items():
        q=root/p
        if q.resolve()!=q or not q.is_file() or blob(q.read_bytes())!=pin:
            raise ValueError("HOLD_VERDICT_DEPENDENCY:"+p)
    raw=SOURCE.read_bytes()
    if blob(raw)!=SOURCE_PIN:
        raise ValueError("HOLD_VERDICT_SOURCE")
    dst=root/DEST
    if dst.resolve()!=dst or dst.exists():
        raise ValueError("HOLD_VERDICT_OVERWRITE")
    dst.parent.mkdir(parents=True,exist_ok=True)
    with dst.open("xb") as f:
        f.write(raw)
    return dst

if __name__=="__main__":
    import sys
    print(stage_verdict(sys.argv[1]))
