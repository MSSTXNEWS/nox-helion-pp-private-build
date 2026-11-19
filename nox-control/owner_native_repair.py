#!/usr/bin/env python3
"""Legacy workflow syntax-check compatibility only.

The owner GitHub workflow compiles this historical path before executing
owner_native_operator.py. This one-shot branch's FILES['repair'] points only
to owner_safe_cgroup_reclaim_oneshot.py; this shim is never the entrypoint.
"""
if __name__ == '__main__':
    raise SystemExit('HOLD_REPAIR_LEGACY_SHIM_NOT_EXECUTABLE')
