"""A.1 · Autonomous initiative / lessons bridge for EXISTING NOX EXPRESS INTEGRATOR.

ONE existing OneHost idle tick; no new thread, model, crawler, SQLite database,
network transport, permissions, executable loader or live-source modification.
Invokes the ALREADY EXISTING WormAutopilot and NativeIdeaLoop and writes only
native-owner-attested proposals to the ORIGINAL S03 actor via readback port.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Callable

from .worms import WormHold
from .a1_official_catalog import probe_official_catalog

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_HEAD = re.compile(r"[0-9a-f]{40}\Z")
_ERROR = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{3,127}\Z")
MAX_NATIVE_LESSONS_PER_TICK = 4
MAX_NATIVE_LESSONS_PER_DAY = 24
MAX_NATIVE_LESSON_SOURCE_BYTES = 2048


class A1InitiativeBridge:
    """Native-lifecycle adapter, NOT an alternative autonomous agent service.

    All callbacks must be bound to the original authenticated OneHost/S03 owner.
    A model or website cannot supply authorization, owner identity, or receipts.
    """
    def __init__(self, *, worm_autopilot, idea_loop,
                 native_authorize: Callable, native_stop: Callable,
                 native_stop_epoch: Callable, current_source_head: Callable,
                 native_s03_recent_lessons: Callable, native_verify_lesson: Callable,
                 native_s03_append_readback: Callable,
                 native_catalog_queries=None, catalog_fetch_json=None):
        callbacks = (native_authorize, native_stop, native_stop_epoch,
                     current_source_head, native_s03_recent_lessons,
                     native_verify_lesson, native_s03_append_readback)
        if (not all(callable(x) for x in callbacks) or
                not all(callable(getattr(worm_autopilot, x, None))
                        for x in ("boot", "tick", "status")) or
                not all(callable(getattr(idea_loop, x, None))
                        for x in ("tick", "status"))):
            raise WormHold("A1_EXISTING_ONEHOST_PORTS_REQUIRED")
        self._worms, self._ideas = worm_autopilot, idea_loop
        self._authorize, self._stop = native_authorize, native_stop
        self._epoch, self._head = native_stop_epoch, current_source_head
        self._lessons, self._verify, self._save = (
            native_s03_recent_lessons, native_verify_lesson,
            native_s03_append_readback)
        if (native_catalog_queries is None) != (catalog_fetch_json is None) or (
                native_catalog_queries is not None and
                (not callable(native_catalog_queries) or not callable(catalog_fetch_json))):
            raise WormHold("A1_CATALOG_NATIVE_CALLBACK_PAIR_REQUIRED")
        self._catalog_queries, self._catalog_fetch = native_catalog_queries, catalog_fetch_json
        self._catalog_seen = set()
        self._catalog_saved = 0
        self._session = None
        self._boot_head = None
        self._day = None
        self._seen = set()
        self._saved_today = 0

    @staticmethod
    def _clock(now):
        if not isinstance(now, datetime) or now.tzinfo is None:
            raise WormHold("A1_AWARE_CLOCK_REQUIRED")
        return now.astimezone(timezone.utc)

    def _live(self, session, epoch, head, action):
        try:
            if (self._stop() is not False or self._epoch() != epoch or
                    self._head() != head or
                    self._authorize(session, action) is not True):
                raise WormHold("A1_STOP_OR_POLICY_OR_HEAD_CHANGED")
        except WormHold:
            raise
        except Exception as exc:
            raise WormHold("A1_NATIVE_PORT_UNAVAILABLE") from exc

    def _snapshot(self, state, *, reason=None, worm=None, ideas=None):
        return {"schema": "NOX-A1-INITIATIVE-SOURCE-v1", "state": state,
                "reason": reason, "source_head": self._boot_head,
                "verified_lesson_proposals_saved_today": self._saved_today,
                "reviewed_catalog_candidates_saved_today": self._catalog_saved,
                "lesson_daily_cap": MAX_NATIVE_LESSONS_PER_DAY,
                "worm": worm, "ideas": ideas,
                "production_code_changed": False, "weights_updated": False,
                "models_installed": False, "native_windows_e07": False}

    def boot(self, session, *, now):
        """Reuse original boot, never treat a planned agenda as a fetched source."""
        self._clock(now)
        try:
            epoch = self._epoch()
            head = self._head()
            if type(epoch) is not int or epoch < 0 or not isinstance(head, str) or not _HEAD.fullmatch(head):
                raise WormHold("A1_NATIVE_HEAD_OR_STOP_EPOCH_REQUIRED")
            self._live(session, epoch, head, "evolution.autonomy.read")
            if self._session is not None and (session != self._session or head != self._boot_head):
                raise WormHold("A1_BOOT_SCOPE_OR_HEAD_CHANGED")
            status = self._worms.boot(session, now=now)
            self._live(session, epoch, head, "evolution.autonomy.read")
            if status.get("state") != "RESEARCH_READY_FOR_EXISTING_IDLE_TICK":
                return self._snapshot("HOLD", reason=status.get("state"), worm=status)
            self._session = session
            self._boot_head = head
            return self._snapshot("READY_FOR_EXISTING_IDLE_TICK", worm=status)
        except WormHold as exc:
            return self._snapshot("HOLD", reason=str(exc))

    def _proof_candidate(self, lesson, session, head):
        if not isinstance(lesson, dict) or set(lesson) != {
            "schema", "error_id", "source_head", "cause", "fix",
            "regression_sha256", "source_sha256", "state"}:
            raise WormHold("A1_LESSON_SCHEMA_HOLD")
        if (lesson["schema"] != "NOX-S03-NATIVE-ERROR-LESSON-v1" or
                lesson["state"] != "NATIVE_REGRESSION_VERIFIED" or
                lesson["source_head"] != head or
                not isinstance(lesson["error_id"], str) or
                not _ERROR.fullmatch(lesson["error_id"]) or
                not all(isinstance(lesson[k], str) and _SHA.fullmatch(lesson[k])
                        for k in ("regression_sha256", "source_sha256")) or
                not all(isinstance(lesson[k], str) and 8 <= len(lesson[k].encode("utf-8"))
                        <= MAX_NATIVE_LESSON_SOURCE_BYTES and "\x00" not in lesson[k]
                        for k in ("cause", "fix"))):
            raise WormHold("A1_UNVERIFIED_ERROR_LESSON")
        proof = {"error_id": lesson["error_id"],
                 "source_head": head,
                 "regression_sha256": lesson["regression_sha256"],
                 "source_sha256": lesson["source_sha256"]}
        if self._verify(session, proof) is not True:
            raise WormHold("A1_NATIVE_REGRESSION_RECEIPT_REQUIRED")
        canonical = json.dumps([head, proof["error_id"],
                                proof["regression_sha256"], proof["source_sha256"]],
                               separators=(",", ":"), ensure_ascii=False)
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return {"schema": "NOX-A1-COMPETENCY-CANDIDATE-v1",
                "candidate_sha256": digest, "source_head": head,
                "error_id": lesson["error_id"],
                "cause": lesson["cause"], "proposed_prevention": lesson["fix"],
                "regression_sha256": lesson["regression_sha256"],
                "source_sha256": lesson["source_sha256"],
                "state": "OWNER_REVIEW_REQUIRED",
                "skill_installed": False, "code_merged": False,
                "model_trained": False}

    def tick(self, session, *, now):
        """One bounded owner-initiated tick: research -> P02 ideas -> lessons.

        A report is a receipt of attempted work, not a claim of installed AI.
        """
        clock = self._clock(now)
        if session != self._session or self._boot_head is None:
            return self._snapshot("HOLD", reason="A1_NATIVE_BOOT_REQUIRED")
        head = self._boot_head
        try:
            epoch = self._epoch()
            if type(epoch) is not int or epoch < 0:
                raise WormHold("A1_NATIVE_STOP_EPOCH_REQUIRED")
            self._live(session, epoch, head, "evolution.autonomy.read")
            date = clock.date().isoformat()
            if self._day != date:
                self._day, self._saved_today = date, 0
                self._catalog_saved = 0
                self._seen.clear()
                self._catalog_seen.clear()
            worms = self._worms.tick(session, now=now)
            self._live(session, epoch, head, "evolution.autonomy.read")
            if worms.get("status") != "READY_FOR_NATIVE_APPROVED_TICK":
                return self._snapshot("HOLD", reason=worms.get("reason", "WORMS_NOT_READY"), worm=worms)
            ideas = self._ideas.tick(session, now=now)
            self._live(session, epoch, head, "evolution.autonomy.read")
            if ideas.get("schema") != "NOX-GROWTH-AUTONOMOUS-IDEAS-v1":
                raise WormHold("A1_ORIGINAL_P02_IDEA_RECEIPT_REQUIRED")
            # Reuse A3's original audited no-redirect JSON fetch, not another
            # network adapter. The original signed owner chooses exact names.
            if self._catalog_queries is not None:
                self._live(session, epoch, head, "worm.official_catalog.read")
                queries = self._catalog_queries(session, head)
                catalog = probe_official_catalog(
                    session, queries, source_head=head, current_head=self._head,
                    authorize=self._authorize, native_stop=self._stop,
                    fetch_json=self._catalog_fetch)
                self._live(session, epoch, head, "worm.official_catalog.read")
                for observation in catalog["candidates"]:
                    if observation["source_id"] in self._catalog_seen:
                        continue
                    self._live(session, epoch, head, "worm.official_catalog.read")
                    if self._save(session, observation) is not True:
                        raise WormHold("A1_CATALOG_S03_READBACK_REQUIRED")
                    self._live(session, epoch, head, "worm.official_catalog.read")
                    self._catalog_seen.add(observation["source_id"])
                    self._catalog_saved += 1
            lessons = self._lessons(session, head)
            if not isinstance(lessons, list) or len(lessons) > 64:
                raise WormHold("A1_BOUNDED_S03_LESSONS_REQUIRED")
            admitted = 0
            for item in lessons:
                if admitted >= MAX_NATIVE_LESSONS_PER_TICK or self._saved_today >= MAX_NATIVE_LESSONS_PER_DAY:
                    break
                self._live(session, epoch, head, "evolution.competency.propose")
                candidate = self._proof_candidate(item, session, head)
                if candidate["candidate_sha256"] in self._seen:
                    continue
                self._live(session, epoch, head, "evolution.competency.propose")
                if self._save(session, candidate) is not True:
                    raise WormHold("A1_ORIGINAL_S03_READBACK_REQUIRED")
                self._live(session, epoch, head, "evolution.competency.propose")
                self._seen.add(candidate["candidate_sha256"])
                admitted += 1
                self._saved_today += 1
            return self._snapshot("SOURCE_CYCLE_COMPLETED_NOT_INSTALLED", worm=worms, ideas=ideas)
        except WormHold as exc:
            return self._snapshot("HOLD", reason=str(exc))
        except Exception:
            return self._snapshot("HOLD", reason="A1_NATIVE_CALLBACK_OR_RUNTIME_HOLD")
