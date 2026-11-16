#!/usr/bin/env python3
"""Pinned S03 history/vector preparation; activation is a separate idle handoff.

This action never restarts chat/llama/dispatcher, changes training admissions,
or exports private memory. The native post-hook source SHA is calculated from
the inspected private preimage for the later explicit lifecycle pin update.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time

try:BUNDLE=__NOX_BUNDLE_JSON__
except NameError:BUNDLE={}

ROOT=Path('/root/nox')
HELPER_SHA='40caff3109111d971ff2d37cb81c0c2050ead08ae42d1f631a245778dd1a7a4d'
BASE_S03_SHA='82c592ea5a59281fb5fc1061d133ac4e149b8e95a6d0947a254882715cba7f91'
SCHEMA='NOX_OWNER_S03_PREPARE_V1'


def emit(kind,data):
    print('NOX_MAINT_REPAIR='+json.dumps({'kind':kind,'data':data},separators=(',',':')),flush=True)


def fail(code):raise RuntimeError(code)


def load_helper():
    raw=base64.b64decode(BUNDLE.get('owner_s03_gateway.py',''),validate=True)
    if hashlib.sha256(raw).hexdigest()!=HELPER_SHA:fail('HOLD_S03_HELPER_SOURCE_PIN')
    compile(raw,'owner_s03_gateway.py','exec')
    # Evaluate only this exact approved helper; it performs no work at import.
    import types
    module=types.ModuleType('owner_s03_gateway')
    module.__file__=str(ROOT/'scripts/owner_s03_gateway.py')
    exec(compile(raw,module.__file__,'exec'),module.__dict__)
    source=ROOT/'scripts/s03_memory.py'
    if module.file_sha(source)!=BASE_S03_SHA:fail('HOLD_S03_BASE_SOURCE_CHANGED')
    transformed=module.patch_s03(source.read_text(),BASE_S03_SHA)
    return module,raw,hashlib.sha256(transformed.encode()).hexdigest()


def install_helper(module,raw):
    path=module.plain(ROOT/'scripts/owner_s03_gateway.py')
    if path.exists():
        if module.file_sha(path)!=HELPER_SHA:fail('HOLD_S03_INSTALLED_HELPER_CHANGED')
        return
    fd,temporary=tempfile.mkstemp(prefix='.s03-helper-',dir=path.parent)
    try:
        os.fchmod(fd,0o644)
        with os.fdopen(fd,'wb') as stream:
            stream.write(raw);stream.flush();os.fsync(stream.fileno())
        # Atomic exclusive publication; never replace another source preimage.
        os.link(temporary,path,follow_symlinks=False)
        directory=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(directory)
        finally:os.close(directory)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)
    if module.file_sha(path)!=HELPER_SHA:fail('HOLD_S03_HELPER_READBACK')


def main():
    request=os.environ.get('NOX_OWNER_REQUEST_ID','');source=os.environ.get('NOX_OWNER_SOURCE_SHA','')
    if not request.isdigit() or not re.fullmatch('[a-f0-9]{40}',source):fail('HOLD_OWNER_CONTEXT')
    action=os.environ.get('NOX_S03_ACTION','PREPARE')
    if action not in ('PREPARE','INDEX','STATUS'):fail('HOLD_S03_PREPARE_ACTION')
    module,raw,after_sha=load_helper()
    if module.stop_active():fail('HOLD_S03_OWNER_STOP')
    module.resource_admission()
    install_helper(module,raw)
    record={'schema':SCHEMA,'request':request,'source_sha':source,'started_at':time.time(),
            'action':action,'gateway_sha256':HELPER_SHA,'s03_before_sha256':BASE_S03_SHA,
            's03_after_activation_sha256':after_sha,'s03_source_changed':False,
            'services_restarted':[],'private_text_exported':False,'training_examples_accepted':0,
            'embedding_model_duplicated':False,'state':'PREPARING'}
    receipt=module.STATE/('prepare_'+request+'.json')
    module.atomic_json(receipt,record)
    try:
        with module.operation_lock():
            fixture=module.semantic_probe()
            record['synthetic_retrieval_acceptance']=fixture
            emit('s03_semantic_fixture',fixture)
            if fixture['state']!='SYNTHETIC_SEMANTIC_FIXTURES_VERIFIED':fail('HOLD_S03_SEMANTIC_FIXTURE')
            if action=='PREPARE':
                record['history_import']=module.migrate_history(request)
                emit('s03_history_import',record['history_import'])
                module.atomic_json(receipt,record)
            if action in ('PREPARE','INDEX'):
                deadline=time.monotonic()+140;indexed=0;last=0
                while time.monotonic()<deadline:
                    module.resource_admission()
                    batch=module.index_batch();indexed+=batch['indexed']
                    if time.monotonic()-last>5 or batch['stale_remaining']==0:
                        emit('s03_index_progress',{'indexed_in_action':indexed,'stale_remaining':batch['stale_remaining'],
                                                  'dimensions':module.DIMENSIONS,'private_text_exported':False})
                        last=time.monotonic()
                    if batch['stale_remaining']==0:break
                record['indexed_in_action']=indexed
            record['status']=module.status()
            record['state']='HISTORY_AND_INDEX_PREPARED' if record['status']['stale_embeddings']==0 else 'HISTORY_IMPORTED_INDEX_INCOMPLETE'
            record['activation']='PENDING_SOURCE_AND_LIFECYCLE_PIN_UPDATE_THEN_IDLE_CHAT_RELOAD'
        record['finished_at']=time.time();module.atomic_json(receipt,record)
        emit('s03_preparation',record)
        emit('s03_preparation_receipt',{'path':str(receipt),'sha256':module.file_sha(receipt)})
        if record['status']['stale_embeddings']:return 3
        print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True);return 0
    except Exception as exc:
        reason=str(exc)
        record.update(state='HOLD_S03_PREPARATION',reason=reason if re.fullmatch('HOLD_[A-Z0-9_]+',reason) else type(exc).__name__,finished_at=time.time())
        module.atomic_json(receipt,record)
        emit('s03_preparation',record)
        emit('s03_preparation_receipt',{'path':str(receipt),'sha256':module.file_sha(receipt)})
        return 2


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        value=str(exc)
        emit('s03_prepare_hold',{'reason':value if re.fullmatch('HOLD_[A-Z0-9_]+',value) else type(exc).__name__})
        raise SystemExit(2)
