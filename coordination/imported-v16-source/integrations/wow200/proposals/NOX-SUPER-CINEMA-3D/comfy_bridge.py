"""NOX HELION optional trusted-native adapter for one EXISTING ComfyUI on 127.0.0.1.
No server, duplicate model, weight download, content-filter override or training.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import copy
import json
import re
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8188"
HASH = re.compile(r"^[a-f0-9]{64}$", re.I)
ID = re.compile(r"^[A-Za-z0-9._:-]{2,128}$")
MAX_WORKFLOW = 250_000
MAX_PROMPT = 8_000

class Hold(RuntimeError):
    """Required backend, source, installed weights, or authorization unavailable."""

class Denied(PermissionError):
    """The trusted host has not authorized this generation request."""

@dataclass(frozen=True)
class ApprovedModel:
    model_id: str
    source_sha256: str
    license: str
    installed: bool
    rights_approved: bool

    def check(self):
        if (not ID.fullmatch(self.model_id or "")
            or not HASH.fullmatch(self.source_sha256 or "")
            or not self.license or len(self.license) > 100
            or self.license == "REVIEW_REQUIRED"
            or not self.installed or not self.rights_approved):
            raise Hold("INSTALLED_LICENSED_MODEL_REQUIRED")

class LocalTransport:
    """No redirects to public/other servers. Never bind on 0.0.0.0."""
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            raise Hold("COMFY_REDIRECT_DENIED")

    def __init__(self, timeout=20):
        self.timeout = timeout
        self.opener = urllib.request.build_opener(self.NoRedirect())

    def request(self, method, route, payload=None):
        if not re.fullmatch(r"/(?:prompt|history/[0-9a-f-]{8,40}|queue)", route):
            raise Denied("UNAPPROVED_COMFY_ROUTE")
        raw = None if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
        if raw is not None and len(raw) > 300_000:
            raise Denied("WORKFLOW_REQUEST_TOO_LARGE")
        req = urllib.request.Request(BASE + route, data=raw, method=method)
        if raw is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with self.opener.open(req, timeout=self.timeout) as stream:
                data = stream.read(1_000_001)
                if len(data) > 1_000_000:
                    raise Hold("COMFY_REPLY_TOO_LARGE")
                return json.loads(data)
        except (OSError, ValueError, urllib.error.HTTPError) as exc:
            raise Hold("LOCAL_COMFY_NOT_READY") from exc

class ComfyImagePort:
    """Native host owns this instance. User session never creates a transport."""
    def __init__(self, transport=None):
        self.transport = transport or LocalTransport()

    def prepare(self, *, workflow: dict, workflow_digest: str, prompt_node: str,
                prompt: str, model: ApprovedModel, native_authorized: bool,
                rights_confirmed: bool, client_id: str) -> dict:
        if not native_authorized or not rights_confirmed:
            raise Denied("NATIVE_PERMISSION_AND_RIGHTS_REQUIRED")
        if not isinstance(model, ApprovedModel):
            raise Hold("MODEL_ATTESTATION_REQUIRED")
        model.check()
        if (not isinstance(workflow, dict) or not workflow
            or len(workflow) > 200 or not HASH.fullmatch(workflow_digest or "")):
            raise Hold("APPROVED_WORKFLOW_REQUIRED")
        canonical = json.dumps(workflow, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        if len(canonical.encode("utf-8")) > MAX_WORKFLOW:
            raise Denied("WORKFLOW_TOO_LARGE")
        if sha256(canonical.encode("utf-8")).hexdigest() != workflow_digest.lower():
            raise Hold("WORKFLOW_SOURCE_HASH_MISMATCH")
        if (not isinstance(prompt, str) or not prompt.strip()
            or len(prompt) > MAX_PROMPT or "\x00" in prompt):
            raise Denied("INVALID_PROMPT")
        if not ID.fullmatch(client_id or ""):
            raise Denied("INVALID_CLIENT_ID")
        if (not isinstance(prompt_node, str) or prompt_node not in workflow
            or not isinstance(workflow[prompt_node], dict)
            or not isinstance(workflow[prompt_node].get("inputs"), dict)
            or not isinstance(workflow[prompt_node]["inputs"].get("text"), str)):
            raise Hold("TRUSTED_TEXT_NODE_REQUIRED")
        # The host must independently approve all actual workflow nodes and their model files.
        # The digest binds exactly this previously approved API-format graph.
        approved = copy.deepcopy(workflow)
        approved[prompt_node]["inputs"]["text"] = prompt.strip()
        return {"prompt": approved, "client_id": client_id}

    def submit(self, prepared, *, native_authorized: bool):
        if native_authorized is not True:
            raise Denied("NATIVE_APPROVAL_REQUIRED")
        if not isinstance(prepared, dict) or set(prepared) != {"prompt", "client_id"}:
            raise Denied("INVALID_PREPARED_WORKFLOW")
        answer = self.transport.request("POST", "/prompt", prepared)
        if not isinstance(answer, dict) or not isinstance(answer.get("prompt_id"), str):
            raise Hold("COMFY_DID_NOT_ACCEPT")
        pid = answer["prompt_id"]
        if not re.fullmatch(r"[0-9a-f-]{8,40}", pid, re.I):
            raise Hold("INVALID_COMFY_PROMPT_ID")
        return {"status": "QUEUED_NOT_RENDERED", "prompt_id": pid}

    def result(self, prompt_id):
        if not isinstance(prompt_id, str) or not re.fullmatch(r"[0-9a-f-]{8,40}", prompt_id, re.I):
            raise Denied("INVALID_PROMPT_ID")
        history = self.transport.request("GET", "/history/" + prompt_id)
        record = history.get(prompt_id) if isinstance(history, dict) else None
        if not isinstance(record, dict):
            return {"status": "NOT_COMPLETE", "images": []}
        if record.get("status", {}).get("status_str") != "success":
            return {"status": "NOT_COMPLETE", "images": []}
        assets = []
        for block in record.get("outputs", {}).values():
            if not isinstance(block, dict):
                continue
            for image in block.get("images", []):
                name = image.get("filename")
                if (isinstance(name, str) and len(name) < 200
                    and name.lower().endswith((".png", ".webp", ".jpg", ".jpeg"))
                    and "/" not in name and "\\" not in name):
                    assets.append({"filename": name, "type": image.get("type", "output")})
        return {"status": "RENDERED_IN_COMFY_NOT_IMPORTED", "images": assets[:12]}
