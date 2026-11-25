"""Build one deterministic source-only delivery artifact, never install it."""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import subprocess
import zipfile

ROOT = Path("nox-control/d3-r95")
R93 = Path("nox-control/d3-r93/release.json")
EXTENSIONS = {".py", ".js", ".cjs", ".mjs"}

def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args])

def blob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def read(repo, path, expected=None):
    path = str(path)
    raw = git(repo, "show", "HEAD:" + path)
    if expected is not None and blob(raw) != expected:
        raise ValueError("HOLD_JOINT_PIN:" + path)
    return raw

def build(repo):
    own = ROOT / "release.json"
    own_raw = read(repo, own)
    cfg = json.loads(own_raw)
    if any(cfg[k] is not False for k in ("native_accepted", "authentication_verified",
                                        "next_post_allowed", "training_admitted")):
        raise ValueError("HOLD_JOINT_AUTHORITY")
    parent = git(repo, "rev-parse", "HEAD^").decode().strip()
    if parent != cfg["parent"]:
        raise ValueError("HOLD_JOINT_PARENT")
    r93_raw = read(repo, R93, cfg["r93_manifest"]["blob"])
    r93 = json.loads(r93_raw)
    data = {str(own): own_raw, str(R93): r93_raw}
    pins = {x["path"]: x["blob"] for x in cfg["wire"] + r93["donors"]}
    pins[r93["entrypoint"]] = r93["entrypoint_blob"]
    dirs = r93["python_paths"] + ["nox-control/d3-r74/staging/b4"]
    for path in dirs:
        if not path.startswith("nox-control/") or ".." in PurePosixPath(path).parts:
            raise ValueError("HOLD_JOINT_SCOPE")
        for name in git(repo, "ls-tree", "-r", "-z", "--name-only", "HEAD", "--", path).decode().split("\0"):
            if not name:
                continue
            p = PurePosixPath(name)
            if p.suffix not in EXTENSIONS or any(x in ("tests", "__pycache__") for x in p.parts):
                continue
            if p.name.startswith("test_") or p.name.startswith("test.") or p.name.endswith(("_test.py", ".test.js", ".test.cjs", ".test.mjs")):
                continue
            data[name] = read(repo, name, pins.get(name))
    for name, expected in pins.items():
        data[name] = read(repo, name, expected)
    # Preserve paths and import precedence instead of flattening different versions.
    layout = {"schema":"NOX_JOINT_SOURCE_LAYOUT_V1", "native_accepted":False,
              "authentication_verified":False, "next_post_allowed":False,
              "training_admitted":False, "python_paths":r93["python_paths"],
              "wire_path":str(ROOT / "wire"),
              "files":[{"path":name,"git_blob":blob(raw),"sha256":sha(raw),"bytes":len(raw)}
                       for name,raw in sorted(data.items())]}
    data["JOINT_SOURCE_MANIFEST.json"] = (json.dumps(layout,sort_keys=True,indent=2)+"\n").encode()
    out = io.BytesIO()
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_STORED) as z:
        for name, raw in sorted(data.items()):
            info = zipfile.ZipInfo(name,(1980,1,1,0,0,0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            z.writestr(info,raw)
    return out.getvalue()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    raw=build(args.repo.resolve())
    with args.output.open("xb") as f:
        f.write(raw)
    print(json.dumps({"artifact_sha256":sha(raw),"bytes":len(raw),"native_accepted":False}))

if __name__ == "__main__":
    main()
