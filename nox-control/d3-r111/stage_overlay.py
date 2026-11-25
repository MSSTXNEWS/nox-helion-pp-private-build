"""Use the original A6 ZIP, never rebuild or overwrite it. Offline staging only."""
import hashlib, io, json, pathlib, subprocess, sys, zipfile
HERE=pathlib.Path(__file__).resolve().parent
REPO=HERE.parent.parent
CFG=json.loads((HERE/"release.json").read_text())
FLAGS=("production_ready","native_accepted","authentication_verified","host_provider_bound","pre_ack_observer_bound","ack_allowed","next_post_allowed","training_admitted")
def require(ok,msg):
    if not ok: raise ValueError("HOLD_"+msg)
def sha(b): return hashlib.sha256(b).hexdigest()
def blob(b): return hashlib.sha1(b"blob "+str(len(b)).encode()+b"\0"+b).hexdigest()
def safe(p):
    q=pathlib.PurePosixPath(p)
    require(not q.is_absolute() and q.parts and ".." not in q.parts and str(q)==p and "\\" not in p,"PATH")
    return q
def pinned(raw,pin):
    require(blob(raw)==pin,"OVERLAY_PIN")
    return raw
def stage(outer, target):
    require(all(CFG[k] is False for k in FLAGS),"AUTHORITY")
    require(sha(outer)==CFG["base"]["outer_sha256"],"OUTER_SHA")
    with zipfile.ZipFile(io.BytesIO(outer)) as z:
        names=z.namelist()
        require(len(names)==1 and names[0].endswith(".zip"),"OUTER_LAYOUT")
        inner=z.read(names[0])
    require(sha(inner)==CFG["base"]["inner_sha256"],"INNER_SHA")
    with zipfile.ZipFile(io.BytesIO(inner)) as z:
        m=json.loads(z.read("JOINT_SOURCE_MANIFEST.json"))
        require(all(m[k] is False for k in FLAGS),"BASE_AUTHORITY")
        records=m["files"]
        names=[r["path"] for r in records]
        require(len(names)==len(set(names))==CFG["base"]["files"],"BASE_COUNT")
        require(sorted(z.namelist())==sorted(names+["JOINT_SOURCE_MANIFEST.json"]),"BASE_LAYOUT")
        data={}
        for r in records:
            p=r["path"]; safe(p); b=z.read(p)
            require(blob(b)==r["git_blob"] and sha(b)==r["sha256"] and len(b)==r["bytes"],"BASE_PIN")
            data[p]=b
        data["JOINT_SOURCE_MANIFEST.json"]=z.read("JOINT_SOURCE_MANIFEST.json")
    require(blob(data["nox-control/a6-r109-r80-release/release.json"])==CFG["base"]["manifest_blob"],"BASE_MANIFEST")
    for p in CFG["pins"]:
        dst=p["destination"]; safe(dst); require(dst not in data,"OVERWRITE")
        data[dst]=pinned((REPO/dst).read_bytes(),p["blob"])
    def read(p): return json.loads(data["nox-control/d3-r111/inputs/"+p+".json"])
    b0,b1,b3=read("b0"),read("b1"),read("b3")
    for r in (b0["base_release"],b1["base_release"],b3["release"]):
        require(r["commit"]==CFG["base"]["commit"] and r["artifact_id"]==CFG["base"]["artifact_id"] and r["inner_sha256"]==CFG["base"]["inner_sha256"],"DONOR_BASE")
    require(all(r["native_accepted"] is False and r["host_provider_bound"] is False for r in (b0,b1,b3)),"DONOR_AUTHORITY")
    require(b1["wire_input"]["blob"]==CFG["pins"][0]["blob"],"WIRE_BIND")
    require(b1["browser"]["blob"]==CFG["pins"][6]["blob"]==b3["roles"]["browser_adapter"]["blob"],"BROWSER_BIND")
    require(b3["roles"]["physical_bridge"]["blob"]==CFG["pins"][7]["blob"],"BRIDGE_BIND")
    require([p["blob"] for p in CFG["pins"][3:6]]==[p["blob"] for p in b0["wire_candidates"]],"WIRE_CLOSURE")
    require(b3["pins"][-1]["blob"]==CFG["pins"][-1]["blob"],"REVIEW_BIND")
    require(b1["r100"]["provider_status"]=="HOLD_UNBOUND","DISPOSITION")
    target.mkdir(parents=True,exist_ok=False)
    for p,b in data.items():
        dst=target/safe(p); dst.parent.mkdir(parents=True,exist_ok=True); dst.write_bytes(b)
    return len(records),len(CFG["pins"])
def verify(root):
    wire=root/"nox-control/d3-r111/wire"
    code="import sys,pathlib; p=pathlib.Path(sys.argv[1]); sys.path.insert(0,str(p)); import b0_http_chunked_r76 as w,b0_proxy_stream_iter as i,b0_named_delta_encoder as e; assert w.ProxyDeltaBody is i.ProxyDeltaBody; assert callable(w.write_chunked_sse) and callable(e.encode_native_delta); assert all(pathlib.Path(m.__file__).parent==p for m in (w,i,e))"
    subprocess.run([sys.executable,"-I","-B","-c",code,str(wire)],check=True,cwd=root)
    browser=root/"nox-control/d3-r111/browser/b1_browser_bundle.js"
    bridge=root/"nox-control/d3-r111/bridge/b3_r64_eof_candidate.js"
    subprocess.run(["node","--check",str(browser)],check=True)
    subprocess.run(["node","--check",str(bridge)],check=True)
    js="const a=require('node:assert/strict');const {makeReportedReview}=require(process.argv[1]);const r=makeReportedReview()(Buffer.from('[]'),'{}');a.equal(r.status,'HOLD_RELEASE_PROVIDER');for(const k of ['native_accepted','authentication_verified','training_admitted','ack_allowed','next_post_allowed'])a.equal(r[k],false);a.equal(r.reported_review_diagnostics,null);a.equal(r.metrics,null);a.equal(r.quality_sample,null)"
    subprocess.run(["node","-e",js,str(root/"nox-control/b2-r110/reported_review.cjs")],check=True,cwd=root)
    try: pinned(b"tampered",CFG["pins"][0]["blob"])
    except ValueError: pass
    else: raise ValueError("HOLD_NEGATIVE_TEST")
if __name__=="__main__":
    root=pathlib.Path(sys.argv[2]).resolve()
    base,overlay=stage(pathlib.Path(sys.argv[1]).read_bytes(),root)
    verify(root)
    print(json.dumps({"base_files":base,"overlay_files":overlay,"exact_extracted_overlay":"PASS","bridge_executed":False,"full_joint_ci":False,"host_provider_bound":False,"native_accepted":False}))
