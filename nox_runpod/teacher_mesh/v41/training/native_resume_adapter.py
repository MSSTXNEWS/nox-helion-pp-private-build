"""NOX V40: resume only via existing V37 native_admin signed OneHost callbacks.
Not an SSH proxy, scheduler, trainer or self-executing script.
"""
from __future__ import annotations
from .recovery_plan import build_plan
try:
    from nox_runpod.teacher_mesh.v37.nox_v37.native_admin import dispatch, canonical_request
except ImportError:
    # Source pack can be tested on its own, but no arbitrary fallback is allowed.
    dispatch = canonical_request = None


def propose_or_execute(state, request, *, approved_request_sha=None, host=None):
    plan=build_plan(state)
    if plan['state']!='READY_FOR_EXISTING_NATIVE_APPROVAL':
        return {'state':'HOLD_PREFLIGHT','performed':False,'gate':plan}
    if dispatch is None or canonical_request is None or host is None:
        return {'state':'HOLD_NATIVE_ONEHOST_NOT_BOUND','performed':False,'gate':plan}
    if request.get('action')!='training.resume' or request.get('target_id')!='nox.train.volta':
        return {'state':'HOLD_ACTION_TARGET_NOT_MATCHED','performed':False}
    try:
        return dispatch(request,
            host_authorize=host.authorize, host_stop=host.stop,
            host_inspect=host.inspect,host_approve=host.approve,
            host_execute=host.execute,host_receipt_verify=host.receipt_verify,
            host_readback=host.readback,approved_request_sha=approved_request_sha)
    except (ValueError,AttributeError):
        return {'state':'HOLD_NATIVE_SCHEMA_INVALID','performed':False}
