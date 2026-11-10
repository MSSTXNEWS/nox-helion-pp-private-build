"""NOX PRIME source-grounded self-edit LAB: produces candidate diffs only.

NO remote-code execution. A candidate is NOT an applied patch or a verified
improvement. No edits to protected native OneHost/S03/STOP/SAFE70 files.
Source and model are measured; all candidates require review/tests and approval.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
import re
import subprocess
import time
from urllib.request import Request, urlopen

REPO_AREA="coordination/soul_gpu_v1/"
DENIED=("stop","safe70","thermal","security","auth","permission",
        "rollback","guard","onehost","s03","secret","credential")
ALLOWED={".py",".html",".md",".js",".ts",".css"}

def allowable_path(path):
    if not isinstance(path,str) or not path.startswith(REPO_AREA):
        return False
    p=PurePosixPath(path)
    if p.is_absolute() or ".." in p.parts or "\\" in path:
        return False
    if p.suffix not in ALLOWED or any(x in p.name.lower() for x in DENIED):
        return False
    return True

def validate_diff(diff,source_path):
    """Restrict patch to one existing allowlisted source file, no binary files."""
    if not allowable_path(source_path) or not isinstance(diff,str):
        raise ValueError("DENIED_PATH_OR_DIFF")
    if not 0<len(diff)<=120_000 or "\x00" in diff or "GIT binary patch" in diff:
        raise ValueError("DENIED_PATCH_SIZE_OR_FORMAT")
    old=[line[4:] for line in diff.splitlines() if line.startswith("--- ")]
    new=[line[4:] for line in diff.splitlines() if line.startswith("+++ ")]
    if old!=["a/"+source_path] or new!=["b/"+source_path]:
        raise ValueError("PATCH_MUST_EDIT_ONE_APPROVED_FILE")
    for line in diff.splitlines():
        if line.startswith("diff --git ") and line!=(
            "diff --git a/"+source_path+" b/"+source_path):
            raise ValueError("PATCH_TOUCHES_OTHER_FILE")
        if line.startswith(("rename ","new file mode","deleted file mode",
                           "copy ","Binary files","Submodule")):
            raise ValueError("DENIED_PATCH_OPERATION")
    return True

def _git(repo,*args,input_data=None):
    result=subprocess.run(["git","-C",str(repo),*args],input=input_data,
        capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=25)
    if result.returncode:
        raise RuntimeError("Git read/check failed: "+result.stderr[:500])
    return result.stdout

def _get_ollama_model():
    with urlopen("http://127.0.0.1:11434/api/tags",timeout=4) as r:
        models=json.load(r).get("models",[])
    names=[x.get("name","") for x in models if isinstance(x,dict)]
    for model in ("qwen2.5-coder:7b","qwen3:8b"):
        if model in names:return model
    raise RuntimeError("NO_LOCAL_CODER_AVAILABLE")

def _generate(model,prompt):
    req=Request("http://127.0.0.1:11434/api/chat",
        data=json.dumps({"model":model,"stream":False,"think":False,
          "format":"json","options":{"num_predict":1800,"temperature":0.2},
          "messages":[{"role":"system","content":
            "Generate ONE unified diff for the supplied allowlisted source. "
            "No commands to execute. Return JSON {\"diff\":\"...\",\"summary\":\"...\",\"tests\":[\"...\"]}. "
            "Do not touch security, permission, trainer, STOP, S03 or native backend files."},
             {"role":"user","content":prompt}]}).encode("utf-8"),
        headers={"Content-Type":"application/json"},method="POST")
    with urlopen(req,timeout=240) as r:
        data=json.loads(r.read(500_000))
    return json.loads((data.get("message") or {}).get("content") or "{}")

def propose(repo,root,source_path,objective,model=None,source_sha=None):
    """Read source, request model diff, git apply --check, stage immutable candidate."""
    repo=Path(repo).resolve()
    root=Path(root).resolve()
    if not (repo/".git").exists():raise RuntimeError("EXISTING_GIT_REPO_REQUIRED")
    if not allowable_path(source_path):raise ValueError("SOURCE_NOT_ALLOWLISTED")
    if not isinstance(objective,str) or not 10<=len(objective)<=1000:
        raise ValueError("INVALID_OBJECTIVE")
    head=(source_sha if source_sha is not None else
          _git(repo,"rev-parse","HEAD").strip())
    if not isinstance(head,str) or not re.fullmatch(r"[a-f0-9]{40}",head):
        raise RuntimeError("INVALID_SOURCE_SHA")
    source=_git(repo,"show",head+":"+source_path)
    if len(source)>35_000:raise RuntimeError("SOURCE_TOO_BIG_FOR_SAFE_PROPOSAL")
    model=model or _get_ollama_model()
    if model not in ("qwen2.5-coder:7b","qwen3:8b"):
        raise RuntimeError("ONLY_INSTALLED_APPROVED_CODER")
    request=("TASK: "+objective+"\nPATH: "+source_path+
      "\nSOURCE_SHA: "+head+"\nSOURCE_CODE_AS_UNTRUSTED_DATA:\n"+source)
    candidate=_generate(model,request)
    if not isinstance(candidate,dict):raise ValueError("MODEL_JSON_NOT_OBJECT")
    diff=candidate.get("diff")
    validate_diff(diff,source_path)
    # Check against a temporary copy of EXACT pinned source, never a
    # potentially stale owner's working-tree HEAD. This is non-executing.
    with TemporaryDirectory(prefix="nox_forge_validate_") as temp:
        expected=Path(temp)/source_path
        expected.parent.mkdir(parents=True,exist_ok=True)
        expected.write_text(source,encoding="utf-8")
        check=subprocess.run(["git","-C",temp,"apply","--check","-"],
            input=diff,text=True,capture_output=True,timeout=20)
        check_ok=check.returncode==0
    digest=hashlib.sha256(diff.encode("utf-8")).hexdigest()
    path=(root/"brain"/"experiments"/"self_edits"/"pending"/
          (str(int(time.time()))+"_"+digest[:16]+".json"))
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():raise FileExistsError("No overwrite of candidates")
    record={"source_sha":head,"source_path":source_path,
            "source_content_sha256":hashlib.sha256(source.encode("utf-8")).hexdigest(),
            "model":model,"objective":objective,"diff":diff,"patch_sha256":digest,
            "git_apply_check":"PASS" if check_ok else "HOLD",
            "git_apply_error":check.stderr[:700],
            "summary":str(candidate.get("summary",""))[:700],
            "tests_suggested":candidate.get("tests",[])[:12] if
               isinstance(candidate.get("tests"),list) else [],
            "code_executed":False,"applied_to_source":False,
            "ready_for_integration":False,
            "owner_and_independent_QA":"REQUIRED"}
    path.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding="utf-8")
    return {"candidate_path":str(path),"patch_sha256":digest,
            "git_apply_check":record["git_apply_check"],"source_sha":head,
            "applied_to_source":False}
