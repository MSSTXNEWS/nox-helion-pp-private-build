"""Bounded real P02 brainstorming for NOX roles using S03 research receipts.

No second LLM, no background thread or second storage. Native owner injects
a trusted retrieval callback and a receipt-verified S03 candidate writer.
Scheduled by the EXISTING OneHost idle loop after worm source ingestion.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime, timezone
from typing import Callable

from .worms import ROLES, WormHold
from .growth_sandbox import design_brief, generate_ideas

MAX_P02_CALLS_PER_TICK = 2
MAX_P02_CALLS_PER_DAY = 24
MAX_S03_REVIEW_CANDIDATES_PER_DAY = 96


class NativeIdeaLoop:
    def __init__(self, *, authorized: Callable, source_head: Callable,
                 s03_verified_observations: Callable,
                 p02_model_propose: Callable, s03_save_candidate_readback: Callable,
                 native_stop: Callable):
        funcs = (authorized, source_head, s03_verified_observations,
                 p02_model_propose, s03_save_candidate_readback, native_stop)
        if not all(callable(x) for x in funcs):
            raise WormHold("GROWTH_EXISTING_P02_S03_NATIVE_PORTS_REQUIRED")
        self._authorized = authorized
        self._head = source_head
        self._observed = s03_verified_observations
        self._model = p02_model_propose
        self._save = s03_save_candidate_readback
        self._stop = native_stop
        self._day = None
        self._calls = 0
        self._saved = 0
        self._processed = set()
        self._owner_session = None

    def tick(self, session, *, now, max_calls=MAX_P02_CALLS_PER_TICK):
        if not isinstance(now, datetime) or now.tzinfo is None or \
           type(max_calls) is not int or not 1 <= max_calls <= MAX_P02_CALLS_PER_TICK:
            raise WormHold("GROWTH_BOUNDED_IDEA_TICK_REQUIRED")
        if self._stop() is not False or self._authorized(session, "worm.brainstorm.read") is not True:
            return self.status(reason="NATIVE_STOP_OR_POLICY_DENIED")
        # One authenticated native owner per runtime: no cross-tenant quota/dedupe.
        if self._owner_session is None:
            self._owner_session = session
        elif session != self._owner_session:
            raise WormHold("GROWTH_NATIVE_SESSION_SCOPE_CHANGED")
        day = now.astimezone(timezone.utc).date().isoformat()
        if day != self._day:
            self._day = day
            self._calls = self._saved = 0
            self._processed.clear()
        head = self._head()
        rows = self._observed(session)
        if not isinstance(rows, list) or len(rows) > 120:
            raise WormHold("GROWTH_S03_RESEARCH_EVIDENCE_REQUIRED")
        # Research may be empty during offline boot: no dummy ideas or calls.
        if not rows:
            return self.status(reason="NO_VERIFIED_EVIDENCE_YET")
        by_role = defaultdict(list)
        for row in rows:
            if (not isinstance(row, dict) or
                    row.get("schema") != "NOX-WORM-SOURCE-OBSERVATION-v1" or
                    row.get("status") != "SOURCE_OBSERVED_REVIEW_REQUIRED"):
                raise WormHold("GROWTH_UNTRUSTED_S03_ROW")
            role = row.get("core_id")
            if role not in ROLES:
                raise WormHold("GROWTH_UNKNOWN_CORE")
            by_role[role].append(row)
        for role in ROLES:
            if max_calls <= 0 or self._calls >= MAX_P02_CALLS_PER_DAY or \
               self._saved >= MAX_S03_REVIEW_CANDIDATES_PER_DAY:
                break
            observations = by_role.get(role)
            if not observations:
                continue
            # One idea generation per exact (HEAD, role, observed source set).
            subset = observations[:24]
            key = (head, role, tuple(x.get("source_sha256") for x in subset))
            if key in self._processed:
                continue
            if self._stop() is not False or self._authorized(session, "worm.brainstorm.read") is not True:
                return self.status(reason="NATIVE_STOP_OR_POLICY_DENIED")
            brief = design_brief(role, subset, source_head=head)
            # The original P02 adapter is invoked only by native owner.
            ideas = generate_ideas(brief, self._model, subset,
                                   authorize=self._authorized, session=session, limit=8)
            self._calls += 1
            max_calls -= 1
            if (self._stop() is not False or self._head() != head or
                    self._authorized(session, "worm.brainstorm.read") is not True):
                return self.status(reason="NATIVE_STOP_HEAD_OR_GRANT_CHANGED_AFTER_P02")
            # Candidate generation does not change installed menu, weights or EXE.
            for c in ideas:
                if (self._stop() is not False or self._head() != head or
                        self._authorized(session, "worm.candidate.persist") is not True):
                    return self.status(reason="NATIVE_STOP_HEAD_OR_GRANT_CHANGED_BEFORE_S03")
                if self._saved >= MAX_S03_REVIEW_CANDIDATES_PER_DAY:
                    break
                if self._save(session, c) is not True:
                    raise WormHold("GROWTH_S03_CANDIDATE_READBACK_REQUIRED")
                # The callback may durably commit while STOP/reset arrives.
                # Do not claim success or consume dedupe after the boundary.
                if (self._stop() is not False or self._head() != head or
                        self._authorized(session, "worm.candidate.persist") is not True):
                    return self.status(reason="S03_COMMIT_AFTER_REVOKE_READBACK_REQUIRED")
                self._saved += 1
            self._processed.add(key)
        return self.status()

    def status(self, *, reason=None):
        return {
            "schema": "NOX-GROWTH-AUTONOMOUS-IDEAS-v1",
            "day": self._day, "p02_calls": self._calls,
            "p02_limit": MAX_P02_CALLS_PER_DAY,
            "review_candidates_saved": self._saved,
            "max_review_candidates": MAX_S03_REVIEW_CANDIDATES_PER_DAY,
            "distinct_p02_groups": len(self._processed),
            "state": "RESEARCH_IDEAS_ONLY_NOT_INSTALLED",
            "reason": reason,
            "menu_changed": False, "weights_updated": False,
            "self_awareness_proven": False,
        }
