"""OneHost control of the existing P04 trainer; no trainer or active adapter of its own.

Adapted from PATCH03. Native owner supplies jobs and consent callbacks. UI input
can select only an existing job ID, never executable/model/output paths. Training
stays a candidate until native same-SHA admission and E07.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import importlib.util
import json
import math
import os
import re
import subprocess
import sys
import threading
import time
from typing import Callable

_HEX40 = re.compile(r"^[0-9a-fA-F]{40}$")
_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_PROFILES = {"ECO": 20, "BALANCED": 40, "INTENSIVE": 80}


class ForgeHold(RuntimeError):
    pass


@dataclass(frozen=True)
class ForgeJob:
    run_id: str
    task_id: str
    base_model_dir: Path
    model_lock: Path
    model_revision: str
    dataset_manifest: Path
    rights_verifier: Path
    train_jsonl: Path
    holdout_jsonl: Path
    output_dir: Path
    profile: str = "BALANCED"
    steps: int = 10
    gpu_index: int = 0
    license_source: str | None = None


class ExistingP04Background:
    """One operation in the existing host/task loop; never a second daemon.

    A source request ACK is distinct from a worker/checkpoint receipt. STOP and
    revocation remain live while run_one executes on the existing host executor.
    """
    def __init__(self, *, trusted_root: Path, p04_dir: Path,
                 owner_permit: Callable[[], bool], owner_stop: Callable[[], bool],
                 owner_busy: Callable[[], bool], python_exe: Path | None = None,
                 cadence_seconds: int = 172800, event_sink=None):
        if not all(callable(x) for x in (owner_permit, owner_stop, owner_busy)):
            raise ForgeHold("TRUSTED_WINDOWS_NATIVE_CALLBACK_REQUIRED")
        if type(cadence_seconds) is not int or cadence_seconds < 3600:
            raise ForgeHold("TRAINING_CADENCE_HOLD")
        self.root = Path(trusted_root).resolve(strict=True)
        self.p04 = Path(p04_dir).resolve(strict=True)
        if getattr(sys, 'frozen', False) and python_exe is None:
            raise ForgeHold("P04_EXISTING_PYTHON_INTERPRETER_REQUIRED")
        self.python = Path(python_exe or sys.executable).resolve(strict=True)
        if (not self.python.is_file() or (getattr(sys, 'frozen', False)
                and self.python == Path(sys.executable).resolve(strict=True))):
            raise ForgeHold("P04_FROZEN_HOST_IS_NOT_TRAINER_INTERPRETER")
        self.permit, self.stop, self.busy = owner_permit, owner_stop, owner_busy
        self.cadence, self.event_sink = cadence_seconds, event_sink
        self._gate = threading.Lock()
        self._control_lock = threading.Lock()
        self._active = None
        self._requested = None
        self._relayed = set()
        self._merge_active = False
        self._merge_stop = False
        for name in ("train_qlora.py", "preflight_local_gpu.py"):
            f = self.p04 / name
            if not f.is_file() or f.is_symlink():
                raise ForgeHold("EXISTING_P04_SCRIPT_REQUIRED:" + name)
        spec = importlib.util.spec_from_file_location("_nox_existing_p04_trainer", self.p04 / "train_qlora.py")
        self.trainer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.trainer)
        self.trainer.reject_reparse_ancestors(Path(trusted_root).absolute())
        self.trainer.reject_reparse_ancestors(Path(p04_dir).absolute())

    @staticmethod
    def _hold(reason, **extra):
        return {"status": "HOLD", "reason": reason, "weights_updated": False,
                "activation_allowed": False, **extra}

    def _trusted_file(self, path):
        p = Path(path).absolute()
        self.trainer.reject_reparse_ancestors(p)
        if not p.is_file():
            raise ForgeHold("TRAINING_INPUT_NOT_EXISTING_REGULAR_FILE")
        return str(p.resolve(strict=True))

    def _output(self, path, *, resume=False):
        p = Path(path).absolute()
        self.trainer.reject_reparse_ancestors(p)
        resolved = p.resolve()
        if resolved == self.root or not resolved.is_relative_to(self.root):
            raise ForgeHold("OWNER_APPROVED_OUTPUT_ROOT_REQUIRED")
        if resume and not p.is_dir():
            raise ForgeHold("RESUME_OUTPUT_MISSING")
        if not resume and p.exists():
            raise ForgeHold("FRESH_TRAINER_OUTPUT_MUST_NOT_EXIST")
        return resolved

    def _control(self, job):
        if not _ID.fullmatch(job.run_id) or not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", job.task_id):
            raise ForgeHold("EXACT_RUN_TASK_REQUIRED")
        p = self.root / (".forge-control-" + job.run_id)
        self.trainer.reject_reparse_ancestors(p)
        p.mkdir(exist_ok=True)
        return p

    def _job_command(self, job, out, *, resume=False):
        if (not _HEX40.fullmatch(job.model_revision) or job.profile not in _PROFILES
                or type(job.steps) is not int or not 1 <= job.steps <= _PROFILES[job.profile]
                or type(job.gpu_index) is not int or job.gpu_index < 0):
            raise ForgeHold("MODEL_REVISION_PROFILE_STEPS_HOLD")
        model_dir = Path(job.base_model_dir).absolute()
        self.trainer.reject_reparse_ancestors(model_dir)
        if not model_dir.is_dir():
            raise ForgeHold("OWNER_APPROVED_LOCAL_MODEL_REQUIRED")
        files = {key: self._trusted_file(getattr(job, key)) for key in (
            "model_lock", "dataset_manifest", "rights_verifier", "train_jsonl", "holdout_jsonl")}
        controls = self._control(job)
        stop_marker, pause_marker = controls / "stop.marker", controls / "pause.marker"
        for marker in (stop_marker, pause_marker):
            self.trainer.reject_reparse_ancestors(marker)
            if marker.exists():
                raise ForgeHold("STALE_OWNER_TRAINING_MARKER")
        cmd = [str(self.python), str(self.p04 / "train_qlora.py"),
               "--model", str(model_dir.resolve(strict=True)), "--model-lock", files["model_lock"],
               "--model-revision", job.model_revision, "--dataset-manifest", files["dataset_manifest"],
               "--rights-verifier", files["rights_verifier"], "--train-jsonl", files["train_jsonl"],
               "--holdout-jsonl", files["holdout_jsonl"], "--output-dir", str(out),
               "--events-jsonl", str(controls / "events.jsonl"), "--run-id", job.run_id,
               "--task-id", job.task_id, "--profile", job.profile, "--max-steps", str(job.steps),
               "--gpu-index", str(job.gpu_index), "--stop-marker", str(stop_marker),
               "--pause-marker", str(pause_marker)]
        if resume:
            receipt = self.verified_receipt(job)
            if receipt["status"] != "PAUSED":
                raise ForgeHold("RESUME_REQUIRES_MATCHING_PAUSED_RECEIPT")
            cmd.extend(["--resume-from-checkpoint", str(out / receipt["checkpoint"]["path"])])
        return cmd, stop_marker, pause_marker

    def due(self, *, last_run_utc, now_utc=None):
        now_utc = now_utc or datetime.now(timezone.utc)
        if now_utc.tzinfo is None or (last_run_utc is not None and last_run_utc.tzinfo is None):
            raise ForgeHold("UTC_DURABLE_LAST_RUN_REQUIRED")
        return last_run_utc is None or (now_utc - last_run_utc).total_seconds() >= self.cadence

    def preflight(self, job):
        if os.name != "nt":
            return self._hold("GPU_TRAINING_HOLD", errors=["REAL_WINDOWS_GPU_HOST_REQUIRED"])
        result = subprocess.run([str(self.python), str(self.p04 / "preflight_local_gpu.py"),
                                 "--profile", job.profile, "--gpu-index", str(job.gpu_index)],
                                cwd=str(self.p04), stdin=subprocess.DEVNULL, capture_output=True,
                                text=True, encoding="utf-8", timeout=70, check=False, shell=False)
        if len(result.stdout) > 65536:
            return self._hold("GPU_PREFLIGHT_RESPONSE_BOUND")
        try:
            report = json.loads(result.stdout)
        except (ValueError, TypeError):
            report = {}
        if (result.returncode != 0 or not isinstance(report, dict)
                or report.get("status") != "HARDWARE_READY_ONLY"
                or report.get("runtime_training_verified") is not False):
            return self._hold("GPU_TRAINING_HOLD", preflight=report)
        return report

    def request_stop(self):
        return self._request("STOP")

    def request_pause(self, job=None):
        return self._request("PAUSE", job=job)

    def _request(self, operation, *, job=None):
        with self._control_lock:
            if self._active is None:
                if self._merge_active and operation == "STOP":
                    self._merge_stop = True
                    return {"status":"STOP_REQUESTED", "weights_updated":False}
                return self._hold("NO_ACTIVE_TRAINER")
            if job is not None and self._active[2:] != (job.run_id, job.task_id):
                raise ForgeHold("ACTIVE_TRAINER_JOB_SCOPE_MISMATCH")
            self._requested = operation if self._requested != "STOP" else "STOP"
            marker = self._active[0 if self._requested == "STOP" else 1]
            self.trainer.reject_reparse_ancestors(marker)
            with marker.open("a", encoding="utf-8"):
                pass
            return {"status": self._requested + "_REQUESTED", "weights_updated": False}

    def verified_receipt(self, job):
        out = self._output(job.output_dir, resume=True)
        path = out / "training-receipt.json"
        receipt = self.trainer.read_object(path)
        digest = self.trainer.sha256_file(path)
        archived = out / "receipts" / (digest + ".json")
        if self.trainer.sha256_file(Path(self._trusted_file(archived))) != digest:
            raise ForgeHold("TRAIN_RECEIPT_ARCHIVE_MISMATCH")
        if (receipt.get("schema") != self.trainer.RECEIPT_SCHEMA
                or receipt.get("run_id") != job.run_id
                or receipt.get("status") not in {"PAUSED", "STOPPED", "COMPLETED"}):
            raise ForgeHold("TRAIN_RECEIPT_IDENTITY_HOLD")
        lock = self.trainer.read_object(job.model_lock)
        model = receipt.get("model", {})
        data = receipt.get("dataset", {})
        if (model.get("id") != lock.get("model_id") or model.get("revision") != job.model_revision
                or model.get("snapshot_sha256") != self.trainer.sha256_tree(job.base_model_dir)
                or data.get("train_sha256") != self.trainer.sha256_file(job.train_jsonl)
                or data.get("holdout_sha256") != self.trainer.sha256_file(job.holdout_jsonl)):
            raise ForgeHold("TRAIN_RECEIPT_SOURCE_MISMATCH")
        checkpoint = receipt.get("checkpoint")
        if not isinstance(checkpoint, dict) or checkpoint.get("status") != "HASHED":
            raise ForgeHold("TRAIN_CHECKPOINT_REQUIRED")
        selected = out / str(checkpoint.get("path", ""))
        step, sha = self.trainer.validated_checkpoint(out / "checkpoints", selected)
        if checkpoint.get("tree_sha256") != sha or checkpoint.get("step") != step:
            raise ForgeHold("TRAIN_CHECKPOINT_SHA_MISMATCH")
        if receipt.get("adapter_sha256") != self.trainer.sha256_tree(out / "adapter"):
            raise ForgeHold("TRAIN_ADAPTER_SHA_MISMATCH")
        training = receipt.get("training", {})
        if type(training.get("global_step")) is not int or training["global_step"] < 1:
            raise ForgeHold("TRAIN_STEP_EVIDENCE_MISSING")
        if receipt["status"] == "COMPLETED" and (training.get("evaluation_status") != "VALID"
                or any(self.trainer.finite_metric(training.get(k)) is None for k in
                       ("baseline_eval_loss", "adapter_eval_loss", "train_loss"))):
            raise ForgeHold("TRAIN_HOLDOUT_EVALUATION_REQUIRED")
        return receipt

    def run_one(self, job, *, last_run_utc, now_utc=None, monitor_seconds=2.0,
                max_seconds=36000, resume=False, require_idle=True):
        if type(require_idle) is not bool:
            raise ForgeHold("NATIVE_IDLE_POLICY_REQUIRED")
        if (not isinstance(job, ForgeJob) or (not resume and not self.due(
                last_run_utc=last_run_utc, now_utc=now_utc))):
            return self._hold("CADENCE_OR_JOB_HOLD")
        if (not isinstance(monitor_seconds, (int, float)) or not math.isfinite(monitor_seconds)
                or not .01 <= monitor_seconds <= 10 or type(max_seconds) is not int or max_seconds < 1):
            raise ForgeHold("MONITOR_BOUNDS_INVALID")
        if not self._gate.acquire(blocking=False):
            return self._hold("TRAINER_ALREADY_ACTIVE")
        try:
            return self._run(job, monitor_seconds, max_seconds, resume, require_idle)
        finally:
            with self._control_lock:
                self._active = None
            self._gate.release()

    def _run(self, job, monitor_seconds, max_seconds, resume, require_idle):
        if self.stop() or not self.permit() or (require_idle and self.busy()):
            return self._hold("NO_OWNER_IDLE_CONSENT_OR_STOP")
        preflight = self.preflight(job)
        if preflight.get("status") != "HARDWARE_READY_ONLY":
            return preflight
        out = self._output(job.output_dir, resume=resume)
        cmd, stop_marker, pause_marker = self._job_command(job, out, resume=resume)
        if self.stop() or not self.permit() or (require_idle and self.busy()):
            return self._hold("OWNER_REVOKED_AFTER_PREFLIGHT")
        controls = self._control(job)
        # Logs/events are outside fresh output: the original trainer owns mkdir.
        log_path = controls / ("worker-" + str(time.time_ns()) + ".log")
        self.trainer.reject_reparse_ancestors(log_path)
        with self._control_lock:
            self._active, self._requested = (stop_marker, pause_marker, job.run_id, job.task_id), None
        forced = False
        monitor_error = None
        prior_receipt_sha = self.trainer.sha256_file(out / "training-receipt.json") if resume else None
        with log_path.open("xb") as log:
            proc = subprocess.Popen(cmd, cwd=str(self.p04), stdin=subprocess.DEVNULL,
                                    stdout=log, stderr=subprocess.STDOUT, shell=False)
            started = time.monotonic()
            requested_at = None
            while proc.poll() is None:
                try:
                    if self.stop() or not self.permit() or time.monotonic() - started > max_seconds:
                        self.request_stop()
                    elif require_idle and self.busy() and self._requested is None:
                        self.request_pause()
                    self.relay_events(job, live=True)
                except Exception as exc:
                    monitor_error = type(exc).__name__
                    self.request_stop()
                if self._requested is not None:
                    requested_at = requested_at or time.monotonic()
                    if time.monotonic() - requested_at > 120:
                        proc.terminate()
                        try:
                            proc.wait(timeout=15)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                            proc.wait()
                        forced = True
                        break
                time.sleep(monitor_seconds)
            proc.wait()
        if monitor_error:
            return self._hold("TRAINER_MONITOR_FAILED", error_type=monitor_error)
        if forced or proc.returncode != 0:
            return self._hold("TRAINER_STOP_TIMEOUT" if forced else "TRAINER_EXIT_HOLD", return_code=proc.returncode)
        receipt = self.verified_receipt(job)
        if prior_receipt_sha == self.trainer.sha256_file(out / "training-receipt.json"):
            return self._hold("RESUME_RECEIPT_NOT_UPDATED")
        if receipt["status"] == "PAUSED" and pause_marker.exists():
            # Only remove this run's request after verifying all checkpoint bytes.
            self.trainer.reject_reparse_ancestors(pause_marker)
            pause_marker.unlink()
        self.relay_events(job)
        return {"status": "ADAPTER_CANDIDATE_PENDING_E07" if receipt["status"] == "COMPLETED" else receipt["status"],
                "run_id": job.run_id, "receipt_sha256": self.trainer.sha256_file(out / "training-receipt.json"),
                "checkpoint": receipt["checkpoint"], "weights_updated": False, "activation_allowed": False}

    def merge_candidate(self, job, *, output_dir, owner_approve, max_seconds=36000):
        """Native-only merge via original P04; never switches the active model.

        The safe/read-only training.evaluate route does not call this method.
        A native owner task must explicitly approve this exact job/output first.
        """
        if not callable(owner_approve) or owner_approve(job, output_dir) is not True:
            return self._hold("MERGE_OWNER_CONSENT_REQUIRED")
        if type(max_seconds) is not int or not 1 <= max_seconds <= 36000:
            raise ForgeHold("MERGE_TIMEOUT_BOUND")
        if not self._gate.acquire(blocking=False):
            return self._hold("TRAINER_ALREADY_ACTIVE")
        try:
            if self.stop() or not self.permit():
                return self._hold("MERGE_OWNER_REVOKED")
            receipt = self.verified_receipt(job)
            if receipt['status'] != 'COMPLETED':
                return self._hold("MERGE_REQUIRES_COMPLETED_EVALUATION")
            destination = self._output(output_dir)
            if not destination.parent.is_dir():
                raise ForgeHold("MERGE_PARENT_MUST_EXIST")
            script = Path(self._trusted_file(self.p04 / 'merge_qlora_adapter.py'))
            command = [str(self.python), str(script), '--model-dir', str(job.base_model_dir),
                       '--model-lock', str(job.model_lock), '--adapter-dir', str(job.output_dir / 'adapter'),
                       '--training-receipt', str(job.output_dir / 'training-receipt.json'),
                       '--dataset-manifest', str(job.dataset_manifest),
                       '--rights-verifier', str(job.rights_verifier), '--output-dir', str(destination)]
            controls = self._control(job)
            log = controls / ('merge-' + str(time.time_ns()) + '.log')
            started = time.monotonic()
            with self._control_lock:
                self._merge_active, self._merge_stop = True, False
            with log.open('xb') as stream:
                proc = subprocess.Popen(command, cwd=str(self.p04), stdin=subprocess.DEVNULL,
                                        stdout=stream, stderr=subprocess.STDOUT, shell=False)
                while proc.poll() is None:
                    try:
                        stop_merge = (self._merge_stop or self.stop() or not self.permit()
                            or owner_approve(job, output_dir) is not True
                            or time.monotonic()-started > max_seconds)
                    except Exception:
                        stop_merge = True
                    if stop_merge:
                        # Existing merge publishes only after full validation; an
                        # interrupted temporary candidate is never selected.
                        proc.terminate()
                        try: proc.wait(timeout=15)
                        except subprocess.TimeoutExpired: proc.kill(); proc.wait()
                        return self._hold('MERGE_STOPPED_NO_ACTIVATION')
                    time.sleep(.1)
            if proc.returncode != 0:
                return self._hold('EXISTING_P04_MERGE_HOLD', return_code=proc.returncode)
            merge = self.trainer.read_object(destination / 'merge-receipt.json')
            if (merge.get('schema') != 'NOX-QLORA-MERGE-RECEIPT-v1'
                    or merge.get('status') != 'CREATED'
                    or merge.get('training_receipt_sha256') != self.trainer.sha256_file(job.output_dir / 'training-receipt.json')
                    or merge.get('adapter_sha256') != receipt['adapter_sha256']):
                raise ForgeHold('MERGE_RECEIPT_BINDING_HOLD')
            spec = importlib.util.spec_from_file_location('_nox_existing_p04_merge', script)
            merger = importlib.util.module_from_spec(spec); spec.loader.exec_module(merger)
            payload_sha = merger.tree_sha256(destination, skip_merge_receipt=True)
            if payload_sha != merge.get('merged_payload_sha256'):
                raise ForgeHold('MERGE_PAYLOAD_SHA_MISMATCH')
            return {'status':'MERGED_CANDIDATE_PENDING_IMPORT', 'merged_payload_sha256':payload_sha,
                    'merge_receipt_sha256':self.trainer.sha256_file(destination / 'merge-receipt.json'),
                    'weights_updated':False, 'activation_allowed':False,
                    'reason':'VERIFIED_EXISTING_P03_IMPORT_REQUIRED_BEFORE_P02_SELECTION'}
        finally:
            with self._control_lock:
                self._merge_active = False
            self._gate.release()

    def event_snapshot(self, job):
        """Bounded real events for existing training.checkpoints polling.

        Background jobs do not borrow a completed request's framed nonce.
        These payloads keep original EventID and evidence_verified=False.
        """
        path = self._control(job) / 'events.jsonl'
        if not path.exists():
            return []
        if path.stat().st_size > 64*1024*1024:
            raise ForgeHold('EVENT_LOG_REVIEW_SIZE_LIMIT')
        # Same original full-history parser as resume, not a synthetic sensor.
        self.trainer.EventWriter(path, job.run_id, job.task_id)
        from collections import deque
        with path.open(encoding='utf-8') as stream:
            return [json.loads(line) for line in deque(stream, maxlen=64)]

    def relay_events(self, job, *, live=False):
        """Forward real canonical events to the injected existing host bus only."""
        if self.event_sink is None:
            return 0
        path = self._control(job) / "events.jsonl"
        if not path.exists():
            return 0
        # Existing validator checks complete sequence/identity, duplicate IDs,
        # bounds and ambiguous JSON before any event is forwarded.
        if not live:
            self.trainer.EventWriter(path, job.run_id, job.task_id)
        count = 0
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                if not line.endswith("\n"):
                    break  # worker may be writing its last bounded NDJSON row
                if len(line) > 4096:
                    raise ForgeHold("P04_EVENT_SIZE_HOLD")
                event = json.loads(line)
                if (event.get("schema") != "NOX-INSTALLER-EVENT-v3"
                        or event.get("run_id") != job.run_id or event.get("task_id") != job.task_id
                        or event.get("package_id") != "P04" or event.get("evidence_verified") is not False
                        or event.get("source") != "P04.QLoRA"
                        or event.get("event_type") not in {"task.started", "task.progress", "task.failed", "task.completed", "training.step", "checkpoint.saved", "model.stopped", "gpu.sample"}
                        or event.get("state") not in {"QUEUED", "RUNNING", "PAUSED", "COMPLETED", "ERROR", "STOPPED", "OFFLINE", "HOLD", "READY", "N_D"}
                        or not isinstance(event.get("message"), str) or len(event["message"]) > 240
                        or not re.fullmatch(r"[0-9a-f]{32}", str(event.get("event_id", "")))):
                    raise ForgeHold("P04_EVENT_PROVENANCE_HOLD")
                identity = (job.run_id, event["event_id"])
                if identity not in self._relayed:
                    if self.event_sink(event) is False:
                        raise ForgeHold("P04_HOST_EVENT_REJECTED")
                    self._relayed.add(identity)
                    count += 1
        return count
