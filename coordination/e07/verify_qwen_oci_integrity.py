"""Fail-closed byte-level OCI cache provenance for frozen Qwen2.5-Coder:1.5b.

A read-only release test for an *existing* Ollama installation, not a provider,
model downloader, approval decision or E07 acceptance. No model bytes are copied.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

MODEL = "qwen2.5-coder:1.5b"
APPROVED_MANIFEST_SHA256 = "d7372fd828518a4d38b1eb196c673c31a85f2ed302b3d1e406c4c2d1b64a0668"
_DIGEST = re.compile(r"sha256:([0-9a-f]{64})\Z")
_MAX_MANIFEST = 2_000_000
_MAX_TOTAL = 8 * 1024**3


class IntegrityHold(RuntimeError):
    pass


def _nonreparse(path: Path, root: Path) -> None:
    """Reject reparse/symlink components, including final file and cache root."""
    try:
        relative = path.relative_to(root)
        chain = [root] + [root.joinpath(*relative.parts[:n])
                          for n in range(1, len(relative.parts) + 1)]
        for item in chain:
            mode = item.lstat().st_mode
            if stat.S_ISLNK(mode) or item.is_symlink() or getattr(item, "is_junction", lambda: False)():
                raise IntegrityHold("OCI_REPARSE_COMPONENT_HOLD")
    except (OSError, ValueError):
        raise IntegrityHold("OCI_PATH_UNTRUSTED_HOLD") from None


def _read_hash(path: Path, root: Path, expected: str, size: int | None = None,
               *, capture: bool = False) -> bytes | int:
    _nonreparse(path, root)
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or (size is not None and before.st_size != size):
            raise IntegrityHold("OCI_FILE_SIZE_OR_KIND_HOLD")
        if capture and before.st_size > _MAX_MANIFEST:
            raise IntegrityHold("OCI_MANIFEST_OVERSIZE_HOLD")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
        try:
            opened = os.fstat(fd)
            fingerprint = lambda st: (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns)
            if not stat.S_ISREG(opened.st_mode) or fingerprint(before) != fingerprint(opened):
                raise IntegrityHold("OCI_FD_IDENTITY_HOLD")
            hasher = hashlib.sha256()
            payload = bytearray() if capture else None
            amount = 0
            while part := os.read(fd, 1024 * 1024):
                amount += len(part)
                if amount > (_MAX_MANIFEST if capture else _MAX_TOTAL):
                    raise IntegrityHold("OCI_FILE_OVERSIZE_HOLD")
                hasher.update(part)
                if payload is not None:
                    payload.extend(part)
            if (hasher.hexdigest() != expected or amount != opened.st_size or
                    (size is not None and amount != size)):
                raise IntegrityHold("OCI_SHA256_OR_SIZE_HOLD")
            if fingerprint(opened) != fingerprint(os.fstat(fd)) or fingerprint(before) != fingerprint(path.lstat()):
                raise IntegrityHold("OCI_CHANGED_WHILE_READING_HOLD")
            _nonreparse(path, root)
            return bytes(payload) if payload is not None else amount
        finally:
            os.close(fd)
    except OSError:
        raise IntegrityHold("OCI_FILE_IO_HOLD") from None


def _unique(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise IntegrityHold("OCI_DUPLICATE_JSON_FIELD_HOLD")
        out[key] = value
    return out


def verify(root: Path, manifest_digest: str) -> dict:
    """Verify the frozen manifest bytes and every described OCI layer/config byte."""
    if not re.fullmatch(r"[0-9a-f]{64}", manifest_digest):
        raise IntegrityHold("OCI_EXPECTED_MANIFEST_DIGEST_INVALID")
    root = root.absolute()
    # Ollama v0.40.13 writes a SHA-pinned named manifest into manifests-v2.
    # Always prefer that canonical store to a possibly stale legacy manifest.
    # A present but invalid v2 entry MUST HOLD; no downgrade to the legacy path.
    v2 = root / "manifests-v2/ollama.com/library/qwen2.5-coder/1.5b"
    legacy = root / "manifests/registry.ollama.ai/library/qwen2.5-coder/1.5b"
    manifest_path = v2 if (v2.exists() or v2.is_symlink() or
                           getattr(v2, "is_junction", lambda: False)()) else legacy
    payload = _read_hash(manifest_path, root, manifest_digest, capture=True)
    try:
        manifest = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique,
                              parse_constant=lambda _: (_ for _ in ()).throw(IntegrityHold("OCI_JSON_NONFINITE_HOLD")))
    except (UnicodeError, ValueError):
        raise IntegrityHold("OCI_MANIFEST_JSON_HOLD") from None
    if type(manifest) is not dict:
        raise IntegrityHold("OCI_MANIFEST_SCHEMA_HOLD")
    # A v2 tag can point to an Ollama manifest-list. Its PARENT hash is pinned
    # above; follow only one local runner's content-addressed child and verify
    # that child byte-for-byte before touching any weights.
    if manifest.get("mediaType") == "application/vnd.ollama.manifest.list.v2+json":
        options = manifest.get("manifests")
        if (manifest.get("schemaVersion") != 2 or type(options) is not list or
                not 1 <= len(options) <= 16 or
                any(type(item) is not dict for item in options)):
            raise IntegrityHold("OCI_MANIFEST_LIST_SCHEMA_HOLD")
        child = None
        for runner in ("llamacpp", "ggml", "mlx"):
            matches = [item for item in options if item.get("runner") == runner]
            if matches:
                if len(matches) != 1:
                    raise IntegrityHold("OCI_MANIFEST_RUNNER_AMBIGUOUS_HOLD")
                child = matches[0]
                break
        if child is None or child.get("mediaType") != "application/vnd.docker.distribution.manifest.v2+json":
            raise IntegrityHold("OCI_MANIFEST_RUNNER_NOT_FOUND_HOLD")
        if "digest" in child:
            match = _DIGEST.fullmatch(str(child["digest"]))
            if not match:
                raise IntegrityHold("OCI_MANIFEST_CHILD_DIGEST_HOLD")
            child_raw = _read_hash(root / "blobs" / ("sha256-" + match.group(1)),
                                   root, match.group(1), capture=True)
            try:
                manifest = json.loads(child_raw.decode("utf-8"), object_pairs_hook=_unique)
            except (UnicodeError, ValueError):
                raise IntegrityHold("OCI_MANIFEST_CHILD_JSON_HOLD") from None
        else:
            # Inline child is authenticated by the already-verified parent SHA.
            manifest = child
    if (type(manifest.get("config")) is not dict or
            type(manifest.get("layers")) is not list or not manifest["layers"] or
            len(manifest["layers"]) > 48):
        raise IntegrityHold("OCI_MANIFEST_SCHEMA_HOLD")
    entries = [manifest["config"], *manifest["layers"]]
    verified = []
    overall = 0
    seen = set()
    for entry in entries:
        if type(entry) is not dict or type(entry.get("size")) is not int:
            raise IntegrityHold("OCI_LAYER_SCHEMA_HOLD")
        match = _DIGEST.fullmatch(str(entry.get("digest", "")))
        if not match or not 0 <= entry["size"] <= _MAX_TOTAL:
            raise IntegrityHold("OCI_LAYER_DIGEST_OR_SIZE_HOLD")
        digest = match.group(1)
        if digest in seen:
            raise IntegrityHold("OCI_DUPLICATE_LAYER_DIGEST_HOLD")
        seen.add(digest)
        overall += entry["size"]
        if overall > _MAX_TOTAL:
            raise IntegrityHold("OCI_TOTAL_SIZE_HOLD")
        path = root / "blobs" / ("sha256-" + digest)
        _read_hash(path, root, digest, entry["size"])
        verified.append({"sha256": digest, "bytes": entry["size"]})
    return {"schema": "nox.qwen.oci.bytes.v1", "model": MODEL,
            "manifest_sha256": manifest_digest, "verified_blobs": len(verified),
            "verified_blob_bytes": overall, "independent_weights_sha_verified": True,
            "release_accepted": False, "independent_e07": "HOLD"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ollama-model-root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    receipt = {"schema": "nox.qwen.oci.bytes.v1", "model": MODEL,
               "independent_weights_sha_verified": False,
               "release_accepted": False, "independent_e07": "HOLD"}
    try:
        if not (sys.platform == "win32" and os.environ.get("GITHUB_ACTIONS") == "true" and
                os.environ.get("RUNNER_OS") == "Windows" and
                os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted" and
                os.environ.get("GITHUB_REPOSITORY") == "MSSTXNEWS/nox-helion-pp-private-build"):
            raise IntegrityHold("OCI_PHYSICAL_WINDOWS_RUNNER_REQUIRED")
        receipt.update(verify(args.ollama_model_root, APPROVED_MANIFEST_SHA256))
        receipt["first_unmet_gate"] = "ACTIVE_STOP_HISTORY_UI_E07_FULL_SAME_SETUP_NOT_PROVEN"
    except IntegrityHold as exc:
        receipt["first_unmet_gate"] = str(exc)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, sort_keys=True, indent=2), encoding="utf-8")
    print("NOX_QWEN_OCI_BYTES_GATE", receipt["first_unmet_gate"], flush=True)
    return 0 if receipt["independent_weights_sha_verified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
