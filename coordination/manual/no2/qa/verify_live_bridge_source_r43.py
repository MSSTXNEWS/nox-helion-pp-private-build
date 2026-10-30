"""NOX V16 T08: read-only source evidence classifier for WPF -> Python live bridge.

This is deliberately NOT a SOURCE_READY or Windows acceptance signer.  It avoids
mistaking a successful diagnostic --diagnose process for working chat/STOP/RAG.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import stat

FILES = {
    "builder": "coordination/e06/build_onehost_installer.ps1",
    "diagnostic_bridge": "coordination/e06/OriginalPythonDiagnosticBridge.cs",
    "native_ingress": "Packages/P02/worker-python/p02_native_ingress.py",
}
MAX_BYTES = 2_000_000
SCOPE_RE = re.compile(r"(?:^|[;\n])\s*native_bridge_scope\s*=\s*['\"]([^'\"\r\n]+)['\"]", re.I)
DIAG_ARGS_RE = re.compile(r'\bArguments\s*=\s*"--diagnose"')
DIAG_RESULT_RE = re.compile(r'\bdiagnosticOnly\s*=\s*true\b', re.I)


class EvidenceHold(ValueError):
    pass


def _safe_text(root: Path, relative: str) -> tuple[str, dict]:
    """Read only canonical, regular source files; reject symlinked ancestors."""
    current = root
    for part in Path(relative).parts:
        if part in ("", ".", ".."):
            raise EvidenceHold("UNSAFE_SOURCE_PATH")
        current = current / part
        if current.is_symlink():
            raise EvidenceHold("SOURCE_SYMLINK_NOT_ACCEPTED:" + relative)
    if not current.is_file():
        raise EvidenceHold("REQUIRED_SOURCE_MISSING:" + relative)
    st = current.stat()
    if not stat.S_ISREG(st.st_mode) or st.st_size <= 0 or st.st_size > MAX_BYTES:
        raise EvidenceHold("SOURCE_NOT_BOUNDED_REGULAR_FILE:" + relative)
    raw = current.read_bytes()
    if len(raw) != st.st_size:
        raise EvidenceHold("SOURCE_CHANGED_DURING_READ:" + relative)
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise EvidenceHold("SOURCE_INVALID_UTF8:" + relative) from exc
    return text, {"path": relative, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def audit(root: Path) -> dict:
    """Report evidence, never infer that live Windows runtime or E07 has passed."""
    result = {
        "schema": "NOX_V16_T08_R43_LIVE_BRIDGE_SOURCE_EVIDENCE_V1",
        "status": "HOLD",
        "sourceReady": False,
        "independentT08Accepted": False,
        "nativeWindowsTested": False,
        "e07Accepted": False,
        "sourceFiles": [],
        "observations": {},
        "blockers": [],
    }
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        result["blockers"].append("SOURCE_ROOT_UNSAFE_OR_MISSING")
        return result
    sources = {}
    for name, path in FILES.items():
        try:
            sources[name], evidence = _safe_text(root, path)
            result["sourceFiles"].append(evidence)
        except (EvidenceHold, OSError) as exc:
            result["blockers"].append(str(exc) if isinstance(exc, EvidenceHold) else "SOURCE_IO_HOLD:" + name)
    if len(sources) != len(FILES):
        return result

    scopes = SCOPE_RE.findall(sources["builder"])
    diagnostic_only = DIAG_ARGS_RE.search(sources["diagnostic_bridge"]) is not None
    diagnostic_result = DIAG_RESULT_RE.search(sources["diagnostic_bridge"]) is not None
    ingress_available = (
        re.search(r"(?m)^class NativeIngress\s*:", sources["native_ingress"]) is not None
        and re.search(r"(?m)^\s+def handle\(self, encoded:\s*bytes\)", sources["native_ingress"]) is not None
    )
    result["observations"] = {
        "builderBridgeScope": scopes[0] if len(scopes) == 1 else None,
        "scopeDeclarations": len(scopes),
        "diagnosticCliOnlyObserved": diagnostic_only,
        "diagnosticOnlyResponseObserved": diagnostic_result,
        "nativeIngressSourceExists": ingress_available,
    }
    if len(scopes) != 1:
        result["blockers"].append("EXACTLY_ONE_BUILDER_BRIDGE_SCOPE_REQUIRED")
    elif scopes[0] == "ORIGINAL_PYTHON_READ_ONLY_DIAGNOSE":
        result["blockers"].append("BUILDER_DECLARES_DIAGNOSTIC_ONLY_NOT_LIVE")
    if diagnostic_only and diagnostic_result:
        result["blockers"].append("DIAGNOSTIC_BRIDGE_NOT_LIVE_FUNCTION_PROOF")
    if not ingress_available:
        result["blockers"].append("EXISTING_NATIVE_INGRESS_SOURCE_NOT_FOUND")
    if not result["blockers"]:
        # An absent diagnostic marker is not evidence of a working live bridge.
        result["blockers"].append("LIVE_NATIVE_WPF_IPC_OWNER_RECEIPT_NOT_VERIFIED")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    output = json.dumps(audit(args.root), ensure_ascii=False, indent=2) + "\n"
    if args.out:
        if args.out.is_symlink() or args.out.exists():
            parser.error("OUTPUT_ALREADY_EXISTS_NO_OVERWRITE")
        args.out.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 2  # Source-only evidence classifier never self-accepts SOURCE_READY.


if __name__ == "__main__":
    raise SystemExit(main())
