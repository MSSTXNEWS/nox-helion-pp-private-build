"""HF01–HF08 cognitive facade binding to technical CoreIDs and live provider.

User-facing facets (from ROLE 4 HF→COREID contract):
  HF01 СОЗНАНИЕ, HF02 ЭМОЦИИ, HF03 ЛИЧНОСТЬ, HF04 ПАМЯТЬ,
  HF05 ЗНАНИЯ, HF06 РАЗВИТИЕ, HF07 ПРОФЕССИИ, HF08 ОБЩЕНИЕ.

These are compatibility adapters over the existing 8 technical CoreIDs.
They do not create a 9th core or replace CONSCIOUSNESS/PERSONA/ATLAS/etc.
"""
from __future__ import annotations

from typing import Callable, Mapping

from .worms import WormHold

# Exact HF facade registry (user-visible cognitive facets).
HF_FACADES = (
    "HF01", "HF02", "HF03", "HF04",
    "HF05", "HF06", "HF07", "HF08",
)

# Human-readable labels (Russian, per source contract).
HF_LABELS: Mapping[str, str] = {
    "HF01": "СОЗНАНИЕ",
    "HF02": "ЭМОЦИИ",
    "HF03": "ЛИЧНОСТЬ",
    "HF04": "ПАМЯТЬ",
    "HF05": "ЗНАНИЯ",
    "HF06": "РАЗВИТИЕ",
    "HF07": "ПРОФЕССИИ",
    "HF08": "ОБЩЕНИЕ",
}

# Compatibility mapping: HF facade → primary technical CoreID.
# Does not replace the original 8 CoreIDs.
HF_TO_CORE: Mapping[str, str] = {
    "HF01": "CONSCIOUSNESS",  # сознание
    "HF02": "PERSONA",         # эмоции
    "HF03": "PERSONA",         # личность
    "HF04": "REFLECTION",      # память
    "HF05": "ATLAS",           # знания
    "HF06": "REFLECTION",      # развитие
    "HF07": "FORGE",           # профессии
    "HF08": "VOICE",           # общение
}

TECHNICAL_CORES = frozenset({
    "CONSCIOUSNESS", "PERSONA", "ATLAS", "VOICE",
    "REFLECTION", "CORE", "NEXUS", "FORGE",
})


def bind_hf_to_live_provider(
    *,
    hf_id: str,
    session: str,
    authorize: Callable,
    native_stop: Callable,
    provider_callback: Callable,
) -> dict:
    """Bind one HF facade to the live provider through its technical CoreID.

    Raises WormHold on missing STOP, unauthorized session, or unknown HF.
    Returns a receipt; does not execute training or model mutation.
    """
    if not isinstance(hf_id, str) or hf_id not in HF_FACADES:
        raise WormHold("HF_FACADE_UNKNOWN")
    if not all(callable(fn) for fn in (authorize, native_stop, provider_callback)):
        raise WormHold("HF_NATIVE_PORTS_REQUIRED")

    try:
        if native_stop() is not False:
            raise WormHold("HF_NATIVE_STOP_REVOKED")
        if authorize(session, f"hf.{hf_id}.bind") is not True:
            raise WormHold("HF_AUTHORIZE_DENIED")
    except WormHold:
        raise
    except Exception as exc:
        raise WormHold("HF_NATIVE_PORT_UNAVAILABLE") from exc

    core = HF_TO_CORE[hf_id]
    if core not in TECHNICAL_CORES:
        raise WormHold("HF_CORE_MAPPING_INVALID")

    try:
        result = provider_callback(hf_id=hf_id, core_id=core, session=session)
    except Exception as exc:
        raise WormHold("HF_PROVIDER_CALLBACK_FAILED") from exc

    if not isinstance(result, dict):
        raise WormHold("HF_PROVIDER_RECEIPT_REQUIRED")

    return {
        "schema": "NOX-HF-LIVE-BINDING-v1",
        "hf_id": hf_id,
        "label": HF_LABELS[hf_id],
        "core_id": core,
        "session": session,
        "provider_result": result,
        "training_performed": False,
        "weights_updated": False,
    }
