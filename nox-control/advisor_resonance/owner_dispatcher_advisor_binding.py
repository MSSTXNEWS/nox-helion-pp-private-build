"""Register an adviser worker in the existing, reviewed NOX dispatcher."""

import re

from nox_advisors.host import HANDLER_KIND
from nox_advisors.native import NativeAdvisors, OPENROUTER_FREE, PUBLIC_QUESTIONS
from nox_advisors.transport import CancelToken

DISPATCHER_SHA256 = 'eac3ce9e2d8c862d1a7917ec447ea72e84454b7775a4260ad1e72e59de96fe11'
REQUEST_ID = re.compile(r'[a-f0-9]{32}')
RECEIPT_SHA = re.compile(r'[a-f0-9]{64}')
TASK_PREFIX = 'nox-online-advice-'


def _hold(reason):
    return {'state': 'HOLD', 'reason': reason, 'handler_registered': False}


def _params(task):
    if type(task) is not dict or task.get('handler') != HANDLER_KIND:
        return None
    params = task.get('params')
    if type(params) is not dict or set(params) != {'topic', 'request_id'}:
        return None
    topic, request = params['topic'], params['request_id']
    if (not isinstance(topic, str) or topic not in PUBLIC_QUESTIONS or not isinstance(request, str)
            or not REQUEST_ID.fullmatch(request) or task.get('id') != TASK_PREFIX + request
            or type(task.get('max_retries')) is not int or task['max_retries'] != 1
            or type(task.get('retries')) is not int or task['retries'] != 0):
        return None
    return params


def _evidence(result, request_id, readback):
    if type(result) is not dict or type(result.get('advice')) is not dict:
        return None
    advice = result['advice']
    lease = result.get('host_lease')
    receipt = result.get('native_result_receipt')
    if (advice.get('request_id') != request_id or advice.get('provider') != 'openrouter'
            or advice.get('requested_model') != OPENROUTER_FREE or advice.get('status') != 'OK'
            or advice.get('outcome_uncertain') is not False
            or type(advice.get('attempts')) is not int or advice['attempts'] != 1
            or type(lease) is not dict or lease.get('release_uncertain', False) is not False
            or type(receipt) is not dict):
        return None
    row = readback(request_id, receipt)
    receipt_sha = row.get('receipt_sha256') if type(row) is dict else None
    if (type(row) is not dict or row.get('request_id') != request_id or row.get('status') != 'OK'
            or row.get('provider') != 'openrouter' or row.get('requested_model') != OPENROUTER_FREE
            or not isinstance(receipt_sha, str) or not RECEIPT_SHA.fullmatch(receipt_sha)):
        return None
    return {'schema': 'NOX_ADVISOR_DISPATCHER_RESULT_V1', 'request_id': request_id,
            'receipt_sha256': receipt_sha, 'advice_only': True}


def bind_dispatcher_advisor(namespace, *, advisor=None, owner_review=None,
                            cancel_for_task=None, read_advisory_receipt=None):
    """Register no handler unless the actual host supplies its reviewed ports.

    Invoke after the existing bind_dispatcher has established native ownership.
    The host must independently supply an approved queue adapter, request review,
    a dispatcher-owned STOP token and a separate durable advice readback.
    Owner review and readiness must be local nonblocking snapshots because
    admission is called under the dispatcher's queue lock.
    """
    native = namespace.get('_nox_owner_autonomy_native')
    handlers = namespace.get('HANDLERS')
    mentor = namespace.get('owner_mentor')
    old_admission = namespace.get('_nox_owner_task_admitted')
    if (getattr(native, 'ns', None) is not namespace or getattr(native, 'source', None) != DISPATCHER_SHA256
            or type(handlers) is not dict or not callable(old_admission)
            or not all(callable(getattr(native, name, None)) for name in
                       ('owner_allowed', 'stop_active', 'writer_lease', '_claim_current'))
            or not all(callable(getattr(mentor, name, None)) for name in ('on_failure', 'verify_success'))):
        return _hold('ADVISOR_DISPATCHER_PREIMAGE_OR_ABI')
    if HANDLER_KIND in handlers:
        return _hold('ADVISOR_HANDLER_ALREADY_BOUND')
    if (type(advisor) is not NativeAdvisors or not callable(advisor.provider_ready)
            or not all(callable(fn) for fn in (owner_review, cancel_for_task, read_advisory_receipt))):
        return _hold('ADVISOR_OWNER_QUEUE_LEASE_CANCEL_OR_READBACK_UNBOUND')

    old_failure, old_verify = mentor.on_failure, mentor.verify_success

    def ready(task):
        return (_params(task) is not None and native.owner_allowed() is True
                and native.stop_active() is False and advisor.status()['state'] == 'CONFIGURED_UNVERIFIED'
                and owner_review(task) is True)

    def admission(task):
        if task.get('handler') != HANDLER_KIND:
            return old_admission(task)
        try:
            return ready(task) and bool(old_admission(task))
        except Exception:
            return False

    def handle(task):
        try:
            params = _params(task)
            if params is None or not ready(task) or not native.writer_lease() or not native._claim_current(task, durable=True):
                return False, 'HOLD_ADVISOR_OWNER_CLAIM'
            if advisor.foreground_active() is not False:
                return 'wait', 'HOLD_ADVISOR_FOREGROUND_CHAT'
            cancel = cancel_for_task(task)
            if not isinstance(cancel, CancelToken) or cancel.cancelled or native.stop_active() is not False:
                return False, 'HOLD_ADVISOR_CANCEL_OR_STOP'
            result = advisor.worker(params, cancel=cancel)
            if cancel.cancelled or native.stop_active() is not False or not native._claim_current(task, durable=True):
                return False, 'HOLD_ADVISOR_RESULT_CLAIM'
            evidence = _evidence(result, params['request_id'], read_advisory_receipt)
            return (True, evidence) if evidence else (False, 'HOLD_ADVISOR_RESULT_NOT_VERIFIED')
        except Exception:
            return False, 'HOLD_ADVISOR_OUTCOME_UNCERTAIN'

    def on_failure(task, error):
        if task.get('handler') != HANDLER_KIND:
            return old_failure(task, error)
        # The generic mentor may invoke another model or schedule a retry.
        # An adviser task is single-attempt and never uses that fallback.
        task['status'] = 'blocked'
        task['mentor'] = {'state': 'BLOCKED_ADVISOR_NO_RETRY', 'needs_owner_input': True}
        return task['mentor']

    def verify(task, evidence=None):
        if task.get('handler') == HANDLER_KIND:
            # Dispatcher learning must not promote adviser work into training.
            return None
        return old_verify(task, evidence)

    namespace['_nox_owner_task_admitted'] = admission
    mentor.on_failure = on_failure
    mentor.verify_success = verify
    handlers[HANDLER_KIND] = handle
    return {'state': 'SOURCE_BINDING_ATTACHED', 'handler_registered': True, 'native_job_started': False}
