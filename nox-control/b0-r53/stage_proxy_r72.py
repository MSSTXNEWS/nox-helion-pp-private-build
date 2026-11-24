"""Deterministic B0 proxy/browser owner staging; no runtime deployment."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import zipfile

B0 = "1610a9688bae986a30621befc58b004e07b67d31"
B1 = "2e26491241fb2483e6b6c2a4647810ae4ed15058"
FILES = (
    ("b0_proxy_stream_iter.py", B0, "nox-control/b0-r53/b0_proxy_stream_iter.py", "fa6ac58ac4af6797b1d61b0e3c1ee8950641ce79"),
    ("b0_named_delta_encoder.py", B0, "nox-control/b0-r53/b0_named_delta_encoder.py", "c7d0c351b0239bb7155ffbc8c0362e919ee79cb1"),
    ("b1_browser_bundle.js", B1, "nox-control/b1-r79/b1_browser_bundle.js", "b42f00e572ad000b87d7e9e5bf210aba0362494a"),
)

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def build(repo):
    data, pins = {}, []
    for name, commit, path, pin in FILES:
        raw = subprocess.check_output(["git", "-C", str(repo), "show", commit + ":" + path])
        blob = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()
        if blob != pin:
            raise ValueError("HOLD_PROXY_STAGING_PIN:" + name)
        data[name] = raw
        pins.append(dict(name=name, commit=commit, path=path, git_blob=pin, sha256=digest(raw), bytes=len(raw)))
    data["manifest.json"] = (json.dumps(dict(schema="NOX_B0_R72_PROXY_STAGING_V1",
        native_accepted=False, authentication_verified=False, next_post_allowed=False,
        scope="proxy_browser_source_only", bridge_role="separate_B5_R74", files=pins), sort_keys=True, indent=2) + "\n").encode()
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_STORED) as z:
        for name, raw in sorted(data.items()):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            z.writestr(info, raw)
    return out.getvalue()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    raw = build(a.repo)
    with a.output.open("xb") as f:
        f.write(raw)
    print(json.dumps(dict(sha256=digest(raw), files=len(FILES), native_accepted=False)))

if __name__ == "__main__":
    main()
