"""NOX SelfBuilder R2: Windows-first persistent event cycle on the existing owner host.

This module does NOT own a DB, HTTP downloader, model runner or Windows installer.
Only owner-authorized P02/S03/REFLECTION/FORGE callbacks can act. GENERATED code
is written to candidate staging, never executed, installed or merged by this worker.
"""
from __future__ import annotations

import importlib
import re
import signal
import time
from dataclasses import dataclass
from typing import Any

from .builder import SelfBuilder, SelfBuilderHold
from .complete_builder import CompleteBuilder
from .p02_coder import CodingHold
from .learning import make_forge_handoff, make_learning_record
from .release_governor import inspect_release_task

_FACTORY_NAME = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_.]*:[a-zA-Z_][a-zA-Z0-9_]*$")
_TASK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_ALLOWED_KINDS = frozenset({"SELF_WRITE", "REFLECT", "FORGE_REVIEW", "REVIEW_LESSON"})

class EvolutionHold(RuntimeError):
    pass


def load_trusted_factory(ref: str):
    """Only the trusted native owner selects a factory; no external scripts executed."""
    if not isinstance(ref, str) or not _FACTORY_NAME.fullmatch(ref):
        raise EvolutionHold("INVALID_NATIVE_HOST_FACTORY")
    module_name, func_name = ref.split(":", 1)
    module = importlib.import_module(module_name)
    factory = getattr(module, func_name, None)
    if not callable(factory):
        raise EvolutionHold("NATIVE_FACTORY_NOT_CALLABLE")
    return factory()


@dataclass(frozen=True)
class Cycle:
    status: str
    task_id: str | None = None
    receipt: dict | None = None


class EvolutionWorker:
    """Persistent light CPU process, in process with existing P02 when embedded.

    Required host methods (implemented by EXISTING trusted P02/S03 host adapter):
    worker_enabled() -> bool: owner opt-in + consent still valid
    stop_requested() -> bool: globally scoped STOP/revoke, checked each turn
    claim_task() -> dict | None: atomic S03 TASK ID claim, no second queue
    native_authorize(session, route, args) -> bool: OS/native approval
    recall(session,task,sources) -> list[verified scoped evidence]
    generate(session,request) -> str: existing P02 installed model callback
    record_result(task_id,status,receipt) -> bool: durable existing S03 ACK
    finish_task(task_id,status) -> bool: atomic disposition in existing ledger
    For SELF_WRITE also REQUIRED: release_ticket(task)->dict and current_source_head()->str;
    Optional: reflect(task), forge_preflight(task), heartbeat(status),
    discovery_due(), discover_opportunities(limit), record_opportunities(items)

    A new or unapproved capability never becomes active through this worker.
    """
    def __init__(self, host: Any, *, workspace: str, idle_seconds: float = 30.0,
                 max_tasks_per_cycle: int = 1):
        if not 0.2 <= idle_seconds <= 3600:
            raise ValueError("IDLE_INTERVAL_OUT_OF_BOUNDS")
        if max_tasks_per_cycle != 1:
            raise ValueError("SINGLE_TASK_ATOMIC_CYCLE_REQUIRED")
        for method in ("worker_enabled", "stop_requested", "claim_task", "native_authorize",
                       "recall", "generate", "record_result", "finish_task"):
            if not callable(getattr(host, method, None)):
                raise EvolutionHold("EXISTING_OWNER_CALLBACK_REQUIRED:" + method)
        self.host = host
        self.workspace = workspace
        self.idle_seconds = idle_seconds
        self._stop = False
        self.builder = SelfBuilder(recall=host.recall, generate=host.generate,
                                   native_authorize=host.native_authorize)
        source_admission=getattr(host,"source_admission",None)
        self.complete_builder = CompleteBuilder(recall=host.recall,generate=host.generate,
            native_authorize=host.native_authorize,source_admission=source_admission,
            target_admission=getattr(host,"target_admission",None)) if callable(source_admission) else None

    def stop(self):
        self._stop = True

    def _guard(self):
        if self._stop or self.host.stop_requested() is True:
            raise EvolutionHold("GLOBAL_STOP_OR_REVOKE")
        if self.host.worker_enabled() is not True:
            raise EvolutionHold("NO_OWNER_OPT_IN")

    @staticmethod
    def _validate_task(task):
        if not isinstance(task, dict) or not isinstance(task.get("task_id"), str) or not _TASK_ID.fullmatch(task["task_id"]):
            raise EvolutionHold("INVALID_EXISTING_TASK")
        if task.get("kind") not in _ALLOWED_KINDS:
            raise EvolutionHold("UNKNOWN_TASK_KIND_HOLD")
        return task

    def tick(self):
        """One bounded task; no hidden downloads, installs or package edits."""
        self._guard()
        task = self.host.claim_task()
        if task is None:
            # Discovery is scheduled and authorized by the existing owner host.
            # It may SAVE suggestions, but never execute proposals or change files.
            due = getattr(self.host, "discovery_due", None)
            discover = getattr(self.host, "discover_opportunities", None)
            record = getattr(self.host, "record_opportunities", None)
            if all(callable(x) for x in (due, discover, record)) and due() is True:
                self._guard()
                suggestions = discover(limit=2)
                if not isinstance(suggestions, list) or len(suggestions) > 2:
                    raise EvolutionHold("UNBOUNDED_DISCOVERY_RESULT")
                if suggestions:
                    if any(not isinstance(x,dict) or not isinstance(x.get("source_id"),str)
                           or x.get("evidence_verified") is not True
                           or not isinstance(x.get("summary"),str)
                           or len(x["summary"]) > 700 for x in suggestions):
                        raise EvolutionHold("UNVERIFIED_DISCOVERY_EVIDENCE")
                    self._guard()
                    if record(suggestions) is not True:
                        raise EvolutionHold("S03_DISCOVERY_NOT_SAVED")
                    return Cycle("OPPORTUNITIES_REVIEW_REQUIRED")
            return Cycle("IDLE")
        task = self._validate_task(task)
        tid = task["task_id"]
        try:
            self._guard()
            kind = task["kind"]
            if kind == "SELF_WRITE":
                release_ticket = getattr(self.host, "release_ticket", None)
                current_head = getattr(self.host, "current_source_head", None)
                if not callable(release_ticket) or not callable(current_head):
                    raise EvolutionHold("RELEASE_GOVERNOR_NATIVE_CALLBACK_REQUIRED")
                self._guard()
                ticket = release_ticket(task)
                if not isinstance(ticket,dict) or ticket.get("task_id") != tid:
                    raise EvolutionHold("RELEASE_TICKET_TASK_MISMATCH")
                head = current_head()
                gate = inspect_release_task(ticket, current_head=head)
                if gate.status != "PATCH_CANDIDATE_ALLOWED":
                    raise EvolutionHold("RELEASE_GOVERNOR_HOLD:" + ",".join(gate.reasons))
                if task.get("source_head") != head:
                    raise EvolutionHold("TASK_SOURCE_HEAD_DRIFT")
                if not isinstance(task.get("source_head"), str):
                    raise EvolutionHold("EXACT_OWNER_HEAD_REQUIRED")
                if task.get("candidate_language") == "multilang":
                    if self.complete_builder is None:
                        raise EvolutionHold("NATIVE_SOURCE_ADMISSION_CALLBACK_REQUIRED")
                    receipt = self.complete_builder.propose(
                        session=task.get("session"), task=task.get("task", ""),
                        source_head=task["source_head"], workspace=self.workspace,
                        source_ids=tuple(task.get("source_ids", ())))
                else:
                    receipt = self.builder.propose(
                        session=task.get("session"), task=task.get("task", ""),
                        source_head=task["source_head"], workspace=self.workspace,
                        extra_sources=tuple(task.get("source_ids", ())))
                # Never install this candidate; native owner performs the real code tests.
                status = "CANDIDATE_REVIEW_REQUIRED"
            elif kind == "REFLECT":
                self._guard()
                method = getattr(self.host, "reflect", None)
                if not callable(method):
                    raise EvolutionHold("EXISTING_REFLECTION_CALLBACK_MISSING")
                if self.host.native_authorize(task.get("session"), "selfbuilder.reflect", {"task_id":tid}) is not True:
                    raise EvolutionHold("REFLECTION_SCOPE_DENIED")
                receipt = method(task)
                if not isinstance(receipt,dict) or receipt.get("verified") is not True:
                    raise EvolutionHold("REFLECTION_EVIDENCE_HOLD")
                status = "REFLECTION_REVIEW_REQUIRED"
            elif kind == "REVIEW_LESSON":
                self._guard()
                if self.host.native_authorize(task.get("session"), "selfbuilder.feedback", {"task_id":tid}) is not True:
                    raise EvolutionHold("LESSON_OWNER_REVIEW_DENIED")
                receipt = make_learning_record(
                    run_id=task.get("run_id",tid),
                    receipt=task.get("proposal_receipt",{}),
                    outcome=task.get("outcome", ""),
                    reviewer_source_id=task.get("reviewer_source_id", ""),
                    native_approve=True)
                status = "LESSON_READY_FOR_EXISTING_S03"
            else:  # FORGE_REVIEW
                self._guard()
                if self.host.native_authorize(task.get("session"), "selfbuilder.train.request", {"task_id":tid}) is not True:
                    raise EvolutionHold("FORGE_SCOPE_DENIED")
                preflight = getattr(self.host, "forge_preflight", None)
                if not callable(preflight):
                    raise EvolutionHold("EXISTING_P04_PREFLIGHT_UNAVAILABLE")
                receipt = make_forge_handoff(
                    dataset_manifest_sha256=task.get("dataset_sha256", ""),
                    base_model_snapshot_sha256=task.get("base_sha256", ""),
                    rights_receipt_id=task.get("rights_id", ""),
                    approved=True, gpu_preflight=preflight(task))
                # Only a handoff. Existing P04 trainer owns actual training.
                status = "FORGE_HANDOFF_NOT_TRAINED"
            self._guard()
        except (SelfBuilderHold, EvolutionHold, CodingHold, PermissionError, ValueError, KeyError) as exc:
            receipt = {"schema":"NOX-SELFBUILDER-FAILED-v1", "reason":str(exc)[:160],
                       "task_id":tid, "weights_updated":False, "integrated":False}
            status = "HOLD"
        # Host must durably record the result before it ACKs task completion.
        if self.host.record_result(tid, status, receipt) is not True:
            raise EvolutionHold("S03_RESULT_NOT_DURABLE")
        if self.host.finish_task(tid, status) is not True:
            raise EvolutionHold("EXISTING_S03_TASK_ACK_HOLD")
        return Cycle(status, tid, receipt)

    def run(self, *, max_ticks: int | None = None, sleeper=time.sleep):
        if max_ticks is not None and (not isinstance(max_ticks,int) or max_ticks < 1):
            raise ValueError("INVALID_MAX_TICKS")
        ticks = 0
        while not self._stop:
            self._guard()
            result = self.tick()
            ticks += 1
            hb = getattr(self.host, "heartbeat", None)
            if callable(hb):
                hb(result.status)
            if max_ticks is not None and ticks >= max_ticks:
                return ticks
            if self._stop or self.host.stop_requested() is True:
                return ticks
            sleeper(self.idle_seconds if result.status == "IDLE" else .2)
        return ticks


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="NOX SelfBuilder existing-owner worker. OFF unless owner enabled.")
    parser.add_argument("--factory", required=True, help="Trusted P02 native host module:factory")
    parser.add_argument("--workspace", required=True, help="Owner-approved staging directory")
    parser.add_argument("--idle-seconds", type=float, default=30)
    parser.add_argument("--max-ticks", type=int)
    args=parser.parse_args(argv)
    host=load_trusted_factory(args.factory)
    worker=EvolutionWorker(host,workspace=args.workspace,idle_seconds=args.idle_seconds)
    try:
        signal.signal(signal.SIGINT,lambda *_:worker.stop())
        if hasattr(signal,"SIGTERM"):
            signal.signal(signal.SIGTERM,lambda *_:worker.stop())
        worker.run(max_ticks=args.max_ticks)
    except (EvolutionHold,KeyboardInterrupt) as exc:
        print("NOX_SELFBUILDER_HOLD:",str(exc))
        return 2
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
