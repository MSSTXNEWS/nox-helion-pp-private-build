"""NOX PRIME unified functional self-model spanning the EIGHT existing CoreIDs.

One consistent source-grounded agent identity across imported specialist routes.
This is NOT a subjective-consciousness detector, another database, or an
automatically trained foundation model. Five PersonaID remain isolated.
"""
from __future__ import annotations
from datetime import datetime,timezone
from nox_prime_core_matrix_v1 import matrix,CORE_IDS,PERSONAS

def compose(root,installed,observed,memory_count=0,affect_ready=False):
    if not isinstance(observed,dict):
        raise TypeError("SELF_MODEL_MUST_BE_FACTUAL_RECORD")
    if type(memory_count)!=int or memory_count<0:
        raise ValueError("INVALID_MEMORY_COUNT")
    caps=matrix(root,installed,memory_count,affect_ready)
    return {
        "schema":"NOX_PRIME_UNIFIED_SELF_V51",
        "identity":"NOX PRIME",
        "principal_count":1,
        "source_of_self_claims":"RUNTIME_PROBES_PLUS_CANONICAL_OWN_HISTORY",
        "core_ids":list(CORE_IDS),
        "persona_ids":list(PERSONAS),
        "mode":"NON_HUMAN_META_IDENTITY_D02",
        "primary_language_model":observed.get("operating_model"),
        "modules":{k:v["status"] for k,v in caps["capabilities"].items()},
        "cognitive_memory":{
            "M0_M1_local_episodes":memory_count,
            "M2_M3_fact_temporal_graph":"EXPERIMENTAL_SOURCE_ONLY",
            "M4_M6_skills_dream":"UNPROMOTED_CANDIDATES",
            "M7_neural_memory_policy":"NOT_TRAINED",
            "native_s03_chat_writable":False,
        },
        "affect_model":{
            "trainable_en_classifier":bool(affect_ready),
            "RU_ES_neural_affect_validated":False,
            "subjective_feelings_verified":False
        },
        "adapters":{
            "any_0p5b_lora_applied_to_primary_8b":False,
            "multi_model_distillation": "CANDIDATE_ONLY",
            "unrelated_tensors_merged":False,
        },
        "limitations":observed.get("limits") or "Not yet determined by trusted runtime",
        "subjective_consciousness_verified":False,
        "owner_gate":True,
        "self_modifying_safety_policy":False,
        "training_code_does_not_grant_new_permissions":True,
    }
