"""One-host adapter to the EXISTING ComfyImagePort, not a ComfyUI clone.

The official ComfyUI API's /prompt and /history stay in comfy_bridge.py.
The user/UI cannot choose endpoint, workflow, model bytes or trusted disk paths.
"""
from __future__ import annotations

from typing import Callable


class ImageHold(RuntimeError):
    pass


class ImageDenied(PermissionError):
    pass


class P04ComfyOwnerPort:
    def __init__(self, existing_port, *, select_approved_request: Callable,
                 native_permission: Callable, native_stop: Callable,
                 native_backend_ready: Callable):
        if not all(callable(fn) for fn in (select_approved_request, native_permission,
                                           native_stop, native_backend_ready)):
            raise ImageHold("NATIVE_COMFY_CALLBACKS_REQUIRED")
        if not callable(getattr(existing_port, "prepare", None)) or not callable(getattr(existing_port, "submit", None)):
            raise ImageHold("ORIGINAL_COMFY_IMAGE_PORT_REQUIRED")
        self.port = existing_port
        self.select = select_approved_request
        self.permission = native_permission
        self.stop = native_stop
        self.ready = native_backend_ready

    def available(self) -> bool:
        try:
            return self.ready() is True and self.stop() is False
        except Exception:
            return False

    def generate(self, session, payload: dict) -> dict:
        if type(payload) is not dict or payload:
            raise ImageDenied("WEB_PAGE_MAY_NOT_CHOOSE_IMAGE_WORKFLOW")
        if self.stop() is not False or self.ready() is not True:
            raise ImageHold("LOCAL_COMFY_BACKEND_OR_STOP_HOLD")
        if self.permission(session, "images.generate") is not True:
            raise ImageDenied("NATIVE_IMAGE_CONSENT_REQUIRED")
        selected = self.select(session)
        if type(selected) is not dict or set(selected) != {
            "workflow", "workflow_digest", "prompt_node", "prompt", "model", "client_id"
        }:
            raise ImageHold("APPROVED_COMFY_NATIVE_SELECTION_REQUIRED")
        # Existing ComfyImagePort verifies installed model, rights, graph digest,
        # prompt limits and exact trusted text node. No second image generator.
        prepared = self.port.prepare(**selected, native_authorized=True, rights_confirmed=True)
        if (self.stop() is not False or self.ready() is not True or
                self.permission(session, "images.generate") is not True):
            raise ImageDenied("NATIVE_IMAGE_CONSENT_REVOKED")
        result = self.port.submit(prepared, native_authorized=True)
        if not isinstance(result, dict) or result.get("status") != "QUEUED_NOT_RENDERED" or not isinstance(result.get("prompt_id"), str):
            raise ImageHold("LOCAL_COMFY_DID_NOT_QUEUE")
        return {"status": "QUEUED_NOT_RENDERED", "prompt_id": result["prompt_id"],
                "accepted": False}
