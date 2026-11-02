"""Read-only original P01/NSIS uninstall admission for same-VM T06 smoke.

A completed NSIS process is not proof of a complete uninstall. Verify that
EVERY manifest-owned installed file and original NSIS metadata disappeared,
while permitting unrelated files and keeping user data outside the app root.
This is only SAME-VM component evidence, never independent E07 acceptance.
"""
from __future__ import annotations

from pathlib import Path


_UNINSTALL_KEY = (
    r"Software\Microsoft\Windows\CurrentVersion\Uninstall\NOXHELION.P01"
)


def owned_payload_paths(install: Path, inventory: dict) -> tuple[Path, ...]:
    """Snapshot exact original manifest paths BEFORE running Uninstall.exe."""
    if (not isinstance(install, Path) or not install.is_dir() or
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
            if (not path.is_file() or path.is_symlink() or
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
    """Query BOTH Windows registry views; access errors must HOLD, not PASS."""
    if registry is None:
        import winreg as registry
    for view in (registry.KEY_WOW64_32KEY, registry.KEY_WOW64_64KEY):
        try:
            key = registry.OpenKey(registry.HKEY_CURRENT_USER, _UNINSTALL_KEY,
                                   0, registry.KEY_READ | view)
        except FileNotFoundError:
            continue
        registry.CloseKey(key)
        return False
    return True


def verify_original_uninstall(install: Path, owned_paths: tuple[Path, ...],
                              registry=None) -> None:
    """Only a complete removal of original owned files and key passes."""
    if (not owned_paths or
            any(p.exists() or p.is_symlink() for p in owned_paths)):
        raise RuntimeError("T06_CONSERVATIVE_UNINSTALL_MANIFEST_FILE_REMAINS")
    for metadata in ("payload.sha256.json", "nox-p01-owned.txt", "Uninstall.exe"):
        path = install / metadata
        if path.exists() or path.is_symlink():
            raise RuntimeError("T06_CONSERVATIVE_UNINSTALL_METADATA_REMAINS")
    if not original_nsis_uninstall_registration_absent(registry):
        raise RuntimeError("T06_CONSERVATIVE_UNINSTALL_REGISTRY_REMAINS")
