"""Owner 3 / NOX V16 C40: fail-closed admission for the ONE existing model downloader.

Pure policy: no network, process, filesystem writes, weights, queue or server here.
Trusted E06 native host must provide attest() and measured hardware; only after a
PASS may it call existing P03 ModelDownloadQueueStore/Worker/OllamaModelAdapter.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Any
import re
import json
import ipaddress
import ntpath
import unicodedata
from urllib.parse import urlsplit

BASE_COMMIT = "0b3a7d435be735148d64171deb9027093a89646e"
BASE_TREE = "f108d604c444f718b32aaecfd07b90b8f91b9a6f"
DONOR_OWNER3_HEAD = "8657491117f4221c053a0ea5111f68a61f5ad06a"

# Original owner-3 ModelTagReviewLeads.cs: 25 exact variants, NOT immutable pins.
OLLAMA_TAG_LEADS = (
    "qwen3:0.6b", "qwen3:1.7b", "qwen3:4b", "qwen3:8b", "qwen3:14b",
    "qwen3:30b", "qwen3:32b", "qwen2.5:0.5b", "qwen2.5:1.5b",
    "qwen2.5:3b", "qwen2.5:7b", "qwen2.5:14b", "qwen2.5:32b",
    "qwen2.5:72b", "gemma3:270m", "gemma3:1b", "gemma3:4b",
    "gemma3:12b", "gemma3:27b", "llama3.2:1b", "llama3.2:3b",
    "deepseek-r1:1.5b", "deepseek-r1:7b", "deepseek-r1:8b",
    "deepseek-r1:14b",
)
# Original ModelQuickActions.cs: project discovery, NOT artifact URLs.
EXTERNAL_LEADS = (
    ("asr-whisper-small", "ASR"), ("asr-whisper-large-v3", "ASR"),
    ("asr-faster-whisper", "ASR"), ("tts-piper-voices", "TTS"),
    ("tts-xtts-v2", "TTS"), ("tts-mms-rus", "TTS"),
    ("tts-mms-spa", "TTS"), ("tts-kokoro", "TTS"),
    ("image-sdxl", "IMAGE"), ("image-flux-schnell", "IMAGE"),
    ("image-qwen", "IMAGE"), ("video-wan", "VIDEO"),
    ("video-ltx", "VIDEO"), ("video-cogvideo", "VIDEO"),
    ("video-hunyuan", "VIDEO"), ("train-qwen3-0.6b", "TRAINING"),
    ("aligner-wav2vec", "ALIGNER"),
)
SHA = re.compile(r"^[a-f0-9]{64}$")
REVISION = re.compile(r"^[a-f0-9]{40}$")


@dataclass(frozen=True)
class Decision:
    status: str  # PASS_FOR_EXISTING_QUEUE or HOLD, NEVER 'installed'
    reasons: tuple[str, ...]
    existing_route: str | None = None

    @property
    def allowed(self) -> bool:
        return self.status == "PASS_FOR_EXISTING_QUEUE"


def _sha(s: Any) -> bool:
    return isinstance(s, str) and SHA.fullmatch(s) is not None and s != "0" * 64


def _immutable_revision(s: Any, kind: str) -> bool:
    """Recognize existing owner formats without treating digest as Git commit.

    Historical evidence uses a 40-hex source revision. Original Ollama
    ModelArtifactReviewRegistry.TryPromote also emits a 64-hex digest reference,
    optionally sha256-prefixed. Only that route has this native contract; never
    infer it for GGUF/external source revisions or turn syntax into rights proof.
    The original string still reaches the trusted attestor unchanged.
    """
    if not isinstance(s, str):
        return False
    if REVISION.fullmatch(s):
        return True
    if kind != "ollama":
        return False
    digest = s[7:] if s[:7].lower() == "sha256:" else s
    return re.fullmatch(r"[a-fA-F0-9]{64}", digest) is not None and digest != "0" * 64


def _https_url(s: Any) -> bool:
    """Lexical E06 evidence URL gate; NEVER fetch/DNS-resolve in this policy.

    urlsplit discards certain ASCII controls and allows empty userinfo or invalid
    DNS label shapes. Reject BEFORE parsing so a misleading UI/license receipt
    cannot be normalized into a different URL for the existing native queue.
    The E06 host must still pin/verify any DNS, redirect and license evidence.
    """
    if not isinstance(s, str) or not (0 < len(s) <= 2048):
        return False
    if (s != s.strip() or any(ch.isspace() or unicodedata.category(ch) in
                                  {"Cc", "Cf", "Cs"} for ch in s)
            or re.search(r"%(?:0[0-9a-f]|1[0-9a-f]|7f)", s, re.I)):
        return False
    try:
        u = urlsplit(s)
        hostname = u.hostname
        if not (u.scheme == "https" and hostname and u.username is None
                and u.password is None and u.port in (None, 443) and not u.fragment):
            return False
        # Do not forward local/network-internal or malformed hostnames into the
        # native license review. This is only structural, NOT DNS/rights proof.
        if hostname == "localhost" or hostname.endswith((".localhost", ".local", ".internal", ".")):
            return False
        try:
            return ipaddress.ip_address(hostname).is_global
        except ValueError:
            labels = hostname.split(".")
            return len(labels) >= 2 and all(
                re.fullmatch(r"(?:[A-Za-z0-9]|[A-Za-z0-9][A-Za-z0-9-]{0,61}[A-Za-z0-9])", label)
                for label in labels
            )
    except ValueError:
        return False


def _positive(value: Any) -> bool:
    return type(value) is int and 0 < value < (1 << 63)


def _evidence_snapshot(*values: Mapping[str, Any]) -> str:
    """Bound callback evidence including nested MappingProxyType records.

    Native attestations must describe exactly the objects evaluated by policy;
    mutating valid identifiers after an earlier check cannot inherit its PASS.
    No user-defined scalar coercion, non-finite JSON or unbounded graphs.
    """
    nodes = 0

    def plain(value, depth=0):
        nonlocal nodes
        nodes += 1
        if depth > 32 or nodes > 4096:
            raise ValueError("Evidence structure limit")
        if isinstance(value, Mapping):
            if len(value) > 4096 or any(type(k) is not str or len(k) > 65536 for k in value):
                raise ValueError("Evidence object keys")
            return {k: plain(v, depth + 1) for k, v in value.items()}
        if type(value) is list:
            if len(value) > 4096:
                raise ValueError("Evidence array limit")
            return [plain(v, depth + 1) for v in value]
        if type(value) is str:
            if len(value) > 65536:
                raise ValueError("Evidence text limit")
            return value
        if value is None or type(value) in (bool, int, float):
            return value
        raise ValueError("Evidence JSON value required")

    encoded = json.dumps([plain(v) for v in values], sort_keys=True,
                         separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    if len(encoded.encode("utf-8")) > 262144:
        raise ValueError("Evidence byte limit")
    return encoded


def _nonblank_license_id(value: Any) -> bool:
    return (isinstance(value, str) and 0 < len(value) <= 160
            and value == value.strip()
            and all((ch == " " or not ch.isspace())
                    and unicodedata.category(ch) not in {"Cc", "Cf", "Cs"}
                    for ch in value))


# This is lexical screening only; the ORIGINAL P03 native GGUF queue must still
# resolve real paths, ACLs, reparse points, file identity and SHA-256 itself.
_WIN_DEVICE_STEM = re.compile(r"^(?:CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])$", re.I)
_WIN_INVALID_CHARS = frozenset('<>:"|?*')


def _windows_local_gguf_path(value: Any) -> bool:
    if not isinstance(value, str) or not value.lower().endswith(".gguf"):
        return False
    drive, tail = ntpath.splitdrive(value)
    if not re.fullmatch(r"[A-Za-z]:", drive) or not tail.startswith(("/", "\\")):
        return False  # no UNC, device, drive-relative or POSIX/root-relative paths
    parts = re.split(r"[\\/]", tail[1:])
    return bool(parts) and all(
        part not in {"", ".", ".."}
        and not part.endswith((" ", "."))
        and not _WIN_DEVICE_STEM.fullmatch(part.split(".", 1)[0])
        and all(ch not in _WIN_INVALID_CHARS
                and unicodedata.category(ch) not in {"Cc", "Cf", "Cs"} for ch in part)
        for part in parts
    )


def review_lead(tag_or_id: str) -> Decision:
    """25 Ollama tags + 17 multi-modal leads are all HOLD until attestations."""
    if not isinstance(tag_or_id, str):
        return Decision("HOLD", ("UNKNOWN_MODEL",))
    if tag_or_id in OLLAMA_TAG_LEADS:
        return Decision("HOLD", ("TAG_NOT_IMMUTABLE_PIN", "ARTIFACT_RIGHTS_SHA_UNVERIFIED"))
    if tag_or_id in dict(EXTERNAL_LEADS):
        return Decision("HOLD", ("EXTERNAL_WEIGHT_REVISION_RIGHTS_SHA_UNVERIFIED",))
    return Decision("HOLD", ("UNKNOWN_MODEL",))


def prerequisite_gates(facts: Mapping[str, Any], role: str) -> tuple[str, ...]:
    """Only host-measured and owner-attested facts count."""
    if not isinstance(role, str):
        return ("PREREQUISITE_ROLE_UNVERIFIED",)
    if not isinstance(facts, Mapping):
        facts = {}
    needed = ("ollama",) if role == "OLLAMA" else ("python", "git")
    if role == "GGUF":
        # Original ImportGgufAsync uploads api/blobs and invokes api/create on
        # the SAME local Ollama service. Python/Git alone cannot fulfill it.
        needed = ("python", "git", "ollama")
    if role in {"TRAINING", "GPU_TRAINING"}:
        needed = ("python", "git", "cuda", "torch", "peft", "trl", "accelerate")
    return tuple("PREREQUISITE_" + x.upper() + "_UNVERIFIED"
                 for x in needed if facts.get(x) is not True)


def admit_for_existing_downloader(
    evidence: Mapping[str, Any], context: Mapping[str, Any],
    trusted_attestor: Callable[[Mapping[str, Any], Mapping[str, Any]], bool] | None,
) -> Decision:
    """Return route admission only, never initiate download or model install.

    Attestor MUST be E06's original owner-verified native bridge, and MUST
    independently bind both candidate artifact evidence AND measured context to
    the SAME native session and immutable SourceLock. No one-argument attestor
    compatibility fallback: it would silently skip context/source verification.
    Supplied JSON by itself is NEVER license/hardware/source proof.
    """
    if not isinstance(evidence, Mapping):
        return Decision("HOLD", ("INVALID_EVIDENCE_SHAPE",))
    if not isinstance(context, Mapping):
        return Decision("HOLD", ("INVALID_NATIVE_CONTEXT_SHAPE",))
    reasons: list[str] = []
    kind = evidence.get("kind")
    if not isinstance(kind, str) or kind not in {"ollama", "gguf", "external"}:
        return Decision("HOLD", ("UNSUPPORTED_KIND",))
    if context.get("sourceCommit") != BASE_COMMIT or context.get("sourceTree") != BASE_TREE:
        reasons.append("FROZEN_SOURCELOCK_MISMATCH")
    if context.get("owner3DonorHead") != DONOR_OWNER3_HEAD:
        reasons.append("OWNER3_DONOR_DRIFT")
    lock = context.get("nativeSourceLock")
    if (not isinstance(lock, Mapping)
            or lock.get("attested") is not True
            or type(lock.get("verifiedRawPartCount")) is not int
            or lock.get("verifiedRawPartCount") != 3
            or type(lock.get("verifiedExtractedMemberCount")) is not int
            or lock.get("verifiedExtractedMemberCount") != 729
            or not _sha(lock.get("ownerReceiptSha256"))
            or not _sha(lock.get("hostSourceReceiptSha256"))):
        reasons.append("CANONICAL_ORIGINAL_SOURCELOCK_UNVERIFIED")
    if context.get("sessionTrusted") is not True:
        reasons.append("UNTRUSTED_NATIVE_SESSION")
    if context.get("hostQueueAvailable") is not True:
        reasons.append("EXISTING_QUEUE_UNAVAILABLE")
    if context.get("explicitUserDownloadConsent") is not True:
        reasons.append("USER_DOWNLOAD_CONSENT_REQUIRED")
    if evidence.get("licenseAcknowledged") is not True:
        reasons.append("LICENSE_ACK_REQUIRED")
    if not _https_url(evidence.get("licenseEvidenceUrl")) or not _nonblank_license_id(evidence.get("licenseId")):
        reasons.append("LICENSE_EVIDENCE_MISSING")
    if not _sha(evidence.get("artifactSha256")) or not _sha(evidence.get("manifestSha256")):
        reasons.append("ARTIFACT_AND_MANIFEST_SHA_UNVERIFIED")
    if not _positive(evidence.get("artifactBytes")) or not _positive(evidence.get("requiredDiskBytes")):
        reasons.append("ARTIFACT_BYTES_UNVERIFIED")
    elif evidence["requiredDiskBytes"] < evidence["artifactBytes"]:
        reasons.append("INSUFFICIENT_REQUIRED_DISK_BUDGET")
    if not _immutable_revision(evidence.get("immutableRevision"), kind):
        reasons.append("IMMUTABLE_REVISION_UNVERIFIED")
    if not _sha(evidence.get("ownerRightsReceiptSha256")):
        reasons.append("OWNER_RIGHTS_RECEIPT_MISSING")
    if type(evidence.get("requiresGPU")) is not bool:
        reasons.append("GPU_REQUIREMENT_FLAG_UNVERIFIED")
    if not callable(trusted_attestor):
        reasons.append("TRUSTED_OWNER_ATTESTOR_MISSING")
    else:
        try:
            snapshot = _evidence_snapshot(evidence, context)
            if trusted_attestor(evidence, context) is not True:
                reasons.append("OWNER_ATTESTATION_REJECTED")
            if _evidence_snapshot(evidence, context) != snapshot:
                reasons.append("OWNER_ATTESTATION_EVIDENCE_CHANGED")
        except Exception:
            reasons.append("OWNER_ATTESTATION_ERROR")

    # Never trust editable UI VRAM or disk. Require a measured, attested native
    # probe bound to this exact E06 host/session.
    native = context.get("nativeMeasuredHardware")
    if not isinstance(native, Mapping) or native.get("attested") is not True:
        reasons.append("NATIVE_HARDWARE_NOT_ATTESTED")
    else:
        if not _positive(native.get("freeDiskBytes")):
            reasons.append("REAL_DISK_SENSOR_MISSING")
        elif _positive(evidence.get("requiredDiskBytes")) and native["freeDiskBytes"] < evidence["requiredDiskBytes"]:
            reasons.append("INSUFFICIENT_REAL_DISK")
        if evidence.get("requiresGPU") is True:
            if not _positive(evidence.get("requiredVramBytes")):
                reasons.append("GPU_REQUIREMENTS_UNVERIFIED")
            elif not _positive(native.get("vramBytes")):
                reasons.append("NATIVE_VRAM_SENSOR_MISSING")
            elif native["vramBytes"] < evidence["requiredVramBytes"]:
                reasons.append("INSUFFICIENT_REAL_VRAM")

    if kind == "ollama":
        if evidence.get("modelTag") not in OLLAMA_TAG_LEADS:
            reasons.append("NOT_IN_OWNER3_EXACT_TAG_LEADS")
        if evidence.get("existingRoute") != "EnqueueVerifiedPullAsync":
            reasons.append("WRONG_OR_NEW_DOWNLOADER_ROUTE")
        role = "OLLAMA"
    elif kind == "gguf":
        if evidence.get("existingRoute") != "EnqueueVerifiedGgufAsync":
            reasons.append("WRONG_OR_NEW_DOWNLOADER_ROUTE")
        local = evidence.get("localGgufPath")
        # Windows-host absolute, local-disk path only. The native queue alone
        # resolves it and checks ACL/reparse points + GGUF bytes; this is syntax
        # screening, NOT a second filesystem importer or proof of file safety.
        if not _windows_local_gguf_path(local):
            reasons.append("LOCAL_GGUF_PATH_REQUIRED")
        if evidence.get("nativeGgufMagicVerified") is not True:
            reasons.append("GGUF_NATIVE_MAGIC_UNVERIFIED")
        if not (_sha(evidence.get("nativeLocalFileSha256")) and evidence.get("nativeLocalFileSha256") == evidence.get("artifactSha256")):
            reasons.append("GGUF_LOCAL_FILE_SHA_NOT_MATCHED")
        role = "GGUF"
    else:
        if not isinstance(evidence.get("leadId"), str) or evidence.get("leadId") not in dict(EXTERNAL_LEADS):
            reasons.append("UNKNOWN_EXTERNAL_WEIGHT_LEAD")
        # The owner3 queue supports Ollama and local GGUF only; no imaginary
        # external ASR/TTS/video transport or second downloader is permitted.
        reasons.append("EXTERNAL_WEIGHT_TRANSPORT_NOT_IN_EXISTING_QUEUE")
        role = dict(EXTERNAL_LEADS).get(evidence.get("leadId"), "EXTERNAL") if isinstance(evidence.get("leadId"), str) else "EXTERNAL"
    prereqs = context.get("verifiedPrerequisites")
    reasons.extend(prerequisite_gates(prereqs if isinstance(prereqs, Mapping) else {}, role))
    if reasons:
        return Decision("HOLD", tuple(dict.fromkeys(reasons)))
    return Decision("PASS_FOR_EXISTING_QUEUE", (), evidence["existingRoute"])


# An admission PASS does NOT mark a model installed. This separate guard
# validates native queue receipts before rendering progress or terminal states.
# The values below MUST originate from the single native queue, not from the UI.
_QUEUE_STATES = frozenset({"QUEUED", "RUNNING", "CANCEL_REQUESTED", "CANCELLING",
                           "CANCELLED", "FAILED", "COMPLETED"})
_QUEUE_TRANSITIONS = {
    "QUEUED": frozenset({"QUEUED", "RUNNING", "CANCEL_REQUESTED", "CANCELLING", "CANCELLED", "FAILED"}),
    "RUNNING": frozenset({"RUNNING", "CANCEL_REQUESTED", "CANCELLING", "FAILED", "COMPLETED"}),
    "CANCEL_REQUESTED": frozenset({"CANCEL_REQUESTED", "CANCELLING", "CANCELLED", "FAILED"}),
    "CANCELLING": frozenset({"CANCELLING", "CANCELLED", "FAILED"}),
    "CANCELLED": frozenset(),
    "FAILED": frozenset(),
    "COMPLETED": frozenset(),
}


def _nonempty_id(s: Any) -> bool:
    return (isinstance(s, str) and bool(s.strip()) and s == s.strip()
            and len(s) <= 200 and all(32 <= ord(c) < 127 for c in s))


def _queue_identity_errors(previous: Mapping[str, Any], update: Mapping[str, Any]) -> list[str]:
    reasons = []
    if not (_nonempty_id(previous.get("attemptId")) and _nonempty_id(update.get("attemptId"))
            and previous.get("attemptId") == update.get("attemptId")):
        reasons.append("RETRY_REQUIRES_NEW_QUEUE_JOB_RECEIPT")
    if not (_nonempty_id(previous.get("queueJobId")) and _nonempty_id(update.get("queueJobId"))
            and previous.get("queueJobId") == update.get("queueJobId")):
        reasons.append("QUEUE_JOB_ID_DRIFT_OR_MISSING")
    for key in ("queueJobReceiptSha256", "manifestSha256", "expectedArtifactSha256"):
        if not (_sha(previous.get(key)) and previous.get(key) == update.get(key)):
            reasons.append("QUEUE_JOB_PROVENANCE_DRIFT_OR_MISSING")
            break
    for key in ("nativeHostId", "queueOwnerSessionId"):
        if not (_nonempty_id(previous.get(key)) and previous.get(key) == update.get(key)):
            reasons.append("QUEUE_NATIVE_HOST_OR_SESSION_DRIFT")
            break
    seq_before, seq_after = previous.get("eventSequence"), update.get("eventSequence")
    if not (_positive(seq_before) and _positive(seq_after) and seq_after > seq_before):
        reasons.append("NON_MONOTONIC_NATIVE_EVENT_SEQUENCE")
    return reasons


def _trusted_queue_receipt_errors(
    previous: Mapping[str, Any], update: Mapping[str, Any],
    trusted_queue_verifier: Callable[[Mapping[str, Any], Mapping[str, Any]], bool] | None,
) -> tuple[str, ...]:
    """Invoke E06 native queue verifier, never trust UI-provided attested flags.

    The callback must resolve BOTH snapshots from the same installed P03 queue,
    check their signed/content-addressed receipts, job/session ownership,
    verified bytes and immutable artifact identity. A caller-provided lambda is
    only a TEST fixture, not proof of integration. No network or disk I/O here.
    """
    if not callable(trusted_queue_verifier):
        return ("NATIVE_QUEUE_VERIFIER_MISSING",)
    try:
        snapshot = _evidence_snapshot(previous, update)
        if trusted_queue_verifier(previous, update) is not True:
            return ("NATIVE_QUEUE_RECEIPT_REJECTED",)
        if _evidence_snapshot(previous, update) != snapshot:
            return ("NATIVE_QUEUE_RECEIPT_CHANGED",)
    except Exception:
        return ("NATIVE_QUEUE_VERIFIER_ERROR",)
    return ()


def progress_gate(previous: Mapping[str, Any], update: Mapping[str, Any],
                  trusted_queue_verifier: Callable[[Mapping[str, Any], Mapping[str, Any]], bool] | None = None) -> Decision:
    """Fail-closed progress admission for SAME native attempt, queue job & artifact.

    Exactly one existing queue owns both snapshots and all *ReceiptSha256 fields.
    A number resembling a valid SHA is NOT cryptographic proof: E06's native host
    must verify receipt content/signature and measured downloaded bytes itself.
    This policy never calls a network, downloader, filesystem, or UI callback.
    """
    if not isinstance(previous, Mapping) or not isinstance(update, Mapping):
        return Decision("HOLD", ("INVALID_QUEUE_EVENT_SHAPE",))
    reasons = _queue_identity_errors(previous, update)
    reasons.extend(_trusted_queue_receipt_errors(previous, update, trusted_queue_verifier))
    before, after = previous.get("state"), update.get("state")
    if not isinstance(before, str) or before not in _QUEUE_STATES:
        reasons.append("UNKNOWN_PREVIOUS_QUEUE_STATE")
        # Preserve all other diagnostics while preventing an IPC array/object
        # from reaching hash-table membership below and raising TypeError.
        before = None
    if isinstance(after, str) and after in {"STOP", "CANCEL", "PAUSE", "RETRY"}:
        reasons.append("REQUEST_NOT_SERVER_CONFIRMED")
        if after == "STOP":
            reasons.append("STOP_REQUESTED_NOT_SERVER_CONFIRMED")
    elif not isinstance(after, str) or after not in _QUEUE_STATES:
        reasons.append("UNKNOWN_QUEUE_STATE")
    elif before in _QUEUE_TRANSITIONS and after not in _QUEUE_TRANSITIONS[before]:
        reasons.append("INVALID_OR_TERMINAL_QUEUE_TRANSITION")

    old_total, new_total = previous.get("totalBytes"), update.get("totalBytes")
    old_done, new_done = previous.get("completedBytes"), update.get("completedBytes")
    # Original PullAsync sums discovered digest layers, so aggregate total grows
    # during one native job. It is NOT the immutable artifact size. The trusted
    # verifier above must bind both counters to that original job/manifest.
    # A measured numerator may also precede its denominator; this is real bytes,
    # never a percentage or permission to mark the artifact installed.
    def valid_counters(done, total):
        if done is None:
            return total is None
        return (type(done) is int and 0 <= done < (1 << 63)
                and (total is None or (_positive(total) and done <= total)))

    new_known = (_positive(new_total) and type(new_done) is int
                 and 0 <= new_done <= new_total)
    if not (valid_counters(old_done, old_total) and valid_counters(new_done, new_total)):
        if not _positive(old_total) or not _positive(new_total):
            reasons.append("TOTAL_BYTES_UNVERIFIED_OR_CHANGED")
        reasons.append("NON_MONOTONIC_OR_INVALID_PROGRESS")
    else:
        if old_done is not None and (new_done is None or new_done < old_done):
            reasons.append("NON_MONOTONIC_OR_INVALID_PROGRESS")
        if old_total is not None and (new_total is None or new_total < old_total):
            reasons.extend(("TOTAL_BYTES_UNVERIFIED_OR_CHANGED", "NON_MONOTONIC_OR_INVALID_PROGRESS"))
        if old_done is None and new_done is not None and before not in ("QUEUED", "RUNNING"):
            reasons.append("NON_MONOTONIC_OR_INVALID_PROGRESS")
        if new_total is not None and new_total != old_total:
            if before not in ("QUEUED", "RUNNING") or after not in ("RUNNING", "COMPLETED"):
                reasons.append("TOTAL_BYTES_UNVERIFIED_OR_CHANGED")
    if isinstance(after, str) and after in {"CANCEL_REQUESTED", "CANCELLING"}:
        reasons.append("STOP_REQUESTED_NOT_SERVER_CONFIRMED")
    elif after == "CANCELLED" and not (_sha(update.get("cancelAckReceiptSha256"))
                                            and update.get("nativeCancelAttested") is True):
        reasons.append("CANCELLATION_ACK_NOT_ATTESTED")
    elif after == "FAILED" and not (_sha(update.get("failureReceiptSha256"))
                                         and update.get("nativeFailureAttested") is True):
        reasons.append("FAILURE_RECEIPT_NOT_ATTESTED")
    elif after == "COMPLETED":
        if not (new_known and _sha(update.get("completedReceiptSha256"))
                and new_done == new_total and update.get("nativeCompletionAttested") is True):
            reasons.append("COMPLETION_RECEIPT_OR_BYTES_MISSING")
        if not (_sha(update.get("observedArtifactSha256"))
                and update.get("observedArtifactSha256") == update.get("expectedArtifactSha256")):
            reasons.append("DOWNLOADED_ARTIFACT_SHA_MISMATCH")
    if reasons:
        return Decision("HOLD", tuple(dict.fromkeys(reasons)))
    # This means the transition is source-policy-admissible, NOT model installed.
    return Decision("PASS_FOR_EXISTING_QUEUE", ())


def retry_gate(previous: Mapping[str, Any], new_job: Mapping[str, Any],
               *, user_retry_consent: bool, native_queue_attested: bool,
               trusted_queue_verifier: Callable[[Mapping[str, Any], Mapping[str, Any]], bool] | None = None) -> Decision:
    """Authorize QUEUED retry metadata only, never start/download/re-enqueue.

    The existing P03 queue must create the NEW job/attempt and verify receipts.
    A stopped task may retry only after confirmed terminal CANCELLED or FAILED.
    """
    if not isinstance(previous, Mapping) or not isinstance(new_job, Mapping):
        return Decision("HOLD", ("INVALID_QUEUE_EVENT_SHAPE",))
    reasons = list(_trusted_queue_receipt_errors(previous, new_job, trusted_queue_verifier))
    if not isinstance(previous.get("state"), str) or previous.get("state") not in {"FAILED", "CANCELLED"}:
        reasons.append("RETRY_REQUIRES_CONFIRMED_TERMINAL_STATE")
    elif previous.get("state") == "FAILED" and not (
            _sha(previous.get("failureReceiptSha256")) and previous.get("nativeFailureAttested") is True):
        reasons.append("RETRY_PREVIOUS_FAILURE_UNATTESTED")
    elif previous.get("state") == "CANCELLED" and not (
            _sha(previous.get("cancelAckReceiptSha256")) and previous.get("nativeCancelAttested") is True):
        reasons.append("RETRY_PREVIOUS_CANCEL_UNATTESTED")
    if new_job.get("state") != "QUEUED":
        reasons.append("RETRY_MUST_START_QUEUED")
    if not (_nonempty_id(previous.get("attemptId")) and _nonempty_id(new_job.get("attemptId"))
            and previous.get("attemptId") != new_job.get("attemptId")):
        reasons.append("RETRY_ATTEMPT_NOT_UNIQUE")
    if not (_nonempty_id(previous.get("queueJobId")) and _nonempty_id(new_job.get("queueJobId"))
            and previous.get("queueJobId") != new_job.get("queueJobId")):
        reasons.append("RETRY_QUEUE_JOB_NOT_UNIQUE")
    if not (_sha(new_job.get("queueJobReceiptSha256"))
            and new_job.get("queueJobReceiptSha256") != previous.get("queueJobReceiptSha256")):
        reasons.append("RETRY_NEW_QUEUE_RECEIPT_MISSING")
    for key in ("manifestSha256", "expectedArtifactSha256"):
        if not (_sha(previous.get(key)) and previous.get(key) == new_job.get(key)):
            reasons.append("RETRY_ARTIFACT_IDENTITY_DRIFT")
            break
    for key in ("nativeHostId", "queueOwnerSessionId"):
        if not (_nonempty_id(previous.get(key)) and previous.get(key) == new_job.get(key)):
            reasons.append("RETRY_NATIVE_SESSION_MISMATCH")
            break
    if (type(new_job.get("eventSequence")) is not int
            or new_job.get("eventSequence") != 1
            or not _positive(previous.get("eventSequence"))):
        reasons.append("RETRY_SEQUENCE_NOT_RESET")
    # Original P03 RetryAsync intentionally clears TotalBytes and
    # CompletedBytes to null. A queued retry has no verified bytes yet.
    # Support both this native null reset and an independently attested
    # old-total/zero reset, never carry old progress into the new attempt.
    native_unknown_reset = (new_job.get("totalBytes") is None and
                            new_job.get("completedBytes") is None)
    verified_zero_reset = (_positive(previous.get("totalBytes")) and
                           previous.get("totalBytes") == new_job.get("totalBytes") and
                           type(new_job.get("completedBytes")) is int and
                           new_job.get("completedBytes") == 0)
    if not (native_unknown_reset or verified_zero_reset):
        reasons.append("RETRY_BYTES_INVALID")
    if user_retry_consent is not True:
        reasons.append("RETRY_USER_CONSENT_REQUIRED")
    if native_queue_attested is not True:
        reasons.append("RETRY_NATIVE_ATTESTATION_REQUIRED")
    if reasons:
        return Decision("HOLD", tuple(dict.fromkeys(reasons)))
    return Decision("PASS_FOR_EXISTING_QUEUE", ())

