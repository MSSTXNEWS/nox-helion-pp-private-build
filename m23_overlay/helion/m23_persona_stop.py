"""M2.3 persona history buckets and the physical STOP late-write guard.

The old failure mode kept one shared list. Switching the visible persona did
not partition that list, so another persona's lines were shown and a write
landed in the same list. Buckets are keyed by the canonical five PersonaIDs
and persisted in SQLite. Nothing here is a live model call.
"""
from __future__ import annotations

from datetime import datetime, timezone
import sqlite3
import threading
from pathlib import Path

from helion.personas import get_persona

MAX_BODY = 8000
ROLES = frozenset({'user', 'assistant', 'memory'})
# verified_local_reply is accepted only when a caller already holds a runtime
# flag. A bare "live_ai" source is rejected so this module cannot mint a
# LIVE claim.
SOURCES = frozenset({'owner_input', 'owner_memory', 'stub_callback_not_live_ai',
                     'verified_local_reply'})


def legacy_shared_transcript(turns, persona_id):
    """Historical failure mode: one list, the persona argument is ignored.

    Kept so tests can prove the leak. Production reads must use
    ``PersonaBuckets.history`` instead.
    """
    if not isinstance(persona_id, str) or not persona_id:
        raise ValueError('persona_required')
    return list(turns)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')


def _body(text: str) -> str:
    if not isinstance(text, str):
        raise ValueError('invalid_body')
    cleaned = text.strip()
    if not cleaned or len(cleaned) > MAX_BODY:
        raise ValueError('invalid_body')
    return cleaned


class PersonaBuckets:
    """One SQLite file, many persona partitions. Never a shared transcript."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS persona_bucket_turns (
                id INTEGER PRIMARY KEY,
                persona_id TEXT NOT NULL,
                role TEXT NOT NULL,
                body TEXT NOT NULL,
                generation INTEGER NOT NULL,
                source TEXT NOT NULL,
                created_utc TEXT NOT NULL
            )''')
            conn.execute('''CREATE INDEX IF NOT EXISTS idx_persona_bucket
                ON persona_bucket_turns(persona_id, id)''')

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA journal_mode=WAL')
        return conn

    def append(self, persona_id: str, role: str, body: str, *,
               generation: int, source: str) -> int:
        persona = get_persona(persona_id)
        if role not in ROLES:
            raise ValueError('invalid_role')
        if source not in SOURCES or source == 'live_ai':
            raise ValueError('invalid_source')
        if type(generation) is not int or generation < 0:
            raise ValueError('invalid_generation')
        text = _body(body)
        with self._connect() as conn:
            cursor = conn.execute(
                '''INSERT INTO persona_bucket_turns
                   (persona_id, role, body, generation, source, created_utc)
                   VALUES (?,?,?,?,?,?)''',
                (persona.persona_id, role, text, generation, source, _utc_now()))
            return int(cursor.lastrowid)

    def history(self, persona_id: str) -> list[dict]:
        persona = get_persona(persona_id)
        with self._connect() as conn:
            rows = conn.execute(
                '''SELECT id, persona_id, role, body, generation, source, created_utc
                   FROM persona_bucket_turns WHERE persona_id=? ORDER BY id''',
                (persona.persona_id,)).fetchall()
        return [dict(row) for row in rows]

    def counts(self) -> dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute(
                '''SELECT persona_id, COUNT(*) AS n FROM persona_bucket_turns
                   GROUP BY persona_id''').fetchall()
        return {row['persona_id']: int(row['n']) for row in rows}


class TurnGate:
    """Per-visible-persona turns plus a STOP latch that rejects late writes."""

    def __init__(self, path: str | Path):
        self.buckets = PersonaBuckets(path)
        self._lock = threading.RLock()
        self.generation = 0
        self.halted = False
        self.input_enabled = True
        self.visible_persona = get_persona('persona.kairen_voss').persona_id
        self.inflight: tuple[str, int] | None = None
        self.blocked: set[tuple[str, int]] = set()
        self.late_rejects = 0
        self.resume_count = 0
        self.last_source: str | None = None

    def chips(self) -> dict:
        """Status the HUD is allowed to display. Never a LIVE AI claim."""
        with self._lock:
            if self.halted:
                state = 'HALTED'
            elif self.inflight is not None:
                state = 'IN_FLIGHT'
            elif self.input_enabled:
                state = 'READY'
            else:
                state = 'HOLD'
            if self.last_source == 'verified_local_reply':
                ai = 'LOCAL_REPLY'
            else:
                ai = 'NOT_LIVE'
            return {
                'state': state,
                'ai': ai,
                'input': 'ENABLED' if self.input_enabled and not self.halted else 'DISABLED',
                'persona_id': self.visible_persona,
                'history_count': len(self.buckets.history(self.visible_persona)),
                'late_rejects': self.late_rejects,
                'halted': self.halted,
                'inflight': self.inflight is not None,
                'live_ai': False,
            }

    def switch_persona(self, persona_id: str) -> list[dict]:
        """Show only this persona. Do not copy, clear, or write other buckets."""
        persona = get_persona(persona_id)
        with self._lock:
            if self.inflight is not None:
                self.blocked.add(self.inflight)
                self.inflight = None
                self.late_rejects += 1
                if not self.halted:
                    self.input_enabled = True
            self.visible_persona = persona.persona_id
        return self.buckets.history(persona.persona_id)

    def record_user(self, persona_id: str, text: str) -> int:
        with self._lock:
            self._require_send(persona_id)
            return self.buckets.append(
                persona_id, 'user', text, generation=self.generation,
                source='owner_input')

    def remember(self, persona_id: str, note: str) -> int:
        with self._lock:
            self._require_send(persona_id)
            return self.buckets.append(
                persona_id, 'memory', note, generation=self.generation,
                source='owner_memory')

    def begin_turn(self, persona_id: str, user_text: str) -> int:
        """Open one in-flight slot after storing the owner line for this persona."""
        with self._lock:
            self._require_send(persona_id)
            if self.inflight is not None:
                raise PermissionError('stop_blocks_send')
            self.generation += 1
            generation = self.generation
            self.buckets.append(
                persona_id, 'user', user_text, generation=generation,
                source='owner_input')
            self.inflight = (get_persona(persona_id).persona_id, generation)
            self.input_enabled = False
            return generation

    def arm_inflight(self, persona_id: str, generation: int) -> None:
        """Mark a shell request in-flight without inventing an assistant line."""
        if type(generation) is not int or generation < 1:
            raise ValueError('invalid_generation')
        with self._lock:
            self._require_send(persona_id)
            if self.inflight is not None:
                raise PermissionError('stop_blocks_send')
            persona = get_persona(persona_id).persona_id
            self.inflight = (persona, generation)
            self.input_enabled = False
            if generation > self.generation:
                self.generation = generation

    def invalidate_inflight(self) -> None:
        """Cancel the open slot. Does not latch HALTED and does not append."""
        with self._lock:
            if self.inflight is not None:
                self.blocked.add(self.inflight)
                self.inflight = None
            if not self.halted:
                self.input_enabled = True

    def halt(self) -> dict:
        """Physical STOP. The in-flight generation can never be appended later."""
        with self._lock:
            cancelled = None
            if self.inflight is not None:
                cancelled = self.inflight[1]
                self.blocked.add(self.inflight)
                self.inflight = None
            self.halted = True
            self.input_enabled = False
            self.generation += 1
            return {
                'state': 'HALTED',
                'cancelled_generation': cancelled,
                'live_ai': False,
            }

    def allow_assistant_write(self, persona_id: str, generation: int) -> bool:
        key = (get_persona(persona_id).persona_id, int(generation))
        with self._lock:
            if self.halted or key in self.blocked:
                return False
            if self.inflight is None:
                return True
            return self.inflight == key

    def try_commit_assistant(self, persona_id: str, text: str, generation: int, *,
                             source: str) -> bool:
        """Append an assistant line only for the still-open slot.

        Returns False when STOP, a persona switch, or a stale generation has
        already closed the slot. False means the text was not stored.
        """
        if source == 'live_ai' or source not in ('stub_callback_not_live_ai',
                                                 'verified_local_reply'):
            with self._lock:
                self.late_rejects += 1
            return False
        persona = get_persona(persona_id).persona_id
        key = (persona, int(generation))
        with self._lock:
            if (self.halted or self.inflight != key or key in self.blocked
                    or persona != self.visible_persona):
                self.late_rejects += 1
                if self.inflight is not None:
                    self.blocked.add(self.inflight)
                    self.inflight = None
                return False
            self.buckets.append(
                persona, 'assistant', text, generation=int(generation), source=source)
            self.inflight = None
            self.input_enabled = True
            self.last_source = source
            return True

    def settle_without_reply(self, persona_id: str, generation: int) -> None:
        """Close a slot that finished without a proven assistant line."""
        persona = get_persona(persona_id).persona_id
        key = (persona, int(generation))
        with self._lock:
            if self.inflight != key:
                return
            self.inflight = None
            if not self.halted:
                self.input_enabled = True

    def resume(self) -> dict:
        with self._lock:
            if self.inflight is not None:
                raise PermissionError('inflight_still_active')
            self.halted = False
            self.input_enabled = True
            self.resume_count += 1
            return {
                'state': 'READY',
                'input': 'ENABLED',
                'resume_count': self.resume_count,
                'live_ai': False,
            }

    def _require_send(self, persona_id: str) -> None:
        if self.halted or not self.input_enabled:
            raise PermissionError('stop_blocks_send')
        persona = get_persona(persona_id).persona_id
        if persona != self.visible_persona:
            raise PermissionError('persona_mismatch')
