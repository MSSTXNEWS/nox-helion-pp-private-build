"""Native OneHost tool dispatch; never run shell commands from chat.

Exact scoped owner approval is mandatory for writes. The real host must supply
trustworthy callbacks for authorization, STOP, request-specific approval, execution,
receipt verification, and independent post-action observation.
"""
from __future__ import annotations
import hashlib,json,re,time

READ=frozenset({'server.status','server.gpus','server.jobs','server.logs','server.checkpoints'})
WRITES=frozenset({'teacher.start','teacher.stop','training.pause','training.resume',
                  'checkpoint.backup','model.download','model.activate','host.service.restart'})
DANGEROUS=frozenset({'host.data.cleanup','host.reboot','chat.stop'})
ALL=READ|WRITES|DANGEROUS

def canonical_request(request):
    if not isinstance(request,dict):raise ValueError('REQUEST_DICT_REQUIRED')
    permitted=frozenset({'action','target_id','tenant_id','principal_id','chat_id','request_id','expected_target_sha256'})
    if set(request)-permitted:raise ValueError('UNRECOGNIZED_FIELDS_NO_FREEFORM_SHELL')
    action=request.get('action');target=request.get('target_id')
    if action not in ALL:raise ValueError('ACTION_NOT_ALLOWLISTED')
    if not isinstance(target,str) or not re.fullmatch(r'[A-Za-z0-9._:-]{1,128}',target):
        raise ValueError('TARGET_NOT_ALLOWLISTED_ID')
    if any(not isinstance(request.get(k),str) or not re.fullmatch(r'[A-Za-z0-9._:-]{1,128}',request[k])
           for k in ('tenant_id','principal_id','chat_id','request_id')):
        raise ValueError('SCOPE_REQUIRED')
    if 'expected_target_sha256' in request and not re.fullmatch(r'[0-9a-f]{64}',str(request['expected_target_sha256'])):
        raise ValueError('EXPECTED_PREIMAGE_SHA_REQUIRED')
    payload=json.dumps(request,sort_keys=True,ensure_ascii=False,separators=(',',':'))
    return payload,hashlib.sha256(payload.encode()).hexdigest()

def dispatch(request, *, host_authorize,host_stop,host_inspect,
             host_approve=None,host_execute=None,host_receipt_verify=None,
             host_readback=None,approved_request_sha=None):
    payload,digest=canonical_request(request)
    if not all(callable(x) for x in (host_authorize,host_stop,host_inspect)):
        return {'state':'HOLD_NATIVE_CALLBACKS_MISSING','performed':False}
    def safe():
        try:return host_stop() is False and host_authorize(request) is True
        except Exception:return False
    if not safe():return {'state':'HOLD_STOP_OR_OWNER_SCOPE','performed':False}
    action=request['action'];target=request['target_id']
    try:before=host_inspect(request)
    except Exception:return {'state':'HOLD_NATIVE_INSPECT_FAILED','performed':False}
    if action in READ:
        if not safe():return {'state':'HOLD_STOP_REVOKED','performed':False}
        return {'state':'READ_ONLY_OBSERVED','action':action,'target_id':target,
                'request_sha256':digest,'data':before,'performed':False}
    plan={'action':action,'target_id':target,'scope':request['chat_id'],
          'request_sha256':digest,'current_state':before,
          'requires_confirmation':True,'dangerous':action in DANGEROUS,'performed':False}
    if approved_request_sha!=digest:
        return {'state':'OWNER_CONFIRMATION_REQUIRED','plan':plan,'performed':False}
    if not all(callable(x) for x in (host_approve,host_execute,host_receipt_verify,host_readback)):
        return {'state':'HOLD_MUTATION_CALLBACKS_MISSING','plan':plan,'performed':False}
    if not safe():return {'state':'HOLD_STOP_OR_OWNER_SCOPE','performed':False}
    try:
        if host_approve(request,digest,before) is not True:
            return {'state':'HOLD_SIGNED_APPROVAL_NOT_VALID','performed':False}
        if not safe():return {'state':'HOLD_STOP_OR_OWNER_SCOPE','performed':False}
        receipt=host_execute(request,digest,before)  # host rechecks same preimage and time-limited owner grant
        if host_receipt_verify(receipt,request,digest) is not True:
            return {'state':'HOLD_NATIVE_RECEIPT_NOT_VERIFIED','performed':False}
        after=host_readback(request,receipt)
        if not safe():return {'state':'HOLD_AFTER_EXEC_REVOKED_NEEDS_NATIVE_ROLLBACK','performed':True}
    except Exception:
        return {'state':'HOLD_NATIVE_EXECUTION_OR_READBACK_FAILED','performed':'UNKNOWN'}
    return {'state':'NATIVE_EXECUTED_AND_READBACK_REPORTED','performed':True,
            'request_sha256':digest,'receipt':receipt,'observation':after,
            'release_accepted':False}
