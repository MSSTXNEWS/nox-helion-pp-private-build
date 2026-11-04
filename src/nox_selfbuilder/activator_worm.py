"""ACTIVATOR-WORM for the EXISTING NOX EXPRESS Windows OneHost.

Data-only inventory and first-selfbuild plan. It does not discover arbitrary
private directories, install software, run downloaded code, merge patches, or
grant native consent. The native owner injects its read-only Windows probe.
"""
from __future__ import annotations
import re
from urllib.parse import urlparse

_TAG = re.compile(r"[a-z0-9][a-z0-9_.-]{1,70}:[a-z0-9][a-z0-9_.-]{1,40}\Z")
_SHA = re.compile(r"[a-f0-9]{40}\Z")
MAX_MODELS, MAX_MODULES = 40, 40

class ActivatorHold(ValueError):
    pass

def _native_catalog(entry, schema, *, cap):
    if not isinstance(entry, dict) or entry.get("schema") != schema:
        raise ActivatorHold("ACTIVATOR_CANONICAL_CATALOG_REQUIRED")
    items = entry.get("items")
    if not isinstance(items, list) or len(items) > cap:
        raise ActivatorHold("ACTIVATOR_BOUNDED_CATALOG_REQUIRED")
    return items

def plan_activation(*, foundation, models, modules, source_head=None,
                    owner_scope_verified=False):
    """Create safe per-model cards and next actions from existing P03/P04."""
    if owner_scope_verified is not True:
        raise ActivatorHold("ACTIVATOR_ORIGINAL_NATIVE_OWNER_REQUIRED")
    if not isinstance(foundation, dict) or foundation.get("schema") != "NOX-FOUNDATION-READONLY-v1":
        raise ActivatorHold("ACTIVATOR_LOCAL_PREFLIGHT_REQUIRED")
    model_rows = _native_catalog(models, "NOX-P03-DOWNLOAD-CANDIDATES-V1", cap=MAX_MODELS)
    module_rows = _native_catalog(modules, "NOX-P04-MODULE-CANDIDATES-V1", cap=MAX_MODULES)
    installed = foundation.get("model_tags")
    if not isinstance(installed, list) or len(installed) > 128 or any(
            not isinstance(tag, str) or len(tag) > 255 for tag in installed):
        raise ActivatorHold("ACTIVATOR_UNTRUSTED_LOCAL_MODEL_LIST")
    observed = set(installed)
    cards = []
    for item in model_rows:
        if not isinstance(item, dict):
            raise ActivatorHold("ACTIVATOR_MODEL_RECORD_REQUIRED")
        tag, page = item.get("tag"), item.get("official_page")
        if not isinstance(tag, str) or not _TAG.fullmatch(tag) or not isinstance(page, str):
            raise ActivatorHold("ACTIVATOR_MODEL_ID_OR_URL_REQUIRED")
        parsed = urlparse(page)
        family = tag.split(":", 1)[0]
        if (parsed.scheme != "https" or parsed.netloc != "ollama.com" or
                parsed.path != "/library/" + family or parsed.query or parsed.fragment):
            raise ActivatorHold("ACTIVATOR_OFFICIAL_MODEL_PAGE_REQUIRED")
        # Only the existing P03 reviewed registry can enable native pull.
        if item.get("download_enabled") is not False:
            raise ActivatorHold("ACTIVATOR_UNREVIEWED_MODEL_CANNOT_PULL")
        cards.append({
            "tag": tag, "purpose": str(item.get("role", ""))[:64],
            "official_page": page, "observed_locally": tag in observed,
            "weights_sha_verified": False,
            "download_eligible": False,
            "native_pull_route": "models.pull",
            "state": "LOCAL_TAG_OBSERVED_SHA_HOLD" if tag in observed
                     else "DISCOVERY_ONLY_REVIEW_BEFORE_NATIVE_PULL"
        })
    module_cards = []
    for item in module_rows:
        if not isinstance(item, dict) or item.get("download_enabled") is not False:
            raise ActivatorHold("ACTIVATOR_UNVERIFIED_MODULE")
        name = item.get("name")
        url = item.get("source")
        if (not isinstance(name, str) or not 2 <= len(name) <= 80 or
                not isinstance(url, str) or
                not url.startswith("https://") or len(url) > 512):
            raise ActivatorHold("ACTIVATOR_MODULE_PROVENANCE_REQUIRED")
        module_cards.append({
            "name": name, "purpose": str(item.get("role", ""))[:64],
            "official_page": url, "installed_version_verified": False,
            "download_eligible": False,
            "state": "VERSION_LICENSE_SHA_DEPENDENCY_REVIEW_REQUIRED"
        })
    s03 = foundation.get("s03")
    gpu = foundation.get("gpu")
    head_verified = isinstance(source_head, str) and bool(_SHA.fullmatch(source_head))
    coder = any(x["tag"] == "qwen2.5-coder:7b" and x["observed_locally"] for x in cards)
    embedding = any(x["tag"] == "qwen3-embedding:0.6b" and x["observed_locally"] for x in cards)
    s03_readable = s03 == "READONLY_OK_NOT_WRITE_TESTED"
    return {
        "schema": "NOX-ACTIVATOR-WORM-STATUS-v1",
        "state": "DISCOVERY_AND_OWNER_ACTIONS_ONLY",
        "models": cards, "modules": module_cards,
        "foundation": foundation,
        "coding_model_observed": coder, "embedding_model_observed": embedding,
        "knowledge_memory": "NATIVE_S03_RIGHTS_WRITE_AND_READBACK_REQUIRED",
        "s03_read_only_observed": s03_readable,
        "gpu": gpu if isinstance(gpu, str) else "GPU_UNKNOWN",
        "gpu_training": "APPROVED_GPU_PREFLIGHT_AND_DATASET_REQUIRED",
        "model_weights_sha_verified": False,
        "native_auto_install": False,
        "source_head": source_head if head_verified else None,
        "first_patch": ("REQUEST_APPROVED_SELFBUILDER_PROPOSAL" if coder and head_verified
                        else "CODER_AND_VERIFIED_SOURCE_REQUIRED"),
        "next_action": ("RUN_EXISTING_MODEL_CENTER_REVIEW" if not coder or not embedding
                        else "AUTHORIZE_EXISTING_A1_BOOT_AND_S03_REVIEW"),
        "installed_exe_e07": False,
        "self_update_applied": False,
        "safe_first_patch_scope": ["ui/onehost-menu-bindings.mjs",
                                   "integrations/wow200/runtime/home-scene.mjs",
                                   "integrations/creative/web/theater.js"],
    }
