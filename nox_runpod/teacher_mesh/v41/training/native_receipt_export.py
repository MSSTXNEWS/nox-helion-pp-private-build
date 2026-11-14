"""Native OneHost-only evidence exporter; pure, no fake percentage sources.

The callback MUST be installed by the real authenticated NOX runtime and verify
signed/owned receipts and source integrity. Arbitrary web/chat JSON isn't trusted.
"""
from __future__ import annotations
from collections.abc import Callable, Mapping
from .proof_metrics import assess


def verified_dashboard(native_receipts: Callable[[], Mapping], native_verify: Callable[[Mapping], bool]):
    if not callable(native_receipts) or not callable(native_verify):
        return {'state':'HOLD_NATIVE_EVIDENCE_CALLBACKS_MISSING', 'dashboard':None}
    try:
        e = native_receipts()
        if not isinstance(e, Mapping) or native_verify(e) is not True:
            return {'state':'HOLD_UNTRUSTED_NATIVE_EVIDENCE', 'dashboard':None}
        data=assess(dict(e))
        if data.get('source_state')!='SOURCE_READ':
            return {'state':'HOLD_BAD_EVIDENCE_SCHEMA','dashboard':None}
        return {'state':'NATIVE_SOURCE_VERIFIED', 'dashboard':data}
    except Exception:
        return {'state':'HOLD_EVIDENCE_PORT_ERROR','dashboard':None}
