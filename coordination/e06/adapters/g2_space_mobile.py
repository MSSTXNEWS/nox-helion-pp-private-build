"""NOX V16 G2/05: E06-only, in-process admission to the EXISTING PACK01 host.

No HTTP listener, public Ollama, downloader, SQLite, event journal, sensor
provider, ASR/TTS engine or SIP dialer is created here. This is an adapter
proposal: it cannot activate until the original whole-app SourceLock is sealed.
"""
from __future__ import annotations

import math
import re
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
        if route not in P05_ROUTES or not isinstance(args, dict) or args:
            raise G2Denied("P05 read-only route takes no untrusted filters or URLs")
        if not self.available(route):
            raise G2Hold("Existing owner5 telemetry/feed is not ready")
        raw = self.owner.snapshot(session)
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
                  and 0 < len(tile["Source"]) <= 100
                  and _fresh(tile.get("SourceUtc"), now, 24 * 3600)
                  and _fresh(tile.get("FetchedUtc"), now, 24 * 3600))
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
        seen, safe = set(), {}
        for sample in sensors:
            if not isinstance(sample, dict) or sample.get("Key") not in SENSORS:
                continue
            key = sample["Key"]
            if key in seen:
                safe[key] = {"value": None, "status": "N_D", "source": None}
                continue
            seen.add(key)
            value = sample.get("Value")
            good = (sample.get("Status") == "LIVE"
                    and type(value) in (int, float) and math.isfinite(value)
                    and value >= 0 and (not key.endswith("percent") or value <= 100)
                    and (key != "gpu.temperature.c" or value <= 150)
                    and isinstance(sample.get("Source"), str)
                    and bool(sample["Source"])
                    and _fresh(sample.get("ObservedAtUtc"), now, 30))
            safe[key] = {"value": value if good else None,
                         "status": "LIVE" if good else "N_D",
                         "source": sample["Source"] if good else None}
        used, total = safe.get("gpu.vram.used_bytes"), safe.get("gpu.vram.total_bytes")
        if (used and total and used["value"] is not None and total["value"] is not None
                and (total["value"] <= 0 or used["value"] > total["value"]
                     or used["source"] != total["source"])):
            for key in ("gpu.vram.used_bytes", "gpu.vram.total_bytes"):
                safe[key] = {"value": None, "status": "N_D", "source": None}
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
            return proof["identity"]

        identity = attest()
        advertised = self.host.advertise(session)
        if not self.available():
            raise G2Hold("EXISTING_PRIVATE_HOST_GATEWAY_REVOKED")
        if attest() != identity:
            raise G2Denied("Private device identity changed during advertisement")
        if not isinstance(advertised, dict):
            raise G2Hold("Existing native host advertisement unavailable")
        # Session-scoped capabilities, never a public URL or bearer token.
        return {"mode": "PRIVATE_NATIVE_ATTESTED", "gatewayListening": True,
                "allowed": [r for r in payload["want"]
                            if isinstance(advertised.get(r), dict)
                            and advertised[r].get("enabled") is True]}


def relay_existing_events_v3(event: dict, *, run_id: str,
                             trusted_owner: Callable[[], bool],
                             existing_publish: Callable[[dict], bool]) -> bool:
    """One existing host events.v3 publisher. No bus, queue or invented event."""
    if not callable(trusted_owner) or trusted_owner() is not True:
        raise G2Hold("Existing events.v3 SourceLock not admitted")
    if not callable(existing_publish) or not isinstance(event, dict):
        raise G2Hold("Canonical existing publisher required")
    required = ("schema", "run_id", "event_id", "event_type", "task_id",
                "package_id", "action_id", "timestamp_utc", "state",
                "source", "message", "evidence_verified")
    if (not all(k in event for k in required) or event.get("schema") !=
            "NOX-INSTALLER-EVENT-v3" or event.get("run_id") != run_id
            or event.get("event_type") not in EVENT_TYPES
            or event.get("state") not in EVENT_STATES
            or type(event.get("evidence_verified")) is not bool
            or not _stamp(event.get("timestamp_utc"))
            or any(not isinstance(event.get(k), str) or
                   not 0 < len(event[k]) <= 240
                   for k in ("event_id", "task_id", "package_id",
                             "action_id", "source"))):
        raise G2Denied("Invalid canonical events.v3 envelope")
    if event["event_type"] in ("cpu.sample", "telemetry.snapshot"):
        raise G2Denied("No unapproved events.v3 sensor type")
    if event.get("numerator") is not None or event.get("denominator") is not None:
        n, d = event.get("numerator"), event.get("denominator")
        if type(n) is not int or type(d) is not int or not 0 <= n <= d or d <= 0:
            raise G2Denied("Evidence numerator/denominator must be bounded integers")
    return existing_publish(event) is True


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
            frozen_routes = dict(self.host.routes)
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
                if (route in before or self.host.routes.get(route, {}).get("owner") != owner):
                    raise G2Hold("Existing host route collision or wrong owner: " + route)
            try:
                # Verify inside the existing host lock, not only before it.
                if self.verify_preimages(self.source_lock, dict(self.receipts)) is not True:
                    raise G2Hold("Frozen original archive/preimage/owner conflict")
                p2 = self.p02.register(self.host, receipt=self._receipt("P02"))
                p3 = self.p03.register(self.host, self.port_type,
                                      receipt=self._receipt("P03"))
                for route in sorted(e05_routes):
                    self.host.bind(route, self.port_type(
                        lambda s, a, r=route: self.e05.read(s, r, a),
                        lambda r=route: self.e05.available(r),
                        self._receipt("P05"), 5))
                for route, handler in sorted(voice_routes.items()):
                    self.host.bind(route, self.port_type(
                        handler, lambda r=route: self.voice.available(r),
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
                raise G2Hold("All-or-HOLD existing-host bindings rolled back") from exc
            return frozenset(set(p2) | set(p3) | intended)
