"""Add the exact B4 release entrypoint to an already verified R111 extraction."""
import hashlib
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
SOURCE=HERE.parent/"b4-r111/timing_review.cjs"
DEST="nox-control/b4-r111/timing_review.cjs"
PINS={
    "nox-control/b2-r110/reported_review.cjs":"ea2a46f68770ae613ae6645ddb48de52d37eb9b7",
    "nox-control/a3-r109-r80/joint_frozen.cjs":"8ccc4877f610e6ba32f0bf19efdd7105b6fdedf9",
    "nox-control/b2-r108/atomic_ordered_quality.cjs":"2bd2efcaea708498871b6f913e4b28d5bb8ca90e",
    "nox-control/a3-r109-r80/frozen/b3_r80_frozen_byte_ingress.cjs":"8a95bf6eef67b92964f9a77c54ba71822bdb4b4d",
    "nox-control/a6-r109-r80-release/release.json":"513f61f098574f438b8f9974cfd7ca5f7002428d",
}
SOURCE_PIN="b202135f9ba1114c4501b1c8c5be40fe8faa5a51"

def blob(b):
    return hashlib.sha1(b"blob "+str(len(b)).encode()+b"\0"+b).hexdigest()

def stage_timing(root):
    # Caller must have verified the original archive and R111 overlay.
    root=Path(root).resolve(strict=True)
    for p,pin in PINS.items():
        q=root/p
        if q.resolve()!=q or not q.is_file() or blob(q.read_bytes())!=pin:
            raise ValueError("HOLD_TIMING_DEPENDENCY:"+p)
    raw=SOURCE.read_bytes()
    if blob(raw)!=SOURCE_PIN:
        raise ValueError("HOLD_TIMING_SOURCE")
    dst=root/DEST
    if dst.resolve()!=dst or dst.exists():
        raise ValueError("HOLD_TIMING_OVERWRITE")
    dst.parent.mkdir(parents=True,exist_ok=True)
    with dst.open("xb") as f:
        f.write(raw)
    return dst

if __name__=="__main__":
    import sys
    print(stage_timing(sys.argv[1]))
