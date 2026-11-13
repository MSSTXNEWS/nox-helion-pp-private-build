#!/usr/bin/env python3
"""Fail-closed typed S03 import planner. NEVER bypass native owner ACL / STOP.
This module plans graph records, does NOT open any new DB or call a model API.
"""
import json, hashlib
from pathlib import Path

def load_candidates(path):
    rows=[]
    with open(path,encoding='utf8') as f:
        for l in f:
            if l.strip():
                v=json.loads(l)
                if v.get('verified') is not False or v.get('requires_native_owner_grant') is not True:
                    raise ValueError('UNTRUSTED_IMPORTED_STATE')
                if not str(v.get('source_uri','')).startswith(('https://','user-current-conversation://')):
                    raise ValueError('BAD_SOURCE_URI')
                rows.append(v)
    return rows

def prepare(records, *, native_authorize, native_stop, tenant, principal, chat_id, owner_receipt):
    if not callable(native_authorize) or not callable(native_stop):
        return {'state':'HOLD_NATIVE_CALLBACKS_REQUIRED','items':[]}
    try:
        if native_stop() is not False or native_authorize(tenant,principal,chat_id,owner_receipt) is not True:
            return {'state':'HOLD_STOP_OR_OWNER_DENIED','items':[]}
    except Exception:return {'state':'HOLD_AUTH_FAILURE','items':[]}
    prepared=[]
    for record in records:
        if record.get('verified') is not False or not record.get('requires_manual_review'):
            continue
        prepared.append({'id':record['event_id'],'segment':record['segment'],'content':record['content'],
                         'source_uri':record['source_uri'],'tenant':tenant,'principal':principal,'scope_chat_id':chat_id,
                         'verified':False,'source_status':'UNVERIFIED_NEEDS_NATIVE_OWNER_APPROVAL'})
    if native_stop() is not False:return {'state':'HOLD_STOP_REVOKED','items':[]}
    return {'state':'PREPARED_UNVERIFIED_NOT_WRITTEN','items':prepared}

def submit(prepared, *, native_append, native_authorize, native_stop, tenant, principal, chat_id, owner_receipt):
    if prepared.get('state')!='PREPARED_UNVERIFIED_NOT_WRITTEN' or not callable(native_append):
        return {'state':'HOLD_UNVERIFIED_PLAN','written':0}
    if native_stop() is not False or native_authorize(tenant,principal,chat_id,owner_receipt) is not True:
        return {'state':'HOLD_STOP_OR_OWNER_DENIED','written':0}
    # Delegates all evidence validation, append-only history and signed grants to existing OneHost S03.
    result=native_append(tenant,principal,chat_id,prepared['items'],owner_receipt)
    if not isinstance(result,dict) or result.get('state')!='NATIVE_S03_APPEND_VERIFIED' or type(result.get('written')) is not int:
        return {'state':'HOLD_NO_TRUSTED_NATIVE_S03_RECEIPT','written':0}
    return {'state':'NATIVE_RECEIPT_REPORTED_NOT_INDEPENDENTLY_REPLAYED','written':result['written']}
