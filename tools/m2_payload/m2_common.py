"""Shared constants for the M2.0 payload/fixtures stripe.

The reference executable is identified so builds can refuse to replace it.
Nothing here signs an owner acknowledgement or claims a live model.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

VERSION = "M2.0-PP"
CANDIDATE_GUI_NAME = "NOX_HELION_M2_0_PAYLOAD"
CANDIDATE_BACKGROUND_NAME = "NOX_HELION_M2_0_BACKGROUND"
MARKER_NAME = "M2_PACKAGED_MARKER.txt"
MARKER_TEXT = "NOX_M2_0_PAYLOAD_PACKAGED\nversion=M2.0-PP\nnot_reference_exe=true\n"

REFERENCE_EXE_NAME = "NOX_HELION_PRIVATE_CANDIDATE.exe"
REFERENCE_EXE_SHA256 = "93a329ba1ece9cfd66951b377e04e9c1166ec6ba3ce13a5911ba8e36de99dfb8"
REFERENCE_EXE_BYTES = 79088677
REFERENCE_SOURCE_COMMIT = "ca1a876018655b7b3d12c7fb8f273def8d1e45ad"
REFERENCE_BACKGROUND_SHA256 = "a92594e1f0d349c2e7b8903655a69dace5f8e096557ebda82616d7e6d0ad40b7"

QWEN_MODEL_TAG = "qwen2.5:0.5b-instruct-q4_K_M"
QWEN_LAYER_SHA256 = "c5396e06af294bd101b30dce59131a76d2b773e76950acc870eda801d3ab0515"
QWEN_LAYER_BYTES = 397807936

# Kinds the Windows first-run product_payload_gate requires and this repo does not contain.
ABSENT_PRODUCT_KINDS = (
    "base_model",
    "tokenizer",
    "adapter",
    "rag_index",
    "cultural_index",
)

PERSONA_CODES = {
    "persona.kairen_voss": "KV",
    "persona.adrian_marrow": "AM",
    "persona.leon_ardis": "LA",
    "persona.elina_veil": "EV",
    "persona.kassien_veir": "KW",
}

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PAYLOAD_ROOT = REPO_ROOT / "build_inputs" / "m2"
ARTIFACT_PREFIX = "NOX_HELION_M2_0_PAYLOAD_FIXTURES_20261103_"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def rel_files(root: Path) -> list[Path]:
    """Regular files under root, posix-sorted, skipping nothing."""
    files = [path for path in root.rglob("*") if path.is_file() and not path.is_symlink()]
    return sorted(files, key=lambda path: path.relative_to(root).as_posix())
