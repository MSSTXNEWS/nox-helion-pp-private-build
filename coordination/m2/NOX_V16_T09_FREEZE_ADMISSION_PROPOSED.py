"""M2/T09 exact SHA source-freeze preflight. Read-only; T10 follows, never precedes."""
import json
import re
import subprocess
from pathlib import Path
HEX40=re.compile(r"[0-9a-f]{40}\Z")

def evaluate(repo, evidence):
    root=Path(repo)
    src=evidence.get("source",{})
    head,tree,manifest=(src.get("head"),src.get("tree"),src.get("manifest_blob"))
    def hold(reason):
        return {"status":"FREEZE_HOLD","reason":reason,"head":head,"frozen":False}
    if not all(isinstance(x,str) and HEX40.fullmatch(x) for x in (head,tree,manifest)):
        return hold("T06_ACCEPTED_SHA_TUPLE_REQUIRED")
    try:
        def git(*args):
            p=subprocess.run(["git","-C",str(root),*args],capture_output=True,
                              check=False,timeout=12)
            if p.returncode: raise ValueError("GIT_UNREADABLE")
            return p.stdout
        if git("rev-parse","HEAD").decode().strip()!=head or git("rev-parse","HEAD^{tree}").decode().strip()!=tree:
            return hold("LIVE_HEAD_TREE_MISMATCH")
        if git("cat-file","-t",manifest).strip()!=b"blob":
            return hold("MANIFEST_NOT_GIT_BLOB")
        data=json.loads(git("cat-file","blob",manifest))
        if not isinstance(data,dict) or data.get("head_sha")!=head or data.get("tree_sha")!=tree or data.get("owner_acceptance") is not True:
            return hold("UNACCEPTED_OWNER_MANIFEST")
        if evidence.get("t06_accepted_head")!=head or evidence.get("t08_same_head")!=head:
            return hold("T06_T08_SAME_SHA_UNPROVEN")
        if evidence.get("original_729_lock_pass") is not True or evidence.get("owner_patches_accepted") is not True:
            return hold("NO_LOSS_OR_OWNER_PATCHES_UNPROVEN")
        return {"status":"ELIGIBLE_FOR_IMMUTABLE_T09_RECEIPT","head":head,"tree":tree,
                "manifest_blob":manifest,"frozen":False,"t10_prerequisite":False}
    except (ValueError,TypeError,OSError,UnicodeError,subprocess.TimeoutExpired):
        return hold("EVIDENCE_READBACK_FAILED")
