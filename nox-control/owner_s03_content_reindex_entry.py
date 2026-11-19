#!/usr/bin/env python3
"""Re-embed the prepared S03 index under the verified BGE content identity.

This finite action leaves live source, services, original history and training
flags unchanged. Only derived vectors/cache and private receipts are written.
The historical model content hash was never recorded: old vectors are actually
embedded again, never relabelled as if their content provenance were known.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import time
import types

try:BUNDLE=__NOX_BUNDLE_JSON__
except NameError:BUNDLE={}

ROOT=Path('/root/nox');STATE=ROOT/'state/owner_s03'
SCHEMA='NOX_OWNER_S03_CONTENT_REINDEX_V1'
GATEWAY_SHA='20b9f6b4ad504671eaee24c3a27a44d3a9dd74e6279af463779421da2ee16f0b'
INSTALLED_GATEWAY_SHA='40caff3109111d971ff2d37cb81c0c2050ead08ae42d1f631a245778dd1a7a4d'
S03_SHA='82c592ea5a59281fb5fc1061d133ac4e149b8e95a6d0947a254882715cba7f91'
PREPARE_REQUEST='6904379098'
PREPARE_SOURCE='2a09e5975e0bfbd84e22bbaea1c0347a9b41ec63'
PREPARE_SHA='f6be4b08c1eb3a053b65c977479367354ffa31a50d479ce527b42e096929981c'
MODEL_SHA='6d39681b26c61279ac1f82db35a04a05009e94c415b51c858ff571489a82fc06'
ORIGINAL_HOLD_SHA='dad9cb72d6b253f4568f42cd96ed11f6f6d8a646aeeaecf0467d1b0a78b9a649'
SUCCESS='CONTENT_IDENTITY_AND_REEMBEDDED_INDEX_VERIFIED'
PUBLIC_QUERY='Как NOX сохраняет историю разговоров и воспоминания?'


def fail(code):raise RuntimeError(code)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def safe(exc):
    value=str(exc);return value if re.fullmatch('HOLD_[A-Z0-9_]+',value) else type(exc).__name__
def emit(kind,data):print('NOX_MAINT_REPAIR='+json.dumps({'kind':kind,'data':data},separators=(',',':')),flush=True)


def read(path,limit=1024*1024):
    path=Path(path)
    if any(p.is_symlink() for p in (*path.parents,path)):fail('HOLD_S03_REINDEX_SYMLINK')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        before=os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size>limit:fail('HOLD_S03_REINDEX_FILE_SCOPE')
        raw=stream.read(limit+1);after=os.fstat(stream.fileno());named=path.stat(follow_symlinks=False)
        fields=('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns')
        if (len(raw)!=before.st_size or any(getattr(before,k)!=getattr(after,k) for k in fields)
                or (before.st_dev,before.st_ino)!=(named.st_dev,named.st_ino)):
            fail('HOLD_S03_REINDEX_FILE_RACE')
        return raw


def publish(path,value):
    """One immutable final receipt; a separate progress file may be replaced."""
    path=Path(path)
    if any(p.is_symlink() for p in (*path.parents,path)):fail('HOLD_S03_REINDEX_SYMLINK')
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    fd,temporary=tempfile.mkstemp(prefix='.reindex-',dir=path.parent)
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,'wb') as stream:
            stream.write(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode())
            stream.flush();os.fsync(stream.fileno())
        os.link(temporary,path,follow_symlinks=False)
        directory=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(directory)
        finally:os.close(directory)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)


def context():
    request=os.environ.get('NOX_OWNER_REQUEST_ID','');source=os.environ.get('NOX_OWNER_SOURCE_SHA','')
    if not request.isdigit() or not re.fullmatch('[a-f0-9]{40}',source):fail('HOLD_S03_REINDEX_CONTEXT')
    return request,source


def load_gateway():
    raw=base64.b64decode(BUNDLE.get('owner_s03_gateway.py',''),validate=True)
    if digest(raw)!=GATEWAY_SHA:fail('HOLD_S03_REINDEX_BUNDLE_PIN')
    gateway=types.ModuleType('owner_s03_content_candidate')
    gateway.__file__=str(ROOT/'scripts/owner_s03_gateway.py')
    exec(compile(raw,gateway.__file__,'exec'),gateway.__dict__)
    return gateway


def sources_and_flags():
    result={}
    for name,pin in (('s03_memory.py',S03_SHA),('owner_s03_gateway.py',INSTALLED_GATEWAY_SHA)):
        result[name]=digest(read(ROOT/'scripts'/name))
        if result[name]!=pin:fail('HOLD_S03_REINDEX_LIVE_SOURCE_CHANGED')
    for name in ('TRAIN_HOLD.flag','TRAIN_PAUSE_REQUEST.flag'):
        result[name]=digest(read(ROOT/'state'/name,4096))
        if result[name]!=ORIGINAL_HOLD_SHA:fail('HOLD_S03_REINDEX_TRAINING_HOLD_CHANGED')
    return result


def embedding_process(model):
    matches=[]
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():continue
        try:
            argv=(path/'cmdline').read_bytes().split(b'\0')
            if str(model).encode() not in argv:continue
            tail=(path/'stat').read_text().rsplit(')',1)[1].split()
            if tail[0]=='Z':continue
            matches.append({'pid':int(path.name),'starttime':int(tail[19])})
        except (OSError,ValueError,IndexError):continue
    if len(matches)!=1:fail('HOLD_S03_REINDEX_BGE_PROCESS_IDENTITY')
    return matches[0]


def canonical_snapshot(gateway):
    with gateway.connection(gateway.DB,seconds=3) as conn:
        total=gateway.validate_base(conn)
        rows={row['id']:gateway.text_sha(row['text']) for row in conn.execute('SELECT id,text FROM s03_items')}
        originals=conn.execute('SELECT count(*) FROM nox_s03_import_records').fetchone()[0]
        origins=conn.execute('SELECT count(*) FROM nox_s03_origins').fetchone()[0]
        legacy=conn.execute('SELECT count(*) FROM nox_s03_vectors v JOIN s03_items s ON s.id=v.item_id WHERE v.model_identity!=?',(gateway.content_identity(),)).fetchone()[0]
    return rows,{'canonical_items':total,'original_history_records':originals,'origin_links':origins,'legacy_identity_vectors':legacy}


def public_recall(gateway):
    started=time.monotonic();rows=gateway.recall(PUBLIC_QUERY,k=6)
    methods={name:sum(row.get('how')==name for row in rows) for name in ('semantic','hybrid','fts','like','pin','recent')}
    if methods['semantic']+methods['hybrid']<1 or methods['pin']>2:fail('HOLD_S03_REINDEX_SEMANTIC_RECALL')
    return {'state':'SEMANTIC_LEXICAL_BOUNDED_PINS','methods':methods,'rows':len(rows),
            'elapsed_ms':round((time.monotonic()-started)*1000,3),'private_text_exported':False}


def _valid_restore_proof(value,manifest_sha256):
    return (isinstance(value,dict) and value.get('state')=='STAGING_RESTORE_VERIFIED'
            and value.get('source_key')=='CANONICAL'
            and value.get('manifest_sha256')==manifest_sha256
            and isinstance(value.get('snapshot_sha256'),str)
            and re.fullmatch('[a-f0-9]{64}',value['snapshot_sha256'])
            and value.get('restored_sha256')==value.get('snapshot_sha256')
            and type(value.get('restored_bytes')) is int and 0<value['restored_bytes']<=512*1024*1024
            and value.get('quick_check')=='ok' and type(value.get('canonical_items')) is int
            and value['canonical_items']>=0 and value.get('staging_removed') is True
            and value.get('source_retained') is True
            and value.get('live_database_mutated_by_restore') is False)


def staging_restore_proof(prepare,gateway):
    history=prepare.get('history_import')
    if (not isinstance(history,dict) or history.get('state')!='HISTORICAL_RECORDS_IMPORTED'
            or history.get('source_databases_retained') is not True
            or history.get('training_examples_accepted')!=0
            or history.get('private_text_exported') is not False):
        fail('HOLD_S03_REINDEX_HISTORY_SNAPSHOT')
    manifest_sha=history.get('snapshot_manifest_sha256')
    if not isinstance(manifest_sha,str) or not re.fullmatch('[a-f0-9]{64}',manifest_sha):
        fail('HOLD_S03_REINDEX_MANIFEST_PIN')
    proof=history.get('canonical_staging_restore')
    if proof is not None:
        if not _valid_restore_proof(proof,manifest_sha):fail('HOLD_S03_REINDEX_STAGED_RESTORE_RECEIPT')
        return proof
    proof=gateway.verify_snapshot_restore_staging(
        STATE/'backups'/PREPARE_REQUEST/'manifest.json',manifest_sha,PREPARE_REQUEST)
    if not _valid_restore_proof(proof,manifest_sha):fail('HOLD_S03_REINDEX_STAGED_RESTORE')
    return proof


def validate_record(value,request,source,gateway):
    status=value.get('status',{});identity=value.get('content_identity',{})
    recall=value.get('public_recall',{});methods=recall.get('methods',{})
    before=value.get('before_index',{});process=value.get('bge_process_before',{})
    restore=value.get('canonical_staging_restore',{})
    manifest_sha=value.get('snapshot_manifest_sha256')
    if (value.get('schema')!=SCHEMA or value.get('request')!=request or value.get('source_sha')!=source
            or value.get('state')!=SUCCESS or value.get('gateway_sha256')!=GATEWAY_SHA
            or not isinstance(manifest_sha,str) or not re.fullmatch('[a-f0-9]{64}',manifest_sha)
            or not _valid_restore_proof(restore,manifest_sha)
            or value.get('prepare_request')!=PREPARE_REQUEST or value.get('prepare_source_sha')!=PREPARE_SOURCE
            or value.get('prepare_receipt_sha256')!=PREPARE_SHA
            or identity.get('content_sha256')!=MODEL_SHA or identity.get('identity')!=gateway.content_identity()
            or identity.get('full_file_hash_verified') is not True or identity.get('dimensions')!=1024
            or status.get('model_identity')!=gateway.content_identity() or status.get('stale_embeddings')!=0
            or type(status.get('current_embeddings')) is not int or status['current_embeddings']<514
            or status.get('original_history_records_preserved',0)<1014
            or value.get('legacy_vectors_remaining')!=0 or value.get('legacy_vectors_relabelled') is not False
            or value.get('historical_model_content_sha_known') is not False
            or value.get('canonical_originals_preserved') is not True
            or value.get('sources_and_flags_unchanged') is not True
            or value.get('training_hold_sha256')!=ORIGINAL_HOLD_SHA
            or value.get('training_pause_sha256')!=ORIGINAL_HOLD_SHA
            or value.get('private_text_exported') is not False or value.get('training_examples_accepted')!=0
            or value.get('services_restarted')!=[] or value.get('live_sources_changed') is not False
            or type(value.get('indexed_in_action')) is not int or value['indexed_in_action']<0
            or type(before.get('legacy_identity_vectors')) is not int
            or before['legacy_identity_vectors']<0 or value['indexed_in_action']<before['legacy_identity_vectors']
            or not isinstance(process,dict) or type(process.get('pid')) is not int or process['pid']<1
            or type(process.get('starttime')) is not int or process['starttime']<1
            or value.get('bge_process_before')!=value.get('bge_process_after')
            or value.get('synthetic_retrieval_acceptance',{}).get('state')!='SYNTHETIC_SEMANTIC_FIXTURES_VERIFIED'
            or recall.get('state')!='SEMANTIC_LEXICAL_BOUNDED_PINS'
            or sum(methods.get(k,0) for k in ('semantic','hybrid'))<1 or methods.get('pin',99)>2):
        fail('HOLD_S03_REINDEX_RECEIPT_NOT_VERIFIED')
    return value


def main():
    request,source=context();gateway=load_gateway()
    receipt=STATE/('content_reindex_'+request+'.json')
    if receipt.exists():
        value=validate_record(json.loads(read(receipt)),request,source,gateway)
        emit('s03_content_reindex',value)
        emit('s03_content_reindex_receipt',{'path':str(receipt),'sha256':digest(read(receipt))})
        return 0
    prepare_raw=read(STATE/('prepare_'+PREPARE_REQUEST+'.json'))
    if digest(prepare_raw)!=PREPARE_SHA:fail('HOLD_S03_REINDEX_PREPARE_PIN')
    prepare=json.loads(prepare_raw)
    if (prepare.get('schema')!='NOX_OWNER_S03_PREPARE_V1' or prepare.get('request')!=PREPARE_REQUEST
            or prepare.get('source_sha')!=PREPARE_SOURCE or prepare.get('state')!='HISTORY_AND_INDEX_PREPARED'
            or prepare.get('gateway_sha256')!=INSTALLED_GATEWAY_SHA or prepare.get('s03_before_sha256')!=S03_SHA):
        fail('HOLD_S03_REINDEX_PREPARE_NOT_VERIFIED')
    restore=staging_restore_proof(prepare,gateway)
    before_sources=sources_and_flags();gateway.resource_admission()
    record={'schema':SCHEMA,'request':request,'source_sha':source,'state':'REEMBEDDING',
            'gateway_sha256':GATEWAY_SHA,'prepare_request':PREPARE_REQUEST,'prepare_source_sha':PREPARE_SOURCE,
            'prepare_receipt_sha256':PREPARE_SHA,
            'snapshot_manifest_sha256':restore['manifest_sha256'],
            'canonical_staging_restore':restore,'started_at':time.time(),
            'live_sources_changed':False,'services_restarted':[],'private_text_exported':False,
            'training_examples_accepted':0,'legacy_vectors_relabelled':False,
            'historical_model_content_sha_known':False,'indexed_in_action':0,
            'training_hold_sha256':ORIGINAL_HOLD_SHA,'training_pause_sha256':ORIGINAL_HOLD_SHA}
    success=False
    try:
        record['bge_process_before']=embedding_process(gateway.MODEL)
        with gateway.operation_lock():
            originals,before=canonical_snapshot(gateway);record['before_index']=before
            record['content_identity']=gateway.refresh_model_identity()
            record['synthetic_retrieval_acceptance']=gateway.semantic_probe()
            if record['synthetic_retrieval_acceptance']['state']!='SYNTHETIC_SEMANTIC_FIXTURES_VERIFIED':
                fail('HOLD_S03_REINDEX_SYNTHETIC_RECALL')
            deadline=time.monotonic()+140;last=0
            while time.monotonic()<deadline:
                gateway.resource_admission();batch=gateway.index_batch()
                record['indexed_in_action']+=batch['indexed']
                if time.monotonic()-last>5 or batch['stale_remaining']==0:
                    gateway.atomic_json(STATE/('content_reindex_'+request+'.progress.json'),{
                        'schema':SCHEMA,'request':request,'source_sha':source,'state':'REEMBEDDING',
                        'indexed_in_action':record['indexed_in_action'],'stale_remaining':batch['stale_remaining'],
                        'private_text_exported':False})
                    emit('s03_content_reindex_progress',{'indexed_in_action':record['indexed_in_action'],
                         'stale_remaining':batch['stale_remaining'],'private_text_exported':False});last=time.monotonic()
                if batch['stale_remaining']==0:break
            record['status']=gateway.status()
            current,after=canonical_snapshot(gateway)
            record['canonical_originals_preserved']=(all(current.get(k)==v for k,v in originals.items())
                and after['original_history_records']>=before['original_history_records']
                and after['origin_links']>=before['origin_links'])
            record['legacy_vectors_remaining']=after['legacy_identity_vectors']
            if record['status']['stale_embeddings']:fail('HOLD_S03_REINDEX_BUDGET_PENDING')
            record['public_recall']=public_recall(gateway)
            record['bge_process_after']=embedding_process(gateway.MODEL)
            record['sources_and_flags_unchanged']=sources_and_flags()==before_sources
            if gateway.stop_active():fail('HOLD_S03_OWNER_STOP')
            record['state']=SUCCESS;validate_record(record,request,source,gateway);success=True
    except Exception as exc:record.update(state='HOLD_S03_CONTENT_REINDEX',reason=safe(exc))
    record['finished_at']=time.time();publish(receipt,record)
    emit('s03_content_reindex',record)
    emit('s03_content_reindex_receipt',{'path':str(receipt),'sha256':digest(read(receipt))})
    return 0 if success else 2


if __name__=='__main__':
    try:
        result=main()
        if result==0:print('NOX_MAINT_REPAIR_COMPLETE=true',flush=True)
        raise SystemExit(result)
    except Exception as exc:emit('s03_content_reindex_hold',{'reason':safe(exc)});raise SystemExit(2)
