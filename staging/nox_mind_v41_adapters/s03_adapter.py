"""Map an S03-shaped read/write port onto the staging mind stores.

Production modules are not imported and not patched. The host database
``unified_nox_knowledge.sqlite3`` is refused by ``open_staging_memory``.
The adapter is inert unless ``enabled`` is true or ``NOX_MIND_V41_STAGING``
is explicitly on. Nothing in the NOX control plane constructs this object.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from ._path import ensure_mind_package_on_path

ensure_mind_package_on_path()

from nox_mind_v41.bitemporal import BiTemporalStore
from nox_mind_v41.graph_memory import GraphMemory
from nox_mind_v41.warm_cache import ScopedFTS, WarmS03Cache

from .protocols import InMemoryS03, StagingDisabled, StagingRefused, resolve_enabled

_HOST_MARKERS = ("NOX_UNIFIED_S03", "unified_nox_knowledge")


@dataclass
class StagingMemory:
    store: BiTemporalStore
    fts: ScopedFTS
    cache: WarmS03Cache
    graph: GraphMemory


def open_staging_memory(path: str = ":memory:", clock=None, monotonic=None) -> StagingMemory:
    """Open staging stores. Default is process-local memory, not host S03.

    ``:memory:`` yields three independent connections (SQLite treats each
    ``:memory:`` connect as its own database). A filesystem path is shared as
    one file with separate tables, and is rejected when it points at host S03.
    """
    if path != ":memory:":
        normalized = path.replace("\\", "/")
        if any(marker in normalized for marker in _HOST_MARKERS):
            raise StagingRefused(
                "refusing host S03 database; staging memory is not the unified knowledge file"
            )
    fact_clock = clock or time.time
    cache_clock = monotonic or time.monotonic
    store = BiTemporalStore(path, clock=fact_clock)
    fts = ScopedFTS(path)
    cache = WarmS03Cache(fts, clock=cache_clock)
    graph = GraphMemory(path, clock=fact_clock)
    return StagingMemory(store=store, fts=fts, cache=cache, graph=graph)


class S03MindAdapter:
    """S03MemoryPort implementation over bi-temporal facts, warm FTS, and graph memory.

    ``read`` / ``write`` are the port. An optional ``port`` receives a mirror of
    each write so tests can show the fake and the mind stores side by side.
    The mirror is not a second source of truth and is not the host table.
    """

    def __init__(self, store, cache, graph, *, enabled: bool | None = None, port: InMemoryS03 | None = None):
        self.store = store
        self.cache = cache
        self.graph = graph
        self.port = port
        self.enabled = resolve_enabled(enabled)

    def write(self, persona_id: str, text: str, **meta) -> dict:
        self._guard()
        subject = meta.get("subject", "memory")
        predicate = meta.get("predicate", "text")
        obj = meta.get("object", meta.get("obj", text))
        scope = meta.get("scope", "persona")
        mtype = meta.get("mtype", "episodic")
        valence = float(meta.get("valence", 0.0))
        arousal = float(meta.get("arousal", 0.0))
        source = meta.get("source", "staging")
        already = [row for row in self.store.current(persona_id, subject, predicate) if row["object"] == obj]
        fact_id = self.store.assert_fact(
            persona_id, subject, predicate, obj, source=source, importance=float(meta.get("importance", 0.5))
        )
        if already and already[0]["id"] == fact_id:
            return {"fact_id": fact_id, "node_id": None, "persona_id": persona_id, "idempotent": True}
        node_id = self.graph.write(
            persona_id,
            text,
            mtype=mtype,
            valence=valence,
            arousal=arousal,
            meta={"fact_id": fact_id, "subject": subject, "predicate": predicate},
        )
        self.cache.write(fact_id, persona_id, scope, text)
        if self.port is not None:
            self.port.write(persona_id, text, fact_id=fact_id, node_id=node_id, subject=subject, predicate=predicate)
        return {"fact_id": fact_id, "node_id": node_id, "persona_id": persona_id, "idempotent": False}

    def read(self, persona_id: str, query: str, **opts) -> dict:
        self._guard()
        scopes = opts.get("scopes", ("global", "persona"))
        k = int(opts.get("k", 6))
        warm = self.cache.recall(query, persona_id, scopes=scopes, k=k)
        graph = self.graph.recall(persona_id, query, k=k)
        subject = opts.get("subject")
        predicate = opts.get("predicate")
        if subject is not None and predicate is not None:
            facts = self.store.current(persona_id, subject, predicate)
        else:
            facts = self.store.rank(persona_id, k=k)
        return {"warm": warm, "graph": graph, "facts": facts}

    def _guard(self) -> None:
        if not self.enabled:
            raise StagingDisabled(
                "NOX_MIND_V41_STAGING is off; S03 adapter did not touch bi-temporal, warm cache, or graph memory"
            )
