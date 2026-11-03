"""Read-only original P01/NSIS uninstall admission for same-VM T06 smoke.

A completed NSIS process is not proof of a complete uninstall. Verify that
EVERY manifest-owned installed file and original NSIS metadata disappeared,
while permitting unrelated files and keeping user data outside the app root.
This is only SAME-VM component evidence, never independent E07 acceptance.
"""
from __future__ import annotations

from pathlib import Path
import json
import stat
import sys


_UNINSTALL_KEY = (
    r"Software\Microsoft\Windows\CurrentVersion\Uninstall\NOXHELION.P01"
)


def _no_reparse_components(path: Path, *, allow_missing: bool) -> bool:
    """Reject linked/junction path *ancestors*, even with an in-root target.

    Uninstall may remove leaf files/directories, so verification may allow
    absent components. Existing components remain fail-closed on inaccessible
    metadata; no parent path is followed through a junction or symlink.
    """
    if not isinstance(path, Path):
        return False
    for component in (path, *path.parents):
        try:
            metadata = component.lstat()
        except FileNotFoundError:
            if allow_missing:
                continue
            return False
        except OSError:
            return False
        if (stat.S_ISLNK(metadata.st_mode) or
                getattr(metadata, "st_file_attributes", 0) &
                getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
            return False
        try:
            if getattr(component, "is_junction", lambda: False)():
                return False
        except OSError:
            return False
    return True


def owned_payload_paths(install: Path, inventory: dict) -> tuple[Path, ...]:
    """Snapshot exact original manifest paths BEFORE running Uninstall.exe."""
    if (not isinstance(install, Path) or
            not _no_reparse_components(install, allow_missing=False) or
            not install.is_dir() or
            install.is_symlink() or getattr(install, "is_junction", lambda: False)() or
            type(inventory) is not dict or
            inventory.get("schema") != "NOX_P01_PAYLOAD_SHA256_V1" or
            type(inventory.get("files")) is not list or
            not 12 <= len(inventory["files"]) <= 50000):
        raise RuntimeError("T06_UNINSTALL_ORIGINAL_INVENTORY_HOLD")
    root = install.resolve(strict=True)
    paths = []
    seen = set()
    for item in inventory["files"]:
        name = item.get("path") if type(item) is dict else None
        if (type(name) is not str or not name or "\\" in name or
                ":" in name or "\x00" in name or name.startswith("/") or
                any(part in ("", ".", "..") for part in name.split("/")) or
                name.casefold() in seen):
            raise RuntimeError("T06_UNINSTALL_ORIGINAL_INVENTORY_PATH_HOLD")
        path = install.joinpath(*name.split("/"))
        try:
            if (not _no_reparse_components(path, allow_missing=False) or
                    not path.is_file() or path.is_symlink() or
                    getattr(path, "is_junction", lambda: False)() or
                    not path.resolve(strict=True).is_relative_to(root)):
                raise RuntimeError("T06_UNINSTALL_ORIGINAL_INVENTORY_PATH_HOLD")
        except (OSError, ValueError) as exc:
            raise RuntimeError("T06_UNINSTALL_ORIGINAL_INVENTORY_PATH_HOLD") from exc
        seen.add(name.casefold())
        paths.append(path)
    if ("nox.p01.shell.exe" not in seen or
            "backend/nox_helion_private_candidate.exe" not in seen):
        raise RuntimeError("T06_UNINSTALL_ORIGINAL_BINARIES_UNLISTED")
    return tuple(paths)


def original_nsis_uninstall_registration_absent(registry=None) -> bool:
    """Verify BOTH Windows registry hives and 32/64-bit views, fail-closed."""
    if registry is None:
        import winreg as registry
    # Real Windows winreg supplies HKLM; legacy offline test doubles model HKCU.
    hives = [registry.HKEY_CURRENT_USER]
    machine = getattr(registry, "HKEY_LOCAL_MACHINE", None)
    if machine is not None:
        hives.append(machine)
    for hive in hives:
        for view in (registry.KEY_WOW64_32KEY, registry.KEY_WOW64_64KEY):
            try:
                key = registry.OpenKey(hive, _UNINSTALL_KEY,
                                       0, registry.KEY_READ | view)
            except FileNotFoundError:
                continue
            registry.CloseKey(key)
            return False
    return True


def verify_original_uninstall(install: Path, owned_paths: tuple[Path, ...],
                              registry=None) -> None:
    """Only a complete removal of original owned files and key passes."""
    if not owned_paths:
        raise RuntimeError("T06_CONSERVATIVE_UNINSTALL_MANIFEST_FILE_REMAINS")
    for p in owned_paths:
        if (not _no_reparse_components(p, allow_missing=True) or
                p.exists() or p.is_symlink() or
                getattr(p, "is_junction", lambda: False)()):
            # Emit only one bounded, JSON-escaped manifest-relative name.
            # Never disclose the CI account path or accept lingering payload.
            try:
                relative=p.relative_to(install).as_posix()
            except (ValueError, TypeError, AttributeError):
                relative="[OUTSIDE_INSTALL_ROOT]"
            print("T06_UNINSTALL_FIRST_MANIFEST_RESIDUE " +
                  json.dumps(relative[:160], ensure_ascii=True),
                  file=sys.stderr, flush=True)
            # R116: gather read-only evidence of the FIRST actual physical
            # uninstall failure. Never rerun the remover, alter owned files,
            # accept residue, or replace this original fail-closed verdict.
            try:
                import importlib.util
                witness_source = Path(__file__).resolve().with_name(
                    "t06_uninstall_firstfail_witness.py")
                spec = importlib.util.spec_from_file_location(
                    "nox_t06_uninstall_readonly_witness", witness_source)
                if spec is None or spec.loader is None:
                    raise ImportError("T06_UNINSTALL_READONLY_WITNESS_MISSING")
                witness_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(witness_module)
                repo_root = Path(__file__).resolve().parents[2]
                remover_candidates = (
                    repo_root / "work/e06/staged/R11/Installer/Remove-InstalledPayload.ps1",
                    repo_root / "work/t06-wpf-p02-compile/R11/Installer/Remove-InstalledPayload.ps1",
                )
                remover = next((p for p in remover_candidates if p.is_file()), None)
                witness = witness_module.read_only_uninstall_failure_snapshot(
                    install, owned_paths, remover)
                print("T06_UNINSTALL_READONLY_FIRSTFAIL_WITNESS " +
                      json.dumps(witness, sort_keys=True, ensure_ascii=True),
                      file=sys.stderr, flush=True)
            except Exception as witness_error:
                print("T06_UNINSTALL_READONLY_WITNESS_HOLD " +
                      type(witness_error).__name__[:80],
                      file=sys.stderr, flush=True)
            raise RuntimeError("T06_CONSERVATIVE_UNINSTALL_MANIFEST_FILE_REMAINS")
    for metadata in ("payload.sha256.json", "nox-p01-owned.txt", "Uninstall.exe"):
        path = install / metadata
        if (not _no_reparse_components(path, allow_missing=True) or
                path.exists() or path.is_symlink() or
                getattr(path, "is_junction", lambda: False)()):
            raise RuntimeError("T06_CONSERVATIVE_UNINSTALL_METADATA_REMAINS")
    if not original_nsis_uninstall_registration_absent(registry):
        raise RuntimeError("T06_CONSERVATIVE_UNINSTALL_REGISTRY_REMAINS")
