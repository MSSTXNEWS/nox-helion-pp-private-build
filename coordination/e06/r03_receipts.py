"""E06 R03 exact owner-6 file path receipts with one pinned immutable parent."""
import hashlib
import json
import subprocess
from pathlib import Path

BASE="d0d7489ecbca3c4c93480989acfedc6a5ca94b9e"
RUN="NOX-V16-E06-TURBO10-20261028-R03"
PATHS=(
    "coordination/e06/canonical_source_lock.py",
    "coordination/e06/r03_receipts.py",
    "tests/e06/test_source_lock.py",
    ".github/workflows/nox-e06-original-lock.yml",
)
def git(*args):
    return subprocess.run(["git",*args],capture_output=True,check=True).stdout
def sha(blob):
    return hashlib.sha256(blob).hexdigest()

def main():
    head=git("rev-parse","HEAD").decode().strip()
    tree=git("rev-parse","HEAD^{tree}").decode().strip()
    git("merge-base","--is-ancestor",BASE,head)
    modified=git("diff","--name-only",BASE,head).decode().splitlines()
    if set(modified)!=set(PATHS):
        raise SystemExit("OWNER6_CHANGED_PATHS_MISMATCH")
    rows=[]
    for path in PATHS:
        after=Path(path).read_bytes()
        try:
            before=git("show",f"{BASE}:{path}")
            pre=sha(before)
        except subprocess.CalledProcessError:
            pre="ABSENT_ON_R02"
        patch=git("diff","--binary",BASE,head,"--",path)
        if not patch:
            raise SystemExit("EMPTY_PATCH")
        rows.append({"path":path,"run_id":RUN,"owner":6,"pre_sha256":pre,
                     "post_sha256":sha(after),"patch_sha256":sha(patch),
                     "git_blob_sha1":git("hash-object",path).decode().strip(),
                     "bytes":len(after),"patch_bytes":len(patch)})
    doc={"schema":"NOX-E06-R03-RECEIPTS-v1","run_id":RUN,
         "parent_commit_sha1":BASE,"head_commit_sha1":head,"head_tree_sha1":tree,
         "stage":"ORIGINAL_BASELINE_NOT_MERGED","files":rows,
         "exe_produced":False,"e07_accepted":False}
    dest=Path("e06-r03-source-receipts.json")
    dest.write_text(json.dumps(doc,indent=2)+"\n",encoding="utf-8")
    if json.loads(dest.read_text(encoding="utf-8"))!=doc:
        raise SystemExit("RECEIPT_READBACK_FAILURE")
    print("R03_RECEIPTS_PASS",len(rows),head,tree)
    for item in rows:
        print("R03_PATH_RECEIPT",json.dumps(item,sort_keys=True))
if __name__=="__main__":
    main()
