"""Select diagnostic-only B5 R82 on the verified R111 extracted layout."""
import hashlib, json, pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
PINS = {
    "b5_failed_poststate.py": "381a738e54bdb1bba874ee8e0295c957e92b68b5",
    "b5_bound_failed_poststate.py": "878128ef41095f8bf0d14a02281148e96e4a6ba3",
    "b5_receipted_failed_poststate.py": "c6181ce7a16f787b4b68b2507150c6990da2ef83",
    "b5_strict_receipted_poststate.py": "e2997a136b47f06d47eba519e4cd6a87f1c68fb0",
    "typed_failed_poststate.py": "321c12aff561fa6769ce08e1f7b6854e0ebf08ae"
}
BASE = {"b5_r55_pinned.py":"df94c535273dde1fd2609f555d1d615eacfda831",
        "b5_chain_guard.py":"f321f4ad36867e434ba72db9264a88cf23a91fb8"}
def blob(raw):
    return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()
def require(ok, code):
    if not ok: raise ValueError("HOLD_"+code)
def stage_failed(root):
    root=pathlib.Path(root).resolve()
    manifest=json.loads((root/"JOINT_SOURCE_MANIFEST.json").read_bytes())
    flags=("host_provider_bound","native_accepted","authentication_verified",
           "ack_allowed","next_post_allowed","training_admitted")
    require(manifest["schema"]=="NOX_A6_FROZEN_OFFLINE_LAYOUT_V1" and
            all(manifest[k] is False for k in flags),"FAILED_DIAGNOSTIC_BASE")
    frozen=root/"nox-control/a3-r109-r80/frozen"
    records={r["path"]:r for r in manifest["files"]}
    verified={}
    for name,pin in BASE.items():
        f=frozen/name
        raw=f.read_bytes()
        r=records[f.relative_to(root).as_posix()]
        require(blob(raw)==pin==r["git_blob"] and
                hashlib.sha256(raw).hexdigest()==r["sha256"],"FAILED_DIAGNOSTIC_BASE_PIN")
        verified[name]=raw
    for name,pin in PINS.items():
        raw=(HERE/"donors"/name).read_bytes()
        require(blob(raw)==pin,"FAILED_DIAGNOSTIC_DONOR_PIN")
        verified[name]=raw
    raw=(HERE/"diagnostic.py").read_bytes()
    verified["diagnostic.py"]=raw
    dest=root/"nox-control/a6-r82-failed-selected"
    require(not dest.exists(),"FAILED_DIAGNOSTIC_OVERWRITE")
    dest.mkdir()
    for name,data in verified.items():
        with (dest/name).open("xb") as f: f.write(data)
    return dest
if __name__=="__main__":
    print(stage_failed(sys.argv[1]))
