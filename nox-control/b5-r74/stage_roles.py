"""Offline B5 staging companion. No install, network or native authority."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import zipfile

R73 = "241761e6b4fe58be3e38a5189666cfd4dde4905b"
R64 = "3581b30134446f5e131a0510bb719a78dbf75c0d"
BRIDGE_PATH = "coordination/onepass/b3_r64_eof_candidate.js"
BRIDGE_BLOB = "66595eac01c562aff4daae68f5d146aaed64cbbe"
BRIDGE_SHA = "c44b5aa2ef3d45246276a24bbcfad30bf76533fc2e08089eb91b442002643dc7"
EVIDENCE_SHA = "19e6bc317d85668235938c853f242420cc8f27f6d917bae728b17651428bda3f"
def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def bridge_bytes(repo):
    return subprocess.check_output(["git", "-C", str(repo), "show", R64 + ":" + BRIDGE_PATH])

def compose(evidence, bridge):
    if sha(evidence) != EVIDENCE_SHA:
        raise ValueError("HOLD_R73_EVIDENCE_PIN")
    if sha(bridge) != BRIDGE_SHA or len(bridge) != 25388:
        raise ValueError("HOLD_R64_PHYSICAL_BRIDGE_PIN")
    blob = hashlib.sha1(b"blob " + str(len(bridge)).encode("ascii") + b"\0" + bridge).hexdigest()
    if blob != BRIDGE_BLOB:
        raise ValueError("HOLD_R64_PHYSICAL_BRIDGE_BLOB")
    files = {
        "evidence/b5-r73-staging.zip": evidence,
        "physical-bridge/b3_r64_eof_candidate.js": bridge,
    }
    manifest = dict(schema="NOX_B5_R74_ROLE_CLOSED_STAGING_V1",
                    native_accepted=False, installation_authorized=False,
                    next_post_allowed=False, browser_role="external_required",
                    files=[
                        dict(name="evidence/b5-r73-staging.zip", role="completed_dialog_evidence",
                             commit=R73, sha256=EVIDENCE_SHA, bytes=len(evidence)),
                        dict(name="physical-bridge/b3_r64_eof_candidate.js", role="physical_bridge_candidate",
                             commit=R64, path=BRIDGE_PATH, git_blob=BRIDGE_BLOB,
                             sha256=BRIDGE_SHA, bytes=len(bridge))])
    files["r74-role-manifest.json"] = (json.dumps(manifest, sort_keys=True, indent=2)+"\n").encode()
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, raw in sorted(files.items()):
            info = zipfile.ZipInfo(name, (1980,1,1,0,0,0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, raw)
    return out.getvalue()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = compose(args.evidence.read_bytes(), bridge_bytes(args.repo))
    with args.output.open("xb") as stream:
        stream.write(raw)
    print(json.dumps(dict(sha256=sha(raw), bytes=len(raw), native_accepted=False)))

if __name__ == "__main__":
    main()
