"""Build an offline staged candidate; no deploy, POST, or native authority."""
import hashlib, json, os, pathlib, subprocess, sys, tempfile
root=pathlib.Path(__file__).resolve().parent
stage=root/"staging"
manifest=json.loads((root/"manifest.json").read_text())
def blob(data):
    return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()
for row in manifest["donors"]:
    data=(stage/row["target"]).read_bytes()
    if blob(data)!=row["git_blob"]:
        raise SystemExit("HOLD_STAGE_BLOB "+row["target"])
sys.dont_write_bytecode=True
sys.path.insert(0,str(stage/"py"))
os.environ["D3_B4_MODULE"]=str(stage/"b4/b4_existing_turn_pair.mjs")
import b5_s03_verifier_r54 as canonical
import b5_r55_pinned as alias
import b0_resume_bridge as b0
import b5_browser_prefix_gate as prefix
import d3_r72_calibrated_descriptor_gate as review
assert canonical.BrowserResumeEvidence is alias.BrowserResumeEvidence is b0.BrowserResumeEvidence
assert callable(prefix.bind_observed_browser_prefix) and callable(review.prepare_calibrated_review) and callable(review.verify_calibrated_reviews)
for path in manifest["browser_load_order"]:
    subprocess.run(["node","--check",str(stage/path)],check=True)
for path in sorted((stage/"b4").glob("*.mjs")):
    subprocess.run(["node","--check",str(path)],check=True)
candidate=subprocess.check_output(["node",str(stage/"b3/b3_r60_identity_readback_race.cjs"),"--emit"],timeout=30)
if not candidate or len(candidate)>25454:
    raise SystemExit("HOLD_STAGE_B3_SIZE")
with tempfile.TemporaryDirectory() as tmp:
    p=pathlib.Path(tmp)/"bridge.js"
    p.write_bytes(candidate)
    subprocess.run(["node","--check",str(p)],check=True)
print(json.dumps({"scope":"SOURCE_STAGE_ONLY","donor_blobs":len(manifest["donors"]),"canonical_b5_alias":True,"b3_candidate_bytes":len(candidate),"b3_candidate_sha256":hashlib.sha256(candidate).hexdigest(),"native_accepted":False,"admission":False},sort_keys=True))
