"""NOX P03 owner-3 adapter for the EXISTING Python/P02 native host.

No new HTTP transport, downloader, database, subprocess, web server or model weights.
Only the trusted host passes owner services/NativeSession; unknown actions HOLD.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,99}$")
TAG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}(?::[A-Za-z0-9][A-Za-z0-9._-]{0,127})?$")
READ_ROUTES = ("models.catalog", "models.installed")
OWNER_ROUTES = {
    "models.pull": "pull",
    "models.gguf.import": "import_gguf",
    "models.queue": "queue",
    "models.cancel": "cancel",
    "models.retry": "retry",
    "models.digest": "digest",
    "models.preflight": "preflight",
}
SENSITIVE = frozenset(("models.pull", "models.gguf.import", "models.cancel", "models.retry"))
ROUTES = frozenset(READ_ROUTES) | frozenset(OWNER_ROUTES)

class P03PortHold(RuntimeError):
    """The actual native owner service or required proof is unavailable."""

class P03PortDenied(PermissionError):
    """Caller is not a trusted native principal or lacks out-of-band consent."""

class P03OneHostPort:
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
        doc = json.loads(path.read_text(encoding="utf-8"))
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
        if (not isinstance(args, dict) or route not in ROUTES
                or not all(isinstance(getattr(session, k, None), str)
                           and 0 < len(getattr(session, k)) <= 128
                           for k in ("tenant", "principal", "chat_id"))
                or route not in getattr(session, "allowed", ())):
            raise P03PortDenied("Authenticated native owner3 route scope required")
        if route in SENSITIVE:
            if (route not in getattr(session, "private_approved", ())
                    or not callable(self.native_approve)
                    or self.native_approve(session, route, args) is not True):
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
        try:
            tags = self.ollama.models()  # EXISTING P02 transport and /api/tags
        except Exception as exc:
            raise P03PortHold("Existing local Ollama unavailable") from exc
        if (not isinstance(tags, list) or len(tags) > 4096
                or any(not isinstance(t, str) or not TAG.fullmatch(t) for t in tags)
                or len(tags) != len(set(tags))):
            raise P03PortHold("Installed model evidence invalid")
        return {"models": [{"tag": t, "installed": True, "digest": None} for t in tags],
                "digestVerified": False, "source": "existing P02 OllamaClient.models"}

    def execute_backend(self, session: object, route: str, args: dict) -> Any:
        self._ensure_native_scope(session, route, args)
        method_name = OWNER_ROUTES.get(route)
        if not method_name:
            raise P03PortHold("Owner3 operation not bound")
        backend = self.backend
        func = getattr(backend, method_name, None)
        probe = getattr(backend, "available", None)
        if not callable(func) or not callable(probe):
            raise P03PortHold("Actual owner3 backend and health proof required")
        try:
            if probe() is not True:
                raise P03PortHold("Owner3 backend is not available")
        except P03PortHold:
            raise
        except Exception as exc:
            raise P03PortHold("Owner3 backend health unavailable") from exc
        # The original backend, not this port, owns files, digests, receipts and queue.
        return func(session, args)

    def register(self, dispatcher: object, bound_port_type: type, *, receipt: str) -> frozenset[str]:
        if not isinstance(receipt, str) or not receipt.strip():
            raise P03PortHold("SourceLock-bound owner3 receipt required")
        bound = set()
        for route, callback, ready in (
            ("models.catalog", self.catalog, lambda: True),
            ("models.installed", self.installed, self._local_ready),
        ):
            self._bind(dispatcher, bound_port_type, route, callback, ready, receipt)
            bound.add(route)
        if self.backend is not None:
            for route, method in OWNER_ROUTES.items():
                if not callable(getattr(self.backend, method, None)):
                    continue
                self._bind(dispatcher, bound_port_type, route,
                           lambda session, payload, r=route: self.execute_backend(session, r, payload),
                           self._backend_ready, receipt)
                bound.add(route)
        return frozenset(bound)

    def _local_ready(self) -> bool:
        try:
            return isinstance(self.ollama.models(), list)
        except Exception:
            return False

    def _backend_ready(self) -> bool:
        try:
            return callable(getattr(self.backend, "available", None)) and self.backend.available() is True
        except Exception:
            return False

    @staticmethod
    def _bind(dispatcher, port_type, route, call, available, receipt):
        if not isinstance(getattr(dispatcher, "routes", None), dict) or (
                dispatcher.routes.get(route, {}).get("owner") != 3):
            raise P03PortHold("Owner-route map mismatch")
        dispatcher.bind(route, port_type(call, available, receipt, 3))
