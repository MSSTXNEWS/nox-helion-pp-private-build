"""NOX V16 native-guarded local ComfyUI video generation.
Single existing ComfyUI queue, no new server, external upload, downloads or training.
"""
from dataclasses import dataclass
from pathlib import Path
import json
import re
from comfy_bridge import ApprovedModel, ComfyImagePort, Denied, Hold

CATALOG = Path(__file__).with_name("video_models.json")
NAME = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,159}$", re.I)
SHA = re.compile(r"^[a-f0-9]{64}$", re.I)
VIDEO_EXT = (".mp4", ".webm", ".gif")
OPERATIONS = frozenset(("t2v", "i2v", "v2v", "extend", "a2v"))

def read_catalog():
    info = json.loads(CATALOG.read_text(encoding="utf-8"))
    if info.get("schema") != "NOX_VIDEO_MODEL_CATALOG_V1":
        raise Hold("INVALID_VIDEO_CATALOG")
    rows = info.get("models")
    if not isinstance(rows, list) or len(rows) < 8:
        raise Hold("VIDEO_CATALOG_INCOMPLETE")
    if len({r.get("id") for r in rows}) != len(rows):
        raise Hold("VIDEO_CATALOG_DUPLICATES")
    return {r["id"]: r for r in rows}

@dataclass(frozen=True)
class NativeVideoPreflight:
    """Constructed by the native GPU guardian, NOT by untrusted browser JS."""
    model_id: str
    workflow_sha256: str
    model_sha256: str
    license_verified: bool
    installed: bool
    trusted_native: bool
    user_consent: bool
    current_gpu_vram_free_gb: float
    measured_required_vram_gb: float
    gpu_training_active: bool

    def check(self, model_id, workflow_sha256):
        if (not self.trusted_native or not self.user_consent
            or not self.installed or not self.license_verified
            or self.gpu_training_active or self.model_id != model_id
            or not SHA.fullmatch(self.model_sha256 or "")
            or self.workflow_sha256 != workflow_sha256
            or not SHA.fullmatch(self.workflow_sha256 or "")):
            raise Hold("NATIVE_SOURCE_GPU_PERMISSION_HOLD")
        for number in (self.current_gpu_vram_free_gb, self.measured_required_vram_gb):
            if not isinstance(number, (float, int)) or isinstance(number, bool):
                raise Hold("GPU_VRAM_NOT_MEASURED")
            if not 0 < number < 4096:
                raise Hold("GPU_VRAM_NOT_MEASURED")
        if self.current_gpu_vram_free_gb < self.measured_required_vram_gb:
            raise Hold("NOT_ENOUGH_FREE_GPU_VRAM")

class ComfyVideoPort(ComfyImagePort):
    """Only E06 native host may instantiate and supply preflight."""
    def __init__(self, transport=None):
        super().__init__(transport)
        self.models = read_catalog()

    def visible_models(self):
        # Presentation must never change catalog HOLD into "installed".
        return [{"id": r["id"], "name": r["name"], "license": r["license"],
                 "operations": tuple(r["operations"]), "status": "CATALOG_ONLY_HOLD"}
                for r in self.models.values()]

    def demo_model(self, model_id, operation=None):
        """Show metadata in a demo UI without weights, network, GPU, or execution.

        Displaying a public model name is not an endorsement of its license.
        Real generation remains subject to the separate native preflight.
        """
        row = self.models.get(model_id)
        if row is None:
            raise Denied("UNKNOWN_DEMO_MODEL")
        if operation is not None and operation not in row.get("operations", []):
            raise Denied("UNSUPPORTED_DEMO_OPERATION")
        return {
            "id": row["id"], "name": row["name"],
            "operations": tuple(row["operations"]),
            "source": row["source"],
            "mode": "DEMO_CATALOG_ONLY",
            "status": "PREVIEW_ONLY_NO_INFERENCE",
            "modelInstalled": False, "weightsDownloaded": False,
            "gpuUsed": False, "networkRequest": False,
            "licenseReviewBeforeExecution": True,
            "checkpointReady": False,
        }

    def demo_catalog(self):
        """All candidate options can be inspected in the prototype, regardless of
        their *commercial* clearance state. Does not change execution gating.
        """
        return [self.demo_model(model_id) for model_id in self.models]

    def prepare_video(self, *, model_id, operation, workflow, workflow_digest,
                      prompt_node, prompt, client_id, preflight, user_rights_confirmed,
                      frames=81, width=832, height=480):
        entry = self.models.get(model_id)
        if entry is None or operation not in OPERATIONS or operation not in entry.get("operations", []):
            raise Denied("UNSUPPORTED_VIDEO_MODEL_OR_OPERATION")
        if entry["license"] == "MODEL_LICENSE_VERIFY":
            raise Hold("CHECKPOINT_LICENSE_REVIEW_REQUIRED")
        if not isinstance(preflight, NativeVideoPreflight):
            raise Hold("NATIVE_GPU_PREFLIGHT_REQUIRED")
        preflight.check(model_id, workflow_digest)
        if user_rights_confirmed is not True:
            raise Denied("VIDEO_INPUT_RIGHTS_REQUIRED")
        if (not isinstance(frames, int) or isinstance(frames, bool)
            or not 1 <= frames <= 241 or not isinstance(width, int)
            or not isinstance(height, int) or width % 32 or height % 32
            or width < 256 or height < 256 or width > 1920 or height > 1088):
            raise Denied("VIDEO_BUDGET_INVALID")
        # Graph must be the exact host-verified model/workflow; changing video
        # parameters or reference images changes the digest and requires a new receipt.
        model = ApprovedModel(model_id, preflight.model_sha256,
                              entry["license"], preflight.installed, preflight.license_verified)
        prepared = self.prepare(
            workflow=workflow, workflow_digest=workflow_digest,
            prompt_node=prompt_node, prompt=prompt, model=model,
            native_authorized=preflight.trusted_native,
            rights_confirmed=user_rights_confirmed, client_id=client_id
        )
        return {"prepared": prepared, "modelId": model_id, "operation": operation,
                "framesRequested": frames, "resolutionRequested": [width, height],
                "status": "READY_TO_QUEUE_NOT_RENDERED"}

    def queue_video(self, prepared, *, native_authorized):
        if not isinstance(prepared, dict) or prepared.get("status") != "READY_TO_QUEUE_NOT_RENDERED":
            raise Denied("VIDEO_NOT_PREFLIGHTED")
        result = self.submit(prepared["prepared"], native_authorized=native_authorized)
        return {"status": result["status"], "prompt_id": result["prompt_id"],
                "model_id": prepared["modelId"], "operation": prepared["operation"]}

    def video_result(self, prompt_id):
        if not isinstance(prompt_id, str) or not re.fullmatch(r"[0-9a-f-]{8,40}", prompt_id, re.I):
            raise Denied("INVALID_VIDEO_PROMPT_ID")
        history = self.transport.request("GET", "/history/" + prompt_id)
        record = history.get(prompt_id) if isinstance(history, dict) else None
        if not isinstance(record, dict) or record.get("status", {}).get("status_str") != "success":
            return {"status": "NOT_COMPLETE", "videos": []}
        clips = []
        for output in record.get("outputs", {}).values():
            if not isinstance(output, dict):
                continue
            for kind in ("gifs", "videos"):
                for item in output.get(kind, []):
                    if not isinstance(item, dict):
                        continue
                    filename = item.get("filename")
                    if (isinstance(filename, str) and NAME.fullmatch(filename)
                        and ".." not in filename and filename.lower().endswith(VIDEO_EXT)
                        and item.get("type", "output") == "output"):
                        clips.append({"filename": filename, "type": "output"})
        if not clips:
            return {"status": "OUTPUT_MISSING_HOLD", "videos": []}
        return {"status": "RENDERED_IN_COMFY_NOT_IMPORTED", "videos": clips[:8]}
