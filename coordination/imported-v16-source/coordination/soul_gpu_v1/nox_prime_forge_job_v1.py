"""NOX PRIME FORGE: genuine source patches in isolated staging, triggered by user.

The existing local NOX server owns this manager. A click starts one bounded
job; no hidden long-running agents, scheduler or second backend. The local
coder model proposes a real unified diff, it gets git apply checked, applied
ONLY to an isolated staging copy, and statically inspected. Never executes
generated code on the host. Owner/independent QA approval required to merge.
"""
from __future__ import annotations
import ast
from datetime import datetime,timezone
import json
from pathlib import Path
import secrets
import subprocess
import threading
from nox_prime_self_edit_lab_v1 import propose,allowable_path
from nox_prime_progress_v1 import log_event
from nox_prime_resource_advisor_v1 import trainer_active

TARGETS={
  "chat":("coordination/soul_gpu_v1/nox_unified_chat_v1.html",
           "Improve the existing NOX chat interface for the canonical cinematic D02 design; keep live chat, history, STOP and accessibility."),
  "brain":("coordination/soul_gpu_v1/nox_unified_brain_v1.py",
            "Improve existing NOX PRIME chat reasoning and responsiveness, with trustworthy memory and functional self-model. Do not modify security or S03."),
}
MAX_OBJECTIVE=800

def _now():
    return datetime.now(timezone.utc).isoformat()

class ForgeManager:
    def __init__(self,root,repo,source_sha=None):
        self.root=Path(root).resolve()
        self.repo=Path(repo).resolve()
        self.source_sha=source_sha
        if source_sha is not None and (
            not isinstance(source_sha,str) or len(source_sha)!=40 or
            any(c not in "0123456789abcdef" for c in source_sha)):
            raise ValueError("FORGE_INVALID_PINNED_SOURCE")
        self._lock=threading.Lock()
        self._current={"state":"IDLE","job_id":None}
        self._worker=None

    def status(self):
        with self._lock:
            return dict(self._current)

    def start(self,target="chat",objective=None):
        if target not in TARGETS:raise ValueError("INVALID_FORGE_TARGET")
        if objective is None:objective=TARGETS[target][1]
        if not isinstance(objective,str) or not 10<=len(objective.strip())<=MAX_OBJECTIVE:
            raise ValueError("INVALID_FORGE_OBJECTIVE")
        if trainer_active() is not False:
            raise RuntimeError("GPU_TRAINER_ACTIVE_OR_UNKNOWN: FORGE_CODER_ON_HOLD")
        if not (self.repo/".git").exists():
            raise RuntimeError("CANONICAL_GIT_REPO_MISSING")
        with self._lock:
            if self._current.get("state") in ("PREPARING","GENERATING","STAGING","STATIC_QA"):
                raise RuntimeError("FORGE_ALREADY_RUNNING")
            job_id=datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")+"_"+secrets.token_hex(3)
            self._current={"state":"PREPARING","job_id":job_id,
                           "target":target,"phase":"CHECK_SOURCE",
                           "started_utc":_now(),"applied_to_live":False,
                           "real_vm_verified":False,
                           "note":"Isolation is staged files only; not an authenticated VM."}
            worker=threading.Thread(target=self._run,
                                    args=(job_id,TARGETS[target][0],objective),
                                    daemon=True,name="NOX_FORGE_"+job_id)
            self._worker=worker
            worker.start()
        return self.status()

    def _update(self,job_id,**changes):
        with self._lock:
            if self._current.get("job_id")==job_id:
                self._current.update(changes)

    def _run(self,job_id,source_path,objective):
        staging=None
        try:
            log_event(self.root,"INTEGRATE","START",
                      "FORGE generates a source patch for "+Path(source_path).name)
            self._update(job_id,state="GENERATING",phase="LOCAL_CODER_INFERENCE")
            generated=propose(self.repo,self.root,source_path,objective,source_sha=self.source_sha)
            record=json.loads(Path(generated["candidate_path"]).read_text(encoding="utf-8"))
            if generated["git_apply_check"]!="PASS":
                self._update(job_id,state="HOLD",phase="GIT_APPLY_CHECK",
                             reason="Proposed patch did not apply",candidate=generated["candidate_path"])
                log_event(self.root,"INTEGRATE","HOLD","FORGE patch failed git apply --check")
                return
            if not allowable_path(source_path):
                raise RuntimeError("FORGE_SOURCE_OUTSIDE_ALLOWLIST")
            staged=(self.root/"brain"/"experiments"/"self_edits"/
                    "isolated"/job_id).resolve()
            staged.mkdir(parents=True,exist_ok=False)
            staging=staged
            file=staged/source_path
            file.parent.mkdir(parents=True,exist_ok=True)
            # Load EXACT committed original from canonical repo (never live file).
            origin=subprocess.run(
                ["git","-C",str(self.repo),"show",
                 record["source_sha"]+":"+source_path],
                capture_output=True,timeout=25,check=True)
            file.write_bytes(origin.stdout)
            self._update(job_id,state="STAGING",phase="APPLY_TO_STAGED_COPY")
            apply=subprocess.run(["git","-C",str(staged),"apply","--check","-"],
                input=record["diff"].encode("utf-8"),capture_output=True,timeout=25)
            if apply.returncode!=0:
                raise RuntimeError("STAGED_GIT_APPLY_CHECK_FAILED")
            subprocess.run(["git","-C",str(staged),"apply","-"],
                input=record["diff"].encode("utf-8"),check=True,
                capture_output=True,timeout=25)
            self._update(job_id,state="STATIC_QA",phase="CODE_PARSER")
            text=file.read_text(encoding="utf-8")
            if source_path.endswith(".py"):
                ast.parse(text,filename=source_path)
                qa="PYTHON_AST_PARSED"
            elif source_path.endswith(".html"):
                for required in ("id=\"message\"","id=\"stop\"","id=\"send\"",
                                 "api/nox/chat/stream","id=\"log\""):
                    if required not in text:
                        raise RuntimeError("NO_LOSS_UI_REQUIRED_ELEMENT_REMOVED: "+required)
                qa="HTML_REQUIRED_UI_CONTRACTS_PRESERVED"
            else:
                qa="GIT_DIFF_ONLY_NO_RUNTIME_QA"
            receipt=staged/"NOX_FORGE_CANDIDATE.json"
            result={"job_id":job_id,"source_sha":record["source_sha"],
                "source_path":source_path,"candidate":generated["candidate_path"],
                "staged_source":str(file),"static_qa":qa,
                "code_applied_to_staging":True,
                "code_applied_to_live":False,
                "runtime_tests_executed":False,
                "s03_modified":False,
                "ready_for_merge":"HOLD_OWNER_AND_INDEPENDENT_QA",
                "virtual_machine_verified":False}
            receipt.write_text(json.dumps(result,ensure_ascii=False,indent=2),
                               encoding="utf-8")
            self._update(job_id,state="CANDIDATE_READY",
                phase="WAIT_OWNER_REVIEW_AND_INDEPENDENT_QA",
                static_qa=qa,staging=str(staged),
                candidate=generated["candidate_path"],finished_utc=_now())
            log_event(self.root,"INTEGRATE","SAVED",
                      "FORGE staged real source patch; owner review required")
        except Exception as ex:
            self._update(job_id,state="HOLD",phase="ERROR",
                         reason=type(ex).__name__+": "+str(ex)[:220],
                         finished_utc=_now())
            try:
                log_event(self.root,"INTEGRATE","HOLD",
                          "FORGE stopped "+type(ex).__name__+"; live NOX unchanged")
            except Exception:
                pass
