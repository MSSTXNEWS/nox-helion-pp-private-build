"""NOX PRIME: capability-overlap inventory, teach/study/retire planning.

Makes ONE brain the owner of learned skills, and keeps teacher/expert models
ONLY until independent skill-retention tests prove replacement. Comparing
model names or SHA alone does not prove functional equivalence. This script
never deletes, unloads, changes S03, activates LoRA or claims neural training.

A report is a functional plan, not a physical merger. Owner confirmation and
a passing independent evaluation remain mandatory for future removal.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime,timezone
import argparse
import json
from pathlib import Path
import re

from nox_prime_weight_audit_v1 import model_catalog

CORE_BASE="Qwen/Qwen3-0.6B"
MAIN_ONLINE="qwen3:8b"
CAPABILITIES={
  "text_reasoning":"Dialog RU/ES, planning, generalized understanding",
  "coding":"Code generation, tests, Windows, app and site building",
  "semantic_memory":"Embeddings, retrieval, reranking and time-aware memory",
  "emotion_context":"Emotion classification and behavior without claims of feeling",
  "speech_recognition":"RU/ES speech-to-text",
  "speech_synthesis":"RU/ES text-to-speech and selectable voices",
  "vision":"Image understanding and visual QA",
  "image_generation":"Image creation or editing",
  "video_generation":"Video creation and editing",
  "tool_use":"Safe external tools, browsing and application development",
}
TEXT={"text_reasoning","tool_use"}
CODE={"coding","tool_use","text_reasoning"}
PRESERVE={"qwen3:8b","qwen2.5-coder:7b","qwen3-embedding:0.6b"}
MIN_TESTS_PER_CAPABILITY=12

def classify(name):
    """Conservative candidate taxonomy, not a competence measurement."""
    value=name.lower()
    if re.search(r"embedding|embed|rerank|bge|nomic-embed|e5[-:]",value):
        return {"semantic_memory"},"MEMORY_SPECIALIST"
    if re.search(r"asr|whisper|speech[-_]?to[-_]?text|stt",value):
        return {"speech_recognition"},"AUDIO_SPECIALIST"
    if re.search(r"tts|text[-_]?to[-_]?speech|piper|voice",value):
        return {"speech_synthesis"},"AUDIO_SPECIALIST"
    if re.search(r"video|wan[0-9]|ltx[-:]|hunyuanvideo",value):
        return {"video_generation"},"MEDIA_SPECIALIST"
    if re.search(r"flux|sdxl|stable[-_]?diffusion|image[-:]|z[-_]?image",value):
        return {"image_generation"},"MEDIA_SPECIALIST"
    if re.search(r"vision|llava|moondream|(?:^|[-:])vl(?:[-:]|$)",value):
        return {"vision","text_reasoning"},"VISION_SPECIALIST"
    if re.search(r"coder|codestral|codegemma|starcoder",value):
        return set(CODE),"CODE_TEACHER"
    if re.search(r"qwen|llama|gemma|mistral|phi[-:]|deepseek|granite",value):
        return set(TEXT),"LANGUAGE_TEACHER"
    return set(),"UNKNOWN_REQUIRES_PROFILE"

def _approved_receipts(path,models):
    """Only evidence referencing current model digests can count.

    External owner/QA verification is NOT derivable from student-generated
    content. Reports are read-only and never sufficient for deleting files.
    """
    base=Path(path)
    results=[]
    if not base.is_dir() or base.is_symlink():return results
    for file in sorted(base.glob("*.json"))[:300]:
        if file.is_symlink() or file.stat().st_size>500_000:continue
        try:
            p=json.loads(file.read_text(encoding="utf-8"))
            if not isinstance(p,dict) or p.get("schema")!="NOX_CAPABILITY_EVAL_V1":
                continue
            donor=p.get("donor_model")
            cap=p.get("capability")
            if donor not in models or cap not in CAPABILITIES:continue
            if p.get("donor_digest")!=models[donor]:continue
            if p.get("student_family")!=CORE_BASE:continue
            checks=p.get("checks") or {}
            if not isinstance(checks,dict):continue
            if (p.get("owner_approved") is not True or
                p.get("independent_qa_pass") is not True or
                p.get("source_reproducible") is not True or
                p.get("rollback_available") is not True or
                p.get("old_skills_regression_pass") is not True or
                p.get("student_inference_verified") is not True or
                type(checks.get("heldout_count")) is not int or
                checks["heldout_count"]<MIN_TESTS_PER_CAPABILITY or
                type(checks.get("student_score")) not in (float,int) or
                type(checks.get("teacher_score")) not in (float,int) or
                checks["student_score"]<checks["teacher_score"] or
                type(checks.get("student_p95_ms")) not in (float,int) or
                checks["student_p95_ms"]<=0 or
                type(checks.get("teacher_p95_ms")) not in (float,int) or
                checks["teacher_p95_ms"]<=0):
                continue
            results.append({"model":donor,"capability":cap,
                           "evidence_file":file.name,
                           "student_score":checks["student_score"],
                           "teacher_score":checks["teacher_score"],
                           "can_propose_retirement":True})
        except (OSError,ValueError,TypeError):
            continue
    return results

def plan(rows,receipts=()):
    """Group models by FUNCTION and propose, never perform, retirement."""
    groups=defaultdict(list)
    all_names={}
    for model in rows:
        if not isinstance(model,dict):continue
        name=model.get("tag")
        digest=model.get("digest")
        if not isinstance(name,str) or not isinstance(digest,str):
            continue
        if not re.fullmatch(r"[a-f0-9]{64}",digest):continue
        all_names[name]=digest
        capabilities,role=classify(name)
        for cap in capabilities:groups[cap].append(name)
    # Proof of competence is per named capability, not per model tag.
    verified={(e["model"],e["capability"]):e for e in receipts
              if isinstance(e,dict) and "model" in e and "capability" in e}
    proposals=[]
    for name in sorted(all_names):
        abilities,role=classify(name)
        accepted=[cap for cap in sorted(abilities) if (name,cap) in verified]
        remaining=sorted(abilities-set(accepted))
        unique=sorted(cap for cap in abilities if len(groups[cap])==1)
        default_keep=name in PRESERVE or role in (
            "UNKNOWN_REQUIRES_PROFILE","AUDIO_SPECIALIST",
            "VISION_SPECIALIST","MEDIA_SPECIALIST","MEMORY_SPECIALIST")
        candidates=[]
        if role=="UNKNOWN_REQUIRES_PROFILE":
            route="PROFILE_THEN_INTEGRATE_AS_TOOL"
        elif role in ("AUDIO_SPECIALIST","VISION_SPECIALIST",
                       "MEDIA_SPECIALIST","MEMORY_SPECIALIST"):
            route="KEEP_AS_HIDDEN_EXPERT_UNTIL_MODALITY_SPECIFIC_TARGET_PASSES"
        else:
            route="DISTILL_TO_NOX_NEURAL_CORE_AND_SKILL_MEMORY"
        for cap in sorted(abilities):
            if len(groups[cap])>=2:
                candidates.append(cap)
        # A model can only be retired if ALL capabilities have evidence, it
        # is not the live base/active protected engine, and owner decides.
        retire_review=(bool(abilities) and not remaining and not default_keep)
        proposals.append({"model":name,"digest":all_names[name],
             "role":role,"transfer_route":route,
             "potential_functional_overlap":candidates,
             "unique_capabilities_to_protect":unique,
             "verified_student_capabilities":accepted,
             "unverified_capabilities":remaining,
             "keep_for_now":not retire_review,
             "retirement_review_only":retire_review,
             "auto_delete":False,
             "reason":("INDEPENDENT_EVIDENCE_REQUIRED" if remaining else
                       "ACTIVE_PROTECTION_OR_EXPERT_FALLBACK" if default_keep else
                       "OWNER_RETIREMENT_REVIEW_REQUIRED")})
    return {"capability_to_models":{k:sorted(v) for k,v in sorted(groups.items())},
            "models":proposals,
            "potential_functional_overlaps":
                {cap:names for cap,names in sorted(groups.items()) if len(names)>1},
            "retirement_review_candidates":sum(x["retirement_review_only"] for x in proposals),
            "models_deleted":0}

def create(root):
    root=Path(root).resolve()
    if not (root/"brain").is_dir():raise RuntimeError("NOX_BRAIN_ROOT_MISSING")
    models=model_catalog(root)
    hashes={m["tag"]:m["digest"] for m in models}
    evidence=_approved_receipts(root/"brain"/"intelligence"/"skill_evaluations",hashes)
    result=plan(models,evidence)
    result.update({
        "schema":"NOX_PRIME_FUNCTIONAL_CONSOLIDATION_V1",
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "target_neural_core":"NOX-PRIME based on compatible "+CORE_BASE+" weights, after own training",
        "teacher_primary_still_online":MAIN_ONLINE in hashes,
        "base_trained_into_independent_superior_llm":False,
        "priority":["SOUL emotion+RU/ES","M0-M7 error-memory","FORGE finish NOX menu/code",
                    "coding and tool-use transfer","other expert capabilities"],
        "source":"INSTALLED_OLLAMA_CATALOG_PLUS_ACCEPTED_LOCAL_EVALUATIONS",
        "policy":"ONLY_REPLACE_A_SKILL_AFTER_INDEPENDENT_PROOF_WITH_NO_LOSS",
        "S03_modified":False,"trained_LoRA_modified":False,"no_unique_model_deleted":True,
    })
    dst=root/"brain"/"telemetry"/"capability_plans"
    dst.mkdir(parents=True,exist_ok=True)
    from uuid import uuid4
    path=dst/("functional_"+datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")+
              "_"+uuid4().hex[:5]+".json")
    with path.open("x",encoding="utf-8") as f:
        json.dump(result,f,ensure_ascii=False,indent=2)
    return {"report":str(path),"models_compared":len(models),
            "capabilities_compared":len(result["capability_to_models"]),
            "functional_overlap_groups":len(result["potential_functional_overlaps"]),
            "eligible_for_owner_review":result["retirement_review_candidates"],
            "models_removed":0,"next":"benchmark > train own NOX core > replay > promote > retire"}

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=Path(r"C:\NOX_HELION\NOX_NEW"))
    args=p.parse_args()
    print(json.dumps(create(args.root),ensure_ascii=False,indent=2))
