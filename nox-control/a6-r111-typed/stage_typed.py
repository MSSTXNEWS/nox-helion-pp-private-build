"""Add only typed producer files to an existing verified extracted layout."""
import hashlib, json, pathlib, sys
HERE=pathlib.Path(__file__).resolve().parent
CFG=json.loads((HERE/"release_input.json").read_bytes())
def blob(b):
    return hashlib.sha1(b"blob "+str(len(b)).encode()+b"\0"+b).hexdigest()
def require(condition, reason):
    if not condition: raise ValueError("HOLD_"+reason)
def stage_typed(root):
    root=pathlib.Path(root).resolve()
    m=json.loads((root/"JOINT_SOURCE_MANIFEST.json").read_bytes())
    require(m["schema"]=="NOX_A6_FROZEN_OFFLINE_LAYOUT_V1","BASE_LAYOUT")
    require(m["frozen_python_paths"]==["nox-control/a3-r109-r80",CFG["frozen_namespace"]],"FROZEN_NAMESPACE")
    require(not set(m["frozen_python_paths"]) & set(m["python_paths"]),"NAMESPACE_ALIAS")
    flags=("host_provider_bound","native_accepted","authentication_verified","ack_allowed","next_post_allowed","training_admitted")
    require(all(m[k] is False and CFG[k] is False for k in flags),"AUTHORITY")
    records={r["path"]:r for r in m["files"]}
    frozen=root/CFG["frozen_namespace"]
    for path,r in records.items():
        if path.startswith(CFG["frozen_namespace"]+"/"):
            raw=(root/path).read_bytes()
            require(blob(raw)==r["git_blob"] and hashlib.sha256(raw).hexdigest()==r["sha256"],"FROZEN_PIN")
    donor=(HERE/"typed_prefix.py").read_bytes()
    require(blob(donor)==CFG["typed_donor_blob"],"TYPED_DONOR")
    files={"typed_prefix.py":donor,"freeze_typed_release.py":(HERE/"freeze_typed_release.py").read_bytes()}
    require(all(not (frozen/n).exists() for n in files),"OVERWRITE")
    for n,raw in files.items():
        with (frozen/n).open("xb") as f: f.write(raw)
    return frozen
if __name__=="__main__":
    print(stage_typed(sys.argv[1]))
