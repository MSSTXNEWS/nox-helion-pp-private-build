"""NOX PRIME -> one Resonance -> one main model -> native S03.

Drop-in owner-authorized adapter around the EXISTING P02/OneHost callbacks.
No second LLM, server, database, job scheduler, process or other intelligence.
Background teachers are not allowed to write to the user-facing chat stream.
"""
from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
import threading
import time
from typing import Any

from nox_runpod.teacher_mesh.v38.native_bridge_v38 import AttachedNOX, HostBindings
from nox_runpod.teacher_mesh.v38.synaptic_brain import PulseConfig, Session
from nox_runpod.teacher_mesh.v41.training.priority_autonomy import (
    ChatFirstBudget, SchedulerPorts, chat_first_admission, submit_verified_plan,
)
from nox_runpod.teacher_mesh.v43.nox.resource_brain import (
    Policy as ResourcePolicy, plan_load,
)
from .ram_policy import plan_ram, plan_warm_weight
from .offload_policy import plan_offload

MODEL_IDENTITY="NOX PRIME"
CHAT_SURFACE="Резонанс"
ONEHOST="EXISTING_NOX_ONEHOST"


@dataclass(frozen=True)
class NativeOneHost:
    chat: HostBindings
    observe: Callable[[], Mapping[str, Any]]
    queue: SchedulerPorts | None = None


class OnePrime:
    """A single existing inference stream with durable S03 and chat P0 lease."""

    def __init__(self, native: NativeOneHost, *,
                 config: PulseConfig | None = None,
                 budget: ChatFirstBudget | None = None):
        if not isinstance(native, NativeOneHost) or not callable(native.observe):
            raise TypeError("EXISTING_ONEHOST_REQUIRED")
        if not isinstance(native.chat, HostBindings):
            raise TypeError("EXISTING_S03_MODEL_CALLBACKS_REQUIRED")
        self.native=native
        self.budget=budget or ChatFirstBudget()
        self._lock=threading.RLock()
        self._active=0
        self._last_chat=None
        self._closed=False
        try:
            ram=plan_ram(native.observe())
        except Exception:
            ram={'state':'HOLD_NATIVE_RAM_TELEMETRY'}
        # Do not guess cached scope/revision: V38 WarmS03Cache already checks both.
        cache_bytes=ram.get("cache_bytes",0) if ram.get("state")=="RAM_CACHE_AND_WORKSPACE_READY" else 8*1024**2
        cache_bytes=max(4096,min(256*1024**2,cache_bytes))
        self.chat=AttachedNOX(native.chat,config,cache_bytes=cache_bytes,
                              cache_ttl_s=45.0)

    def stream(self, session: Session, prompt: str, turn_id: str,
               *, deep: bool = False) -> Iterator[dict]:
        """One real NOX callback, mandatory S03 indexed recall and durable log."""
        with self._lock:
            closed=self._closed
            if not closed:
                self._active+=1
                self._last_chat=time.monotonic()
        if closed:
            yield {"type":"hold","state":"HOLD_PRIME_CLOSED"}
            return
        try:
            # No second editor/rewriter and no teacher talking to the user.
            yield from self.chat.stream(session,prompt,turn_id,deep=deep)
        finally:
            with self._lock:
                self._active-=1
                self._last_chat=time.monotonic()

    def observe(self) -> dict:
        """Native state is authoritative; local stream can only add chat pressure."""
        try:
            status=self.native.observe()
        except Exception:
            return {"state":"HOLD_NATIVE_ONEHOST_OBSERVE"}
        if not isinstance(status,Mapping):
            return {"state":"HOLD_NATIVE_ONEHOST_SNAPSHOT"}
        status=dict(status)
        with self._lock:
            active,last,closed=self._active,self._last_chat,self._closed
        if closed:
            return {"state":"HOLD_PRIME_CLOSED"}
        if active:
            status["chat_state"]="generating"
            status["seconds_since_chat_activity"]=0
        elif last is not None:
            elapsed=status.get("seconds_since_chat_activity")
            age=max(0.0,time.monotonic()-last)
            if type(elapsed) in (int,float) and elapsed>=0:
                status["seconds_since_chat_activity"]=min(elapsed,age)
        status["prime_active_streams"]=active
        return status

    def background_admission(self) -> dict:
        """Advisory ONLY: OneHost owns leases, STOP, queue and device selection."""
        out=chat_first_admission(self.observe(),budget=self.budget)
        return {**out,"identity":MODEL_IDENTITY,"chat_surface":CHAT_SURFACE,
                "queue_owner":ONEHOST,"chat_priority":"P0",
                "background_priority":"P1","main_model_count":1,
                "main_model_gpu":0,"teacher_gpu":1,
                "new_scheduler":False,"new_backend":False,"performed":False}

    def teacher_admission(self,request:Mapping,inventory:Mapping,
                          policy:ResourcePolicy=ResourcePolicy())->dict:
        """May propose ONE already-local teacher, never download or start it."""
        gate=self.background_admission()
        if "REQUEST_ONEHOST_GPU1_DISTILLATION_ADMISSION" not in gate.get("actions",()):
            return {"state":"HOLD_CHAT_OR_GPU_BACKGROUND_GATES",
                    "reasons":gate.get("reasons",[]),"performed":False}
        if not isinstance(request,Mapping) or request.get("role")!="teacher":
            return {"state":"HOLD_TEACHER_SCOPE","performed":False}
        if not isinstance(inventory,Mapping):
            return {"state":"HOLD_MODEL_INVENTORY","performed":False}
        result=plan_load(dict(request),dict(inventory),policy)
        if result.get("state")=="OWNER_NATIVE_APPROVAL_REQUIRED":
            return {**result,"queue_owner":ONEHOST,"priority":"P1",
                    "recheck_chat_before_gpu_start":True,
                    "owner_lease_required":True,"performed":False}
        return result

    def ram_admission(self)->dict:
        """Allocate nothing until the installed native OneHost opts in."""
        return plan_ram(self.observe())

    def warm_weight_admission(self,candidate:Mapping)->dict:
        """Pure RAM warm-up gate. Existing V95/V99 performs owner-native reads."""
        return plan_warm_weight(self.observe(),candidate)

    def offload_admission(self) -> dict:
        """10GB trigger only; archive and deletion require independent receipts."""
        return plan_offload(self.observe())

    def enqueue_existing_verified_plan(self,plan:Mapping,*,owner_scope:str)->dict:
        """Never creates a new task queue or reports a fabricated job ID."""
        gate=self.background_admission()
        if "REQUEST_ONEHOST_GPU1_DISTILLATION_ADMISSION" not in gate.get("actions",()):
            return {"state":"HOLD_BACKGROUND_CHAT_FIRST","jobs_enqueued":0,
                    "reasons":gate.get("reasons",[])}
        if self.native.queue is None:
            return {"state":"HOLD_NATIVE_QUEUE_CALLBACKS","jobs_enqueued":0}
        return submit_verified_plan(plan,self.native.queue,owner_scope=owner_scope)

    def on_s03_write(self,session:Session)->None:
        self.chat.on_s03_write(session)

    def on_acl_revoked(self,session:Session)->None:
        self.chat.on_acl_revoked(session)

    def close(self)->None:
        with self._lock:self._closed=True
        self.chat.close()
