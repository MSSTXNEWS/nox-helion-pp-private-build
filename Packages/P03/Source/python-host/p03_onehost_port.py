"""NOX P03 owner-3 adapter for the EXISTING Python/P02 native host.

No new HTTP transport, downloader, database, subprocess, web server or model weights.
Only the trusted host passes owner services/NativeSession; unknown actions HOLD.
"""
from __future__ import annotations

import json
import math
from collections.abc import Mapping
import re
from pathlib import Path
from typing import Any, Callable

ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,99}$")
TAG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}(?::[A-Za-z0-9][A-Za-z0-9._-]{0,127})?$")
READ_ROUTES = ("models.catalog", "models.installed", "models.digest")
OWNER_ROUTES = {
    "models.pull": "pull",
    "models.gguf.import": "import_gguf",
    "models.queue": "queue",
    "models.cancel": "cancel",
    "models.retry": "retry",
    "models.preflight": "preflight",
}
SENSITIVE = frozenset(("models.pull", "models.gguf.import", "models.cancel", "models.retry"))
ROUTES = frozenset(READ_ROUTES) | frozenset(OWNER_ROUTES)

class P03PortHold(RuntimeError):
    """The actual native owner service or required proof is unavailable."""

class P03PortDenied(PermissionError):
    """Caller is not a trusted native principal or lacks out-of-band consent."""

class P03OneHostPort:
    @staticmethod
    def _command_json(args: dict) -> str:
        """Pin bounded JSON content, without coercing keys or arbitrary objects."""
        if type(args) is not dict:
            raise P03PortDenied("Bounded JSON owner3 command required")
        pending = [(args, 0)]
        count = 0
        while pending:
            value, depth = pending.pop()
            count += 1
            if depth > 32 or count > 4096:
                raise P03PortDenied("Owner3 command nesting/size limit")
            if type(value) is dict:
                if len(value) > 4096 or any(type(k) is not str or len(k) > 65536 for k in value):
                    raise P03PortDenied("Owner3 JSON object keys required")
                pending.extend((v, depth + 1) for v in value.values())
            elif type(value) is list:
                if len(value) > 4096:
                    raise P03PortDenied("Owner3 command size limit")
                pending.extend((v, depth + 1) for v in value)
            elif type(value) is str:
                if len(value) > 65536:
                    raise P03PortDenied("Owner3 command size limit")
            elif value is not None and type(value) not in (bool, int, float):
                raise P03PortDenied("JSON owner3 command values required")
        try:
            encoded = json.dumps(args, ensure_ascii=False, sort_keys=True,
                                 separators=(",", ":"), allow_nan=False)
            if len(encoded.encode("utf-8")) > 65536:
                raise ValueError("command size")
        except (TypeError, ValueError, UnicodeError, RecursionError):
            raise P03PortDenied("Bounded finite JSON owner3 command required") from None
        return encoded

    @staticmethod
    def _scope_token(session: object) -> tuple:
        # Copy mutable route sets so a callback cannot revoke/switch identity
        # after authorization but before the original queue receives a command.
        return tuple(getattr(session, key, None) for key in ("tenant", "principal", "chat_id")) + tuple(
            frozenset(value) if isinstance(value, (set, frozenset)) else None
            for value in (getattr(session, "allowed", None), getattr(session, "private_approved", None)))

    def __init__(self, existing_p02_ollama: object, *,
                 owner3_backend: object | None = None,
                 native_approve: Callable[[object, str, dict], bool] | None = None,
                 catalog_path: str | Path | None = None):
        if not callable(getattr(existing_p02_ollama, "models", None)):
            raise ValueError("Use existing P02 OllamaClient.models(), not another downloader")
        self.ollama = existing_p02_ollama
        self.backend = owner3_backend
        self.native_approve = native_approve
        path = Path(catalog_path) if catalog_path else Path(__file__).with_name("catalog30.discovery.json")
        self.family_cards = self._validate_catalog(path)

    @staticmethod
    def _validate_catalog(path: Path) -> tuple[dict, ...]:
        # Model discovery is immutable until owner review. No source URL means weights.
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 100_000:
            raise P03PortHold("No safe pinned owner3 discovery catalog")
        # Ambiguous JSON or malformed roots must HOLD, never crash/approve a model.
        # Python's default decoder silently accepts duplicate keys and NaN.
        def unique_object(pairs):
            obj = {}
            for key, value in pairs:
                if key in obj:
                    raise P03PortHold("P03 catalog duplicate JSON key")
                obj[key] = value
            return obj

        def reject_constant(value):
            raise P03PortHold("P03 catalog invalid JSON numeric constant")

        def finite_float(value):
            number = float(value)
            if not math.isfinite(number):
                raise P03PortHold("P03 catalog non-finite JSON number")
            return number

        try:
            # Enforce the actual read cap even if the file grows after stat().
            with path.open("rb") as stream:
                raw = stream.read(100_001)
            if len(raw) > 100_000:
                raise P03PortHold("P03 catalog exceeds owner size cap")
            doc = json.loads(raw.decode("utf-8"),
                             object_pairs_hook=unique_object,
                             parse_constant=reject_constant, parse_float=finite_float)
        except (OSError, UnicodeError, ValueError, RecursionError) as exc:
            raise P03PortHold("Malformed/unsafe P03 catalog JSON") from exc
        if not isinstance(doc, dict):
            raise P03PortHold("P03 catalog root must be a JSON object")
        if doc.get("schema") != "NOX-P03-PYTHON-ONEHOST-CATALOG-V1" or doc.get("sourceType") != "discovery_only":
            raise P03PortHold("P03 catalog schema drift")
        data = doc.get("models")
        if not isinstance(data, list) or len(data) != 30:
            raise P03PortHold("Approved 30 family discovery cards missing")
        result, used = [], set()
        for item in data:
            if not isinstance(item, dict):
                raise P03PortHold("Malformed catalog card")
            ident = item.get("id")
            if not isinstance(ident, str) or not ID.fullmatch(ident) or ident in used:
                raise P03PortHold("Duplicated/untrusted model family")
            if (not isinstance(item.get("name"), str) or len(item["name"]) > 128
                    or item.get("url") != "https://ollama.com/library/" + ident
                    or item.get("reviewStatus") != "REVIEW_REQUIRED"
                    or item.get("downloadEligible") is not False):
                raise P03PortHold("Unreviewed catalog card cannot enable a download")
            used.add(ident)
            result.append(dict(item))
        return tuple(result)

    def _ensure_native_scope(self, session: object, route: str, args: dict):
        # Strings and mappings are NOT native route sets: membership would
        # authorize substrings/keys; None and integers would raise TypeError.
        allowed = getattr(session, "allowed", None)
        if (not isinstance(args, dict) or not isinstance(route, str)
                or route not in ROUTES
                or not all(isinstance(getattr(session, k, None), str)
                           and 0 < len(getattr(session, k)) <= 128
                           for k in ("tenant", "principal", "chat_id"))
                or not isinstance(allowed, (set, frozenset))
                or any(not isinstance(value, str) for value in allowed)
                or route not in allowed):
            raise P03PortDenied("Authenticated native owner3 route scope required")
        if route in SENSITIVE:
            approved = getattr(session, "private_approved", None)
            if (not isinstance(approved, (set, frozenset))
                    or any(not isinstance(value, str) for value in approved)
                    or route not in approved
                    or not callable(self.native_approve)):
                raise P03PortDenied("Fresh out-of-band native approval required")
            # A failing native callback must HOLD before any queue operation.
            # Suppress private callback diagnostics; never infer permission.
            try:
                consent = self.native_approve(session, route, args)
            except (P03PortDenied, P03PortHold):
                raise
            except Exception:
                raise P03PortHold("Native consent provider unavailable") from None
            if consent is not True:
                raise P03PortDenied("Fresh out-of-band native approval required")

    def catalog(self, session: object, args: dict) -> dict:
        self._ensure_native_scope(session, "models.catalog", args)
        search = args.get("query", "")
        if not isinstance(search, str) or len(search) > 120:
            raise P03PortDenied("Bounded search required")
        q = search.casefold()
        return {"models": [dict(x) for x in self.family_cards
                           if q in x["name"].casefold() or q in x["id"].casefold()],
                "downloadEligible": False, "source": "P03 discovery only"}

    def installed(self, session: object, args: dict) -> dict:
        self._ensure_native_scope(session, "models.installed", args)
        tags = self._installed_tags()
        return {"models": [{"tag": t, "installed": True, "digest": None} for t in tags],
                "digestVerified": False, "source": "existing P02 OllamaClient.models"}

    def _installed_tags(self) -> list[str]:
        # The health advertisement and actual read use identical validation.
        try:
            tags = self.ollama.models()  # EXISTING P02 transport and /api/tags
        except Exception as exc:
            raise P03PortHold("Existing local Ollama unavailable") from exc
        if (not isinstance(tags, list) or len(tags) > 4096
                or any(not isinstance(t, str) or not TAG.fullmatch(t) for t in tags)
                or len(tags) != len(set(tags))):
            raise P03PortHold("Installed model evidence invalid")
        return tags

    def digest(self, session: object, args: dict) -> dict:
        """Read Ollama-reported local manifest digest using the EXISTING P02 transport.

        A reported digest is neither independently hashed weights nor licensing
        evidence; this method never calls Pull, downloads files or claims rights.
        """
        self._ensure_native_scope(session, "models.digest", args)
        tag = args.get("modelTag")
        if not isinstance(tag, str) or not TAG.fullmatch(tag):
            raise P03PortDenied("Exact installed model tag required")
        raw_open = getattr(self.ollama, "_open", None)
        if not callable(raw_open):
            raise P03PortHold("No owner2 existing metadata reader")
        try:
            with raw_open("/api/tags") as response:
                raw = response.read(2 * 1024 * 1024 + 1)
            if len(raw) > 2 * 1024 * 1024:
                raise P03PortHold("Ollama metadata exceeds owner2 size cap")
            # R16: Ollama metadata is evidence, not an ambiguously decoded JSON claim.
            def unique_object(pairs):
                obj = {}
                for key, value in pairs:
                    if key in obj:
                        raise P03PortHold("Duplicate Ollama metadata JSON key")
                    obj[key] = value
                return obj

            def reject_constant(_value):
                raise P03PortHold("Invalid Ollama metadata JSON constant")

            def finite_float(value):
                number = float(value)
                if not math.isfinite(number):
                    raise P03PortHold("Non-finite Ollama metadata JSON number")
                return number

            data = json.loads(raw, object_pairs_hook=unique_object,
                              parse_constant=reject_constant, parse_float=finite_float)
        except P03PortHold:
            raise
        except Exception as exc:
            raise P03PortHold("Existing P02 Ollama metadata unavailable") from exc
        models = data.get("models") if isinstance(data, dict) else None
        if not isinstance(models, list) or len(models) > 4096:
            raise P03PortHold("Invalid Ollama metadata models")
        matching = []
        for item in models:
            if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                raise P03PortHold("Malformed Ollama metadata row")
            name = item["name"]
            if not TAG.fullmatch(name):
                raise P03PortHold("Malformed local model tag")
            if name == tag:
                matching.append(item)
        if len(matching) != 1:
            raise P03PortHold("Model absent or ambiguous in /api/tags")
        reported = matching[0].get("digest")
        if reported is not None:
            if (not isinstance(reported, str) or not re.fullmatch(
                    r"sha256:[a-fA-F0-9]{64}", reported)):
                raise P03PortHold("Invalid Ollama manifest digest")
            reported = reported.lower()
        return {
            "modelTag": tag,
            "ollamaReportedManifestDigest": reported,
            "independentlyVerified": False,
            "licenseVerified": False,
            "source": "existing P02 transport /api/tags",
        }

    def execute_backend(self, session: object, route: str, args: dict) -> Any:
        command_json = self._command_json(args)
        args = json.loads(command_json)  # detach caller-owned nested payloads
        scope = self._scope_token(session)
        self._ensure_native_scope(session, route, args)
        if self._command_json(args) != command_json or self._scope_token(session) != scope:
            raise P03PortDenied("Native consent command or identity changed")
        method_name = OWNER_ROUTES.get(route)
        if not method_name:
            raise P03PortHold("Owner3 operation not bound")
        backend = self.backend
        try:
            func = getattr(backend, method_name, None)
            probe = getattr(backend, "available", None)
        except Exception:
            raise P03PortHold("Owner3 backend contract unavailable") from None
        if not callable(func) or not callable(probe):
            raise P03PortHold("Actual owner3 backend and health proof required")
        try:
            if probe() is not True:
                raise P03PortHold("Owner3 backend is not available")
        except P03PortHold:
            raise
        except Exception as exc:
            raise P03PortHold("Owner3 backend health unavailable") from exc
        if self._command_json(args) != command_json or self._scope_token(session) != scope:
            raise P03PortDenied("Native consent command or identity changed")
        # The original backend, not this port, owns files, digests, receipts and queue.
        # No raw worker exception may escape as a false native success ACK.
        try:
            # No reference retained by approval/health callbacks is handed to
            # the queue; execute exactly the command whose consent was checked.
            return func(session, json.loads(command_json))
        except (P03PortDenied, P03PortHold):
            raise
        except Exception:
            raise P03PortHold("Owner3 backend operation unavailable") from None

    def register(self, dispatcher: object, bound_port_type: type, *, receipt: str) -> frozenset[str]:
        if not isinstance(receipt, str) or not receipt.strip():
            raise P03PortHold("SourceLock-bound owner3 receipt required")
        # Validate the complete owner3 route set BEFORE the first mutation.
        # A partially registered Models menu would misrepresent capabilities
        # and could clash with the separate PACK01 P03OwnerPack donor.
        pending = [
            ("models.catalog", self.catalog, lambda: True),
            ("models.installed", self.installed, self._local_ready),
            ("models.digest", self.digest, self._metadata_ready),
        ]
        if self.backend is not None:
            for route, method in OWNER_ROUTES.items():
                if route in SENSITIVE and not callable(self.native_approve):
                    continue
                if not callable(getattr(self.backend, method, None)):
                    continue
                pending.append((
                    route,
                    lambda session, payload, r=route: self.execute_backend(session, r, payload),
                    self._backend_ready,
                ))
        host_routes = getattr(dispatcher, "routes", None)
        ports = getattr(dispatcher, "ports", None)
        if not isinstance(host_routes, Mapping) or not isinstance(ports, dict):
            raise P03PortHold("Existing PACK01 host ports/owner map required")
        ids = [route for route, _, _ in pending]
        if len(ids) != len(set(ids)) or any(
                not isinstance(host_routes.get(route), Mapping)
                or type(host_routes[route].get("owner")) is not int
                or host_routes[route]["owner"] != 3 or route in ports
                for route in ids):
            raise P03PortHold("P03 route ownership collision: register none")
        # Prebuild all native ports before mutating the shared dispatcher.
        staged = [(route, bound_port_type(callback, ready, receipt, 3))
                  for route, callback, ready in pending]
        try:
            for route, port in staged:
                # NoxPackHost.bind enforces single owner and duplicate denial.
                dispatcher.bind(route, port)
        except Exception as exc:
            # A bind implementation may write a port and then raise. Remove
            # ONLY our exact objects; never delete someone else's newer port.
            for route, port in reversed(staged):
                if ports.get(route) is port:
                    del ports[route]
            raise P03PortHold("Owner3 registration rolled back after host rejection") from exc
        return frozenset(ids)

    def _local_ready(self) -> bool:
        try:
            self._installed_tags()
            return True
        except Exception:
            return False

    def _metadata_ready(self) -> bool:
        return callable(getattr(self.ollama, "_open", None)) and self._local_ready()

    def _backend_ready(self) -> bool:
        try:
            return callable(getattr(self.backend, "available", None)) and self.backend.available() is True
        except Exception:
            return False

    @staticmethod
    def _bind(dispatcher, port_type, route, call, available, receipt):
        routes = getattr(dispatcher, "routes", None)
        if (not isinstance(routes, Mapping)
                or not isinstance(routes.get(route), Mapping)
                or type(routes[route].get("owner")) is not int
                or routes[route]["owner"] != 3):
            raise P03PortHold("Owner-route map mismatch")
        dispatcher.bind(route, port_type(call, available, receipt, 3))
