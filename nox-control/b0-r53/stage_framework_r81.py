"""B0 R81: additive, offline framework entrypoint for verified R111 extraction.
Caller must select a private staging root; never use on a live server.
Selection of framing and native authority remain with the authenticated owner.
"""
import hashlib
from pathlib import Path

SOURCE = Path(__file__).resolve().with_name("b0_framework_r80.py")
WIRE = "nox-control/d3-r111/wire/"
DEST = WIRE + "b0_framework_r80.py"
PINS = {
    "nox-control/a6-r109-r80-release/release.json": "513f61f098574f438b8f9974cfd7ca5f7002428d",
    "nox-control/d3-r111/inputs/b0.json": "b0ec743f17d94a1399b1fc3d8860d6d9a4d55d14",
    WIRE+"b0_http_chunked_r76.py": "0f2698d56723bed3615b40ad8c4f98894189ed50",
    WIRE+"b0_proxy_stream_iter.py": "385906bc443effbea92f38b881c13d04d2103e28",
    WIRE+"b0_named_delta_encoder.py": "c7d0c351b0239bb7155ffbc8c0362e919ee79cb1",
}
SOURCE_PIN = "659876e07af733988d8499221180f66c9d90ca20"

def blob(raw):
    return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()

def stage_framework(root):
    root = Path(root).resolve(strict=True)
    for name, pin in PINS.items():
        path = root/name
        if path.resolve() != path or not path.is_file() or blob(path.read_bytes()) != pin:
            raise ValueError("HOLD_FRAMEWORK_DEPENDENCY:"+name)
    raw = SOURCE.read_bytes()
    if blob(raw) != SOURCE_PIN:
        raise ValueError("HOLD_FRAMEWORK_SOURCE")
    target = root/DEST
    if target.resolve() != target or target.exists():
        raise ValueError("HOLD_FRAMEWORK_OVERWRITE")
    # Existing wire directory only, no replacement or path creation.
    with target.open("xb") as f:
        f.write(raw)
    return target
