"""Read-only original SEED evidence; never execute or extract donor scripts."""
from pathlib import Path
import hashlib
import json
import os
import stat
import zipfile

EXPECTED_ARCHIVE_SHA256 = "b1bc0c27997d76b4c654842101d28738080e8c83d3b077b12585aaa28b500c9f"
EXPECTED_GRU_SHA256 = "a58ab3523b2a063b502f0bb0211d3c67672ca5a259d64b32fa4450699bfb2566"
EXPECTED_OPTIMIZER_SHA256 = "24c4f4c7ab5699863d945ba1299b2d903b6ed224ccb324b55e514682739b2c53"
MAX_ZIP_BYTES = 32_000_000
MAX_MEMBER_BYTES = 8_000_000


def _sha256_stream(stream):
    digest = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(block)
    return digest.hexdigest()


def _regular_file(path: Path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or path.is_symlink() or (getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)):
        raise ValueError("SEED_UNTRUSTED_FILE_OR_REPARSE")


def attest_file(path: str | Path, expected_sha256: str) -> dict:
    p = Path(path)
    _regular_file(p)
    if len(expected_sha256) != 64 or not all(c in "0123456789abcdef" for c in expected_sha256.lower()):
        raise ValueError("INVALID_EXPECTED_SHA256")
    with p.open("rb") as f:
        actual = _sha256_stream(f)
    return {"path": str(p), "size_bytes": p.stat().st_size,
            "sha256": actual, "verified": actual == expected_sha256.lower(),
            "read_only": True}


def attest_seed(archive: str | Path) -> dict:
    p = Path(archive)
    _regular_file(p)
    if p.stat().st_size > MAX_ZIP_BYTES:
        raise ValueError("SEED_ARCHIVE_SIZE_HOLD")
    outer = attest_file(p, EXPECTED_ARCHIVE_SHA256)
    if not outer["verified"]:
        raise ValueError("SEED_ARCHIVE_SHA_MISMATCH")
    with zipfile.ZipFile(p) as z:
        names = z.namelist()
        if len(names) != len(set(names)) or len(names) > 128:
            raise ValueError("SEED_ARCHIVE_DUPLICATE_OR_TOO_MANY")
        for item in z.infolist():
            if (item.is_dir() or item.file_size > MAX_MEMBER_BYTES or
                item.filename.startswith(("/", "\\")) or
                "\\" in item.filename or
                any(part in ("", ".", "..") for part in item.filename.split("/"))):
                raise ValueError("SEED_ARCHIVE_MEMBER_HOLD")
        metadata = json.loads(z.read("SHA256_MANIFEST.json"))
        manifest = metadata["files_sha256"]
        if set(manifest) != set(names) - {"SHA256_MANIFEST.json"}:
            raise ValueError("SEED_MEMBER_COVERAGE_HOLD")
        for name, sha in manifest.items():
            with z.open(name) as f:
                actual = _sha256_stream(f)
            if actual != sha:
                raise ValueError("SEED_MEMBER_SHA_MISMATCH:" + name)
        if manifest["nox_soul_tiny_gru_full_weights_v1.safetensors"] != EXPECTED_GRU_SHA256 or manifest["nox_soul_optimizer_state_v1.safetensors"] != EXPECTED_OPTIMIZER_SHA256:
            raise ValueError("SEED_WEIGHTS_OR_OPTIMIZER_SHA_MISMATCH")
        gates = json.loads(z.read("RELEASE_CANDIDATE_GATES.json"))
        metrics = json.loads(z.read("weights_metrics.json"))
        if gates.get("release1_ready") is not False or metrics.get("approved_model_for_release") is not False:
            raise ValueError("SEED_RELEASE_STATUS_INCONSISTENT")
        if metrics.get("trainable_parameter_count") != 72422:
            raise ValueError("SEED_PARAMETER_COUNT_HOLD")
        return {"schema":"NOX-SELFBUILDER-SEED-ATTEST-v1", "status":"ORIGINAL_BYTES_VERIFIED_NOT_RELEASE_ACCEPTED",
                "archive_sha256":outer["sha256"],"archive_size_bytes":outer["size_bytes"],
                "member_count":len(names),"gru_sha256":EXPECTED_GRU_SHA256,
                "optimizer_sha256":EXPECTED_OPTIMIZER_SHA256,
                "parameters":72422,"open_dialogue_passed":False,"release_accepted":False,
                "execution_performed":False,"training_performed":False}
