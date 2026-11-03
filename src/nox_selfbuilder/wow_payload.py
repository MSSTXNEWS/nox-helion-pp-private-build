"""WOW payload contract (M2.6).

Temple, orbital cores, glass panels, living animations.
Rule 10+10+10. Does not replace approved HOME/MENU assets.
"""
from __future__ import annotations

from typing import Mapping

WOW_SCENES = (
    "HOME",
    "MENU",
    "MODELCENTER",
    "WORK",
)

# Visual elements that must be present in a cinematic payload.
REQUIRED_ELEMENTS = (
    "central_sun",       # black liquid sun / arc reactor
    "eight_orbits",      # HF01–HF08
    "glass_panels",      # frosted glass
    "smoke_layer",       # volumetric smoke
    "heat_traces",       # Harkonnen heat
    "reduced_motion",    # accessibility
)


def wow_manifest(*, scene: str) -> dict:
    """Return the expected visual contract for a scene."""
    if scene not in WOW_SCENES:
        raise ValueError("WOW_SCENE_UNKNOWN")
    return {
        "schema": "NOX-WOW-PAYLOAD-v1",
        "scene": scene,
        "elements": list(REQUIRED_ELEMENTS),
        "rule": "10+10+10",
        "style": "Harkonnen + Iron Man",
        "core_ids": ["HF01", "HF02", "HF03", "HF04", "HF05", "HF06", "HF07", "HF08"],
        "assets_required": True,
        "motion_safe": True,
    }


def validate_wow(payload: Mapping) -> dict:
    """Check that a payload declares the required cinematic elements."""
    if not isinstance(payload, Mapping):
        raise ValueError("WOW_PAYLOAD_REQUIRED")
    missing = [e for e in REQUIRED_ELEMENTS if e not in payload.get("elements", [])]
    return {
        "schema": "NOX-WOW-VALIDATION-v1",
        "ok": len(missing) == 0,
        "missing": missing,
        "scene": payload.get("scene"),
    }
