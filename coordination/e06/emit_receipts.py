"""E06 exact file receipts: diff against immutable main, no modifications to sources."""
import hashlib
import json
import subprocess
from pathlib import Path

BASE="eb46b49fb8a022cefa679afb8606877016808db1"
RUN_ID="NOX-V16-E06-TURBO10-20261028-R01"
PATHS=(
    "coordination/e06/intake.json",
    "coordination/e06/verify_integration.py",
    "coordination/e06/emit_receipts.py",
    "coordination/e06/README.md",
    "tests/e06/test_verify_integration.py",
    "tests/e06/test_hardening.py",
    ".github/workflows/nox-e06-intake.yml",
)
def git(*args):
    return subprocess.run(["git",*args],check=True,capture_output=True).stdout
def digest(data):
    return hashlib.sha256(data).hexdigest()
def main():
    commit=git("rev-parse","HEAD").decode().strip()
    tree=git("rev-parse","HEAD^{tree}").decode().strip()
    out=[]
    for path in PATHS:
        data=Path(path).read_bytes()
        try:
            before=git("show",f"{BASE}:{path}")
            pre_sha=digest(before)
        except subprocess.CalledProcessError:
            pre_sha="ABSENT_ON_BASE"
        patch=git("diff","--binary",BASE,"HEAD","--",path)
        if not patch:
            raise SystemExit(f"no diff vs frozen main: {path}")
        out.append({
            "run_id":RUN_ID,"task_id":"E06-INTAKE-PREFLIGHT","owner":6,
            "path":path,"base_commit_sha1":BASE,
            "post_commit_sha1":commit,"post_tree_sha1":tree,
            "pre_sha256":pre_sha,"post_sha256":digest(data),
            "git_patch_sha256":digest(patch),"patch_bytes":len(patch),
            "file_bytes":len(data),"tested_by":"GitHub Actions E06 deterministic Windows CI"
        })
    document={"schema":"NOX-E06-FILE-RECEIPTS-v1","run_id":RUN_ID,
              "base_commit_sha1":BASE,"candidate_commit_sha1":commit,
              "candidate_tree_sha1":tree,"status":"SOURCE_CANDIDATE_NOT_PRODUCT_ACCEPTANCE",
              "files":out}
    target=Path("e06-file-receipts.json")
    target.write_text(json.dumps(document,indent=2)+"\n",encoding="utf-8")
    print(target.read_text(encoding="utf-8"))
if __name__=="__main__":
    main()
