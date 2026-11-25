"""Add the exact B2 verdict entrypoint to an already verified R111 extraction."""
import hashlib
from pathlib import Path

HERE=Path(__file__).resolve().parent
SOURCE=HERE.parent/"b2-r112/verdict_consistency.cjs"
DEST="nox-control/b2-r112/verdict_consistency.cjs"
PINS={
    "nox-control/d3-r111/inputs/b1.json":"3de1fd004cfd76ca17cf7a83dabd7036fb874a38",
    "nox-control/d3-r111/inputs/b3.json":"3f9e77a561c6bb970f5482322bd62a8c2dfe8b25",
    "nox-control/b2-r110/reported_review.cjs":"ea2a46f68770ae613ae6645ddb48de52d37eb9b7",
    "nox-control/a3-r109-r80/joint_frozen.cjs":"8ccc4877f610e6ba32f0bf19efdd7105b6fdedf9",
    "nox-control/b2-r108/atomic_ordered_quality.cjs":"2bd2efcaea708498871b6f913e4b28d5bb8ca90e",
    "nox-control/a3-r109-r80/frozen/b3_r80_frozen_byte_ingress.cjs":"8a95bf6eef67b92964f9a77c54ba71822bdb4b4d",
    "nox-control/a6-r109-r80-release/release.json":"513f61f098574f438b8f9974cfd7ca5f7002428d",
    # Complete literal local require closure of R110, including nested timing and S03 checks.
    "nox-control/a3-r109-r80/frozen/b3_r71_physical_terminal_composition.cjs":"a2f27861d4b7f681059aa1c41c945034c881c296",
    "nox-control/b2-r108/b4_r75_ordered_completion_pair.cjs":"3bbef66163dc365fbaea50b054d9744a25fbdf31",
    "nox-control/a3-r109-r80/frozen/b3_r66_raw_readback_binding.cjs":"c4331cc22cb94da0c67fa765e27c838d7b354c66",
    "nox-control/a3-r109-r80/frozen/b3_r70_s03_terminal_identity.cjs":"64847800e02998aaaad98823d02dd6976c431712",
    "nox-control/b2-r108/b4_r74_completion_pair.cjs":"3668810ff5018d4a2ef7adb69952230118d1fb10",
    "nox-control/a3-r109-r80/frozen/b3_r65_r64_physical_pin_check.cjs":"1e22eff92da6b951ad22dea2b2db09201b2d371b",
    "nox-control/a3-r109-r80/frozen/b3_r69_exchange_scope_binding.cjs":"18b3be8fc4264b32d51a57ad4db367b3ba786d41",
    "nox-control/d3-r107/donor/b4_r74_completion_pair.cjs":"ab7c5f1f82d0163af2fe60ada05b7f9cde3c42e9",
    "nox-control/a3-r109-r80/frozen/b3_r68_route_binding.cjs":"6d0fef57783346fe33d59ca39a625015514ae168",
    "nox-control/d3-r107/donor/b4_r73_pinned_disposition_metric_bridge.cjs":"0eb3f3e1ab9502c0014f9dd7b1b280f4e3fb04f8",
    "nox-control/d3-r107/donor/b4_r72_final_disposition_metric_fence.cjs":"3e31947d7b562d88db13c3c9e3a2a4405ef56ad7",
    "nox-control/d3-r107/donor/b4_r70_completion_metric_fence.cjs":"f539ef04db3b8531b3b16f71eebf21f67c12cfcc",
}
SOURCE_PIN="727600ede64523c899680dec84f2edc1ec4d2d2e"

def blob(b):
    return hashlib.sha1(b"blob "+str(len(b)).encode()+b"\0"+b).hexdigest()

def stage_verdict(root):
    # Caller must have verified the original archive and R111 overlay.
    root=Path(root).resolve(strict=True)
    # R111 stage_overlay verifies the manifest in checkout but does not copy it into root.
    if blob((HERE.parent/"d3-r111/release.json").read_bytes())!="fd6b4dd58465de1b7874c36f292acd98be7bb6c5":
        raise ValueError("HOLD_VERDICT_MANIFEST")
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
