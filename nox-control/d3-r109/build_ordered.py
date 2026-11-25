"""R109: build and read back the ordered offline quality release, no deployment."""
import hashlib
import io
import json
import pathlib
import subprocess
import sys
import tempfile
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent
REPO = ROOT.parent.parent
MANIFEST = "JOINT_SOURCE_MANIFEST.json"
CFG_PATH = "nox-control/d3-r109/release.json"
FLAGS = ("production_ready","native_accepted","authentication_verified","host_provider_bound",
         "pre_ack_observer_bound","ack_allowed","next_post_allowed","training_admitted")
def git(*args):
    return subprocess.check_output(["git","-C",str(REPO),*args])
def blob(raw):
    return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()
def sha(raw):
    return hashlib.sha256(raw).hexdigest()
def pinned(path, pin):
    raw=git("show","HEAD:"+path)
    if blob(raw)!=pin:
        raise ValueError("HOLD_RELEASE_PIN:"+path)
    return raw
def metadata(data):
    return [{"path":p,"git_blob":blob(b),"sha256":sha(b),"bytes":len(b)} for p,b in sorted(data.items())]
def build(out):
    cfg_raw=git("show","HEAD:"+CFG_PATH)
    cfg=json.loads(cfg_raw)
    assert all(cfg[k] is False for k in FLAGS)
    subprocess.run(["git","-C",str(REPO),"merge-base","--is-ancestor",cfg["parent"],"HEAD"],check=True)
    pinned("nox-control/d3-r99/release.json",cfg["r99_manifest_blob"])
    builder=pinned("nox-control/d3-r99/build_joint.py",cfg["r99_builder_blob"])
    ns={"__name__":"r99_builder"}
    exec(compile(builder,"r99-pinned-builder","exec"),ns)
    with zipfile.ZipFile(io.BytesIO(ns["build"](REPO))) as old:
        prior=json.loads(old.read(MANIFEST))
        data={row["path"]:old.read(row["path"]) for row in prior["files"]}
        assert metadata(data)==prior["files"]
    for path,pin in cfg["pins"].items():
        assert path not in data or blob(data[path])==pin
        data[path]=pinned(path,pin)
    data[CFG_PATH]=cfg_raw
    layout=dict(prior,schema="NOX_R109_ORDERED_OFFLINE_LAYOUT_V1",
                python_paths=cfg["python_prefix"]+[p for p in prior["python_paths"] if p not in cfg["python_prefix"]],
                python_entrypoint=cfg["python_entrypoint"],node_entrypoint=cfg["node_entrypoint"],
                browser_pin_state=cfg["browser_pin_state"],files=metadata(data))
    layout.update({k:False for k in FLAGS})
    data[MANIFEST]=(json.dumps(layout,sort_keys=True,indent=2)+"\n").encode()
    with zipfile.ZipFile(out,"x",compression=zipfile.ZIP_STORED) as z:
        for path,raw in sorted(data.items()):
            info=zipfile.ZipInfo(path,(1980,1,1,0,0))
            info.create_system=3
            info.external_attr=0o100644<<16
            z.writestr(info,raw)
    return cfg
def verify(out,cfg):
    with tempfile.TemporaryDirectory() as tmp,zipfile.ZipFile(out) as z:
        root=pathlib.Path(tmp)
        m=json.loads(z.read(MANIFEST))
        assert all(m[k] is False for k in FLAGS)
        assert m["node_entrypoint"]==cfg["node_entrypoint"] and m["python_entrypoint"]==cfg["python_entrypoint"]
        names=[x["path"] for x in m["files"]]
        assert len(set(names))==len(names) and sorted(z.namelist())==sorted(names+[MANIFEST])
        data={}
        for name in names:
            path=pathlib.PurePosixPath(name)
            assert not path.is_absolute() and ".." not in path.parts
            raw=z.read(name)
            data[name]=raw
            dst=root/path
            dst.parent.mkdir(parents=True,exist_ok=True)
            dst.write_bytes(raw)
        assert metadata(data)==m["files"]
        for path,pin in cfg["pins"].items():
            assert blob(data[path])==pin,path
        code="""import sys,os,pathlib,json
root=pathlib.Path(sys.argv[1])
m=json.loads((root/'JOINT_SOURCE_MANIFEST.json').read_text())
sys.path[:0]=[str(root/p) for p in m['python_paths']]
os.environ['D3_B4_MODULE']=str(root/'nox-control/d3-r74/staging/b4/b4_existing_turn_pair.mjs')
import joint_packet, receipt_id_fence, finalized_observation, browser_projection_gate, b5_retained_ingress, canonical_text
assert joint_packet.review_unique_receipt_ids is receipt_id_fence.review_unique_receipt_ids
assert receipt_id_fence.review_finalized_observations is finalized_observation.review_finalized_observations
assert finalized_observation.review_browser_projection is browser_projection_gate.review_browser_projection
assert canonical_text.load_retained_chain is b5_retained_ingress.load_retained_chain
for mod in (joint_packet,receipt_id_fence,finalized_observation,browser_projection_gate,b5_retained_ingress,canonical_text):
    assert pathlib.Path(mod.__file__).resolve().is_relative_to(root)
assert callable(joint_packet.prepare_joint_packet)
"""
        subprocess.run([sys.executable,"-I","-B","-c",code,str(root)],cwd=root,check=True)
        js="""const assert=require('node:assert/strict');
const {makeOfflinePairReview}=require(process.argv[1]);
assert.equal(typeof makeOfflinePairReview,'function');
const r=makeOfflinePairReview()('{}');
assert.equal(r.status,'HOLD_HOST_PROVIDER');
for(const k of ['native_accepted','training_admitted','ack_allowed','next_post_allowed'])assert.equal(r[k],false);
assert.equal(r.metrics,null);assert.equal(r.quality_sample,null);"""
        subprocess.run(["node","-e",js,str(root/cfg["node_entrypoint"])],cwd=root,check=True)
        print(json.dumps({"files":len(names),"pins":len(cfg["pins"]),"archive_sha256":sha(out.read_bytes()),
                          "ordered_entrypoints":"PASS","host_provider_bound":False,"native_accepted":False}))
if __name__=="__main__":
    out=pathlib.Path(sys.argv[1]).resolve()
    verify(out,build(out))
