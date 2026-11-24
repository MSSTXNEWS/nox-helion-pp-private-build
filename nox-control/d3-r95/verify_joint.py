"""Read back the actual joint artifact; no model requests or behavior replay."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

def blob(raw):
    return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()

def verify(artifact):
    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(artifact) as z:
        root=Path(tmp)
        m=json.loads(z.read("JOINT_SOURCE_MANIFEST.json"))
        expected={x["path"]:x for x in m["files"]}
        assert len(expected)==len(m["files"])
        assert len(z.namelist())==len(expected)+1
        assert set(z.namelist())==set(expected)|{"JOINT_SOURCE_MANIFEST.json"}
        for name,x in expected.items():
            p=Path(name)
            assert not p.is_absolute() and ".." not in p.parts
            raw=z.read(name)
            assert blob(raw)==x["git_blob"] and hashlib.sha256(raw).hexdigest()==x["sha256"] and len(raw)==x["bytes"],name
            dst=root/p
            dst.parent.mkdir(parents=True,exist_ok=True)
            dst.write_bytes(raw)
        cfg=json.loads((root/"nox-control/d3-r95/release.json").read_text())
        for k in ("native_accepted","authentication_verified","next_post_allowed","training_admitted"):
            assert m[k] is False and cfg[k] is False
        # Child process imports from extracted files only, never checkout.
        code = """import importlib, json, os, pathlib, sys, hashlib, subprocess
root=pathlib.Path(sys.argv[1])
cfg=json.loads((root/'nox-control/d3-r95/release.json').read_text())
r93=json.loads((root/'nox-control/d3-r93/release.json').read_text())
sys.path[:0]=[str(root/p) for p in r93['python_paths']]+[str(root/'nox-control/d3-r95/wire')]
os.environ['D3_B4_MODULE']=str(root/'nox-control/d3-r74/staging/b4/b4_existing_turn_pair.mjs')
import quality_physical_pair, b0_proxy_stream_iter
assert callable(quality_physical_pair.review_physical_pair)
assert callable(b0_proxy_stream_iter.ProxyDeltaBody)
for name,pin in cfg['b5_imports'].items():
    f=pathlib.Path(importlib.import_module(name).__file__).resolve()
    assert f.is_relative_to(root),name
    b=f.read_bytes()
    assert hashlib.sha1(b'blob '+str(len(b)).encode()+bytes([0])+b).hexdigest()==pin,name
import b5_r55_pinned,b5_s03_verifier_r54
assert b5_r55_pinned.strict_owner_json_bytes is b5_s03_verifier_r54.strict_owner_json_bytes
subprocess.run(['node','-e','if(typeof require(process.argv[1]).check !== "function") process.exit(1)',str(quality_physical_pair.NODE)],check=True)
subprocess.run(['node','-e',"const fs=require('node:fs'),vm=require('node:vm');const s={};vm.createContext(s);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),s);if(typeof s.NOXB1SseUiBinding?.bind!=='function'||typeof s.NOXB1StreamReconnect?.createClient!=='function')process.exit(1)",str(root/'nox-control/d3-r95/wire/b1_browser_bundle.js')],check=True)
print('JOINT_EXTRACTED_ENTRYPOINTS=3 B5_IMPORTS=4 SINGLE_CANONICAL_VERIFIER=true NATIVE_ACCEPTED=false')
"""
        subprocess.run([sys.executable,"-I","-B","-c",code,str(root)],cwd=root,check=True)
        print(json.dumps({"files":len(expected),"archive_sha256":hashlib.sha256(Path(artifact).read_bytes()).hexdigest(),"native_accepted":False}))

if __name__=="__main__":
    verify(Path(sys.argv[1]).resolve())
