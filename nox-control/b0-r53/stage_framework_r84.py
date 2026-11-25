"""Add only the pinned R83 constructor fence to an already staged R81 root.

Offline private staging only. Does not select framing or grant native authority.
"""
from pathlib import Path
from stage_framework_r81 import PINS, DEST as R80_DEST, SOURCE_PIN as R80_PIN, blob

SOURCE = Path(__file__).resolve().with_name("b0_framework_r83.py")
SOURCE_PIN = "9f7ae9ddc837d4fb67a2584c647fdec85764e05f"
DEST = str(Path(R80_DEST).with_name("b0_framework_r83.py").as_posix())
DEPENDENCIES = {**PINS, R80_DEST: R80_PIN}


def stage_r83(root):
    root = Path(root).resolve(strict=True)
    for name, pin in DEPENDENCIES.items():
        path = root / name
        if path.resolve() != path or not path.is_file() or blob(path.read_bytes()) != pin:
            raise ValueError("HOLD_R84_DEPENDENCY:" + name)
    raw = SOURCE.read_bytes()
    if blob(raw) != SOURCE_PIN:
        raise ValueError("HOLD_R84_SOURCE")
    target = root / DEST
    if target.resolve() != target or target.exists():
        raise ValueError("HOLD_R84_OVERWRITE")
    with target.open("xb") as f:
        f.write(raw)
    return target
