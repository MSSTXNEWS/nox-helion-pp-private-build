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
    exact(a6/"a6-r82-failed/diagnostic.py","c2b376d1451e681c76dc5cd212ffba133beeb42c")
    load(exact(a6/"a6-r82-failed/stage_failed.py","f494782ce182ab45bfb08b006aa3fee154c018a6"),"r115_failed").stage_failed(target)
    # B0 exact framework addendum; do not select or activate a framing owner.
    b0=donors/"b0/nox-control/b0-r53"
    r81=exact(b0/"stage_framework_r81.py","1acd388546891a48360024c2029bc54b55272e69")
    r84=exact(b0/"stage_framework_r84.py","eb6d75d66aece439be8e92d32b4ff277a43aaa29")
    wire=target/"nox-control/d3-r111/wire"
    # Isolated import path, no module leakage to the other stages.
    subprocess.run([sys.executable,"-I","-B","-c", """import sys,pathlib
sys.path.insert(0,sys.argv[1])
from stage_framework_r81 import stage_framework
from stage_framework_r84 import stage_r83
stage_framework(sys.argv[2])
stage_r83(sys.argv[2])
""",str(b0),str(target)],check=True,cwd=target)
    exact(wire/"b0_framework_r80.py","659876e07af733988d8499221180f66c9d90ca20")
    exact(wire/"b0_framework_r83.py","9f7ae9ddc837d4fb67a2584c647fdec85764e05f")
    closure=exact(b0/"framing_source_closure_r86.json","7a2d7e9b3c9abf1a5af2a296e55fb0dcce4c40cc")
    with (wire.parent/"framing_source_closure_r86.json").open("xb") as f: f.write(closure.read_bytes())
    failed=target/"nox-control/a6-r82-failed-selected"
    exact(failed/"pending_attempt.py","d32a5d6ca115fc4de9651a6cacd8ca8617ef3c9b")
    exact(failed/"diagnostic.py","c2b376d1451e681c76dc5cd212ffba133beeb42c")
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
    if len(after)-len(before)!=24: raise ValueError("HOLD_R115_STAGE_COUNT:"+str(len(after)-len(before)))
    # Only check the newly changed integration, not the previous R115 fixture.
    subprocess.run([sys.executable,"-I","-B","-c", """import pathlib,sys
wire=pathlib.Path(sys.argv[1])
failed=pathlib.Path(sys.argv[2])
sys.path.insert(0,str(wire))
import b0_framework_r83 as r83, b0_framework_r80 as r80, b0_proxy_stream_iter as r74
assert r83.R80Body is r80.FrameworkDeltaBody
assert r80.ProxyDeltaBody is r74.ProxyDeltaBody
assert all(pathlib.Path(m.__file__).parent == wire for m in (r83,r80,r74))
assert 'b0_http_chunked_r76' not in sys.modules
sys.path.insert(0,str(failed))
import diagnostic, pending_attempt
assert pathlib.Path(diagnostic.__file__).parent == failed
assert diagnostic.classify_pending_attempt is pending_attempt.classify_pending_attempt
r=diagnostic.review_failed(evidence={})
assert r['state'].startswith('HOLD_')
assert all(r[k] is False for k in ('native_accepted','ack_allowed','next_post_allowed','training_admitted','retry_allowed','successful_turn'))
""",str(wire),str(failed)],check=True,cwd=target)
    return {"unchanged":len(before),"added":len(after)-len(before),"entry":entry.relative_to(target).as_posix(),"entry_sha256":after[entry.relative_to(target).as_posix()],"native_accepted":False,"host_provider_bound":False,"positive_dialog_verified":False}
if __name__=="__main__":
    print(json.dumps(stage_all(*sys.argv[1:])))
