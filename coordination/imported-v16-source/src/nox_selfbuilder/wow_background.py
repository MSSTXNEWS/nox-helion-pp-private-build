"""Explicitly opt-in BACKGROUND WOW suggestions on the EXISTING OneHost scheduler.

This is a policy/adapter, NOT a new daemon, SQLite connection, model client,
trainer, timer, or installer. Its owner-provided CAS and conditional write must
run inside transactions of the ORIGINAL S03 StoreActor. No auto-code or merge.
"""
from __future__ import annotations

import re
import threading
from datetime import datetime, timedelta, timezone
from typing import Callable

SCHEMA = 'NOX-SELFBUILDER-BACKGROUND-v1'
INTERVAL = timedelta(hours=24)
FAILURE_RETRY = timedelta(minutes=30)
_HEAD = re.compile(r'^[a-f0-9]{40}(?:[a-f0-9]{24})?$')
_SHA = re.compile(r'^[a-f0-9]{64}$')
TASK = ('Review the existing approved NOX MENU V2, UI navigation and known code '
        'defects. Suggest three original, safely testable WOW interface or button '
        'improvements for owner review. Never modify installed files, routes, '
        'D02 art, SEED, S03, model weights, permissions or payments.')

class BackgroundHold(RuntimeError):
    pass


def _utc(now):
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise BackgroundHold('TRUSTED_UTC_CLOCK_REQUIRED')
    return now.astimezone(timezone.utc)


def _state(raw):
    if raw is None:
        return {'schema': SCHEMA, 'enabled': False, 'revision': 0,
                'next_due_at': None, 'last_attempt_at': None}
    if (type(raw) is not dict or raw.get('schema') != SCHEMA or
        type(raw.get('enabled')) is not bool or type(raw.get('revision')) is not int or
        raw['revision'] < 0 or set(raw) !=
        {'schema','enabled','revision','next_due_at','last_attempt_at'}):
        raise BackgroundHold('ORIGINAL_S03_BACKGROUND_STATE_INVALID')
    for field in ('next_due_at','last_attempt_at'):
        if raw[field] is not None:
            if type(raw[field]) is not str or len(raw[field]) > 45:
                raise BackgroundHold('BACKGROUND_TIMESTAMP_INVALID')
            try:
                stamp = datetime.fromisoformat(raw[field].replace('Z','+00:00'))
                _utc(stamp)
            except ValueError as exc:
                raise BackgroundHold('BACKGROUND_TIMESTAMP_INVALID') from exc
    return dict(raw)


def _iso(t):
    return _utc(t).isoformat().replace('+00:00', 'Z')


class BackgroundWowController:
    """One bounded scheduled suggestion per 24 hours of **eligible** foreground host time.

    s03_compare_and_swap(session, expected_revision, replacement)-> bool must
    compare and commit atomically on the ORIGINAL S03 owner thread. A proposal
    commit callback MUST atomically check enabled+revision before writing its
    owner-review receipt; ordinary unguarded audit callbacks are insufficient.
    """
    def __init__(self, *, s03_read: Callable, s03_compare_and_swap: Callable,
                 native_authorize: Callable, native_stop: Callable,
                 native_idle: Callable, current_head: Callable,
                 generate_proposal: Callable, conditional_s03_proposal: Callable,
                 cancel_background: Callable, now_utc: Callable):
        funcs = (s03_read, s03_compare_and_swap, native_authorize, native_stop,
                 native_idle, current_head, generate_proposal,
                 conditional_s03_proposal, cancel_background, now_utc)
        if not all(callable(x) for x in funcs):
            raise ValueError('EXISTING_ONEHOST_S03_P02_SCHEDULER_CALLBACKS_REQUIRED')
        (self.read, self.cas, self.authorize, self.stopped, self.idle,
         self.head, self.generate, self.persist, self.cancel, self.now) = funcs
        self._lock = threading.Lock()
        self._active = False
        self._cancel = threading.Event()

    @staticmethod
    def _session(session):
        if not callable(getattr(session,'validate',None)):
            raise PermissionError('NATIVE_SESSION_REQUIRED')
        session.validate()

    def status(self, session):
        self._session(session)
        state = _state(self.read(session))
        with self._lock:
            active = self._active
        return {'schema':SCHEMA, 'enabled':state['enabled'],
                'status':('STOPPING' if active and not state['enabled'] else
                          'RUNNING' if active else 'ON' if state['enabled'] else 'OFF'),
                'next_due_at':state['next_due_at'],
                'last_attempt_at':state['last_attempt_at'],
                'interval_hours':24, 'requires_owner_review':True,
                'auto_code':False, 'auto_merge':False, 'auto_install':False,
                'source':'ORIGINAL_S03', 'revision':state['revision']}

    def set_enabled(self, session, enabled):
        self._session(session)
        if type(enabled) is not bool:
            raise BackgroundHold('EXPLICIT_BOOLEAN_SWITCH_REQUIRED')
        action = 'selfbuilder.background.enable' if enabled else 'selfbuilder.background.disable'
        if self.authorize(session,action,{'enabled':enabled}) is not True:
            raise PermissionError('NATIVE_BACKGROUND_SWITCH_DENIED')
        # Cancel in-flight background work first. NEVER use global P02 STOP that
        # would kill a separate manual chat or manual programming request.
        with self._lock:
            active = self._active
            if not enabled:
                self._cancel.set()
            elif enabled:
                # A new revision makes any in-flight older attempt invalid.
                # Clear the cancel token so the NEXT eligible tick may run.
                self._cancel.clear()
        if not enabled and active:
            self.cancel(session)   # must target this background request only
        for _ in range(3):
            previous = _state(self.read(session))
            if previous['enabled'] == enabled:
                return self.status(session)
            if self.authorize(session,action,{'enabled':enabled}) is not True:
                raise PermissionError('NATIVE_SWITCH_REVOKED')
            now = _utc(self.now())
            changed = dict(previous, enabled=enabled,
                           revision=previous['revision']+1,
                           next_due_at=(_iso(now) if enabled else None))
            if self.cas(session,previous['revision'],changed) is True:
                actual = self.status(session)
                if actual['enabled'] != enabled or actual['revision'] != changed['revision']:
                    raise BackgroundHold('S03_SWITCH_READBACK_MISMATCH')
                return actual
        raise BackgroundHold('S03_SWITCH_CAS_CONFLICT')

    def _current(self, session, booked_revision, owner_head):
        if self._cancel.is_set() or self.stopped(session):return False
        state=_state(self.read(session))
        return (state['enabled'] and state['revision']==booked_revision and
                self.head(session)==owner_head and _HEAD.fullmatch(owner_head) is not None)

    def tick(self, session):
        """Call on the original background task worker, NEVER the WPF UI thread.

        NO independent thread/timer/process is started here. Native owner must
        call tick only in an idle event-loop; no tick = no background activity.
        """
        self._session(session)
        state=_state(self.read(session))
        if not state['enabled']:
            return {'status':'OFF','proposal_saved':False}
        now=_utc(self.now())
        if state['next_due_at'] is not None and now < _utc(datetime.fromisoformat(
                state['next_due_at'].replace('Z','+00:00'))):
            return {'status':'NOT_DUE','proposal_saved':False}
        if self.stopped(session) or not self.idle(session):
            return {'status':'WAITING_FOR_IDLE','proposal_saved':False}
        owner_head=self.head(session)
        if type(owner_head) is not str or not _HEAD.fullmatch(owner_head):
            return {'status':'HOLD','reason':'MANAGED_SOURCE_HEAD_REQUIRED','proposal_saved':False}
        if self.authorize(session,'selfbuilder.background.run',{'head':owner_head}) is not True:
            return {'status':'HOLD','reason':'PERSISTED_BACKGROUND_CONSENT_REQUIRED','proposal_saved':False}
        with self._lock:
            if self._active or self._cancel.is_set():
                return {'status':'BACKGROUND_BUSY_OR_STOPPED','proposal_saved':False}
            self._active=True
        booked_revision=None
        try:
            booked=dict(state,revision=state['revision']+1,
                        next_due_at=_iso(now+INTERVAL),last_attempt_at=_iso(now))
            if self.cas(session,state['revision'],booked) is not True:
                return {'status':'S03_STATE_CHANGED','proposal_saved':False}
            rev=booked['revision']
            booked_revision=rev
            if not self._current(session,rev,owner_head):
                return {'status':'STOPPED_OR_REVOKED','proposal_saved':False}
            # Same existing P02 client, same S03/ATLAS evidence and R5 validator.
            # Generator is read-only: it must NOT write a proposal on its own.
            proposal=self.generate(session,TASK,lambda:self._current(session,rev,owner_head))
            if not isinstance(proposal,dict) or proposal.get('schema')!='NOX-WOW-DESIGN-REVIEW-v1' or \
                    proposal.get('state')!='OWNER_REVIEW_REQUIRED' or \
                    proposal.get('source_head')!=owner_head or \
                    type(proposal.get('proposal_sha256')) is not str or not _SHA.fullmatch(proposal['proposal_sha256']):
                raise BackgroundHold('VALIDATED_R5_PROPOSAL_REQUIRED')
            if not self._current(session,rev,owner_head):
                return {'status':'STOPPED_OR_REVOKED','proposal_saved':False}
            # CRITICAL: existing S03 owner must re-check enabled+revision
            # *inside its atomic write transaction*. Avoid TOCTOU after OFF.
            if self.persist(session,proposal,rev,owner_head) is not True:
                return {'status':'S03_ATOMIC_CONSENT_REVOKED','proposal_saved':False}
            return {'status':'OWNER_REVIEW_REQUIRED','proposal_saved':True,
                    'proposal_sha256':proposal['proposal_sha256'],
                    'code_generated':False, 'code_installed':False}
        except Exception as exc:
            # On failure, retry later; do not hammer the P02 model while idle.
            try:
                current=_state(self.read(session))
                if current['enabled'] and current['revision']==booked_revision and current['last_attempt_at']==_iso(now):
                    retry=dict(current,revision=current['revision']+1,
                               next_due_at=_iso(now+FAILURE_RETRY))
                    self.cas(session,current['revision'],retry)
            except Exception:
                pass
            return {'status':'HOLD','reason':type(exc).__name__,'proposal_saved':False}
        finally:
            with self._lock:self._active=False