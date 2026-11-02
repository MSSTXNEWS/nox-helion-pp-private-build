"""Trusted OneHost command adapter for the existing A.1 owner hooks.

Only the original NativeIngress and WPF consent path may invoke this object.
This module does not create another agent, model, store, timer or dispatcher.
A valid installed Windows run is NOT implied by successful source tests.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Callable

_ACTIONS = frozenset({'selfbuilder.a1.status', 'selfbuilder.a1.boot', 'selfbuilder.a1.tick'})
_HEAD = re.compile(r'^[0-9a-f]{40}$')


class A1NativeHold(PermissionError):
    pass


class A1NativeCommand:
    """Original native owner controls single binding, boot, idle tick and STOP.

    `components` is a PRIVATE Windows/native-owned callback returning the two
    already-existing A.1/FirstBoot objects. Never pass a renderer JSON factory.
    `consent` is the actual owner decision, not browser supplied data.
    `authorize` is the original current-SID/ACL/stop-epoch grant callback.
    """

    def __init__(self, *, builder, components: Callable, consent: Callable,
                 authorize: Callable, stopped: Callable,
                 stop_epoch: Callable, source_head: Callable):
        methods = ('bind_native_megapat_a', 'native_a_boot', 'native_a_tick')
        if (not all(callable(getattr(builder, key, None)) for key in methods)
                or not all(callable(v) for v in
                    (components, consent, authorize, stopped, stop_epoch, source_head))):
            raise A1NativeHold('A1_EXISTING_NATIVE_OWNER_PORTS_REQUIRED')
        self._builder = builder
        self._components = components
        self._consent = consent
        self._authorize = authorize
        self._stopped = stopped
        self._epoch = stop_epoch
        self._head = source_head
        self._owner_scope = None
        self._bound = False
        self._binding_verified = False
        self._boot_receipt = None
        self._bound_head = None
        self._bound_epoch = None
        self._last_tick = None

    @staticmethod
    def _scope(session):
        validate = getattr(session, 'validate', None)
        if not callable(validate):
            raise A1NativeHold('A1_NATIVE_SESSION_REQUIRED')
        validate()
        scope = tuple(getattr(session, x, None) for x in
                      ('tenant', 'principal', 'chat_id'))
        if any(type(x) is not str or not 1 <= len(x) <= 128 for x in scope):
            raise A1NativeHold('A1_NATIVE_OWNER_SCOPE_REQUIRED')
        return scope

    @staticmethod
    def _utc(now):
        if not isinstance(now, datetime) or now.tzinfo is None:
            raise A1NativeHold('A1_NATIVE_UTC_CLOCK_REQUIRED')
        return now.astimezone(timezone.utc)

    def _gate(self, session, action):
        if self._stopped() is not False:
            raise A1NativeHold('A1_NATIVE_STOP_OR_UNKNOWN')
        epoch = self._epoch()
        head = self._head()
        if (type(epoch) is not int or epoch < 0 or
                type(head) is not str or not _HEAD.fullmatch(head)):
            raise A1NativeHold('A1_NATIVE_EPOCH_OR_SOURCE_HOLD')
        if self._authorize(session, action) is not True:
            raise A1NativeHold('A1_NATIVE_ACL_OR_CONSENT_HOLD')
        # Native authorization can synchronously observe STOP or a source
        # change. Never return a lease bound to the pre-approval epoch/HEAD.
        if (self._stopped() is not False or self._epoch() != epoch or
                self._head() != head):
            raise A1NativeHold('A1_NATIVE_STOP_OR_HEAD_CHANGED_DURING_AUTH')
        return epoch, head

    def invoke(self, session, payload, *, now):
        now = self._utc(now)
        if type(payload) is not dict or set(payload) != {'action'}:
            raise A1NativeHold('A1_NATIVE_EXACT_COMMAND_REQUIRED')
        action = payload['action']
        if type(action) is not str or action not in _ACTIONS:
            raise A1NativeHold('A1_NATIVE_COMMAND_NOT_APPROVED')
        scope = self._scope(session)
        if self._owner_scope is not None and scope != self._owner_scope:
            raise A1NativeHold('A1_NATIVE_CROSS_OWNER_DENIED')

        if action == 'selfbuilder.a1.status':
            # Status does not invoke code, models, web providers or write to S03.
            current = self._stopped() is False
            valid = (current and self._bound and self._owner_scope == scope
                     and self._epoch() == self._bound_epoch
                     and self._head() == self._bound_head)
            if valid:
                try:
                    valid = self._authorize(session, 'evolution.autonomy.read') is True
                except Exception:
                    valid = False  # Read-only status remains available as HOLD.
            return {
                'schema': 'NOX-A1-NATIVE-COMMAND-STATUS-v1',
                'state': ('ACTIVE_NATIVE_BOOT_RECEIPT' if valid and
                          self._boot_receipt is not None and
                          self._boot_receipt.get('state') ==
                          'READY_FOR_EXISTING_IDLE_TICK' else 'HOLD'),
                'native_bound': bool(valid and self._binding_verified),
                'boot_state': self._boot_receipt.get('state') if valid and
                              self._boot_receipt else 'NOT_VERIFIED',
                'last_tick_state': self._last_tick.get('state') if valid and
                                   isinstance(self._last_tick, dict) else None,
                'installed_windows_e07': False,
                'production_merged_by_this_command': False,
            }

        if action == 'selfbuilder.a1.boot':
            if self._bound:
                raise A1NativeHold('A1_NATIVE_ALREADY_BOUND_NO_DOUBLE_BOOT')
            # Fresh, real, trusted WPF consent mandatory before instantiating.
            if self._consent(session, action) is not True:
                raise A1NativeHold('A1_FRESH_NATIVE_WPF_CONSENT_REQUIRED')
            epoch, head = self._gate(session, 'evolution.autonomy.read')
            # Reserve this owner/HEAD/STOP epoch BEFORE any native factory or
            # builder callback can partially bind and raise (or re-enter boot).
            # Recovery requires a new authenticated OneHost session, not replay.
            self._bound = True
            self._owner_scope = scope
            self._bound_epoch = epoch
            self._bound_head = head
            owner_components = self._components(session)
            if (type(owner_components) is not dict or
                    set(owner_components) != {'initiative_bridge', 'firstboot'}):
                raise A1NativeHold('A1_ORIGINAL_NATIVE_COMPONENTS_REQUIRED')
            if (self._stopped() is not False or self._epoch() != epoch or
                    self._head() != head or
                    self._authorize(session, 'evolution.autonomy.read') is not True):
                raise A1NativeHold('A1_STOP_OR_HEAD_CHANGED_BEFORE_BIND')
            result = self._builder.bind_native_megapat_a(
                session, initiative_bridge=owner_components['initiative_bridge'],
                firstboot=owner_components['firstboot'])
            if (not isinstance(result, dict) or
                    result.get('state') != 'PORTS_BOUND_AWAITING_NATIVE_STARTUP'):
                raise A1NativeHold('A1_ORIGINAL_BUILDER_BINDING_NOT_PROVEN')
            # Only the original builder's exact receipt proves native binding.
            if self._gate(session, 'evolution.autonomy.read') != (epoch, head):
                raise A1NativeHold('A1_STOP_OR_HEAD_CHANGED_BEFORE_BOOT')
            self._binding_verified = True
            boot = self._builder.native_a_boot(session, now=now)
            if not isinstance(boot, dict) or boot.get('schema') != 'NOX-A-NATIVE-BOOT-v1':
                raise A1NativeHold('A1_ORIGINAL_BOOT_RECEIPT_REQUIRED')
            if (self._stopped() is not False or self._epoch() != epoch or
                    self._head() != head or
                    self._authorize(session, 'evolution.autonomy.read') is not True):
                raise A1NativeHold('A1_BOOT_REVOKED_RECHECK_S03')
            self._boot_receipt = boot
            return {**boot, 'installed_windows_e07': False}

        # Tick is allowed ONLY on an authenticated scope with a still-live boot.
        if not self._bound or self._boot_receipt is None or \
           self._boot_receipt.get('state') != 'READY_FOR_EXISTING_IDLE_TICK':
            raise A1NativeHold('A1_NATIVE_BOOT_NOT_READY')
        epoch, head = self._gate(session, 'evolution.autonomy.read')
        if epoch != self._bound_epoch or head != self._bound_head:
            raise A1NativeHold('A1_NATIVE_REBOOT_REQUIRED_AFTER_CHANGE')
        result = self._builder.native_a_tick(session, now=now)
        if (self._stopped() is not False or self._epoch() != epoch or
                self._head() != head or
                self._authorize(session, 'evolution.autonomy.read') is not True):
            raise A1NativeHold('A1_NATIVE_TICK_REVOKED_S03_READBACK_REQUIRED')
        if not isinstance(result, dict) or result.get('schema') != 'NOX-A1-INITIATIVE-SOURCE-v1':
            raise A1NativeHold('A1_ORIGINAL_TICK_RECEIPT_REQUIRED')
        self._last_tick = result
        return {**result, 'installed_windows_e07': False}
