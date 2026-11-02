"""NOX HELION EXPRESS INTEGRATOR: first-launch acquisition using existing OneHost.

Small single-owner handoff: no separate server, installer, browser, database or
thread. This module makes an actionable, authenticated *plan* for the existing
P01 (signed Windows prerequisites) and P03 (reviewed model queue). It never
executes commands, downloads from the network or activates unreviewed code.

The original Windows installer must capture explicit consent for optional
external downloads; native owner enforces permissions, SHA and license review.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Mapping
import re
from .acquisition_library import AcquisitionHold, audit_library

ACTION_IDS = frozenset({11, 31, 32, 49})
MODEL_IDS = frozenset({31, 32})
TRUSTED_ACTIONS = {11: "P01_SIGNED_PREREQUISITE",
                   31: "P03_REVIEWED_MODEL_QUEUE",
                   32: "P03_REVIEWED_MODEL_QUEUE",
                   49: "P01_SIGNED_PREREQUISITE"}
MAX_FOUND_ITEMS = 512
MAX_ROOTS = 12
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_ID = re.compile(r"^[a-zA-Z0-9._:-]{1,128}$")


class FirstBootHold(RuntimeError):
    pass


@dataclass(frozen=True)
class FirstBootCallbacks:
    """Supplied by the existing authenticated native Windows owner only."""
    policy: Callable             # (session) -> signed native authority snapshot
    installed: Callable          # (session) -> native installed-state snapshot
    discover: Callable           # (session, approved_roots) -> data-only local candidates
    dispatch: Callable           # (session, route, verified_action) -> native receipt
    persist: Callable            # (session, document) -> bool after durable readback
    ingest: Callable             # (session, reviewed_digest) -> native S03 durable ACK
    stopped: Callable            # () -> bool
    stop_epoch: Callable         # () -> int, existing native STOP generation

    def verify(self):
        if not all(callable(x) for x in (self.policy, self.installed, self.discover,
                                         self.dispatch, self.persist, self.ingest, self.stopped, self.stop_epoch)):
            raise FirstBootHold("EXISTING_ONEHOST_NATIVE_PORTS_REQUIRED")


def _utc(now):
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise FirstBootHold("UTC_NOW_REQUIRED")
    return now.astimezone(timezone.utc)


def _policy(native: Mapping, now):
    """A remote web page or model output can never mint this trusted policy."""
    if not isinstance(native, Mapping) or native.get("schema") != "NOX-ONEHOST-FIRSTBOOT-POLICY-v1":
        raise FirstBootHold("NATIVE_FIRSTBOOT_POLICY_NOT_PRESENT")
    if native.get("windows_sid_attested") is not True or native.get("source_lock_verified") is not True:
        raise FirstBootHold("OWNER_WINDOWS_SOURCELOCK_REQUIRED")
    if native.get("signed_by_native_owner") is not True:
        raise FirstBootHold("NATIVE_POLICY_SIGNATURE_REQUIRED")
    if native.get("allow_firstboot_downloads") is not True or native.get("installer_consent_recorded") is not True:
        raise FirstBootHold("OWNER_DOWNLOAD_CONSENT_REQUIRED")
    raw = native.get("expiry_utc")
    if not isinstance(raw, str):
        raise FirstBootHold("POLICY_EXPIRY_REQUIRED")
    try:
        deadline = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as ex:
        raise FirstBootHold("POLICY_EXPIRY_INVALID") from ex
    if deadline.tzinfo is None or deadline.astimezone(timezone.utc) <= _utc(now):
        raise FirstBootHold("POLICY_EXPIRED")
    roots = native.get("approved_scan_roots")
    if (not isinstance(roots, list) or len(roots) > MAX_ROOTS or
        any(not isinstance(x, str) or not x or len(x) > 260 for x in roots) or
        len(set(roots)) != len(roots)):
        raise FirstBootHold("APPROVED_SCAN_ROOTS_REQUIRED")
    # Native owner itself checks realpath, Windows reparse ancestors and ACL.
    return tuple(roots)


def _native_installed(snapshot):
    if not isinstance(snapshot, Mapping) or snapshot.get("schema") != "NOX-P03-L01-INSTALLED-v1":
        raise FirstBootHold("NATIVE_INSTALLED_READBACK_REQUIRED")
    items = snapshot.get("items")
    if not isinstance(items, Mapping):
        raise FirstBootHold("NATIVE_INSTALLED_ITEMS_REQUIRED")
    for k, v in items.items():
        if str(k) not in {"11", "31", "32", "49"} or type(v) is not bool:
            raise FirstBootHold("NATIVE_INSTALLED_ITEM_INVALID")
    return items


def _asset_observations(rows):
    if not isinstance(rows, list) or len(rows) > MAX_FOUND_ITEMS:
        raise FirstBootHold("LOCAL_ASSET_SCAN_BOUNDED_REQUIRED")
    by_digest = {}
    for row in rows:
        # Native scanner reads user-approved directories only. Do not import
        # a raw executable, ZIP, or model weight without explicit admission.
        if not isinstance(row, Mapping):
            raise FirstBootHold("LOCAL_SCAN_UNTRUSTED_ROW")
        digest = row.get("sha256")
        typ = row.get("kind")
        size = row.get("size_bytes")
        if (not isinstance(digest, str) or not _HEX64.fullmatch(digest) or
            typ not in ("MODEL_WEIGHTS", "PYTHON_WHEEL", "DOTNET_NUGET", "ARCHIVE_DONOR",
                        "SOURCE_CANDIDATE", "DESIGN_CANDIDATE", "INSTALLER_CANDIDATE") or
            type(size) is not int or not 0 < size <= 200_000_000_000):
            raise FirstBootHold("LOCAL_SCAN_HASH_TYPE_SIZE_REQUIRED")
        previous = by_digest.get(digest)
        if previous is not None:
            # A native scan may encounter the same bytes through multiple approved
            # roots. Conflicting metadata must not silently change S03 admission.
            if previous["kind"] != typ or previous["size_bytes"] != size:
                raise FirstBootHold("LOCAL_SCAN_CONFLICTING_DIGEST_METADATA")
            continue
        by_digest[digest] = {"sha256": digest, "kind": typ, "size_bytes": size,
                             "status": "DISCOVERED_UNTRUSTED_NOT_IMPORTED"}
    # A digest identifies candidates only; it does not authorize loading.
    return sorted(by_digest.values(), key=lambda x: x["sha256"])


def _reviewed(native, item_id: int):
    """Only native immutable artifacts authorize use of P03/L01 transports."""
    entries = native.get("reviewed_artifacts")
    if not isinstance(entries, Mapping):
        return None
    art = entries.get(str(item_id))
    if not isinstance(art, Mapping):
        return None
    digest, version, rights = (art.get("sha256"), art.get("version"), art.get("rights_receipt_id"))
    if (not isinstance(digest, str) or not _HEX64.fullmatch(digest) or
        not isinstance(version, str) or not _ID.fullmatch(version) or
        not isinstance(rights, str) or not _ID.fullmatch(rights) or
        art.get("license_review_passed") is not True or
        art.get("hardware_compatible") is not True):
        return None
    tag = art.get("model_tag")
    if item_id in MODEL_IDS and (not isinstance(tag, str) or not _ID.fullmatch(tag) or
                                tag not in ("qwen2.5-coder:7b", "qwen3-embedding:0.6b")):
        return None
    return {"id": item_id, "version": version, "sha256": digest,
            "rights_receipt_id": rights, **({"model_tag": tag} if tag else {})}


class FirstBootCoordinator:
    def __init__(self, callbacks: FirstBootCallbacks):
        if not isinstance(callbacks, FirstBootCallbacks):
            raise FirstBootHold("EXISTING_CALLBACKS_REQUIRED")
        callbacks.verify()
        self.callbacks = callbacks
        # Native P03/P01 is the only durable, per-principal queue/dedupe authority.
        # A process-wide cache would conflate different Windows principals.

    def run(self, session, *, now):
        now = _utc(now)
        # Reuse original host's epoch: STOP followed by quick RESET still cancels
        # this run, including a native callback whose ACK arrives late.
        try:
            epoch = self.callbacks.stop_epoch()
            if type(epoch) is not int or epoch < 0:
                raise FirstBootHold("NATIVE_STOP_EPOCH_REQUIRED")
            def cancelled():
                return self.callbacks.stopped() is not False or self.callbacks.stop_epoch() != epoch
            if cancelled():
                raise FirstBootHold("NATIVE_STOP")
            native = self.callbacks.policy(session)
            roots = _policy(native, now)
            if cancelled():
                raise FirstBootHold("NATIVE_STOP")
            installed = _native_installed(self.callbacks.installed(session))
            if cancelled():
                raise FirstBootHold("NATIVE_STOP")
            discovered = _asset_observations(self.callbacks.discover(session, roots))
            if cancelled():
                raise FirstBootHold("NATIVE_STOP")
            # Acquisition V2 is an OPTIONAL owner-signed, SHA-pinned local
            # library. It is a read-only observation, not another queue or an
            # authorization to install tools/model weights.
            acquisition = {"schema": "NOX-ACQUISITION-AUDIT-v1",
                           "status": "NOT_CONFIGURED", "physical_files_verified": 0,
                           "models_installed": False, "tools_installed": False}
            if "acquisition_library" in native:
                spec = native["acquisition_library"]
                allowed = {"schema", "db_path", "db_sha256", "manifest_path",
                           "manifest_sha256", "assets_root"}
                if (type(spec) is not dict or set(spec) - allowed or
                    spec.get("schema") != "NOX-ACQUISITION-NATIVE-CONFIG-v1" or
                    type(spec.get("db_path")) is not str or
                    type(spec.get("db_sha256")) is not str):
                    raise FirstBootHold("NATIVE_ACQUISITION_POLICY_INVALID")
                try:
                    acquisition = audit_library(
                        spec["db_path"], spec["db_sha256"], approved_roots=roots,
                        manifest_path=spec.get("manifest_path"),
                        manifest_sha256=spec.get("manifest_sha256"),
                        assets_root=spec.get("assets_root"))
                except (AcquisitionHold, OSError, TypeError, ValueError) as exc:
                    raise FirstBootHold("ACQUISITION_V2_AUDIT_HOLD") from exc
                if cancelled():
                    raise FirstBootHold("NATIVE_STOP")
        except FirstBootHold as ex:
            return {"schema": "NOX-FIRSTBOOT-RECEIPT-v1",
                    "status": "STOPPED" if str(ex) == "NATIVE_STOP" else "HOLD",
                    "reason": str(ex), "downloaded": 0, "installed": 0,
                    "release_accepted": False}
        planned, held, already = [], [], []
        for i in sorted(ACTION_IDS):
            if installed.get(str(i)) is True:
                already.append(i)
                continue
            approved = _reviewed(native, i)
            if approved is None:
                held.append({"id": i, "reason": "PINNED_LICENSE_HARDWARE_ARTIFACT_REQUIRED"})
            else:
                planned.append({"route": TRUSTED_ACTIONS[i], "artifact": approved})
        # Record intent before invoking native download queue; on failure no dispatch.
        intent = {"schema": "NOX-FIRSTBOOT-INTENT-v1", "utc": now.isoformat(),
                  "approved_scan_roots_count": len(roots), "found": discovered,
                  "acquisition": acquisition,
                  "already_installed_ids": already, "held": held, "planned": planned,
                  "executed_code": False, "weights_changed": False,
                  "installer_changed": False, "auto_merge": False}
        if cancelled():
            return {"schema": "NOX-FIRSTBOOT-RECEIPT-v1", "status": "STOPPED",
                    "downloaded": 0, "release_accepted": False}
        if self.callbacks.persist(session, intent) is not True:
            return {"schema": "NOX-FIRSTBOOT-RECEIPT-v1", "status": "HOLD",
                    "reason": "NATIVE_S03_INTENT_READBACK_REQUIRED", "downloaded": 0,
                    "release_accepted": False}
        if cancelled():
            return {"schema": "NOX-FIRSTBOOT-RECEIPT-v1", "status": "STOPPED",
                    "downloaded": 0, "release_accepted": False}
        # Ingest compatible, reviewed *knowledge* through the existing native
        # S03 source-admission route. Never load code, models or packages as
        # executable; unknown/unsigned local candidates stay inventory-only.
        ingested = []
        local_review = native.get("reviewed_local_artifacts", {})
        if not isinstance(local_review, Mapping):
            local_review = {}
        if native.get("allow_local_knowledge_ingest") is True:
            for found in discovered:
                digest = found["sha256"]
                evidence = local_review.get(digest)
                if (not isinstance(evidence, Mapping) or
                    evidence.get("rights_verified") is not True or
                    evidence.get("content_safe_for_s03") is not True or
                    found["kind"] not in ("SOURCE_CANDIDATE", "DESIGN_CANDIDATE")):
                    continue
                if cancelled():
                    break
                receipt = self.callbacks.ingest(session, {"sha256": digest,
                    "kind": found["kind"], "action": "S03_NATIVE_REVIEWED_KNOWLEDGE_IMPORT"})
                if cancelled():
                    break  # Late native ACK is not an import completion receipt.
                if (isinstance(receipt, Mapping) and receipt.get("ack") is True and
                    receipt.get("s03_readback") is True and receipt.get("sha256") == digest):
                    ingested.append(digest)
        # STOP+RESET may arrive in the final S03 callback while there are NO
        # queued P03 actions to iterate. Never publish ALREADY_PRESENT then.
        # Native owner must independently read back any durable S03 write.
        if cancelled():
            return {"schema": "NOX-FIRSTBOOT-RECEIPT-v1", "status": "STOPPED",
                    "reason": "NATIVE_STOP_DURING_S03_INGEST_READBACK_REQUIRED",
                    "downloaded": 0, "release_accepted": False}
        dispatched, denied, already_queued = [], [], []
        for action in planned:
            i = action["artifact"]["id"]
            if cancelled():
                denied.append({"id": i, "reason": "STOP"})
                break
            # Native callback must re-check signed installer consent, current SID,
            # SourceLock, license, STOP epoch and digest atomically at enqueue.
            receipt = self.callbacks.dispatch(session, action["route"], dict(action["artifact"]))
            if cancelled():
                # Native enqueue outcome may already be durable: NEVER infer
                # cancellation or accept a late ACK. Next run reads native queue.
                denied.append({"id": i, "reason": "STOP_DURING_DISPATCH_READBACK_REQUIRED"})
                break
            if (not isinstance(receipt, Mapping) or receipt.get("ack") is not True or
                    receipt.get("native_durable_queue") is not True or
                    receipt.get("id") != i or
                    receipt.get("sha256") != action["artifact"]["sha256"] or
                    type(receipt.get("already_queued", False)) is not bool):
                denied.append({"id": i, "reason": "NATIVE_QUEUE_ACK_OR_DIGEST_MISMATCH"})
                continue
            if receipt.get("already_queued", False):
                already_queued.append(i)
            else:
                dispatched.append(i)
        # Any failed/uncertain native ACK keeps the overall FirstBoot in HOLD,
        # even when other actions were durably queued in the same run.
        # Keep their IDs in the receipt so the next owner can read back and
        # resume, never replaying an uncertain action or claiming full success.
        state = ("HOLD" if denied or held else
                 "QUEUED_NOT_INSTALLED" if dispatched else
                 "ALREADY_QUEUED_NOT_INSTALLED" if already_queued else
                 "ALREADY_PRESENT")
        return {"schema": "NOX-FIRSTBOOT-RECEIPT-v1", "status": state,
                "found_candidates": len(discovered), "already_installed_ids": already,
                "enqueued_ids": dispatched, "already_queued_ids": already_queued,
                "local_knowledge_ingested": len(ingested), "held": held + denied,
                "acquisition_library": {"status": acquisition["status"],
                    "physical_files_verified": acquisition["physical_files_verified"]},
                "downloaded": 0, "installed": len(already),
                "release_accepted": False, "e07_same_sha": False}
