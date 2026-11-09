"""NOX PRIME 8 CoreID runtime capability matrix, not symbolic-only labels.

Pure status probes. Never load/download models or alter native S03.
The status distinguishes actual operation from source-only candidates.
"""
from __future__ import annotations
import json
from pathlib import Path

CORE_IDS=("CONSCIOUSNESS","PERSONA","ATLAS","VOICE", "REFLECTION","CORE","NEXUS","FORGE")
PERSONAS=("KV","AM","LA","EV","KW")


def _voice(root):
    f=Path(root)/"brain"/"voice"/"receipts"/"qwen3_06_customvoice.json"
    if not f.is_file() or f.is_symlink():
        return {"status":"HOLD","detail":"Voice weights not confirmed downloaded", "inference_tested":False}
    try:
        obj=json.loads(f.read_text(encoding="utf-8"))
        ready=obj.get("status")=="DOWNLOADED_AND_HASHED" and obj.get("id")=="qwen3_06_customvoice"
    except (OSError,ValueError,TypeError):
        ready=False
    return {"status":"WEIGHTS_ONLY" if ready else "HOLD",
            "detail":"SHA receipt found" if ready else "Voice receipt not accepted",
            "inference_tested":False}


def matrix(root, available_models=(), memory_event_count=0, affect_available=False):
    models=set(available_models)
    voice=_voice(root)
    return {
        "identity":"NOX PRIME",
        "core_ids":list(CORE_IDS),
        "capabilities":{
          "CONSCIOUSNESS":{"status":"FUNCTIONAL_SELF_MODEL",
             "detail":"Grounded model/hardware/capability self-description; no subjective consciousness claim",
             "subjective_consciousness_verified":False},
          "PERSONA":{"status":"ISOLATION_REQUIRED",
             "known_persona_ids":list(PERSONAS),"memory_cross_access":False,
             "detail":"Five PersonaIDs reserved; native persona routes not yet accepted"},
          "ATLAS":{"status":"PLANNED",
             "detail":"Planning/goal task executor not physically accepted"},
          "VOICE":voice,
          "REFLECTION":{"status":"CANDIDATE_ONLY",
             "detail":"Reflection and test receipts; no autonomous repair promotion"},
          "CORE":{"status":"INFERENCE_AVAILABLE" if "qwen3:8b" in models else "HOLD",
             "primary_model":"qwen3:8b" if "qwen3:8b" in models else None,
             "detail":"Ollama model availability only; GPU placement separately measured"},
          "NEXUS":{"status":"LOCAL_TRANSCRIPT_READ_ONLY",
             "historical_episodes":int(memory_event_count),"native_s03_writable":False,
             "detail":"Source-linked PRIME history; authorized OneHost S03 write missing"},
          "FORGE":{"status":"SOURCE_CANDIDATES_ONLY",
             "detail":"Checkpoint registry and code candidate lab; no unattended validated code/LoRA promotion"},
        },
        "soul_affect":{"status":"EN_ONLY_HOLDOUT_MODEL" if affect_available else "HOLD",
                       "scope":"EN_ONLY", "main_llm_weights_changed":False},
    }
