"""NOX V16 E06 R07: exact-PR27 native route type admission (SOURCE/HOLD).

Read-only: tests the original owner module from the pinned checkout, never
performs a system operation, calls SIP, opens a network port, or rewrites it.
A passing fixture is not a Windows acceptance receipt.
"""
from __future__ import annotations
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

OWNER_COMMIT = "be1fe05d88443e41b0d196617840508d9dd39b7d"
SOURCE_BLOB = "486e4d29a2f4d859a2923122706657915da011aa"
CATALOG_BLOB = "c8c9b19e44d9b5ff3af00a38e8446d8c0507b69d"


def blob_sha1(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def audit(source: Path, catalog: Path) -> dict:
    src, cat = source.read_bytes(), catalog.read_bytes()
    hashes = {"source_sha256": hashlib.sha256(src).hexdigest(),
              "catalog_sha256": hashlib.sha256(cat).hexdigest(),
              "source_git_blob": blob_sha1(src), "catalog_git_blob": blob_sha1(cat)}
    if hashes["source_git_blob"] != SOURCE_BLOB or hashes["catalog_git_blob"] != CATALOG_BLOB:
        return {"status": "HOLD_PREIMAGE_DRIFT", "checks": [], **hashes}
    spec = importlib.util.spec_from_file_location("nox_pinned_owner_bridge_r07", source)
    if spec is None or spec.loader is None:
        return {"status": "HOLD_MODULE_UNAVAILABLE", "checks": [], **hashes}
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    host = module.NoxPackHost(json.loads(cat.decode("utf-8")))
    session = module.NativeSession("t", "p", "chat", allowed=frozenset({"helion.chat", "chat.history", "system.update"}),
                                   private_approved=frozenset({"system.update"}))
    checks = []
    for label, route, expected in (
        ("untrusted_json_array_route", [], "HostDenied"),
        ("untrusted_json_object_route", {}, "HostDenied"),
        ("untrusted_nested_route", ["helion.chat"], "HostDenied"),
        ("unknown_route", "nonexistent.route", "HostDenied"),
        ("sensitive_without_scope", "chat.history", "HostDenied"),
        ("dangerous_without_consent", "system.update", "HostDenied"),
        ("known_unbound_route", "helion.chat", "HostHold"),
    ):
        try:
            host.execute(route, {}, session)
            actual = "RETURNED"
        except Exception as exc:
            actual = type(exc).__name__
        checks.append({"id": label, "expected": expected, "actual": actual, "pass": actual == expected})
    # A valid route with a restricted session must be denied, not run.
    try:
        host.execute("helion.chat", {}, module.NativeSession("t", "p", "chat"))
        actual = "RETURNED"
    except Exception as exc:
        actual = type(exc).__name__
    checks.append({"id": "missing_route_scope", "expected": "HostDenied", "actual": actual,
                   "pass": actual == "HostDenied"})
    failures = [x["id"] for x in checks if not x["pass"]]
    return {"status": "HOLD_ROUTE_TYPE_ADMISSION" if failures else "SOURCE_GATE_PASS_ONLY",
            "owner_commit": OWNER_COMMIT, "checks": checks, "failures": failures,
            "windows_accepted": False, **hashes}


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    source = root / "proposals/NOX-PACK01-50/native_bridge.py"
    catalog = root / "proposals/NOX-PACK01-50/catalog.json"
    if len(sys.argv) == 3:
        source, catalog = Path(sys.argv[1]), Path(sys.argv[2])
    try:
        result = audit(source, catalog)
    except (OSError, ValueError, SyntaxError, TypeError) as exc:
        result = {"status": "HOLD_SOURCE_UNREADABLE", "reason": type(exc).__name__,
                  "windows_accepted": False}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "SOURCE_GATE_PASS_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
