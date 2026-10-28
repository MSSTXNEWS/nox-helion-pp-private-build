"""Owner 3 / NOX V16 C40: fail-closed admission for the ONE existing model downloader.

Pure policy: no network, process, filesystem writes, weights, queue or server here.
Trusted E06 native host must provide attest() and measured hardware; only after a
PASS may it call existing P03 ModelDownloadQueueStore/Worker/OllamaModelAdapter.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Any
import re
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


def _https_url(s: Any) -> bool:
    if not isinstance(s, str):
        return False
    try:
        u = urlsplit(s)
        return (u.scheme == "https" and bool(u.hostname) and not u.username
                and not u.password and u.port in (None, 443) and not u.fragment)
    except ValueError:
        return False


def _positive(value: Any) -> bool:
    return type(value) is int and 0 < value < (1 << 63)


def review_lead(tag_or_id: str) -> Decision:
    """25 Ollama tags + 17 multi-modal leads are all HOLD until attestations."""
    if tag_or_id in OLLAMA_TAG_LEADS:
        return Decision("HOLD", ("TAG_NOT_IMMUTABLE_PIN", "ARTIFACT_RIGHTS_SHA_UNVERIFIED"))
    if tag_or_id in dict(EXTERNAL_LEADS):
        return Decision("HOLD", ("EXTERNAL_WEIGHT_REVISION_RIGHTS_SHA_UNVERIFIED",))
    return Decision("HOLD", ("UNKNOWN_MODEL",))


def prerequisite_gates(facts: Mapping[str, Any], role: str) -> tuple[str, ...]:
    """Only host-measured and owner-attested facts count."""
    needed = ("ollama",) if role == "OLLAMA" else ("python", "git")
    if role in {"TRAINING", "GPU_TRAINING"}:
        needed = ("python", "git", "cuda", "peft")
    return tuple("PREREQUISITE_" + x.upper() + "_UNVERIFIED"
                 for x in needed if facts.get(x) is not True)


def admit_for_existing_downloader(
    evidence: Mapping[str, Any], context: Mapping[str, Any],
    trusted_attestor: Callable[[Mapping[str, Any]], bool] | None,
) -> Decision:
    """Return route admission only, never initiate download or model install.

    Attestor MUST be E06's original owner-verified native bridge. Without one
    supplied JSON fields are not considered license/hardware/source proof.
    """
    reasons: list[str] = []
    kind = evidence.get("kind")
    if kind not in {"ollama", "gguf", "external"}:
        return Decision("HOLD", ("UNSUPPORTED_KIND",))
    if context.get("sourceCommit") != BASE_COMMIT or context.get("sourceTree") != BASE_TREE:
        reasons.append("FROZEN_SOURCELOCK_MISMATCH")
    if context.get("owner3DonorHead") != DONOR_OWNER3_HEAD:
        reasons.append("OWNER3_DONOR_DRIFT")
    if context.get("sessionTrusted") is not True:
        reasons.append("UNTRUSTED_NATIVE_SESSION")
    if context.get("hostQueueAvailable") is not True:
        reasons.append("EXISTING_QUEUE_UNAVAILABLE")
    if context.get("explicitUserDownloadConsent") is not True:
        reasons.append("USER_DOWNLOAD_CONSENT_REQUIRED")
    if evidence.get("licenseAcknowledged") is not True:
        reasons.append("LICENSE_ACK_REQUIRED")
    if not _https_url(evidence.get("licenseEvidenceUrl")) or not evidence.get("licenseId"):
        reasons.append("LICENSE_EVIDENCE_MISSING")
    if not _sha(evidence.get("artifactSha256")) or not _sha(evidence.get("manifestSha256")):
        reasons.append("ARTIFACT_AND_MANIFEST_SHA_UNVERIFIED")
    if not _positive(evidence.get("artifactBytes")) or not _positive(evidence.get("requiredDiskBytes")):
        reasons.append("ARTIFACT_BYTES_UNVERIFIED")
    elif evidence["requiredDiskBytes"] < evidence["artifactBytes"]:
        reasons.append("INSUFFICIENT_REQUIRED_DISK_BUDGET")
    if not isinstance(evidence.get("immutableRevision"), str) or not REVISION.fullmatch(evidence["immutableRevision"]):
        reasons.append("IMMUTABLE_REVISION_UNVERIFIED")
    if not _sha(evidence.get("ownerRightsReceiptSha256")):
        reasons.append("OWNER_RIGHTS_RECEIPT_MISSING")
    if not callable(trusted_attestor):
        reasons.append("TRUSTED_OWNER_ATTESTOR_MISSING")
    else:
        try:
            if trusted_attestor(evidence) is not True:
                reasons.append("OWNER_ATTESTATION_REJECTED")
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
        if not isinstance(evidence.get("localGgufPath"), str) or not evidence["localGgufPath"].lower().endswith(".gguf"):
            reasons.append("LOCAL_GGUF_PATH_REQUIRED")
        role = "EXTERNAL"
    else:
        if evidence.get("leadId") not in dict(EXTERNAL_LEADS):
            reasons.append("UNKNOWN_EXTERNAL_WEIGHT_LEAD")
        # The owner3 queue supports Ollama and local GGUF only; no imaginary
        # external ASR/TTS/video transport or second downloader is permitted.
        reasons.append("EXTERNAL_WEIGHT_TRANSPORT_NOT_IN_EXISTING_QUEUE")
        role = dict(EXTERNAL_LEADS).get(evidence.get("leadId"), "EXTERNAL")
    prereqs = context.get("verifiedPrerequisites")
    reasons.extend(prerequisite_gates(prereqs if isinstance(prereqs, Mapping) else {}, role))
    if reasons:
        return Decision("HOLD", tuple(dict.fromkeys(reasons)))
    return Decision("PASS_FOR_EXISTING_QUEUE", (), evidence["existingRoute"])


def progress_gate(previous: Mapping[str, Any], update: Mapping[str, Any]) -> Decision:
    """Byte counters monotonic per attempt; STOP not server-confirmed cancellation."""
    if previous.get("attemptId") != update.get("attemptId"):
        return Decision("HOLD", ("RETRY_REQUIRES_NEW_QUEUE_JOB_RECEIPT",))
    old_done, new_done, total = previous.get("completedBytes"), update.get("completedBytes"), update.get("totalBytes")
    if not (type(old_done) is int and type(new_done) is int and _positive(total)):
        return Decision("HOLD", ("BYTE_COUNTERS_UNVERIFIED",))
    if not (0 <= old_done <= new_done <= total):
        return Decision("HOLD", ("NON_MONOTONIC_OR_INVALID_PROGRESS",))
    status = update.get("state")
    if status in {"STOP", "CANCEL_REQUESTED", "CANCELLING"}:
        return Decision("HOLD", ("STOP_REQUESTED_NOT_SERVER_CONFIRMED",))
    if status == "COMPLETED" and not (_sha(update.get("completedReceiptSha256")) and new_done == total):
        return Decision("HOLD", ("COMPLETION_RECEIPT_OR_BYTES_MISSING",))
    if status not in {"QUEUED", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"}:
        return Decision("HOLD", ("UNKNOWN_QUEUE_STATE",))
    return Decision("PASS_FOR_EXISTING_QUEUE", ())
