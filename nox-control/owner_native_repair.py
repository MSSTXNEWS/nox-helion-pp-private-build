#!/usr/bin/env python3
"""Legacy workflow syntax-check compatibility only (not the repair entrypoint).

The owner operator in this one-shot branch dispatches exclusively to
owner_live_stream_smoke_oneshot.py. This path is required solely by the
existing workflow's pre-secret py_compile step.
"""
if __name__ == '__main__':
    raise SystemExit('HOLD_LEGACY_REPAIR_SHIM_NOT_EXECUTABLE')
