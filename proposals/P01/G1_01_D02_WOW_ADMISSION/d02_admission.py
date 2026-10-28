"""NOX V16 E01 source-only, fail-closed D02/WOW merge admission.

This does not mount scenes, modify host, certify installation, or attest assets.
An E06 integrator supplies independent receipts and on-disk original files.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path, PurePosixPath
from typing import Any

BASE_COMMIT = "0b3a7d435be735148d64171deb9027093a89646e"
BASE_TREE = "f108d604c444f718b32aaecfd07b90b8f91b9a6f"
CANONICAL_CORES = (
    "CONSCIOUSNESS", "PERSONA", "ATLAS", "VOICE",
    "REFLECTION", "CORE", "NEXUS", "FORGE",
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SHA1 = re.compile(r"^[0-9a-f]{40}$")


def file_evidence(root: Path | str, manifest: dict[str, dict[str, str]]) -> bool:
    """Fail closed on missing bytes, symlinks, malformed receipts and SHA mismatch.

    This function verifies local files only, not an E06 signed SourceLock.
    """
    if not isinstance(root, (Path, str)) or not isinstance(manifest, dict) or not manifest:
        return False
    try:
        real_root = Path(root).resolve(strict=True)
        if not real_root.is_dir():
            return False
        for relative, hashes in manifest.items():
            if (not isinstance(relative, str) or not relative or "\\" in relative or
                PurePosixPath(relative).is_absolute() or
                any(part in (".", "..") for part in relative.split("/")) or
                not isinstance(hashes, dict)):
                return False
            path = real_root / relative
            if (not path.is_file() or path.is_symlink() or
                not path.resolve(strict=True).is_relative_to(real_root)):
                return False
            expected_sha256 = hashes.get("sha256")
            expected_blob = hashes.get("git_blob_sha1")
            if (not isinstance(expected_sha256, str) or
                not isinstance(expected_blob, str) or
                not _SHA256.fullmatch(expected_sha256) or
                not _SHA1.fullmatch(expected_blob)):
                return False
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != expected_sha256:
                return False
            git_blob = hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()
            if git_blob != expected_blob:
                return False
    except (OSError, ValueError, TypeError):
        return False
    return True


def _moves_click_target(block: str) -> bool:
    """animation:none is safe; a duration/name on the clickable node is not."""
    for prop, value in re.findall(r"\b(animation(?:-[a-z-]+)?)\s*:\s*([^;}]+)", block, re.I):
        if prop.lower() != "animation" or not re.match(r"\s*none\b", value, re.I):
            return True
    return False


def _stable_control_css(css: str) -> bool:
    """Conservative source gate: animate pseudo-light, never the click hitbox."""
    if not isinstance(css, str):
        return False
    source = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    controls = 0
    after_safe = False
    for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", source):
        names = [part.strip() for part in selector.split(",")]
        if any(".nox-cinema-control" in part and "::after" in part for part in names):
            after_safe |= bool(re.search(r"pointer-events\s*:\s*none\b", body, re.I))
        if not any(".nox-cinema-control" in part and
                   "::before" not in part and "::after" not in part for part in names):
            continue
        controls += 1
        if _moves_click_target(body):
            return False
        for _, value in re.findall(r"(?:^|;)\s*(transform|translate|rotate|scale)\s*:\s*([^;}]*)", body, re.I):
            if not re.fullmatch(r"\s*none\s*(?:!important)?\s*", value, re.I):
                return False
    return controls > 0 and after_safe


def _visibility_veto(js: str) -> bool:
    """Require *independent* host/viewport/document vetoes from reviewed PR82.

    A source-text gate is not a substitute for live WebView2 behavioral QA.
    """
    if not isinstance(js, str):
        return False
    c = re.sub(r"\s+", "", re.sub(r"/\*.*?\*/|//[^\n]*", "", js, flags=re.S))
    required = (
        "functionisActive(){return!disposed&&!doc.hidden&&hostVisible&&intersectVisible;}",
        'root.dataset.noxFxVisible=isActive()?"true":"false";',
        "if(isActive())wake();elsesleep();",
        "if(!isActive())return;",
        "intersectVisible=items.some(x=>x.isIntersecting);syncVisible();",
        "setVisible(value){hostVisible=value===true;syncVisible();}",
    )
    return all(token in c for token in required)


def _asset_bytes_verified(spec: dict[str, Any]) -> bool:
    """Receipts are never enough without exact local asset bytes."""
    assets = spec.get("asset_receipts")
    if not isinstance(assets, list) or len(assets) < 4:
        return False
    manifest: dict[str, dict[str, str]] = {}
    for item in assets:
        if not isinstance(item, dict):
            return False
        path = item.get("path")
        pre, post, blob = item.get("pre_sha256"), item.get("post_sha256"), item.get("git_blob_sha1")
        if (not isinstance(path, str) or path in manifest or
            not isinstance(pre, str) or not _SHA256.fullmatch(pre) or
            not isinstance(post, str) or post != pre or
            not isinstance(blob, str) or not _SHA1.fullmatch(blob)):
            return False
        manifest[path] = {"sha256": post, "git_blob_sha1": blob}
    return file_evidence(spec.get("asset_root"), manifest)


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
    # PR30 movable clickable target is unsafe, PR82 moves only a pseudo overlay.
    gate(6, _stable_control_css(css))
    js = spec.get("cinema_js", "")
    # Old single-active visibility gate cannot admit PR82; reject missing vetoes.
    gate(7, _visibility_veto(js))
    gate(8, isinstance(css, str) and bool(re.search(
            r"@media\s*\(\s*prefers-reduced-motion\s*:\s*reduce\s*\)", css, re.I))
         and isinstance(js, str) and '"REDUCED"' in js
         and "if(preference)sleep();" in re.sub(r"\s+", "", js))
    gate(9, _asset_bytes_verified(spec))
    source_paths = spec.get("changed_paths") or []
    gate(10, isinstance(source_paths, list) and bool(source_paths)
         and all(isinstance(p, str) and p.startswith("proposals/P01/")
                 and "\\" not in p and "//" not in p and ".." not in PurePosixPath(p).parts
                 and PurePosixPath(p).suffix.lower() not in (".exe", ".dll", ".zip") for p in source_paths)
         and not any(p.lower().endswith((".exe", ".dll", ".zip")) for p in source_paths))
    return result


def overall(spec: dict[str, Any]) -> dict[str, Any]:
    checks = check(spec)
    return {"checks": checks, "source_admission": "CANDIDATE_ONLY" if all(v == "SOURCE_GATE_PASS" for v in checks.values()) else "HOLD",
            "integrated": "HOLD", "windows_accepted": "NOT_RUN", "release_percent": "N/D"}
