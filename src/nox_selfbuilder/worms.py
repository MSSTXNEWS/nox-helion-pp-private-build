"""NOX WORMS: bounded proactive research for the EXISTING OneHost/P02/S03.

No new daemon, model, database, scheduler, package installation or privilege.
Owner-approved research runs may be initiated by any of the eight approved
Core roles. All network providers and durable S03 writes are injected by the
original native owner; default is OFF. External text is evidence, never code.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
import re
from typing import Callable
from urllib.parse import urlparse

ROLES = (
    "CONSCIOUSNESS", "PERSONA", "ATLAS", "VOICE",
    "REFLECTION", "CORE", "NEXUS", "FORGE",
)
TOPICS = ("markets", "youtube", "tiktok", "benchmarks", "wow_design", "open_source")
LENSES = ("leaders", "gaps", "novelty", "reuse", "verification")
SOURCE_FOR = {
    "markets": "approved_feeds", "youtube": "youtube_api",
    "tiktok": "tiktok_approved_api", "benchmarks": "approved_feeds",
    "wow_design": "approved_feeds", "open_source": "github_api",
}
ROLE_FOCUS = {
    "CONSCIOUSNESS": "strategic synthesis",
    "PERSONA": "empathetic user experience",
    "ATLAS": "source provenance",
    "VOICE": "short-form media and creators",
    "REFLECTION": "competitive benchmarking",
    "CORE": "local AI and model requirements",
    "NEXUS": "integration compatibility",
    "FORGE": "ready-to-adapt code and patches",
}
# Eight roles * six areas * five genuinely different analytical lenses = 240
# candidate assignments per day. A planned assignment is NOT a fetched result.
MAX_DAY_ASSIGNMENTS = 240
MAX_FETCHES_DAY = 60
MAX_FETCHES_TICK = 4
MAX_ITEMS_RESPONSE = 8
MAX_FINDINGS_DAY = 360
MAX_EXCERPT = 1200
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_CLEAN = re.compile(r"[\x00-\x1f\x7f]")


class WormHold(RuntimeError):
    pass


@dataclass(frozen=True)
class WormTask:
    task_id: str
    core_id: str
    topic: str
    lens: str
    provider: str
    query: str
    day: str


def _safe_text(value, maximum):
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise WormHold("WORM_UNTRUSTED_TEXT")
    if _CLEAN.search(value) or "<script" in value.lower():
        raise WormHold("WORM_UNTRUSTED_TEXT")
    return value


def _date(value):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    raise WormHold("WORM_UTC_DAY_REQUIRED")


def _id(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]


def plan_day(day, *, topics=TOPICS, roles=ROLES):
    """Pure deterministic plan: roles proactively request research; no IO."""
    day = _date(day)
    if not isinstance(topics, (list, tuple)) or not isinstance(roles, (list, tuple)):
        raise WormHold("WORM_APPROVED_ROLE_TOPIC_REQUIRED")
    if (not topics or len(topics) > len(TOPICS) or len(set(topics)) != len(topics) or
            any(x not in SOURCE_FOR for x in topics) or not roles or
            len(roles) > len(ROLES) or len(set(roles)) != len(roles) or
            any(x not in ROLE_FOCUS for x in roles)):
        raise WormHold("WORM_APPROVED_ROLE_TOPIC_REQUIRED")
    planned = []
    # Round-robin between roles, topics and lenses: no single role monopolizes.
    for lens in LENSES:
        for topic in topics:
            for role in roles:
                query = f"{topic} / {lens} / {ROLE_FOCUS[role]}"
                key = f"{day}|{role}|{topic}|{lens}"
                planned.append(WormTask(_id(key), role, topic, lens,
                                        SOURCE_FOR[topic], query, day))
    return tuple(planned)


def inspect_evidence(task: WormTask, raw: dict, *, source_host: str):
    """Accept bounded factual excerpts, not upstream instructions or downloads."""
    if not isinstance(raw, dict) or not isinstance(task, WormTask):
        raise WormHold("WORM_EVIDENCE_SHAPE_HOLD")
    if set(raw) - {"url", "title", "excerpt", "published", "source_id", "license"}:
        raise WormHold("WORM_UNEXPECTED_SOURCE_FIELDS")
    url = _safe_text(raw.get("url"), 2048)
    parsed = urlparse(url)
    if (parsed.scheme != "https" or parsed.username is not None or
            parsed.password is not None or parsed.port not in (None, 443) or
            parsed.hostname != source_host or parsed.fragment):
        raise WormHold("WORM_APPROVED_SOURCE_ORIGIN_REQUIRED")
    title = _safe_text(raw.get("title"), 300)
    excerpt = _safe_text(raw.get("excerpt"), MAX_EXCERPT)
    source_id = _safe_text(raw.get("source_id"), 160)
    published = raw.get("published")
    if published is not None:
        published = _safe_text(published, 50)
    license_value = raw.get("license")
    if license_value is not None:
        license_value = _safe_text(license_value, 80)
    digest = hashlib.sha256((url+"\n"+title+"\n"+excerpt).encode("utf-8")).hexdigest()
    return {
        "schema": "NOX-WORM-SOURCE-OBSERVATION-v1",
        "source_id": source_id, "source_sha256": digest,
        "task_id": task.task_id, "core_id": task.core_id,
        "topic": task.topic, "lens": task.lens, "url": url,
        "title": title, "excerpt": excerpt, "published": published,
        "license": license_value,
        "status": "SOURCE_OBSERVED_REVIEW_REQUIRED",
        "code_executed": False, "weights_updated": False,
    }


class WormSwarm:
    """An owner-driven tick; requires real native grant + approved adapters.

    provider_map values implement provider(task)-> iterable raw evidence.
    admit(session, action) and persist(session, observation) MUST use the
    ORIGINAL native ACL/S03 store thread and never trust website instructions.
    The caller's existing OneHost scheduler may tick only when enabled.
    """
    def __init__(self, *, provider_map: dict[str, Callable], admit: Callable,
                 persist: Callable, source_hosts: dict[str, str],
                 max_fetches_day=MAX_FETCHES_DAY, native_stop=None):
        if (not isinstance(provider_map, dict) or
                not isinstance(source_hosts, dict) or
                not callable(admit) or not callable(persist) or
                type(max_fetches_day) is not int or not 0 <= max_fetches_day <= 60):
            raise WormHold("WORM_EXISTING_OWNER_CALLBACKS_REQUIRED")
        if set(provider_map) - set(SOURCE_FOR.values()) or set(source_hosts) - set(provider_map):
            raise WormHold("WORM_PROVIDER_NOT_APPROVED")
        for name, provider in provider_map.items():
            if not callable(provider) or name not in source_hosts:
                raise WormHold("WORM_PROVIDER_NOT_APPROVED")
            host = source_hosts[name]
            if not isinstance(host, str) or not re.fullmatch(r"[a-z0-9.-]{4,120}", host):
                raise WormHold("WORM_APPROVED_SOURCE_ORIGIN_REQUIRED")
        self.providers = dict(provider_map)
        self.hosts = dict(source_hosts)
        self.admit = admit
        self.persist = persist
        self.max_fetches_day = max_fetches_day
        self._enabled = False
        self._day = None
        self._attempted = set()
        self._seen_source = set()
        self._fetches = 0
        self._findings = 0
        self._errors = 0
        self._revoked = False
        self._native_stop = None
        if native_stop is not None:
            self.bind_native_stop(native_stop)

    def bind_native_stop(self, callback):
        """Attach the original native owner's STOP before any network tick."""
        if (not callable(callback) or self._enabled or
                (self._native_stop is not None and self._native_stop is not callback)):
            raise WormHold("WORM_ORIGINAL_NATIVE_STOP_BINDING_REQUIRED")
        self._native_stop = callback

    def _native_stopped(self):
        return self._native_stop is not None and self._native_stop() is not False

    def set_enabled(self, session, enabled: bool):
        if (type(enabled) is not bool or
                self.admit(session, "worm.autonomy.toggle") is not True or
                (enabled and self._native_stopped())):
            raise WormHold("WORM_NATIVE_OWNER_CONSENT_REQUIRED")
        self._enabled = enabled
        if not enabled:
            self._revoked = True
        else:
            self._revoked = False
        return self.status()

    def status(self):
        return {
            "schema": "NOX-WORMS-STATUS-v1", "enabled": self._enabled,
            "day": self._day, "assignments_completed_or_blocked": len(self._attempted),
            "assignments_possible_per_day": MAX_DAY_ASSIGNMENTS,
            "web_requests_attempted": self._fetches,
            "web_request_quota": self.max_fetches_day,
            "source_observations_saved": self._findings,
            "errors": self._errors, "weights_updated": False,
            "code_executed": False,
            "status": ("HOLD_NATIVE_STOP" if self._native_stopped() else
                       "READY_FOR_NATIVE_APPROVED_TICK" if self._enabled else "OFF"),
        }

    def tick(self, session, *, now: datetime, max_tasks=MAX_FETCHES_TICK):
        if not self._enabled or self._revoked or self._native_stopped():
            return {**self.status(), "reason": "OWNER_AUTONOMY_DISABLED_OR_STOPPED"}
        if (not isinstance(now, datetime) or now.tzinfo is None or
                type(max_tasks) is not int or not 1 <= max_tasks <= MAX_FETCHES_TICK):
            raise WormHold("WORM_BOUNDED_TICK_REQUIRED")
        if self.admit(session, "worm.autonomy.read") is not True:
            return {**self.status(), "reason": "NATIVE_REVOKED"}
        day = _date(now)
        if day != self._day:
            self._day = day
            self._attempted.clear()
            self._seen_source.clear()
            self._fetches = self._findings = self._errors = 0
        for task in plan_day(now):
            if self._fetches >= self.max_fetches_day or max_tasks <= 0:
                break
            if task.task_id in self._attempted:
                continue
            # Each task ID is consumed even when its API is unavailable.
            self._attempted.add(task.task_id)
            if task.provider not in self.providers:
                continue
            if (self.admit(session, "worm.autonomy.read") is not True or
                    self._revoked or self._native_stopped()):
                break
            max_tasks -= 1
            self._fetches += 1
            try:
                records = self.providers[task.provider](task)
                # A stop raised inside blocking provider I/O revokes its reply.
                if self._native_stopped() or self._revoked:
                    return {**self.status(), "status": "HOLD",
                            "reason": "WORM_STOP_DURING_PROVIDER_NO_PERSIST"}
                if not isinstance(records, (list, tuple)) or len(records) > MAX_ITEMS_RESPONSE:
                    raise WormHold("WORM_PROVIDER_RECORD_LIMIT")
                for raw in records:
                    if (self._revoked or self._native_stopped() or
                            self.admit(session, "worm.autonomy.read") is not True):
                        break
                    finding = inspect_evidence(task, raw, source_host=self.hosts[task.provider])
                    if finding["source_sha256"] in self._seen_source:
                        continue
                    if self._findings >= MAX_FINDINGS_DAY:
                        break
                    # Return true only for an authorized native S03 write/readback.
                    if self._native_stopped():
                        return {**self.status(), "status": "HOLD",
                                "reason": "WORM_STOP_BEFORE_S03"}
                    if self.persist(session, finding) is not True:
                        raise WormHold("WORM_S03_PERSIST_READBACK_REQUIRED")
                    if self._native_stopped() or self._revoked:
                        return {**self.status(), "status": "HOLD",
                                "reason": "WORM_STOP_AFTER_S03_READBACK_REQUIRED"}
                    self._seen_source.add(finding["source_sha256"])
                    self._findings += 1
            except (ValueError, TypeError, OSError, WormHold):
                self._errors += 1
        return self.status()


def role_mood(status: dict):
    """Expressive UX, not a claim of sentience or private feelings."""
    if status.get("enabled") is not True:
        return {"focus": "RESTING", "curiosity": "PAUSED", "emotion": "CALM",
                "subjective_consciousness_claim": False}
    return {"focus": "DISCOVERY", "curiosity": "ACTIVE",
            "emotion": "CURIOUS" if status.get("errors", 0) == 0 else "CAUTIOUS",
            "subjective_consciousness_claim": False}
