"""Deterministic, offline owner staging artifact for B5 completed-dialog evidence.
No runtime installation, native admission, network, POST or S03 writes.
Requires the three immutable donor commits already present in a Git repository.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import zipfile

B5 = "1c9f984247e557f9b2e393f9e2c24246f4f6a8de"
R55 = "4eafa7701e4e3e01c4fc3ecb0cd360054dd9deb3"
B3 = "5a061fb98bd6d9fcab4c64abbe6f65317fef3a47"
FILES = (
    ("b5_r55_pinned.py", R55, "nox-control/b5_s03_verifier_r54.py", "df94c535273dde1fd2609f555d1d615eacfda831"),
    ("b5_chain_guard.py", B5, "nox-control/b5-r63/b5_chain_guard.py", "f321f4ad36867e434ba72db9264a88cf23a91fb8"),
    ("b5_retained_ingress.py", B5, "nox-control/b5-r65/b5_retained_ingress.py", "3e2a8693574608bb773eb7ed4140b574bc5b1efb"),
    ("retained_pair.py", B5, "nox-control/b5-r72/retained_pair.py", "acdd8421db132d7754faa1229e493920d5bf5682"),
    *((name+".cjs", B3, "coordination/onepass/"+name+".cjs", pin) for name,pin in (
        ("b3_r71_physical_terminal_composition", "4c0cd74bc0453d3e450894668338499549217f50"),
        ("b3_r66_raw_readback_binding", "c4331cc22cb94da0c67fa765e27c838d7b354c66"),
        ("b3_r65_r64_physical_pin_check", "1e22eff92da6b951ad22dea2b2db09201b2d371b"),
        ("b3_r70_s03_terminal_identity", "ced1789a8ab19b625888489bf97faa79e07c7e1b"),
        ("b3_r69_exchange_scope_binding", "18b3be8fc4264b32d51a57ad4db367b3ba786d41"),
        ("b3_r68_route_binding", "6d0fef57783346fe33d59ca39a625015514ae168"),
    )),
)
def sha256(raw):
    return hashlib.sha256(raw).hexdigest()

def git_blob(raw):
    return hashlib.sha1(b"blob "+str(len(raw)).encode("ascii")+b"\0"+raw).hexdigest()

def build(repo):
    entries, manifest = {}, []
    for name, commit, path, pin in FILES:
        raw = subprocess.check_output(["git", "-C", str(repo), "show", commit+":"+path])
        if git_blob(raw) != pin:
            raise ValueError("HOLD_STAGING_BLOB_PIN:"+name)
        entries[name] = raw
        manifest.append(dict(name=name, commit=commit, path=path, git_blob=pin, sha256=sha256(raw), bytes=len(raw)))
    entries["manifest.json"] = (json.dumps(dict(schema="NOX_B5_R73_STAGING_V1", scope="completed_dialog_evidence_only",
        native_accepted=False, authentication_verified=False, next_post_allowed=False,
        files=manifest), sort_keys=True, indent=2)+"\n").encode("utf-8")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_STORED) as z:
        for name, raw in sorted(entries.items()):
            info = zipfile.ZipInfo(name, (1980,1,1,0,0,0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            z.writestr(info, raw)
    return out.getvalue()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args=parser.parse_args()
    raw=build(args.repo)
    # Never overwrite even an existing artifact; caller chooses an isolated directory.
    with args.output.open("xb") as f:
        f.write(raw)
    print(json.dumps(dict(artifact_sha256=sha256(raw), files=len(FILES), native_accepted=False)))

if __name__ == "__main__":
    main()
