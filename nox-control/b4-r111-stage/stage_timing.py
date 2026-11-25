"""Add the exact B4 release entrypoint to an already verified R111 extraction."""
import hashlib
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
SOURCE=HERE.parent/"b4-r111/timing_review_projection.cjs"
DEST="nox-control/b4-r111/timing_review.cjs"
JOINT_DEST="nox-control/d3-r113/timing_review.cjs"
PINS={
    "nox-control/b2-r110/reported_review.cjs":"ea2a46f68770ae613ae6645ddb48de52d37eb9b7",
    "nox-control/a3-r109-r80/joint_frozen.cjs":"8ccc4877f610e6ba32f0bf19efdd7105b6fdedf9",
    "nox-control/b2-r108/atomic_ordered_quality.cjs":"2bd2efcaea708498871b6f913e4b28d5bb8ca90e",
    "nox-control/a3-r109-r80/frozen/b3_r80_frozen_byte_ingress.cjs":"8a95bf6eef67b92964f9a77c54ba71822bdb4b4d",
    "nox-control/a6-r109-r80-release/release.json":"513f61f098574f438b8f9974cfd7ca5f7002428d",
    # Full static local require() closure of the extracted timing entrypoint.
    "nox-control/b2-r108/b4_r75_ordered_completion_pair.cjs":"3bbef66163dc365fbaea50b054d9744a25fbdf31",
    "nox-control/b2-r108/b4_r74_completion_pair.cjs":"3668810ff5018d4a2ef7adb69952230118d1fb10",
    "nox-control/d3-r107/donor/b4_r74_completion_pair.cjs":"ab7c5f1f82d0163af2fe60ada05b7f9cde3c42e9",
    "nox-control/d3-r107/donor/b4_r73_pinned_disposition_metric_bridge.cjs":"0eb3f3e1ab9502c0014f9dd7b1b280f4e3fb04f8",
    "nox-control/d3-r107/donor/b4_r72_final_disposition_metric_fence.cjs":"3e31947d7b562d88db13c3c9e3a2a4405ef56ad7",
    "nox-control/d3-r107/donor/b4_r70_completion_metric_fence.cjs":"f539ef04db3b8531b3b16f71eebf21f67c12cfcc",
    "nox-control/a3-r109-r80/frozen/b3_r71_physical_terminal_composition.cjs":"a2f27861d4b7f681059aa1c41c945034c881c296",
    "nox-control/a3-r109-r80/frozen/b3_r66_raw_readback_binding.cjs":"c4331cc22cb94da0c67fa765e27c838d7b354c66",
    "nox-control/a3-r109-r80/frozen/b3_r65_r64_physical_pin_check.cjs":"1e22eff92da6b951ad22dea2b2db09201b2d371b",
    "nox-control/a3-r109-r80/frozen/b3_r70_s03_terminal_identity.cjs":"64847800e02998aaaad98823d02dd6976c431712",
    "nox-control/a3-r109-r80/frozen/b3_r69_exchange_scope_binding.cjs":"18b3be8fc4264b32d51a57ad4db367b3ba786d41",
    "nox-control/a3-r109-r80/frozen/b3_r68_route_binding.cjs":"6d0fef57783346fe33d59ca39a625015514ae168",
}
SOURCE_PIN="dd1aaf8637c6ffa04ac45d32b05941e9446facc7"

def blob(b):
    return hashlib.sha1(b"blob "+str(len(b)).encode()+b"\0"+b).hexdigest()

def stage_timing(root, *, joint=False):
    # Caller must have verified the original archive and R111 overlay.
    root=Path(root).resolve(strict=True)
    for p,pin in PINS.items():
        q=root/p
        if q.resolve()!=q or not q.is_file() or blob(q.read_bytes())!=pin:
            raise ValueError("HOLD_TIMING_DEPENDENCY:"+p)
    raw=SOURCE.read_bytes()
    if blob(raw)!=SOURCE_PIN:
        raise ValueError("HOLD_TIMING_SOURCE")
    dst=root/(JOINT_DEST if joint else DEST)
    other=root/(DEST if joint else JOINT_DEST)
    if other.exists() or other.is_symlink():
        raise ValueError("HOLD_TIMING_DUPLICATE_DESTINATION")
    if dst.resolve()!=dst or dst.is_symlink():
        raise ValueError("HOLD_TIMING_OVERWRITE")
    if dst.exists():
        # The joint owner may already have staged this exact immutable donor.
        if joint and dst.is_file() and dst.read_bytes()==raw:
            return dst
        raise ValueError("HOLD_TIMING_OVERWRITE")
    dst.parent.mkdir(parents=True,exist_ok=True)
    with dst.open("xb") as f:
        f.write(raw)
    return dst

if __name__=="__main__":
    import sys
    print(stage_timing(sys.argv[1]))
