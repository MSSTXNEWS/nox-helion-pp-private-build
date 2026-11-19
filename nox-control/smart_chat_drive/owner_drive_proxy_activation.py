"""Activate the Drive truth patch on only the live Resonance Python proxy."""

from hashlib import sha256
import json
import sys
from pathlib import Path
from types import ModuleType


CONTROL_SHA = "fdd6e646c8cef1fad9a6d39afa2723375fa2e6126bf4da4989b751ffc2355de0"
PROXY = "chat_proxy.py"
PROXY_BEFORE = "54b1932c3e408c91c3086de994eb9b85709d65066746b5ca520582829ab94d89"
COMPANIONS = frozenset({
    "owner_drive_chat_route.py", "nox_dialog_followup.py", "owner_drive_chat_health.py",
    "owner_native_drive_probe.py",
})
RETAIN = {
    "nox_v29_chat_bridge.py": "3b1f1c22279b2fbca3be03ef53579e8dd93ab3ea44a3c5404e7584f07e3bbf1b",
    "nox_v38_native_context.py": "32fa7c3729bbb7a4ab3e43183f10fec70e4c9254d0f9c2f9458db68c1c4a6deb",
    "nox_v38_s03_native.py": "c1c4d77d86e833c69b5af8cee82bbd83211ca0184f4a63f66dc067eb0b50ebc3",
    "nox_s03_scoped_pair.py": "d347ff7247e2f883b955094ca4e98205346ddb6e39b0fa52e13c360a8144c57f",
    "nox_v38_self_model.py": "b15bf20557601028ecc4e6163d1d6add682616d466fa9fb78b3640411f7c1ada",
}


def activate(control_bytes, transform, companions):
    """Transform the pinned proxy on-host, then reuse the exact owner cutover."""
    if type(control_bytes) is not bytes or sha256(control_bytes).hexdigest() != CONTROL_SHA:
        raise ValueError("HOLD_DRIVE_PROXY_CONTROL_PIN")
    if not callable(transform):
        raise ValueError("HOLD_DRIVE_PROXY_TRANSFORM")
    if type(companions) is not dict or set(companions) != COMPANIONS:
        raise ValueError("HOLD_DRIVE_PROXY_COMPANION_SCOPE")
    if any(type(raw) is not bytes for raw in companions.values()):
        raise ValueError("HOLD_DRIVE_PROXY_COMPANION_BYTES")

    old = b'need(raw is not None and digest(raw) == PREIMAGE[name], "SOURCE_PREIMAGE")'
    new = (b'need(raw is None if PREIMAGE[name] is None else '
           b'raw is not None and digest(raw) == PREIMAGE[name], "SOURCE_PREIMAGE")')
    if control_bytes.count(old) != 1:
        raise ValueError("HOLD_DRIVE_PROXY_CONTROL_SHAPE")
    control_bytes = control_bytes.replace(old, new, 1)

    control = ModuleType("_nox_drive_truth_owner_control")
    sys.modules[control.__name__] = control
    try:
        exec(compile(control_bytes, "<pinned-cognition-activation>", "exec"), control.__dict__)
        control.PREIMAGE = {PROXY: PROXY_BEFORE}
        control.KEEP.pop(PROXY)
        control.KEEP.update(RETAIN)
        control.STOP += (Path("/root/nox/state/MEMORY_STOP.flag"),)
        source = control.current_patch_preimages()[PROXY]
        candidate = transform(source)
        if type(candidate) is not bytes or not candidate or candidate == source:
            raise ValueError("HOLD_DRIVE_PROXY_CANDIDATE")
        control.PREIMAGE = {**dict.fromkeys(sorted(COMPANIONS)), PROXY: PROXY_BEFORE}
        payloads = {**companions, PROXY: candidate}
        pins = {name: sha256(raw).hexdigest() for name, raw in payloads.items()}
        receipt = control.activate(payloads=payloads, sha256=pins)
        receipt["schema"] = "NOX_NATIVE_DRIVE_TRUTH_PROXY_RELEASE_V1"
        receipt["proxy_preimage_sha256"] = PROXY_BEFORE
        receipt["proxy_postimage_sha256"] = pins[PROXY]
        return receipt
    finally:
        sys.modules.pop(control.__name__, None)


def emit(receipt):
    print("NOX_MAINT_REPAIR=" + json.dumps({"kind": "drive_truth_proxy_release", "data": receipt},
          sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False), flush=True)
    print("NOX_MAINT_REPAIR_COMPLETE=true", flush=True)
