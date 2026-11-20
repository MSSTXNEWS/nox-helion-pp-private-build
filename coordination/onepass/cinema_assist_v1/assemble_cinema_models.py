"""Reassemble large NOX Cinema model files from numbered Drive parts."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "NOX_CINEMA_MODEL_MANIFEST.json"
PART_SIZE = 90 * 1024 * 1024


def digest(path: Path) -> tuple[int, str]:
    h = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(block)
            h.update(block)
    return size, h.hexdigest()


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    completed = 0
    for model in manifest["models"]:
        folder = ROOT / model.get("drive_folder", model["directory"])
        if not folder.exists():
            folder = ROOT / model["directory"]
        for item in model["files"]:
            if item["bytes"] <= PART_SIZE:
                continue
            target = folder / item["file"]
            if target.is_file() and digest(target) == (item["bytes"], item["sha256"]):
                print(f"OK already complete: {target.relative_to(ROOT)}")
                completed += 1
                continue
            names = item.get("drive_parts")
            if not names:
                part_count = (item["bytes"] + PART_SIZE - 1) // PART_SIZE
                names = [f"{item['file']}.part{index:04d}" for index in range(1, part_count + 1)]
            part_size = int(item.get("drive_part_size_bytes", PART_SIZE))
            parts = [folder / name for name in names]
            missing = [path.name for path in parts if not path.is_file()]
            if missing:
                print(f"MISSING {target.name}: " + ", ".join(missing))
                continue
            pending = target.with_name(target.name + ".rebuild")
            if pending.exists():
                pending.unlink()
            with pending.open("wb") as out:
                for index, part in enumerate(parts, start=1):
                    expected_size = min(part_size, item["bytes"] - (index - 1) * part_size)
                    if part.stat().st_size != expected_size:
                        raise SystemExit(f"BAD PART SIZE: {part.name} expected={expected_size} actual={part.stat().st_size}")
                    with part.open("rb") as src:
                        for block in iter(lambda: src.read(1024 * 1024), b""):
                            out.write(block)
            actual = digest(pending)
            if actual != (item["bytes"], item["sha256"]):
                pending.unlink(missing_ok=True)
                raise SystemExit(f"SHA256 MISMATCH: {target.name} bytes={actual[0]} sha256={actual[1]}")
            os.replace(pending, target)
            print(f"REBUILT {target.relative_to(ROOT)} bytes={actual[0]} sha256={actual[1]}")
            completed += 1
    required = sum(1 for model in manifest["models"] for item in model["files"] if item["bytes"] > PART_SIZE)
    print(f"Complete large model files: {completed}/{required}")
    return 0 if completed == required else 2


if __name__ == "__main__":
    raise SystemExit(main())
