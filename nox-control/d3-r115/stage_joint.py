"""Compose exact existing offline stages, without rebuilding the archive."""
import hashlib, importlib.util, json, pathlib, subprocess, sys
P=pathlib.Path
ROOT=P(__file__).resolve().parents[2]
def blob(b): return hashlib.sha1(b"blob "+str(len(b)).encode()+b"\0"+b).hexdigest()
def exact(p,pin):
    if not p.is_file() or p.is_symlink() or blob(p.read_bytes())!=pin:
        raise ValueError("HOLD_R115_PIN:"+str(p))
    return p
def load(p,name):
    spec=importlib.util.spec_from_file_location(name,p)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
def snapshot(root):
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}
def stage_all(archive,target,donors):
    target=P(target).resolve()
    donors=P(donors).resolve()
    overlay=load(exact(ROOT/"nox-control/d3-r111/stage_overlay.py","82cbfac33a5cc56d53d9547dc8511d5968efbe58"),"r115_overlay")
    exact(ROOT/"nox-control/d3-r111/release.json","fd6b4dd58465de1b7874c36f292acd98be7bb6c5")
    overlay.stage(P(archive).read_bytes(),target)
    before=snapshot(target)
    if len(before)!=93: raise ValueError("HOLD_R115_BASE_COUNT")
    a6=donors/"a6/nox-control"
    exact(a6/"a6-r111-typed/release_input.json","d19f8fa8e38110ffb5f945993f3183069e9c9329")
    exact(a6/"a6-r111-typed/freeze_typed_release.py","3881e1f6c6e229c440eabde96ef514891f27b5bc")
    load(exact(a6/"a6-r111-typed/stage_typed.py","c40841f9aaee849738c0a48a600a17d63c46d482"),"r115_typed").stage_typed(target)
    exact(a6/"a6-r82-failed/diagnostic.py","b7fa386cf4589b7fe42ee35e79ead34177d71d83")
    load(exact(a6/"a6-r82-failed/stage_failed.py","e274f248de93f1dd167824363916599f6749a36a"),"r115_failed").stage_failed(target)
    for key,path,pin,func in (
        ("a3","nox-control/a3-r114-stage/stage_browser.cjs","7bac8b741e4df71d83ccc5f198446d317f80f936","stageBrowser"),
        ("b3","nox-control/b3-r84-stage/stage_physical.cjs","7df0d391b87264bf6bfe5f6891db1c6104c0c309","stagePhysical")):
        entry=exact(donors/key/path,pin)
        subprocess.run(["node","-e","require(process.argv[1])[process.argv[2]](process.argv[3])",str(entry),func,str(target)],check=True,cwd=target)
    load(exact(donors/"b4/nox-control/b4-r111-stage/stage_timing.py","61be5423e18f7bff24d336bef0222158fe618798"),"r115_timing").stage_timing(target,joint=True)
    load(exact(donors/"b2/nox-control/b2-r112-stage/stage_verdict.py","12f40698dc1a0c8c372b5308607725f88ae5d9c1"),"r115_verdict").stage_verdict(target)
    entry=target/"nox-control/d3-r114/joint_extracted.cjs"
    with entry.open("xb") as f: f.write((ROOT/"nox-control/d3-r115/joint_extracted.cjs").read_bytes())
    after=snapshot(target)
    if any(after.get(k)!=v for k,v in before.items()): raise ValueError("HOLD_R115_BASE_MUTATION")
    if len(after)-len(before)!=20: raise ValueError("HOLD_R115_STAGE_COUNT:"+str(len(after)-len(before)))
    js="""const assert=require('node:assert/strict');const {makeReleaseEvidenceReview,releasePins}=require(process.argv[1]);
assert.equal(Object.keys(releasePins().assets).length,5);
let n=0;const a=makeReleaseEvidenceReview(()=>{n++;return null;})(Buffer.from('[]'),'{}');
assert.equal(a.status,'HOLD_ROUTE_DETACHED');assert.equal(n,1);
for(const k of ['native_accepted','authentication_verified','host_provider_bound','ack_allowed','next_post_allowed','training_admitted'])assert.equal(a[k],false);
assert.equal(a.metrics,null);assert.equal(a.quality_sample,null);"""
    subprocess.run(["node","-e",js,str(entry)],check=True,cwd=target)
    return {"unchanged":len(before),"added":len(after)-len(before),"entry":entry.relative_to(target).as_posix(),"entry_sha256":after[entry.relative_to(target).as_posix()],"native_accepted":False,"host_provider_bound":False,"positive_dialog_verified":False}
if __name__=="__main__":
    print(json.dumps(stage_all(*sys.argv[1:])))
