"""NOX V16 E01 source-only, fail-closed D02/WOW merge admission.

This does not mount scenes, modify host, certify installation, or attest assets.
An E06 integrator supplies independent receipts and on-disk original files.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

BASE_COMMIT = "0b3a7d435be735148d64171deb9027093a89646e"
BASE_TREE = "f108d604c444f718b32aaecfd07b90b8f91b9a6f"
CANONICAL_CORES = (
    "CONSCIOUSNESS", "PERSONA", "ATLAS", "VOICE",
    "REFLECTION", "CORE", "NEXUS", "FORGE",
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SHA1 = re.compile(r"^[0-9a-f]{40}$")


def file_evidence(root: Path, manifest: dict[str, dict[str, str]]) -> bool:
    """Independent file bytes vs sha256 AND Git blob SHA1; no symlink escape."""
    if not manifest:
        return False
    real_root = root.resolve(strict=True)
    for relative, hashes in manifest.items():
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
            return False
        path = real_root / relative
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(real_root):
            return False
        expected_sha256 = hashes.get("sha256", "")
        expected_blob = hashes.get("git_blob_sha1", "")
        if not _SHA256.fullmatch(expected_sha256) or not _SHA1.fullmatch(expected_blob):
            return False
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != expected_sha256:
            return False
        git_blob = hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()
        if git_blob != expected_blob:
            return False
    return True


def _moves_click_target(block: str) -> bool:
    """animation:none is safe; a duration/name on the clickable node is not."""
    for prop, value in re.findall(r"\b(animation(?:-[a-z-]+)?)\s*:\s*([^;}]+)", block, re.I):
        if prop.lower() != "animation" or not re.match(r"\s*none\b", value, re.I):
            return True
    return False


def check(spec: dict[str, Any]) -> dict[str, str]:
    """Ten strict source admission conditions; no claim of WINDOWS ACCEPTED."""
    result: dict[str, str] = {}
    def gate(n: int, passed: bool) -> None:
        result[f"E01-G1-{n:02d}"] = "SOURCE_GATE_PASS" if passed else "HOLD"

    # Immutable common identity is not the same thing as extracted source seal.
    gate(1, spec.get("git_commit") == BASE_COMMIT and spec.get("git_tree") == BASE_TREE)
    # Must be third-party owner6 approval of a *whole* extracted source manifest.
    seal = spec.get("owner6_source_lock") or {}
    gate(2, seal.get("owner") == 6 and seal.get("verified") is True
         and seal.get("git_commit") == BASE_COMMIT and seal.get("git_tree") == BASE_TREE
         and bool(seal.get("readback_receipt")) and bool(seal.get("all_source_sha256")))
    mounts = spec.get("mount_candidates", [])
    gate(3, isinstance(mounts, list) and len(mounts) == 1 and mounts[0] in ("PR63", "PR67"))
    cores = spec.get("core_ids")
    gate(4, isinstance(cores, list) and cores == list(CANONICAL_CORES))
    orbs = spec.get("orb_ids")
    gate(5, isinstance(orbs, list) and orbs == ["HELION", *CANONICAL_CORES])
    css = spec.get("cinema_css", "")
    # Catch PR30's movable clickable button; the cosmetic layer may move instead.
    button_rules = re.findall(r'\.nox-cinema-control\[data-nox-float="true"\]\s*\{([^}]*)\}', css) if isinstance(css, str) else []
    gate(6, isinstance(css, str) and bool(button_rules)
         and all(not _moves_click_target(block) for block in button_rules)
         and "pointer-events:none" in css)
    js = spec.get("cinema_js", "")
    gate(7, isinstance(js, str) and "(!doc.hidden&&active)" in js
         and "if(disposed||!active||doc.hidden)return" in js)
    gate(8, isinstance(css, str) and "prefers-reduced-motion:reduce" in css
         and isinstance(js, str) and '"REDUCED"' in js)
    assets = spec.get("asset_receipts") or []
    gate(9, isinstance(assets, list) and len(assets) >= 4
         and len(set(x.get("path") for x in assets if isinstance(x, dict))) == len(assets)
         and all(isinstance(x, dict) and isinstance(x.get("path"), str) and x.get("path") for x in assets)
         and all(isinstance(x, dict) and _SHA256.fullmatch(x.get("pre_sha256", ""))
                 and x.get("pre_sha256") == x.get("post_sha256") for x in assets))
    source_paths = spec.get("changed_paths") or []
    gate(10, isinstance(source_paths, list) and bool(source_paths)
         and all(isinstance(p, str) and p.startswith("proposals/P01/")
                 and ".." not in Path(p).parts for p in source_paths)
         and not any(p.lower().endswith((".exe", ".dll", ".zip")) for p in source_paths))
    return result


def overall(spec: dict[str, Any]) -> dict[str, Any]:
    checks = check(spec)
    return {"checks": checks, "source_admission": "CANDIDATE_ONLY" if all(v == "SOURCE_GATE_PASS" for v in checks.values()) else "HOLD",
            "integrated": "HOLD", "windows_accepted": "NOT_RUN", "release_percent": "N/D"}
