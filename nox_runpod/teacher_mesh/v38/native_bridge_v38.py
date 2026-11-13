"""Opt-in adapter into EXISTING authenticated NOX OneHost/P02 and S03.

It doesn't add a service or invoke shell from conversations. Runtime owner must
inject callbacks; when missing the adapter cannot start. One NOX model call per
normal user turn. Never installs a model or edits weights.
"""
from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from .durable_runtime import DurablePorts, DurableTurn, WarmS03Cache, native_query_plan
from .synaptic_brain import NativePorts, PulseConfig, Session, SynapticBrain


@dataclass(frozen=True)
class HostBindings:
    authorize: Callable[[Session], bool]
    stop: Callable[[], bool]
    s03_recall: Callable[[Session, str, int], list[dict]]
    s03_revision: Callable[[Session], str]
    s03_append: Callable[[Session, dict], Mapping[str, Any]]
    model_stream: Callable[[str, dict], Iterator[str]]
    sensors: Callable[[Session], Mapping[str, Any]] | None = None
    self_receipts: Callable[[Session], list[dict]] | None = None
    affect: Callable[[Session, str], Mapping[str, Any]] | None = None
    preferences: Callable[[Session], Mapping[str, Any]] | None = None
    available_skills: Callable[[Session], Mapping[str, Any]] | None = None
    queue_status: Callable[[Session], Mapping[str, Any]] | None = None
    memory_scope_authorize: Callable[[Session, Mapping[str, Any]], bool] | None = None
    s03_indexed_recall: Callable[[Session, Mapping[str, Any], int], list[dict]] | None = None
    s03_backup: Callable[[Session], Mapping[str, Any]] | None = None
    s03_backup_verify: Callable[[Session, Mapping[str, Any]], bool] | None = None


class AttachedNOX:
    """Small, bounded cognitive overlay using trusted host ports only.

    Attach it to the EXISTING P02 chat path with a verified feature flag and
    rollback. Do not call from a new competing HTTP endpoint.
    """
    def __init__(self, host: HostBindings, config: PulseConfig | None = None,
                 *, cache_bytes: int = 8 * 1024 * 1024, cache_ttl_s: float = 45.0):
        required=('authorize','stop','s03_recall','s03_revision','s03_append','model_stream')
        if any(not callable(getattr(host,n,None)) for n in required):
            raise TypeError('EXISTING_ONEHOST_CALLBACKS_REQUIRED')
        self.host=host
        # Prefer the existing S03 indexed fanout across M0–M7, including temporal
        # and source-linked summaries. The host determines access, indexes and
        # persistence; this adapter never scans all rows or creates another DB.
        def native_recall(session:Session,prompt:str,limit:int)->list[dict]:
            if callable(host.s03_indexed_recall):
                return host.s03_indexed_recall(session,native_query_plan(prompt),limit)
            return host.s03_recall(session,prompt,limit)
        self.cache=WarmS03Cache(native_recall,host.s03_revision,max_bytes=cache_bytes,ttl_seconds=cache_ttl_s)
        self.brain=SynapticBrain(NativePorts(authorize=host.authorize,stop=host.stop,
                     sensors=host.sensors,s03_recall=self.cache,
                     self_receipts=host.self_receipts,affect=host.affect,
                     preferences=host.preferences,available_skills=host.available_skills,
                     queue_status=host.queue_status,
                     memory_scope_authorize=host.memory_scope_authorize),config or PulseConfig())
        self.turn=DurableTurn(self.brain,DurablePorts(s03_append=host.s03_append,
                                  s03_backup=host.s03_backup,
                                  s03_backup_verify=host.s03_backup_verify,
                                  native_revision=host.s03_revision))

    def stream(self,session:Session,prompt:str,turn_id:str,*,deep:bool=False,
               real_postcheck:Callable|None=None,real_revise_stream:Callable|None=None,
               ui_supports_replace:bool=False)->Iterator[dict]:
        session.validate()
        if not isinstance(prompt,str) or len(prompt)>8000 or not prompt.strip():
            yield {'type':'hold','state':'HOLD_INVALID_PROMPT'}
            return
        yield from self.turn.run(session,prompt,turn_id,self.host.model_stream,
                     deep=deep,postcheck=real_postcheck,revise_stream=real_revise_stream,
                     ui_replace_supported=ui_supports_replace)

    def on_s03_write(self,session:Session):
        self.cache.invalidate(session)

    def on_acl_revoked(self,session:Session):
        self.cache.invalidate(session)

    def close(self):
        self.brain.close()
