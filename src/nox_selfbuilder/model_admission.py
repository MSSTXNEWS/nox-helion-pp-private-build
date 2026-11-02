"""Reviewed Ollama model candidate -> owner P03 job proposal, not a downloader.
Published model pages do NOT expose a full independently verified manifest SHA.
Exact model/digest/license/sizes MUST be reviewed before native P03 accepts a job.
"""
from __future__ import annotations
import json,re
from pathlib import Path
from typing import Mapping
SHA=re.compile(r"^[a-f0-9]{64}$")
TAG=re.compile(r"^[a-z0-9][a-z0-9._-]{1,80}:[0-9a-z._-]{1,32}$")

def _unique_catalog_object(pairs):
    """Reject ambiguous on-disk rights/model fields before owner P03 review."""
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("CATALOG_DUPLICATE_JSON_KEY")
        obj[key] = value
    return obj

def model_candidates(path:Path)->list[dict]:
    x=json.loads(path.read_text(encoding="utf-8"),
                 object_pairs_hook=_unique_catalog_object)
    if not isinstance(x, dict) or x.get("schema")!="NOX-CODING-LLM-CANDIDATE-REGISTRY-V3":
        raise ValueError("CATALOG_SCHEMA_INVALID")
    if not isinstance(x.get("models"), list):
        raise ValueError("CATALOG_MODELS_INVALID")
    return x["models"]

def p03_review_handoff(*,catalog_path:Path,tag:str,attestation:Mapping,owner_consent:bool)->dict:
    """Uses official P03 for networking and approval, never invokes Ollama directly."""
    if owner_consent is not True:
        raise PermissionError("OWNER_APPROVAL_REQUIRED")
    if not isinstance(tag,str) or not TAG.fullmatch(tag):
        raise ValueError("MODEL_TAG_INVALID")
    matches=[m for m in model_candidates(catalog_path) if m["tag"]==tag]
    if len(matches)!=1:
        raise ValueError("UNKNOWN_MODEL_CANDIDATE")
    item=matches[0]
    if item["commercial_policy"]!="APACHE_2_0_CANDIDATE":
        raise PermissionError("RESEARCH_LICENSE_NOT_AUTOADMITTED")
    digest=attestation.get("full_manifest_sha256")
    if not isinstance(digest,str) or not SHA.fullmatch(digest):
        raise ValueError("FULL_P03_DIGEST_REQUIRED")
    if not all(attestation.get(x) is True for x in ("official_manifest_verified","license_evidence_verified", "hardware_preflight_passed","reviewer_independent")):
        raise ValueError("NATIVE_P03_ATTESTATION_INCOMPLETE")
    for k in ("immutable_revision","rights_receipt_id","owner_receipt_id"):
        if not isinstance(attestation.get(k),str) or not attestation[k]:
            raise ValueError("P03_"+k.upper()+"_MISSING")
    if item.get("max_recommended_on_24gb") is False and attestation.get("installed_ram_gb",0)<48:
        raise ValueError("MODEL_EXCEEDS_LOCAL_RESOURCE_POLICY")
    return {"schema":"NOX-P03-REVIEWED-MODEL-REQUEST-v3","tag":tag,
        "approved_model_manifest_sha256":digest,"immutable_revision":attestation["immutable_revision"],
        "rights_receipt_id":attestation["rights_receipt_id"],
        "owner_receipt_id":attestation["owner_receipt_id"],
        "purpose":"CODING_COMPETENCY", "status":"P03_QUEUE_REVIEW_REQUIRED_NOT_DOWNLOADED",
        "connector":"EXISTING_P03_ONLY","network_called":False,"training_performed":False}
