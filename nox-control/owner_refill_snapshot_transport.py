"""Keep authenticated refill evidence encrypted when it leaves the Actions runner."""

import base64
import hashlib
import json
import os
from pathlib import Path
import re


BUNDLE_FILES = (
    "nox-control/continuous_executor_20261118/assets/continuous_transaction_helpers.py",
    "nox-control/systemic_relay_20261118/owner_systemic_relay_publish.py",
    "nox-control/complete_executor_20261118/evidence/all295_execution_disposition.json",
)
BUNDLE_TOKEN = "__NOX_BUNDLE_JSON__"
ARTIFACT_NAME = "nox-refill-snapshot.enc"
SCHEMA = "NOX_ENCRYPTED_REFILL_SNAPSHOT_V1"
MARKERS = (
    ("REFILL_OWNER_SNAPSHOT", "owner_snapshot", 64 * 1024),
    ("REFILL_SNAPSHOT_CHECKPOINT", "publisher_checkpoint", 64 * 1024),
    ("REFILL_REQUIRED_REQUEST", "refill_request", 1024 * 1024),
    ("REFILL_SOURCE_CENSUS", "source_census", 64 * 1024),
    ("REFILL_NATIVE_READBACK", "native_readback", 64 * 1024),
)
COMPLETE = "NOX_MAINT_REFILL_SNAPSHOT_COMPLETE=true"
HOLD_PREFIX = "NOX_MAINT_REFILL_SNAPSHOT_HOLD="
PUBLIC_HOLDS = frozenset({
    "HOLD_REFILL_SNAPSHOT_ACTIVE_CLAIMS",
    "HOLD_REFILL_SNAPSHOT_MAINTENANCE_BUSY",
    "HOLD_REFILL_SNAPSHOT_RAW_CGROUP_HEADROOM",
    "HOLD_REFILL_SNAPSHOT_REFILL_RUNTIME_CONTRACT_INCOMPATIBLE",
    "HOLD_REFILL_SNAPSHOT_STOP_OR_MAINTENANCE",
})


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _bounded_read(path, limit):
    with path.open("rb") as source:
        data = source.read(limit + 1)
    if not data or len(data) > limit:
        raise RuntimeError("HOLD_REFILL_SNAPSHOT_SOURCE_LIMIT")
    return data


def build_payload(entry):
    source = _bounded_read(entry, 256 * 1024).decode("utf-8")
    if source.count(BUNDLE_TOKEN) != 1:
        raise RuntimeError("HOLD_REFILL_SNAPSHOT_BUNDLE_SLOT")
    bundle = {}
    for name in BUNDLE_FILES:
        path = Path(name)
        raw = _bounded_read(path, 2 * 1024 * 1024)
        bundle[path.name] = {
            "content": base64.b64encode(raw).decode("ascii"),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
    packed = _canonical(bundle).decode("ascii")
    return source.replace(BUNDLE_TOKEN, packed)


def load_recipient_key(encoded):
    """Only the exact owner command supplies a public RSA recipient key."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey

    if not isinstance(encoded, str) or not re.fullmatch(r"[A-Za-z0-9_-]{500,900}", encoded):
        raise RuntimeError("HOLD_REFILL_SNAPSHOT_RECIPIENT")
    try:
        raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        key = serialization.load_der_public_key(raw)
    except (ValueError, TypeError):
        raise RuntimeError("HOLD_REFILL_SNAPSHOT_RECIPIENT") from None
    if not isinstance(key, RSAPublicKey) or key.key_size != 4096 or key.public_numbers().e != 65537:
        raise RuntimeError("HOLD_REFILL_SNAPSHOT_RECIPIENT")
    expected = key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    if raw != expected or base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=") != encoded:
        raise RuntimeError("HOLD_REFILL_SNAPSHOT_RECIPIENT")
    return key, hashlib.sha256(expected).hexdigest()


def _unique_object(pairs):
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("duplicate key")
    return result


def _parse_value(raw, limit):
    if len(raw.encode()) > limit:
        raise RuntimeError("HOLD_REFILL_SNAPSHOT_OUTPUT_LIMIT")
    try:
        value = json.loads(raw, object_pairs_hook=_unique_object)
        _canonical(value)
    except (ValueError, RecursionError):
        raise RuntimeError("HOLD_REFILL_SNAPSHOT_RECORD") from None
    if not isinstance(value, dict) or not value:
        raise RuntimeError("HOLD_REFILL_SNAPSHOT_RECORD")
    return value


def collect_snapshot(stdout, returncode):
    """Take the exact record sequence without forwarding any server payload."""
    if len(stdout) > 2 * 1024 * 1024:
        raise RuntimeError("HOLD_REFILL_SNAPSHOT_OUTPUT_LIMIT")
    lines = stdout.splitlines()
    if returncode:
        if len(lines) == 1 and lines[0].startswith(HOLD_PREFIX):
            hold = _parse_value(lines[0][len(HOLD_PREFIX):], 1024)
            reason = hold.get("reason")
            if set(hold) == {"reason"} and isinstance(reason, str) and reason in PUBLIC_HOLDS:
                raise RuntimeError(reason)
            raise RuntimeError("HOLD_REFILL_SNAPSHOT_SERVER_GATE")
        raise RuntimeError("HOLD_REFILL_SNAPSHOT_SERVER_FAILED")
    if len(lines) != len(MARKERS) + 1 or lines[-1] != COMPLETE:
        raise RuntimeError("HOLD_REFILL_SNAPSHOT_OUTPUT_SHAPE")
    result = {}
    for line, (marker, record, limit) in zip(lines, MARKERS):
        prefix = f"NOX_MAINT_{marker}="
        if not line.startswith(prefix):
            raise RuntimeError("HOLD_REFILL_SNAPSHOT_OUTPUT_SHAPE")
        result[record] = _parse_value(line[len(prefix):], limit)
    return result


def save_encrypted_snapshot(stdout, returncode, encoded_recipient, request_id, source_sha):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if type(request_id) is not int or request_id <= 0 or not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise RuntimeError("HOLD_REFILL_SNAPSHOT_COMMAND_BINDING")
    recipient, recipient_sha = load_recipient_key(encoded_recipient)
    records = collect_snapshot(stdout, returncode)
    readback = records["native_readback"]
    if (readback.get("schema") != "NOX_SYSTEMIC_REFILL_NATIVE_READBACK_V1"
            or readback.get("instance_id") != 60509551
            or readback.get("owner_request_id") != str(request_id)
            or readback.get("owner_source_sha") != source_sha
            or readback.get("native_write_performed") is not False
            or readback.get("publication_authorized") is not False):
        raise RuntimeError("HOLD_REFILL_SNAPSHOT_COMMAND_BINDING")
    aad = {
        "schema": SCHEMA,
        "request_id": request_id,
        "source_sha": source_sha,
        "recipient_sha256": recipient_sha,
    }
    key = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(12)
    cipher = AESGCM(key).encrypt(nonce, _canonical(records), _canonical(aad))
    wrapped = recipient.encrypt(
        key, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=SCHEMA.encode())
    )
    binary_fields = {
        name: base64.b64encode(value).decode("ascii")
        for name, value in (("ciphertext_b64", cipher), ("nonce_b64", nonce), ("wrapped_key_b64", wrapped))
    }
    envelope = {**aad, **binary_fields}
    encoded = _canonical(envelope)
    runner_temp = os.environ.get("RUNNER_TEMP")
    if not runner_temp or not Path(runner_temp).is_absolute():
        raise RuntimeError("HOLD_REFILL_SNAPSHOT_ARTIFACT_PATH")
    path = Path(runner_temp) / ARTIFACT_NAME
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as artifact:
        artifact.write(encoded)
    return {
        **aad,
        "bytes": len(encoded),
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "record_count": len(records),
    }
