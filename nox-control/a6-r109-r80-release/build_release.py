"""Package existing A3 frozen ingress over the pinned R109 offline release."""
import hashlib
import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent
REPO = ROOT.parent.parent
CFG = "nox-control/a6-r109-r80-release/release.json"
R109 = "nox-control/d3-r109/"
MANIFEST = "JOINT_SOURCE_MANIFEST.json"
FLAGS = ("production_ready","native_accepted","authentication_verified","host_provider_bound",
         "pre_ack_observer_bound","ack_allowed","next_post_allowed","training_admitted")

def git(*args):
    return subprocess.check_output(["git","-C",str(REPO),*args])
def blob(raw):
    return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()
def sha(raw):
    return hashlib.sha256(raw).hexdigest()
def pinned(path, expected):
    raw=git("show","HEAD:"+path)
    if blob(raw)!=expected:
        raise ValueError("HOLD_RELEASE_PIN:"+path)
    return raw
def metadata(data):
    return [{"path":p,"git_blob":blob(b),"sha256":sha(b),"bytes":len(b)} for p,b in sorted(data.items())]

def build(out):
    raw=git("show","HEAD:"+CFG)
    cfg=json.loads(raw)
    assert all(cfg[k] is False for k in FLAGS)
    subprocess.run(["git","-C",str(REPO),"merge-base","--is-ancestor",cfg["parent"],"HEAD"],check=True)
    pinned(R109+"release.json",cfg["r109_manifest_blob"])
    builder=pinned(R109+"build_ordered.py",cfg["r109_builder_blob"])
    ns={"__file__":str(REPO/(R109+"build_ordered.py")),"__name__":"r109_builder"}
    exec(compile(builder,"pinned-r109","exec"),ns)
    with tempfile.TemporaryDirectory() as t:
        old=pathlib.Path(t)/"r109.zip"
        ns["build"](old)
        with zipfile.ZipFile(old) as z:
            prior=json.loads(z.read(MANIFEST))
            data={r["path"]:z.read(r["path"]) for r in prior["files"]}
            assert metadata(data)==prior["files"]
    assert all(prior[k] is False for k in FLAGS)
    for p,pin in cfg["pins"].items():
        assert p not in data
        data[p]=pinned(p,pin)
    data[CFG]=raw
    layout=dict(prior,schema="NOX_A6_FROZEN_OFFLINE_LAYOUT_V1",
        prior_node_entrypoint=prior["node_entrypoint"],
        node_entrypoint=cfg["node_entrypoint"],
        frozen_python_paths=cfg["frozen_python_paths"],
        frozen_python_entrypoint=cfg["frozen_python_entrypoint"],
        frozen_python_namespace="separate interpreter; never append to canonical python_paths",
        detached_provider_required=True,files=metadata(data))
    layout.update({k:False for k in FLAGS})
    data[MANIFEST]=(json.dumps(layout,sort_keys=True,indent=2)+"\n").encode()
    with zipfile.ZipFile(out,"x",compression=zipfile.ZIP_STORED) as z:
        for p,b in sorted(data.items()):
            info=zipfile.ZipInfo(p,(1980,1,1,0,0,0))
            info.create_system=3
            info.external_attr=0o100644<<16
            z.writestr(info,b)
    return cfg

def verify(out,cfg):
    with tempfile.TemporaryDirectory() as t,zipfile.ZipFile(out) as z:
        root=pathlib.Path(t)
        manifest=z.read(MANIFEST)
        m=json.loads(manifest)
        assert all(m[k] is False for k in FLAGS)
        assert m["node_entrypoint"]==cfg["node_entrypoint"]
        assert m["frozen_python_paths"]==cfg["frozen_python_paths"]
        assert not set(m["frozen_python_paths"]) & set(m["python_paths"])
        names=[r["path"] for r in m["files"]]
        assert len(set(names))==len(names) and sorted(z.namelist())==sorted(names+[MANIFEST])
        data={}
        for p in names:
            path=pathlib.PurePosixPath(p)
            assert not path.is_absolute() and ".." not in path.parts
            b=z.read(p)
            data[p]=b
            dst=root/path
            dst.parent.mkdir(parents=True,exist_ok=True)
            dst.write_bytes(b)
        assert metadata(data)==m["files"]
        for p,pin in cfg["pins"].items():
            assert blob(data[p])==pin
        (root/MANIFEST).write_bytes(manifest)
        py="""import sys,pathlib,json
root=pathlib.Path(sys.argv[1])
m=json.loads((root/'JOINT_SOURCE_MANIFEST.json').read_bytes())
sys.path[:0]=[str(root/p) for p in m['frozen_python_paths']]
import freeze_release, frozen_consumer, bind_retained_pair, canonical_text, b5_retained_ingress, b5_r55_pinned
assert freeze_release.freeze_consumer_payload is frozen_consumer.freeze_consumer_payload
assert callable(freeze_release.freeze_release_payload)
for mod in (frozen_consumer,bind_retained_pair,canonical_text,b5_retained_ingress,b5_r55_pinned):
    assert pathlib.Path(mod.__file__).resolve().parent == root/m['frozen_python_paths'][1]
assert not any(str(root/p) in sys.path for p in m['python_paths'])
"""
        subprocess.run([sys.executable,"-I","-B","-c",py,str(root)],cwd=root,check=True)
        js="""const assert=require('node:assert/strict');
const {makeFrozenOrderedReview}=require(process.argv[1]);
const r=makeFrozenOrderedReview()(Buffer.from('[]'),'{}');
assert.equal(r.status,'HOLD_RELEASE_PROVIDER');
for(const k of ['native_accepted','authentication_verified','training_admitted','ack_allowed','next_post_allowed'])assert.equal(r[k],false);
assert.equal(r.metrics,null);assert.equal(r.quality_sample,null);"""
        subprocess.run(["node","-e",js,str(root/cfg["node_entrypoint"])],cwd=root,check=True)
        print(json.dumps({"files":len(names),"new_pins":len(cfg["pins"]),"archive_sha256":sha(out.read_bytes()),
                          "extracted_frozen_entrypoints":"PASS","host_provider_bound":False,"native_accepted":False}))

if __name__=="__main__":
    out=pathlib.Path(sys.argv[1]).resolve()
    verify(out,build(out))
