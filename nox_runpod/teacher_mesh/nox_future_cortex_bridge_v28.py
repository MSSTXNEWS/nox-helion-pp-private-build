#!/usr/bin/env python3
"""NOX Future V28 source-only bridge to the existing OneHost/Resonance.

Compose *plans*, not actions. Existing NOX first generates user-facing text,
then an owner-authorized queue may use advisor/eval/training suggestions.
No new backend, DB, model selector, process, web endpoint or automatic grant.
"""
from __future__ import annotations
from nox_neural_matchmaker_v28 import match_advisors
from nox_curriculum_dna_v28 import build_curriculum
from nox_adviser_arena_v28 import evaluate_teacher_arena
from nox_speed_lab_v28 import propose_speed_trials
from nox_emotional_resonance_v28 import tone_plan
SCHEMA="nox-v28-existing-onehost-bridge-plan-v1"

def compose_noX_plan(*,task:dict,registry:list,training_benchmarks:list,
                     advisor_evidence:list,live_profile:dict,
                     affect_observation:dict|None,owner_s03_preference:dict|None,
                     policies:dict)->dict:
    if not isinstance(policies,dict) or policies.get("trusted_existing_onehost") is not True:
        return {"schema":SCHEMA,"state":"HOLD_EXISTING_ONEHOST_NOT_BOUND","jobs_launched":0}
    core=policies.get("core",{})
    if core.get("stop_requested") is not False or core.get("authenticated_owner") is not True:
        return {"schema":SCHEMA,"state":"HOLD_STOP_OR_OWNER_AUTH","jobs_launched":0}
    if not isinstance(task,dict):
        return {"schema":SCHEMA,"state":"HOLD_BAD_TASK","jobs_launched":0}
    if not isinstance(registry,list) or not isinstance(training_benchmarks,list) or not isinstance(advisor_evidence,list):
        return {"schema":SCHEMA,"state":"HOLD_BAD_EVIDENCE_SET","jobs_launched":0}
    if not isinstance(live_profile,dict):
        live_profile={}
    match=match_advisors(task,registry,policies.get("advisors",{}))
    arena=evaluate_teacher_arena(advisor_evidence,policies.get("arena",{}))
    learn=build_curriculum(training_benchmarks,policies.get("curriculum",{}))
    speed=propose_speed_trials(live_profile,policies.get("speed",{}))
    mood=tone_plan(language=task.get("language","ru"),
                   observation=affect_observation,owner_s03_preference=owner_s03_preference,
                   policy=policies.get("emotion",{}))
    return {
        "schema":SCHEMA,"state":"NOX_FIRST_ADVISORY_PLAN_NOT_EXECUTED",
        "current_visible_model":"ONE_ACTIVE_NOX_STUDENT_ONLY",
        "first_answer":"MUST_BE_GENERATED_BY_EXISTING_NOX",
        "matchmaker":match,"teacher_arena":arena,
        "curriculum":learn,"speed_lab":speed,"emotional_resonance":mood,
        "existing_onehost_queue_required":True,
        "next_actions_only_after_native_admission":True,
        "gpu_trainer_jobs_started":0,"models_downloaded":0,
        "checkpoints_promoted":0,"s03_writes":0,
        "new_os_processes":0,
        "production_modified":False,
    }
