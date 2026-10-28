"""NOX V16 E06: admission contract for the SINGLE existing native host.

NO ROUTER, SERVICE, WEB ENDPOINT, FILE SYSTEM CONTROL OR MODEL ENGINE IS CREATED.
The already-owned host supplies a signed session, native capabilities, approval,
file-picker and real handler ACK; this module refuses everything else.
The 50-route registry remains the approved PACK01 catalog, never a new table.
Source-only candidate until whole application SourceLock and E07 acceptance.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import hmac
import json
import os
import stat
from pathlib import Path
from types import MappingProxyType
import re
import secrets
import threading
import time
import uuid
from urllib.parse import urlsplit

BASE_COMMIT = "0b3a7d435be735148d64171deb9027093a89646e"
BASE_TREE = "f108d604c444f718b32aaecfd07b90b8f91b9a6f"
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
ROUTE = re.compile(r"[a-z][a-z0-9]*(?:[._][a-z0-9]+)*\Z")
TASKS = tuple(f"NIP01-{i:02}" for i in range(1, 51))
# Immutable, SOURCE-only route/owner/risk floor from PR #27 exact HEAD
# be1fe05d88443e41b0d196617840508d9dd39b7d (NOT native SourceLock acceptance).
# Native host must separately attest installed handlers and full source tree.
APPROVED_ROUTE_POLICY = (
    ('helion.chat', 2, 'safe'),
    ('core.chat', 2, 'safe'),
    ('persona.chat', 2, 'safe'),
    ('chat.model', 2, 'safe'),
    ('chat.history', 2, 'sensitive'),
    ('chat.attach', 2, 'sensitive'),
    ('chat.rag', 2, 'safe'),
    ('chat.voice', 2, 'sensitive'),
    ('chat.stop', 2, 'safe'),
    ('chat.commands', 2, 'safe'),
    ('models.catalog', 3, 'safe'),
    ('models.installed', 3, 'safe'),
    ('models.pull', 3, 'sensitive'),
    ('models.gguf.import', 3, 'sensitive'),
    ('models.queue', 3, 'safe'),
    ('models.cancel', 3, 'safe'),
    ('models.retry', 3, 'sensitive'),
    ('models.digest', 3, 'safe'),
    ('models.preflight', 3, 'safe'),
    ('models.licenses', 3, 'safe'),
    ('rag.import', 4, 'sensitive'),
    ('rag.search', 4, 'safe'),
    ('memory.manage', 4, 'sensitive'),
    ('datasets.review', 4, 'safe'),
    ('gpu.preflight', 4, 'safe'),
    ('training.start', 4, 'dangerous'),
    ('training.pause', 4, 'safe'),
    ('training.resume', 4, 'sensitive'),
    ('training.checkpoints', 4, 'sensitive'),
    ('training.evaluate', 4, 'safe'),
    ('translate.ru_es', 2, 'sensitive'),
    ('maestro.spanish', 2, 'safe'),
    ('voice.settings', 2, 'safe'),
    ('calls.dial', 2, 'dangerous'),
    ('calls.history', 2, 'sensitive'),
    ('media.player', 1, 'sensitive'),
    ('media.subtitles', 1, 'safe'),
    ('browser.open', 1, 'sensitive'),
    ('browser.bookmarks', 1, 'safe'),
    ('images.generate', 4, 'sensitive'),
    ('space.news', 5, 'safe'),
    ('space.weather', 5, 'safe'),
    ('space.fx', 5, 'safe'),
    ('space.bitcoin', 5, 'safe'),
    ('space.brent', 5, 'safe'),
    ('system.telemetry', 5, 'safe'),
    ('system.update', 1, 'dangerous'),
    ('system.backup', 1, 'dangerous'),
    ('system.pc_control', 1, 'dangerous'),
    ('mobile.connect', 6, 'sensitive'),
)
STOP_TARGETS = {"chat.stop": frozenset({"helion.chat", "core.chat", "persona.chat"}),
                "models.cancel": frozenset({"models.pull"}),
                "training.pause": frozenset({"training.start"})}
STOP_ROUTES = frozenset(STOP_TARGETS)
# These are catalogue selectors, NOT executable host routes or page-provided paths.
NATIVE_OPTION_SOURCES = frozenset({"host.models.installed", "host.voices.installed",
                                    "host.personas", "host.cores"})
MAX_PENDING = 256
ACK_LEASE_SECONDS = 180
ACK_FIELDS = frozenset({
    "runId", "taskId", "routeId", "owner", "ownerReceiptSha256",
    "payloadSha256", "sourceLockTree", "sessionScopeSha256", "targetRunId",
    "fileSha256", "fileTicketSha256", "event", "proofSha256", "seal",
})
MIC_ROUTES = frozenset({"chat.voice", "translate.ru_es", "maestro.spanish", "calls.dial"})
PICKER_ROUTES = frozenset({"chat.attach", "models.gguf.import", "rag.import",
                           "datasets.review", "media.player", "media.subtitles",
                           "system.backup", "system.update"})
FORBIDDEN_PAGE_KEYS = frozenset({
    "authorization", "password", "token", "nativeConsent", "nativeApproval",
    "filePath", "localPath", "shell", "powershell", "exec", "command",
    "program", "driveLetter", "rawFile", "nativeFileHandle", "session", "origin",
})

class Hold(RuntimeError):
    """Missing proven native capability or source preimage (never a success)."""

class Denied(PermissionError):
    """Native authentication, origin, permission or consent refused."""


def canonical(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(obj: object) -> str:
    return hashlib.sha256(canonical(obj)).hexdigest()


def validate_origin(origin: str) -> str:
    if not isinstance(origin, str):
        raise Denied("ORIGIN_INVALID")
    try:
        p = urlsplit(origin)
    except ValueError as exc:
        raise Denied("ORIGIN_INVALID") from exc
    try:
        bad_port = p.port not in (None, 443)
    except ValueError as exc:
        raise Denied("ORIGIN_INVALID") from exc
    if (p.scheme != "https" or not p.hostname or p.username or p.password or
        bad_port or p.path not in ("", "/") or p.query or p.fragment or
        origin.endswith(".")):
        raise Denied("ORIGIN_INVALID")
    clean = f"https://{p.hostname.lower()}"  # HTTPS virtual-host origin only
    if origin != clean:
        raise Denied("ORIGIN_NOT_CANONICAL")
    return clean


def audit_registry(catalog: dict, bindings: dict) -> dict:
    """Read-only audit of exactly 50 TaskIDs, NOT installation/activation."""
    if not isinstance(catalog, dict) or not isinstance(bindings, dict):
        raise Hold("REGISTRY_JSON_OBJECT_REQUIRED")
    if catalog.get("version") != "NOX-INTEGRATION-PACK-01":
        raise Hold("CATALOG_VERSION")
    actions, rows = catalog.get("actions"), bindings.get("routes")
    if not isinstance(actions, list) or not isinstance(rows, list) or len(actions) != 50 or len(rows) != 50:
        raise Hold("REQUIRE_50_TASKS")
    actions_by_task, rows_by_task = {}, {}
    for src, index in ((actions, actions_by_task), (rows, rows_by_task)):
        for x in src:
            # Type-before-membership: untrusted JSON arrays/objects cannot be TaskIDs.
            task_id = x.get("taskId") if isinstance(x, dict) else None
            if type(task_id) is not str or task_id not in TASKS or task_id in index:
                raise Hold("BAD_OR_DUPLICATE_TASKID")
            index[task_id] = x
        if set(index) != set(TASKS):
            raise Hold("TASK_LEDGER_GAP")
    out = []
    route_set = set()
    for task in TASKS:
        a, b = actions_by_task[task], rows_by_task[task]
        route = a.get("routeId")
        expected_route, expected_owner, expected_risk = APPROVED_ROUTE_POLICY[int(task[-2:])-1]
        # Never take the security classification or owner of an executable action
        # solely from the mutable UI catalog and its matching mutable binding map.
        if (route != expected_route or a.get("owner") != expected_owner or
            type(a.get("owner")) is not int or a.get("risk") != expected_risk):
            raise Hold("IMMUTABLE_ROUTE_OWNER_RISK_POLICY_MISMATCH")
        if (not isinstance(route, str) or not ROUTE.fullmatch(route) or route in route_set or
            b.get("routeId") != route or b.get("owner") != a.get("owner") or
            type(a.get("owner")) is not int or type(b.get("owner")) is not int or
            a.get("owner") not in range(1, 7) or a.get("risk") not in
            ("safe", "sensitive", "dangerous")):
            raise Hold("ROUTE_OWNER_RISK_COLLISION")
        route_set.add(route)
        binding = b.get("sourceBinding")
        if binding is not None and (not isinstance(binding, str) or ":" not in binding):
            raise Hold("UNTRUSTED_BINDING_DESCRIPTOR")
        if b.get("exeIntegrated") is True or b.get("releaseAccepted") is True:
            # A proposal mapping is NOT an authoritative native host attestation.
            raise Hold("UNSIGNED_INTEGRATION_CLAIM")
        settings = a.get("settings", [])
        if (not isinstance(settings, list) or
            any(not isinstance(x, dict) or not isinstance(x.get("key"), str) or
                not ROUTE.fullmatch(x["key"]) for x in settings) or
            len({x["key"] for x in settings}) != len(settings)):
            raise Hold("INVALID_SETTINGS_SCHEMA")
        policy = {}
        for x in settings:
            # An untrusted catalogue may not turn a select into executable input.
            if x.get("kind") != "select" or (("source" in x) == ("options" in x)):
                raise Hold("INVALID_SELECT_POLICY")
            if "source" in x:
                if type(x["source"]) is not str or x["source"] not in NATIVE_OPTION_SOURCES:
                    raise Hold("UNTRUSTED_NATIVE_OPTION_SOURCE")
                policy[x["key"]] = {"source": x["source"]}
            else:
                options = x["options"]
                if (not isinstance(options, list) or not 1 <= len(options) <= 128 or
                    any(not isinstance(option, list) or len(option) != 2 or
                        any(not isinstance(value,str) or not 0 < len(value) <= 128
                            for value in option) for option in options) or
                    len({option[0] for option in options}) != len(options)):
                    raise Hold("INVALID_STATIC_SELECT_OPTIONS")
                policy[x["key"]] = {"options": tuple(option[0] for option in options)}
        out.append({"taskId": task, "routeId": route, "owner": a["owner"],
                    "allowedSettings": [x["key"] for x in settings],
                    "settingPolicy": policy,
                    "risk": a["risk"], "sourceBinding": binding,
                    "sourceState": "SOURCE" if binding else "HOLD",
                    "componentEvidence": b.get("componentCI", "N/D"),
                    "integrated": "HOLD", "windowsAccepted": "NOT_RUN",
                    "blocker": b.get("blocker") or "NO_NATIVE_OWNER_RECEIPT"})
    drift = bindings.get("sourceBaseCommit") != BASE_COMMIT
    return {"schema": "E06_HOST50_SOURCE_AUDIT_V1", "baselineCommit": BASE_COMMIT,
            "baselineTree": BASE_TREE, "ownerMapBaseCommit": bindings.get("sourceBaseCommit"),
            "baselineDrift": drift, "sourceBound": sum(bool(r["sourceBinding"]) for r in out),
            "unbound": sum(not r["sourceBinding"] for r in out),
            "nativeIntegrated": 0, "windowsAccepted": 0,
            "hostStatus": "HOLD_SOURCELOCK_DRIFT" if drift else "HOLD_NATIVE_RECEIPTS",
            "weightedProductProgress": "N/D", "routes": out}


@dataclass(frozen=True)
class Session:
    tenant: str
    principal: str
    chat: str
    origin: str
    scopes: tuple[str, ...]
    sensitive: tuple[str, ...]
    expires_unix: int
    nonce: str
    seal: str


@dataclass(frozen=True)
class Capability:
    route: str
    owner: int
    handler: str
    owner_receipt_sha256: str
    frozen_tree: str
    integrated: bool
    ready: bool


@dataclass(frozen=True)
class NativeFileSelection:
    """Only a native Windows picker supplies an opaque file ticket, NEVER page JSON."""
    ticket: str
    sha256: str
    size_bytes: int
    tenant: str
    principal: str
    chat: str


class Host50Admission:
    """Non-dispatching guard for the already-existing canonical native host.

    Native host MUST protect signing_key, issue_session, installed_capabilities,
    native_consent and native_file_picker from WebView2 Javascript. It must call
    its OWN existing handler AFTER admission, then pass back native ACK evidence.
    """
    def __init__(self, catalog: dict, binding_map: dict, *, signing_key: bytes,
                 allowed_origins: set[str], active_tree: str, capabilities: dict[str, Capability]):
        self.audit = audit_registry(catalog, binding_map)
        if not isinstance(signing_key, bytes) or len(signing_key) < 32:
            raise ValueError("NATIVE_SECRET_REQUIRED")
        if not allowed_origins or any(validate_origin(x) != x for x in allowed_origins):
            raise ValueError("EXACT_NATIVE_ORIGIN_SET_REQUIRED")
        if active_tree != BASE_TREE or self.audit["baselineDrift"]:
            raise Hold("WHOLE_TREE_SOURCELOCK_NOT_RECONCILED")
        self.key = signing_key
        self.origins = frozenset(allowed_origins)
        # Freeze executable policy after the audited catalog has been read.
        # A later catalog/UI mutation must never lower risk, owner, or select rules.
        # Keep separate from reporting rows, which are not authority to dispatch.
        frozen = {}
        for x in self.audit["routes"]:
            frozen[x["routeId"]] = MappingProxyType({
                "taskId": x["taskId"], "routeId": x["routeId"],
                "owner": x["owner"], "risk": x["risk"],
                "sourceBinding": x["sourceBinding"],
                "allowedSettings": frozenset(x["allowedSettings"]),
                "settingPolicy": MappingProxyType({
                    key: MappingProxyType(dict(policy))
                    for key, policy in x["settingPolicy"].items()}),
            })
        self.by_route = MappingProxyType(frozen)
        self.capabilities = dict(capabilities)
        self.pending = {}
        self.pending_deadlines = {}
        # Existing in-process admission state; NOT a second DB/host.
        # Both capacity reservation and ACK consumption must be atomic.
        self._pending_lock = threading.RLock()

    def _reap_pending(self, now: float) -> None:
        """Bound the existing in-process admission store, never a second database."""
        for run_id, deadline in tuple(self.pending_deadlines.items()):
            if deadline <= now:
                self.pending_deadlines.pop(run_id, None)
                self.pending.pop(run_id, None)

    def _seal(self, body: dict) -> str:
        return hmac.new(self.key, canonical(body), hashlib.sha256).hexdigest()

    def issue_session(self, *, tenant: str, principal: str, chat: str,
                      origin: str, scopes: tuple[str,...], sensitive: tuple[str,...],
                      duration_seconds: int = 120) -> Session:
        """NATIVE-ONLY: never expose this constructor to an untrusted page."""
        # Native-only callers still must reject malformed scope frames cleanly.
        if (type(scopes) is not tuple or type(sensitive) is not tuple or
             any(type(x) is not str for x in (*scopes, *sensitive)) or
             origin not in self.origins or not all(isinstance(x,str) and 0<len(x)<=128
             for x in (tenant, principal, chat)) or type(duration_seconds) is not int or
             not 1 <= duration_seconds <= 300 or not set(scopes).issubset(self.by_route) or
             not set(sensitive).issubset(scopes) or not scopes):
            raise Denied("NATIVE_SESSION_ISSUE_DENIED")
        body = dict(tenant=tenant,principal=principal,chat=chat,origin=origin,
                    scopes=tuple(sorted(set(scopes))),sensitive=tuple(sorted(set(sensitive))),
                    expires_unix=int(time.time())+duration_seconds,
                    nonce=secrets.token_hex(16))
        return Session(**body, seal=self._seal(body))

    def _verify_session(self, s: Session, actual_origin: str) -> None:
        if not isinstance(s, Session) or actual_origin not in self.origins or s.origin != actual_origin:
            raise Denied("ORIGIN_OR_SESSION_DENIED")
        body = {k:getattr(s,k) for k in ("tenant","principal","chat","origin",
            "scopes","sensitive","expires_unix","nonce")}
        if (type(s.expires_unix) is not int or s.expires_unix < time.time() or
            not isinstance(s.seal,str) or not hmac.compare_digest(s.seal,self._seal(body))):
            raise Denied("AUTH_INVALID_OR_EXPIRED")

    def _cap(self, row: dict) -> Capability:
        c = self.capabilities.get(row["routeId"])
        if (not isinstance(c, Capability) or not row["sourceBinding"] or
            c.route != row["routeId"] or type(c.owner) is not int or
            c.owner != row["owner"] or
            c.handler != row["sourceBinding"] or c.frozen_tree != BASE_TREE or
            type(c.owner_receipt_sha256) is not str or
            not SHA256.fullmatch(c.owner_receipt_sha256) or
            c.integrated is not True or c.ready is not True):
            raise Hold("NATIVE_OWNER_CAPABILITY_UNVERIFIED")
        return c

    def admit(self, *, session: Session, actual_origin: str, request: dict,
              native_consent=None, native_file_picker=None,
              native_device_permission=None, active_runs: dict | None = None,
              native_option_verifier=None) -> dict:
        self._verify_session(session, actual_origin)
        if not isinstance(request, dict):
            raise Denied("INVALID_REQUEST")
        try:
            raw = canonical(request)
        except (TypeError, ValueError, OverflowError) as exc:
            raise Denied("INVALID_JSON") from exc
        if len(raw) > 131072 or set(request)-{"routeId", "taskId", "intent", "settings", "runId"}:
            raise Denied("REQUEST_TOO_LARGE_OR_EXTRA_KEYS")
        if request.get("intent") != "nox.feature.request":
            raise Denied("UNAUTHORIZED_INTENT")
        route = request.get("routeId")
        row = self.by_route.get(route) if isinstance(route,str) else None
        if not row or request.get("taskId") != row["taskId"]:
            raise Denied("UNKNOWN_OR_MISMATCHED_ROUTE")
        if route not in session.scopes:
            raise Denied("SCOPE_DENIED")
        opts = request.get("settings", {})
        if (not isinstance(opts, dict) or any(k in FORBIDDEN_PAGE_KEYS for k in opts)
            or set(opts)-set(row["allowedSettings"])):
            raise Denied("WEB_TO_NATIVE_PRIVILEGED_ARGUMENT")
        if any(not isinstance(k,str) or not ROUTE.fullmatch(k) or isinstance(v,(dict,list))
               or type(v) not in (str,int,bool) or len(str(v))>256 for k,v in opts.items()):
            raise Denied("UNSAFE_SETTING")
        for key, value in opts.items():
            selected = row["settingPolicy"].get(key)
            if not selected or type(value) is not str:
                raise Denied("SETTING_REQUIRES_APPROVED_SELECT_VALUE")
            if "options" in selected:
                if value not in selected["options"]:
                    raise Denied("STATIC_SELECT_OPTION_DENIED")
            else:
                # Only the already-authenticated native host can check installed
                # models/voices/personas/cores. No page-provided option inventory.
                if not callable(native_option_verifier):
                    raise Hold("NATIVE_SELECT_VERIFIER_MISSING")
                try:
                    verified = native_option_verifier(session,route,key,
                                                      selected["source"],value)
                except Exception as exc:
                    raise Hold("NATIVE_SELECT_VERIFIER_FAILED") from exc
                if verified is not True:
                    raise Denied("UNVERIFIED_NATIVE_SELECT_VALUE")
        cap = self._cap(row)
        with self._pending_lock:
            self._reap_pending(time.monotonic())
            if len(self.pending) >= MAX_PENDING:
                raise Hold("TOO_MANY_UNACKNOWLEDGED_NATIVE_ACTIONS")
        if row["risk"] != "safe" and route not in session.sensitive:
            raise Denied("SENSITIVE_NATIVE_PERMISSION_REQUIRED")
        if row["risk"] == "dangerous" and (
            not callable(native_consent) or native_consent(session,route,request) is not True):
            raise Denied("FRESH_NATIVE_CONSENT_REQUIRED")
        if route in MIC_ROUTES and (
            not callable(native_device_permission) or
            native_device_permission(session,route) is not True):
            raise Denied("NATIVE_MIC_OR_SIP_PERMISSION_REQUIRED")
        file_info = None
        file_ticket_bytes = None
        if route in PICKER_ROUTES:
            if not callable(native_file_picker):
                raise Hold("NATIVE_FILE_PICKER_MISSING")
            file_info = native_file_picker(session,route)
            if (not isinstance(file_info,NativeFileSelection) or
                file_info.tenant != session.tenant or file_info.principal != session.principal or
                file_info.chat != session.chat or
                type(file_info.ticket) is not str or not 16<=len(file_info.ticket)<=256 or
                type(file_info.sha256) is not str or not SHA256.fullmatch(file_info.sha256) or
                type(file_info.size_bytes) is not int or not 0<file_info.size_bytes<=20000000000):
                raise Denied("UNTRUSTED_NATIVE_FILE_SELECTION")
            # A native picker is a trust boundary too. Never let malformed wire
            # text escape as a raw UnicodeEncodeError or create a pending action.
            try:
                file_ticket_bytes = file_info.ticket.encode("utf-8")
            except UnicodeError as exc:
                raise Denied("UNTRUSTED_NATIVE_FILE_SELECTION") from exc
        if route in STOP_ROUTES:
            run_id = request.get("runId")
            if not isinstance(run_id,str):
                raise Denied("STOP_NEEDS_EXACT_RUNID")
            try:
                if str(uuid.UUID(run_id)) != run_id:
                    raise ValueError("Noncanonical UUID")
            except (ValueError, AttributeError) as exc:
                raise Denied("STOP_NEEDS_EXACT_RUNID") from exc
            active = (active_runs or {}).get(run_id)
            if (not isinstance(active,tuple) or len(active)!=4 or
                active[:3] != (session.tenant,session.principal,session.chat) or
                active[3] not in STOP_TARGETS[route]):
                raise Denied("STOP_SCOPE_OR_OWNER_MISMATCH")
        else:
            if "runId" in request:
                raise Denied("WEB_SUPPLIED_RUNID_FORBIDDEN")
        # A native picker, consent dialog, or device prompt can change what is
        # actually installed. Recheck live native-select membership after them.
        # The canonical owner must STILL validate selections at dispatch time.
        for key, value in opts.items():
            selected = row["settingPolicy"][key]
            if "source" in selected:
                try:
                    verified = native_option_verifier(session, route, key,
                                                     selected["source"], value)
                except Exception as exc:
                    raise Hold("NATIVE_SELECT_RECHECK_FAILED") from exc
                if verified is not True:
                    raise Denied("UNVERIFIED_NATIVE_SELECT_VALUE")
        run_id = str(uuid.uuid4())
        ticket = {"runId":run_id,"taskId":row["taskId"],"routeId":route,
                  "owner":row["owner"],"sourceLockTree":BASE_TREE,
                  "ownerReceiptSha256":cap.owner_receipt_sha256,
                  "payloadSha256":hashlib.sha256(raw).hexdigest(),
                  "sessionScopeSha256":digest({"tenant":session.tenant,
                    "principal":session.principal,"chat":session.chat,"origin":session.origin}),
                  "targetRunId":request.get("runId") if route in STOP_ROUTES else None,
                  "fileSha256":file_info.sha256 if file_info else None,
                  # Native opaque ticket is NOT returned to the WebView2 page.
                  "fileTicketSha256":hashlib.sha256(file_ticket_bytes).hexdigest()
                      if file_info else None,
                  "state":"ADMITTED_NOT_EXECUTED","nativeAck":"PENDING"}
        with self._pending_lock:
            # Native checks may call UI/native code and take arbitrary time.
            # A mutable WebView2 request, expired session or revoked capability
            # cannot be admitted based on the earlier pre-callback snapshot.
            self._verify_session(session, actual_origin)
            try:
                still_raw = canonical(request)
            except (TypeError, ValueError, OverflowError) as exc:
                raise Denied("REQUEST_MUTATED_DURING_NATIVE_CHECKS") from exc
            if still_raw != raw:
                raise Denied("REQUEST_MUTATED_DURING_NATIVE_CHECKS")
            if self._cap(row) != cap:
                raise Hold("NATIVE_CAPABILITY_CHANGED_DURING_ADMISSION")
            if route in STOP_ROUTES:
                # STOP can become stale while the request is being admitted.
                # The native executor must still enforce its own atomic STOP.
                still_active = (active_runs or {}).get(request["runId"])
                if (not isinstance(still_active, tuple) or len(still_active) != 4 or
                    still_active[:3] != (session.tenant, session.principal, session.chat) or
                    still_active[3] not in STOP_TARGETS[route]):
                    raise Denied("STOP_SCOPE_OR_OWNER_MISMATCH")
            # Only the existing native owner may execute the exact approved
            # payload; the page request object is never a dispatch authority.
            # Its hash must match payloadSha256 in the eventual sealed ACK.
            self._reap_pending(time.monotonic())
            if len(self.pending) >= MAX_PENDING:
                raise Hold("TOO_MANY_UNACKNOWLEDGED_NATIVE_ACTIONS")
            self.pending[run_id] = ticket
            self.pending_deadlines[run_id] = time.monotonic() + ACK_LEASE_SECONDS
        return dict(ticket)

    def finish(self, run_id: str, native_ack: dict) -> dict:
        """Consume each signed native ACK exactly once, even across threads."""
        with self._pending_lock:
            return self._finish_locked(run_id, native_ack)

    def _finish_locked(self, run_id: str, native_ack: dict) -> dict:
        """ACK only after EXISTING owner handler performed a real action.
        Not a new executor. No page-provided OK can produce completed status.
        """
        ticket=self.pending.get(run_id)
        if not ticket:raise Denied("UNKNOWN_OR_REPLAYED_RUNID")
        now = time.monotonic()
        if self.pending_deadlines.get(run_id, 0) <= now:
            self.pending.pop(run_id, None)
            self.pending_deadlines.pop(run_id, None)
            raise Denied("NATIVE_ACK_LEASE_EXPIRED")
        # Every signed receipt must bind all fields, including explicit nulls.
        # Allowing missing file fields made a validly signed but incomplete
        # "DONE" receipt indistinguishable from a complete native proof.
        if (not isinstance(native_ack,dict) or set(native_ack) != ACK_FIELDS or
            any(not isinstance(k,str) for k in native_ack)):
            raise Denied("NATIVE_ACK_SCHEMA_INVALID")
        sign=native_ack.get("seal")
        body={k:v for k,v in native_ack.items() if k!="seal"}
        try:
            authenticated = isinstance(sign,str) and hmac.compare_digest(sign,self._seal(body))
        except (TypeError, ValueError, OverflowError):
            authenticated = False
        if (not authenticated or
            body.get("runId")!=run_id or body.get("taskId")!=ticket["taskId"] or
            body.get("routeId")!=ticket["routeId"] or
            type(body.get("owner")) is not int or body.get("owner")!=ticket["owner"] or
            body.get("ownerReceiptSha256")!=ticket["ownerReceiptSha256"] or
            body.get("payloadSha256")!=ticket["payloadSha256"] or
            body.get("sourceLockTree")!=ticket["sourceLockTree"] or
            body.get("sessionScopeSha256")!=ticket["sessionScopeSha256"] or
            body.get("targetRunId","MISSING")!=ticket["targetRunId"] or
            body.get("fileSha256")!=ticket["fileSha256"] or
            body.get("fileTicketSha256")!=ticket["fileTicketSha256"] or
            body.get("event") not in ("DONE","STOP_REQUESTED","HOLD","FAILED") or
            (ticket["routeId"] in STOP_ROUTES and body.get("event") == "DONE") or
            (ticket["routeId"] not in STOP_ROUTES and body.get("event") == "STOP_REQUESTED") or
            not isinstance(body.get("proofSha256"),str) or not SHA256.fullmatch(body["proofSha256"])):
            raise Denied("NATIVE_ACK_INVALID")
        result=dict(ticket)
        result["state"]={"DONE":"NATIVE_ACK_EVIDENCED_NOT_E07_ACCEPTED",
          "STOP_REQUESTED":"STOP_REQUESTED_NOT_CONFIRMED_STOPPED",
          "HOLD":"HOLD","FAILED":"FAILED"}[body["event"]]
        result["nativeAck"]="VERIFIED_HMAC"
        result["nativeProofSha256"]=body["proofSha256"]
        del self.pending[run_id]
        self.pending_deadlines.pop(run_id, None)
        return result


# Audit inputs are untrusted *source descriptions*, not executable host files.
# A digest of a second read must never be attached to a different parsed first read.
MAX_AUDIT_SOURCE_BYTES = 8 * 1024 * 1024
REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


def _snapshot_source_bytes(path: Path) -> bytes:
    """Read one bounded regular-file snapshot and keep its provenance together.

    This is a component-level source audit. It is NOT a Windows SourceLock or
    an atomic native-host deployment attestation.
    """
    try:
        # Include every existing ancestor: on Windows a directory junction is
        # not necessarily reported by Path.is_symlink() on older Python builds.
        for ancestor in (path, *path.parents):
            st = ancestor.lstat()
            if stat.S_ISLNK(st.st_mode) or (getattr(st, "st_file_attributes", 0) & REPARSE_POINT):
                raise Hold("AUDIT_SOURCE_REPARSE_POINT")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as source:
            opened = os.fstat(source.fileno())
            if (not stat.S_ISREG(opened.st_mode) or
                (getattr(opened, "st_file_attributes", 0) & REPARSE_POINT) or
                opened.st_size > MAX_AUDIT_SOURCE_BYTES):
                raise Hold("AUDIT_SOURCE_NOT_BOUNDED_REGULAR_FILE")
            data = source.read(MAX_AUDIT_SOURCE_BYTES + 1)
            if len(data) > MAX_AUDIT_SOURCE_BYTES:
                raise Hold("AUDIT_SOURCE_TOO_LARGE")
            current = path.lstat()
            if ((opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino) or
                stat.S_ISLNK(current.st_mode) or
                (getattr(current, "st_file_attributes", 0) & REPARSE_POINT)):
                raise Hold("AUDIT_SOURCE_CHANGED_DURING_READ")
        return data
    except Hold:
        raise
    except (OSError, ValueError) as exc:
        raise Hold("INVALID_SOURCE_FILE") from exc


def _strict_json_object_pairs(pairs: list[tuple[str, object]]) -> dict:
    out = {}
    for key, value in pairs:
        if key in out:
            raise Hold("AUDIT_DUPLICATE_JSON_KEY")
        out[key] = value
    return out


def _reject_nonfinite_source_number(token: str) -> object:
    """Python json.loads accepts NaN/Infinity by default; source JSON must not."""
    raise Hold("AUDIT_NONFINITE_JSON_CONSTANT")


def run_read_only_audit(catalog_path: str, bindings_path: str) -> dict:
    src1, src2 = Path(catalog_path), Path(bindings_path)
    # Exactly one byte sequence is parsed AND hashed for each provenance entry.
    catalog_bytes = _snapshot_source_bytes(src1)
    binding_bytes = _snapshot_source_bytes(src2)
    try:
        a = json.loads(catalog_bytes.decode("utf-8"), object_pairs_hook=_strict_json_object_pairs,
                       parse_constant=_reject_nonfinite_source_number)
        b = json.loads(binding_bytes.decode("utf-8"), object_pairs_hook=_strict_json_object_pairs,
                       parse_constant=_reject_nonfinite_source_number)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise Hold("AUDIT_INVALID_UTF8_JSON") from exc
    if not isinstance(a, dict) or not isinstance(b, dict):
        raise Hold("AUDIT_REQUIRES_JSON_OBJECTS")
    result = audit_registry(a, b)
    result["catalogSha256"] = hashlib.sha256(catalog_bytes).hexdigest()
    result["bindingMapSha256"] = hashlib.sha256(binding_bytes).hexdigest()
    return result


if __name__ == "__main__":
    import sys
    if len(sys.argv)!=3:
        raise SystemExit("Usage: admission.py <existing-PACK01-catalog.json> <existing-owner-binding-map.json>")
    print(json.dumps(run_read_only_audit(sys.argv[1],sys.argv[2]),ensure_ascii=False,indent=2))
