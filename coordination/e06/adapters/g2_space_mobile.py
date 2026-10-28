"""NOX V16 G2/05: E06-only, in-process admission to the EXISTING PACK01 host.

No HTTP listener, public Ollama, downloader, SQLite, event journal, sensor
provider, ASR/TTS engine or SIP dialer is created here. This is an adapter
proposal: it cannot activate until the original whole-app SourceLock is sealed.
"""
from __future__ import annotations

import copy
import json
import math
import re
from g2_gpu_provenance import valid_source, valid_device, reconcile_gpu_tile
from g2_gpu_sample_gate import valid_sample_id, enforce_gpu_tile_sample
from g2_event_state_gate import EventStateHold, require_event_state_coherence
from datetime import datetime, timezone
from typing import Any, Callable

_SHA1 = re.compile(r"^[a-f0-9]{40}$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
FEED_ROUTES = frozenset(("space.news", "space.weather", "space.fx",
                         "space.bitcoin", "space.brent"))
P05_ROUTES = FEED_ROUTES | {"system.telemetry"}
VOICE_METHODS = {
    "translate.ru_es": "translate",
    "maestro.spanish": "maestro",
    "voice.settings": "voice_settings",
    "calls.history": "call_history",
}
# The only permitted callback for a paid call is the actual quote+native
# consent gate owned by P02; generic execute()/URL handlers are not accepted.
REMOTE_SAFE = frozenset(("helion.chat", "core.chat", "persona.chat",
    "chat.history", "chat.rag", "chat.stop", "chat.voice", "chat.model",
    "models.catalog", "models.installed", "models.digest",
    "space.news", "space.weather", "space.fx", "space.bitcoin",
    "space.brent", "system.telemetry"))
EVENT_TYPES = frozenset(("task.started", "task.progress", "task.failed",
    "task.completed", "model.tokens", "model.stopped", "gpu.sample",
    "training.step", "checkpoint.saved", "acceptance.updated"))
EVENT_STATES = frozenset(("QUEUED", "RUNNING", "PAUSED", "COMPLETED",
    "ERROR", "STOPPED", "OFFLINE", "HOLD", "READY", "N_D"))
SENSORS = frozenset(("cpu.system.percent", "gpu.percent",
    "gpu.vram.used_bytes", "gpu.vram.total_bytes", "gpu.temperature.c"))
P02_REQUIRED = frozenset(("helion.chat", "core.chat", "persona.chat",
    "chat.model", "chat.history", "chat.stop"))
P03_REQUIRED = frozenset(("models.catalog", "models.installed", "models.digest"))


class G2Hold(RuntimeError):
    """No current source seal or real owner service; never claim success."""


class G2Denied(PermissionError):
    """Invalid trusted-session, origin or privilege boundary."""


def _stamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or len(value) > 48:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None or dt.utcoffset().total_seconds() != 0:
            return None
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None


def _fresh(value: Any, now: datetime, seconds: int) -> bool:
    stamp = _stamp(value)
    return stamp is not None and 0 <= (now - stamp).total_seconds() <= seconds


class ExistingE05Projection:
    """Read only the real C# E05ApprovedSpace/E05HostStateAdapter DTO.

    The E06 host provides an already-authorized snapshot() and an immutable
    feed_id map from owner5. This adapter never fetches feeds or guesses prices.
    """

    def __init__(self, owner5: object, *, run_id: str,
                 feed_ids: dict[str, str], clock: Callable[[], datetime] | None = None):
        if not isinstance(run_id, str) or not 0 < len(run_id) <= 160:
            raise ValueError("Current host RunID required")
        if not callable(getattr(owner5, "snapshot", None)) or not callable(
                getattr(owner5, "available", None)):
            raise G2Hold("Existing E05 owner snapshot/health required")
        if not isinstance(feed_ids, dict) or set(feed_ids) != FEED_ROUTES:
            raise G2Hold("Exact existing E05 route-to-approved-feed mapping required")
        if not all(isinstance(v, str) and 0 < len(v) <= 100
                   for v in feed_ids.values()) or len(set(feed_ids.values())) != 5:
            raise G2Hold("E05 feed aliases must be unique, nonempty and preapproved")
        self.owner = owner5
        self.run_id = run_id
        self.feed_ids = dict(feed_ids)
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def available(self, route: str) -> bool:
        try:
            return route in P05_ROUTES and self.owner.available(route) is True
        except Exception:
            return False

    def read(self, session: object, route: str, args: dict) -> dict:
        if type(route) is not str or route not in P05_ROUTES or not isinstance(args, dict) or args:
            raise G2Denied("P05 read-only route takes no untrusted filters or URLs")
        if not self.available(route):
            raise G2Hold("Existing owner5 telemetry/feed is not ready")
        raw = self.owner.snapshot(session)
        # Owner5 approval may be revoked while collecting the snapshot.
        # Never publish previously-LIVE feed/sensor data after that revoke.
        if not self.available(route):
            raise G2Hold("Existing owner5 source revoked during snapshot")
        now = self.clock()
        if (not isinstance(raw, dict) or raw.get("Schema") != "NOX-E05-READONLY-v1"
                or raw.get("RunId") != self.run_id or raw.get("Access") != "READ_ONLY"
                or not _fresh(raw.get("SnapshotUtc"), now, 30)):
            raise G2Hold("Owner5 snapshot schema/run/freshness mismatch")
        if route in FEED_ROUTES:
            tiles = raw.get("Tiles")
            if not isinstance(tiles, list) or len(tiles) > 16:
                raise G2Hold("Untrusted E05 tile collection")
            matched = [t for t in tiles if isinstance(t, dict)
                       and t.get("FeedId") == self.feed_ids[route]]
            if len(matched) != 1:
                return {"status": "N_D", "source": None, "sourceUtc": None,
                        "fetchedUtc": None, "preview": None}
            tile = matched[0]
            ok = (tile.get("Status") == "SOURCE_DATED"
                  and isinstance(tile.get("Source"), str)
                  and 0 < len(tile["Source"].strip()) <= 100
                  and _fresh(tile.get("SourceUtc"), now, 24 * 3600)
                  and _fresh(tile.get("FetchedUtc"), now, 24 * 3600)
                  and _stamp(tile.get("SourceUtc")) <= _stamp(tile.get("FetchedUtc"))
                  and _stamp(tile.get("FetchedUtc")) <= _stamp(raw.get("SnapshotUtc")))
            return {"status": "SOURCE_DATED" if ok else
                    "STALE" if tile.get("Status") == "STALE" else "N_D",
                    "source": tile["Source"] if ok else None,
                    "sourceUtc": tile["SourceUtc"] if ok else None,
                    "fetchedUtc": tile["FetchedUtc"] if ok else None,
                    # E05 currently supplies no licensed price/news previews.
                    "preview": None}
        sensors = raw.get("Hardware")
        if not isinstance(sensors, list) or len(sensors) > 32:
            raise G2Hold("E05 hardware payload malformed")
        seen, safe, observed_by_key, device_by_key, sample_by_key = set(), {}, {}, {}, {}
        for sample in sensors:
            if (not isinstance(sample, dict) or type(sample.get("Key")) is not str
                    or sample.get("Key") not in SENSORS):
                continue
            key = sample["Key"]
            if key in seen:
                safe[key] = {"value": None, "status": "N_D", "source": None}
                continue
            seen.add(key)
            value = sample.get("Value")
            # Both original E05 C# DeviceId and P05 JS device_id name are
            # accepted only when unambiguous. Unknown device => GPU N/D.
            native_device = sample.get("DeviceId", sample.get("device_id"))
            if ("DeviceId" in sample and "device_id" in sample
                    and sample["DeviceId"] != sample["device_id"]):
                native_device = None
            # A native sample identity is optional for legacy P05 producers,
            # but a supplied ID must be lexical, stable and unambiguous.
            sample_present = "SampleId" in sample or "sample_id" in sample
            native_sample = sample.get("SampleId", sample.get("sample_id"))
            if ("SampleId" in sample and "sample_id" in sample
                    and sample["SampleId"] != sample["sample_id"]):
                native_sample = None
            good = (sample.get("Status") == "LIVE"
                    and type(value) in (int, float) and math.isfinite(value)
                    and value >= 0
                    and (not key.endswith("_bytes") or type(value) is int)
                    and (not key.endswith("percent") or value <= 100)
                    and (key != "gpu.temperature.c" or value <= 150)
                    and valid_source(sample.get("Source"))
                    and (not key.startswith("gpu.") or valid_device(native_device))
                    and (not key.startswith("gpu.") or not sample_present
                         or valid_sample_id(native_sample))
                    and _fresh(sample.get("ObservedAtUtc"), now, 30)
                    and _stamp(sample.get("ObservedAtUtc")) <= _stamp(raw.get("SnapshotUtc")))
            safe[key] = {"value": value if good else None,
                         "status": "LIVE" if good else "N_D",
                         "source": sample["Source"] if good else None}
            observed_by_key[key] = sample.get("ObservedAtUtc") if good else None
            device_by_key[key] = native_device if good and key.startswith("gpu.") else None
            sample_by_key[key] = native_sample if good and key.startswith("gpu.") else None
        # One physical GPU and one VRAM sample, consistent with owner E05 R08.
        # No second sensor, poller or events bus.
        reconcile_gpu_tile(safe, observed_by_key, device_by_key)
        # Reuse the approved E05 snapshot; never merge providers, sample IDs
        # or observation windows into a fictional single LIVE GPU tile.
        enforce_gpu_tile_sample(safe, observed_by_key, sample_by_key)
        seal = getattr(self.owner, "product_receipts_sealed", None)
        percent = raw.get("ProductProgress")
        verified = callable(seal) and seal() is True
        if not (verified and type(percent) in (int, float)
                and math.isfinite(percent) and 0 <= percent <= 100):
            percent = None
        return {"sensors": safe, "productProgress": percent,
                "productProgressStatus": "VERIFIED" if percent is not None else "N_D"}


class PrivateMobileContract:
    """Native-only authorization contract; NOT a VPN/HTTPS gateway.

    Host must derive proof from its authenticated private peer/session, rotate
    CSRF and check TLS/origin. Browser-provided identity/headers are not proof.
    """

    def __init__(self, existing_p02_policy: Callable, trusted_peer: Callable,
                 existing_host: object, clock: Callable[[], float],
                 gateway_ready: Callable[[], bool] | None = None):
        if not all(callable(x) for x in (existing_p02_policy, trusted_peer, clock)):
            raise G2Hold("Existing P02 mobile auth + native peer verifier required")
        self.policy, self.peer, self.host, self.clock = (
            existing_p02_policy, trusted_peer, existing_host, clock)
        self.gateway_ready = gateway_ready

    def available(self) -> bool:
        # A native host probe must attest private HTTPS gateway/Tailscale is
        # actually configured; the mere presence of this file is not proof.
        try:
            return callable(self.gateway_ready) and self.gateway_ready() is True
        except Exception:
            return False

    def connect(self, session: object, payload: dict) -> dict:
        if not self.available():
            raise G2Hold("EXISTING_PRIVATE_HOST_GATEWAY_NOT_READY")
        if (not isinstance(payload, dict) or set(payload) != {"want"}
                or not isinstance(payload["want"], list)
                or len(payload["want"]) > 18
                or any(not isinstance(r, str) or r not in REMOTE_SAFE
                       for r in payload["want"])
                or len(set(payload["want"])) != len(payload["want"])):
            raise G2Denied("Remote request may ask only safe registered capabilities")
        def attest() -> object:
            # Recheck native proof after host advertisement too: a peer,
            # session, CSRF or gateway can be revoked during an owner call.
            proof = self.peer(session)  # Never trust request-supplied headers.
            if not isinstance(proof, dict) or set(proof) != {
                "identity", "verified_private_peer", "trusted_origin",
                "observed_origin", "expected_csrf", "received_csrf",
                "native_session_approved", "expires_at"}:
                raise G2Denied("Missing private host-attested device/session")
            expiry, now = proof["expires_at"], self.clock()
            if (type(expiry) not in (int, float) or not math.isfinite(expiry)
                    or not now < expiry <= now + 300):
                raise G2Denied("Expired or implausible private authorization")
            try:
                ok = self.policy(proof["identity"],
                                 verified_private_peer=proof["verified_private_peer"],
                                 trusted_origin=proof["trusted_origin"],
                                 observed_origin=proof["observed_origin"],
                                 expected_csrf=proof["expected_csrf"],
                                 received_csrf=proof["received_csrf"],
                                 native_session_approved=proof["native_session_approved"])
            except Exception as exc:
                raise G2Denied("Private origin/CSRF verification failed") from exc
            if ok is not True:
                raise G2Denied("Private peer/CSRF/user consent denied")
            return (proof["identity"], proof["expected_csrf"],
                    proof["observed_origin"])

        identity = attest()
        advertised = self.host.advertise(session)
        if not self.available():
            raise G2Hold("EXISTING_PRIVATE_HOST_GATEWAY_REVOKED")
        if attest() != identity:
            raise G2Denied("Private identity, origin or CSRF epoch changed during advertisement")
        if not isinstance(advertised, dict):
            raise G2Hold("Existing native host advertisement unavailable")
        # Session-scoped capabilities, never a public URL or bearer token.
        return {"mode": "PRIVATE_NATIVE_ATTESTED", "gatewayListening": True,
                "allowed": [r for r in payload["want"]
                            if isinstance(advertised.get(r), dict)
                            and advertised[r].get("enabled") is True]}


def _frozen_event_wire(event: dict) -> tuple[str, dict]:
    """Bounded JSON-only snapshot shared across attestation and publication."""
    try:
        wire = json.dumps(event, ensure_ascii=False, allow_nan=False,
                          sort_keys=True, separators=(",", ":"))
        if len(wire.encode("utf-8")) > 8192:
            raise G2Denied("Unbounded events.v3 envelope")
        canonical = json.loads(wire)
        if canonical != event:
            raise G2Denied("Noncanonical JSON events.v3 payload")
    except (TypeError, ValueError, OverflowError, RecursionError,
            UnicodeError) as exc:
        raise G2Denied("Non-JSON or invalid events.v3 payload") from exc
    return wire, canonical


def relay_existing_events_v3(event: dict, *, run_id: str,
                             trusted_owner: Callable[[], bool],
                             existing_publish: Callable[[dict], bool],
                              trusted_evidence: Callable[[dict], bool] | None = None) -> bool:
    """One existing host events.v3 publisher. No bus, queue or invented event."""
    if not callable(trusted_owner):
        raise G2Hold("Existing events.v3 SourceLock callback missing")
    try:
        initial_seal = trusted_owner() is True
    except Exception as exc:
        raise G2Hold("Existing events.v3 SourceLock callback failed") from exc
    if not initial_seal:
        raise G2Hold("Existing events.v3 SourceLock not admitted")
    if not callable(existing_publish) or type(event) is not dict:
        raise G2Hold("Canonical existing publisher required")
    wire, frozen = _frozen_event_wire(event)
    required = ("schema", "run_id", "event_id", "event_type", "task_id",
                "package_id", "action_id", "timestamp_utc", "state",
                "source", "message", "evidence_verified")
    if (not all(k in event for k in required) or frozen.get("schema") !=
            "NOX-INSTALLER-EVENT-v3" or frozen.get("run_id") != run_id
            or type(frozen.get("event_type")) is not str
            or frozen["event_type"] not in EVENT_TYPES
            or type(frozen.get("state")) is not str
            or frozen["state"] not in EVENT_STATES
            or type(frozen.get("evidence_verified")) is not bool
            or not isinstance(frozen.get("message"), str)
            or len(frozen["message"]) > 480
            or not _stamp(frozen.get("timestamp_utc"))
            or any(not isinstance(frozen.get(k), str) or
                   not 0 < len(frozen[k]) <= 240
                   for k in ("event_id", "task_id", "package_id",
                             "action_id", "source"))):
        raise G2Denied("Invalid canonical events.v3 envelope")
    try:
        require_event_state_coherence(frozen["event_type"], frozen["state"])
    except EventStateHold as exc:
        raise G2Denied("Inconsistent native events.v3 event type/state") from exc
    if frozen["event_type"] in ("cpu.sample", "telemetry.snapshot"):
        raise G2Denied("No unapproved events.v3 sensor type")
    if frozen.get("numerator") is not None or frozen.get("denominator") is not None:
        n, d = frozen.get("numerator"), frozen.get("denominator")
        if type(n) is not int or type(d) is not int or not 0 <= n <= d or d <= 0:
            raise G2Denied("Evidence numerator/denominator must be bounded integers")
    # Terminal/accepted states cannot be projected LIVE without native proof.
    terminal = (frozen["event_type"] in ("task.completed", "model.stopped",
                "checkpoint.saved", "acceptance.updated")
                or frozen["state"] in ("COMPLETED", "STOPPED", "READY"))
    if terminal and frozen["evidence_verified"] is not True:
        raise G2Hold("Unverified terminal/accepted event cannot be published")
    # Untrusted event.evidence_verified flag is never a native receipt.
    if frozen["evidence_verified"] is True:
        try:
            attested = callable(trusted_evidence) and trusted_evidence(json.loads(wire)) is True
            still_sealed = trusted_owner() is True
        except Exception as exc:
            raise G2Hold("Native event evidence verification failed") from exc
        if not attested or not still_sealed:
            raise G2Hold("Verified event lacks native receipt or stable SourceLock")
    # Even an unverified progress event must not cross a revoked SourceLock.
    try:
        still_sealed = trusted_owner() is True
    except Exception as exc:
        raise G2Hold("SourceLock check failed immediately before publish") from exc
    if not still_sealed:
        raise G2Hold("SourceLock revoked before existing events.v3 publish")
    # No foreign/native callback may change the checked bytes before publish.
    try:
        if _frozen_event_wire(event)[0] != wire:
            raise G2Hold("events.v3 changed during native attestation")
    except G2Denied as exc:
        raise G2Hold("events.v3 became invalid during native attestation") from exc
    return existing_publish(json.loads(wire)) is True


class G2OneHostBinder:
    """Serial, all-or-HOLD registration to the existing NoxPackHost only."""

    def __init__(self, host: object, bound_port_type: type, *,
                 existing_p02: object, existing_p03: object,
                 e05: ExistingE05Projection, mobile: PrivateMobileContract | None,
                 existing_p02_voice: object | None,
                 source_lock_sha256: str | None,
                 owner_receipts_sha256: dict[str, str],
                 verify_original_preimages: Callable,
                 existing_host_mutation_lock: object):
        self.host, self.port_type = host, bound_port_type
        self.p02, self.p03, self.e05, self.mobile, self.voice = (
            existing_p02, existing_p03, e05, mobile, existing_p02_voice)
        if not isinstance(owner_receipts_sha256, dict):
            raise G2Hold("Owner receipts must be an immutable binding snapshot")
        self.source_lock, self.receipts = source_lock_sha256, dict(owner_receipts_sha256)
        self.verify_preimages, self.lock = (
            verify_original_preimages, existing_host_mutation_lock)

    def _receipt(self, owner: str) -> str:
        digest = self.receipts.get(owner)
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise G2Hold("Owner SHA-256 receipt absent: " + owner)
        return digest

    def bind(self) -> frozenset[str]:
        if (not isinstance(self.source_lock, str) or not _SHA256.fullmatch(self.source_lock)
                or not callable(self.verify_preimages)
                or not all(callable(getattr(self.lock, method, None))
                           for method in ("__enter__", "__exit__"))):
            raise G2Hold("Current original app SourceLock / host serial lock missing")
        for owner in ("P02", "P03", "P05"):
            self._receipt(owner)
        if not isinstance(getattr(self.host, "routes", None), dict) or not isinstance(
                getattr(self.host, "ports", None), dict):
            raise G2Hold("Existing PACK01 one-host route registry is mandatory")
        if not all(callable(getattr(self.p02, m, None)) for m in ("register",)) or (
                not callable(getattr(self.p03, "register", None))):
            raise G2Hold("Original P02/P03 owner adapters are missing")
        with self.lock:  # Canonical host registry lock, never an E06 copy.
            before = dict(self.host.ports)
            try:
                # dict() aliases nested owner permissions: freeze the actual ACL.
                frozen_routes = copy.deepcopy(self.host.routes)
            except Exception as exc:
                raise G2Hold("Native route descriptors cannot be frozen") from exc
            e05_routes = {route for route in P05_ROUTES
                          if self.e05.available(route)}
            voice_routes = {}
            if self.voice is not None:
                for route, method in VOICE_METHODS.items():
                    ready = getattr(self.voice, "available", None)
                    handler = getattr(self.voice, method, None)
                    if callable(ready) and callable(handler) and ready(route) is True:
                        voice_routes[route] = handler
                # No SIP bind without real P02 ConsentGatedSip and quote + local
                # native confirmation. Merely a UI quote is NEVER authority.
                sip = getattr(self.voice, "verified_sip", None)
                dial = getattr(self.voice, "dial_with_native_quote", None)
                if callable(sip) and sip() is True and callable(dial) and (
                        callable(getattr(self.host, "native_approve", None))):
                    voice_routes["calls.dial"] = dial
            mobile_routes = {"mobile.connect"} if (self.mobile is not None and
                    self.mobile.available()) else set()
            intended = set(e05_routes) | set(voice_routes) | mobile_routes
            for route in intended:
                owner = 5 if route in e05_routes else 6 if route in mobile_routes else 2
                descriptor = frozen_routes.get(route)
                if (route in before or type(descriptor) is not dict
                        or type(descriptor.get("owner")) is not int
                        or descriptor["owner"] != owner):
                    raise G2Hold("Existing host route collision or wrong owner: " + route)
            try:
                # Verify inside the existing host lock, not only before it.
                if self.verify_preimages(self.source_lock, dict(self.receipts)) is not True:
                    raise G2Hold("Frozen original archive/preimage/owner conflict")
                p2 = self.p02.register(self.host, receipt=self._receipt("P02"))
                p3 = self.p03.register(self.host, self.port_type,
                                      receipt=self._receipt("P03"))
                # Registration reports alone are not evidence of installed ports.
                claimed = set()
                for owner_no, routes, mandatory, name in (
                    (2, p2, P02_REQUIRED, "P02"),
                    (3, p3, P03_REQUIRED, "P03"),
                ):
                    if (not isinstance(routes, (set, frozenset))
                            or not mandatory.issubset(routes)):
                        raise G2Hold("Missing original mandatory " + name + " routes")
                    for route in routes:
                        port = self.host.ports.get(route)
                        if (not isinstance(route, str) or route not in frozen_routes
                                or port is None
                                or type(getattr(port, "owner", None)) is not int
                                or port.owner != owner_no
                                or type(getattr(port, "evidence_id", None)) is not str
                                or port.evidence_id != self._receipt(name)):
                            raise G2Hold("Unattested owner route registration: " + str(route))
                        claimed.add(route)
                if set(p2) & set(p3) or claimed & intended:
                    raise G2Hold("Cross-owner route collision on one host")
                for route in sorted(e05_routes):
                    self.host.bind(route, self.port_type(
                        lambda s, a, r=route: self.e05.read(s, r, a),
                        lambda r=route: self.e05.available(r),
                        self._receipt("P05"), 5))
                def voice_ready(route):
                    try:
                        return (self.voice.available(route) is True
                            and (route != "calls.dial"
                                 or (self.voice.verified_sip() is True
                                     and callable(getattr(self.host, "native_approve", None)))))
                    except Exception:
                        return False
                for route, handler in sorted(voice_routes.items()):
                    self.host.bind(route, self.port_type(
                        handler, lambda r=route: voice_ready(r),
                        self._receipt("P02"), 2))
                if "mobile.connect" in mobile_routes:
                    self.host.bind("mobile.connect", self.port_type(
                        self.mobile.connect, self.mobile.available,
                        self._receipt("P02"), 6))
                # An owner can revoke preimage readiness while registering.
                # Reject changed source trees and modified pre-existing ports.
                if (self.verify_preimages(self.source_lock, dict(self.receipts)) is not True
                        or self.host.routes != frozen_routes
                        or any(self.host.ports.get(r) is not p
                               for r, p in before.items())):
                    raise G2Hold("SourceLock or existing registry changed during binding")
            except Exception as exc:
                # Roll back even if a misbehaving owner overwrote an old port;
                # original source/assets and existing host object stay intact.
                self.host.ports.clear()
                self.host.ports.update(before)
                # Restore owner-mutated nested route ACLs, but never rewrite
                # native routes when their pre-bind value is unchanged.
                if self.host.routes != frozen_routes:
                    self.host.routes.clear()
                    self.host.routes.update(copy.deepcopy(frozen_routes))
                raise G2Hold("All-or-HOLD existing-host bindings rolled back") from exc
            return frozenset(set(p2) | set(p3) | intended)
