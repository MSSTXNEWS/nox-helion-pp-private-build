"""Read-only encrypted export of one exact saved, zero-update checkpoint.

No key creation, native writes, extraction, pickle loading, training or upload.
The existing reviewed media transport supplies only crypto/file primitives;
its fixed media manifest and limits are not modified.
"""
from __future__ import annotations
import base64
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import time
import zipfile

import owner_media_fixture_transport as primitives

ROOT=Path('/root/nox');OUTPUT=ROOT/'lora/qlora_t866u/runs_owner_hybrid'
STEP=5;INSTANCE_ID=60509551
ORIGIN={'request':'6905764817','source_sha':'e4549616aa13295febc44dc78a3a033870f9071d',
        'receipt_sha256':'960e96fba9d24bb0835df1a46bf9971f770aaab78c0587e20a897b53fd6aeb46'}
RECEIPT_SHA='ba19160382025630d41f8187122bc1f51c7aa3abe2c2a8608e9b8804eeac72fe'
LINEAGE_SHA='b2bc1b3630ba40736acdc309b7aa8ea631a756da4913b425ad2e5efcbd7f74bd'
NATIVE_SHA='703da2adf5620ce4979bd559c73a15446c743e6608f39d34a6b17e016b47920a'
TENSOR_SHA='6365775e7b5039a291f49ee92e63de263356b2490be29436699cf786bf1c3b13'
DATASET_SHA='31b0d6983d6bb6e40d05ffca505b4b1d68c9e9212648cd9cd270dedafd79fc1d'
CHECKPOINT_NAMES=('adapter_model.safetensors','adapter_config.json','optimizer.pt',
                  'scheduler.pt','rng_state.pth','scaler.pt','trainer_state.json')
NAMES=CHECKPOINT_NAMES+('owner_lineage.json','owner_receipt_step_5.json')
ALGORITHM='RSA4096-OAEP-SHA256+A256GCM'
OAEP_LABEL=b'NOX_CHECKPOINT5_ZERO_UPDATE_BACKUP_V1'
MAX_ARCHIVE=64*1024**2;MAX_JSON=256*1024;MAX_TTL=3600
CHUNK_CHARS=60000;MAX_CHUNKS=1200
MAX_CIPHER_CHARS=CHUNK_CHARS*MAX_CHUNKS
MAX_WIRE=MAX_CIPHER_CHARS+MAX_CHUNKS*1024+65536


class BackupHold(RuntimeError):pass
def require(condition,code='HOLD_CHECKPOINT_BACKUP_SCOPE'):
    if not condition:raise BackupHold(code)
def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(raw):return hashlib.sha256(raw).hexdigest()
def sha(value):return isinstance(value,str) and re.fullmatch('[a-f0-9]{64}',value) is not None
def decode_json(raw,maximum=MAX_JSON):
    require(isinstance(raw,bytes) and len(raw)<=maximum,'HOLD_CHECKPOINT_BACKUP_JSON_SIZE')
    return json.loads(raw,object_pairs_hook=primitives.unique,
        parse_constant=lambda _:(_ for _ in ()).throw(BackupHold('HOLD_CHECKPOINT_BACKUP_JSON_NUMBER')))


def trainer_state_step(raw):
    """Read only the saved step; diagnostic NaN never becomes a proof value.

    Transformers can retain nonfinite gradient diagnostics in log_history after
    skipped AMP attempts. Those exact, already hash-checked bytes are archived
    unchanged. Receipt, lineage and all other JSON still use decode_json().
    """
    require(isinstance(raw,bytes) and len(raw)<=MAX_JSON,'HOLD_CHECKPOINT_BACKUP_JSON_SIZE')
    diagnostic_number=object()
    state=json.loads(raw,object_pairs_hook=primitives.unique,
                     parse_constant=lambda _:diagnostic_number)
    require(isinstance(state,dict) and type(state.get('global_step')) is int
            and state['global_step']==STEP,'HOLD_CHECKPOINT_BACKUP_TRAINER_STEP')
    history=state.get('log_history',[])
    require(isinstance(history,list) and len(history)<=1024
            and all(isinstance(row,dict) for row in history),
            'HOLD_CHECKPOINT_BACKUP_TRAINER_DIAGNOSTIC_SCOPE')
    pending=[(state,(),0)];visited=0
    while pending:
        value,path,depth=pending.pop();visited+=1
        require(depth<=32 and visited<=20000,'HOLD_CHECKPOINT_BACKUP_TRAINER_METADATA_BUDGET')
        if value is diagnostic_number or (type(value) is float and not math.isfinite(value)):
            require(len(path)==3 and path[0]=='log_history' and type(path[1]) is int
                    and path[2]=='grad_norm',
                    'HOLD_CHECKPOINT_BACKUP_TRAINER_DIAGNOSTIC_SCOPE')
        elif isinstance(value,dict):
            pending.extend((item,path+(key,),depth+1) for key,item in value.items())
        elif isinstance(value,list):
            pending.extend((item,path+(index,),depth+1) for index,item in enumerate(value))
    return state['global_step']


def scope():
    return {'schema':'NOX_CHECKPOINT_BACKUP_SCOPE_V1','instance_id':INSTANCE_ID,
        'checkpoint_step':STEP,'origin_admission':dict(ORIGIN),'checkpoint_receipt_sha256':RECEIPT_SHA,
        'lineage_canonical_sha256':LINEAGE_SHA,'native_trainer_sha256':NATIVE_SHA,
        'files':list(NAMES),'state':'SAVED_CHECKPOINT_WITH_ZERO_OPTIMIZER_UPDATES',
        'successful_optimizer_steps':0,'amp_skipped_optimizer_steps':5,
        'full_model_backup':False,'base_weights_included':False,'training_corpus_included':False}


def scope_sha():return digest(canonical(scope()))


def public_key_metadata(value,now=None):
    now=int(time.time()) if now is None else now
    require(isinstance(value,dict) and set(value)=={'schema','key_id','public_key_pem','transfer_id',
        'created_at','expires_at','scope_sha256'},'HOLD_CHECKPOINT_BACKUP_KEY_SCHEMA')
    require(value['schema']=='NOX_CHECKPOINT_BACKUP_PUBLIC_KEY_V1' and value['scope_sha256']==scope_sha()
        and isinstance(value['transfer_id'],str) and re.fullmatch('[a-f0-9]{32}',value['transfer_id'])
        and type(value['created_at']) is int and type(value['expires_at']) is int
        and 0<value['expires_at']-value['created_at']<=MAX_TTL
        and value['created_at']-5<=now<value['expires_at'],'HOLD_CHECKPOINT_BACKUP_KEY_CONTEXT')
    pem=value['public_key_pem']
    require(isinstance(pem,str) and pem.startswith('-----BEGIN PUBLIC KEY-----\n')
        and len(pem)<=1200,'HOLD_CHECKPOINT_BACKUP_PUBLIC_KEY')
    key=primitives.serialization.load_pem_public_key(pem.encode('ascii'))
    require(isinstance(key,primitives.rsa.RSAPublicKey) and key.key_size==4096
        and key.public_numbers().e==65537,'HOLD_CHECKPOINT_BACKUP_PUBLIC_KEY')
    der=key.public_bytes(primitives.serialization.Encoding.DER,primitives.serialization.PublicFormat.SubjectPublicKeyInfo)
    require(value['key_id']==digest(der),'HOLD_CHECKPOINT_BACKUP_KEY_ID')
    return key


def validate_payload(files):
    """Verify all seven saved bytes and both source records; never unpickle."""
    require(isinstance(files,dict) and set(files)==set(NAMES)
        and all(isinstance(v,bytes) and v for v in files.values())
        and sum(map(len,files.values()))<=MAX_ARCHIVE,'HOLD_CHECKPOINT_BACKUP_FILES')
    raw=files['owner_receipt_step_5.json']
    require(digest(raw)==RECEIPT_SHA,'HOLD_CHECKPOINT_BACKUP_RECEIPT_SHA')
    receipt=decode_json(raw);lineage=decode_json(files['owner_lineage.json'])
    require(digest(canonical(lineage))==LINEAGE_SHA
        and lineage.get('native_sha256')==NATIVE_SHA and lineage.get('dataset_sha256')==DATASET_SHA,
        'HOLD_CHECKPOINT_BACKUP_LINEAGE')
    require(receipt.get('schema')=='NOX_T866U_FP32_ADAPTER_CONTINUATION_V1'
        and receipt.get('native_sha256')==NATIVE_SHA and receipt.get('lineage_sha256')==LINEAGE_SHA
        and type(receipt.get('global_step')) is int and receipt['global_step']==STEP
        and type(receipt.get('start_step')) is int and receipt['start_step']==0
        and type(receipt.get('successful_optimizer_steps')) is int and receipt['successful_optimizer_steps']==0
        and type(receipt.get('skipped_optimizer_steps')) is int and receipt['skipped_optimizer_steps']==5
        and type(receipt.get('loss')) in (int,float) and math.isfinite(receipt['loss'])
        and receipt.get('before_tensor_sha256')==receipt.get('after_tensor_sha256')==TENSOR_SHA
        and receipt.get('adapter_delta_verified') is False and receipt.get('merged') is False
        and receipt.get('live_promoted') is False,'HOLD_CHECKPOINT_BACKUP_ZERO_UPDATE_PROOF')
    cp=receipt.get('checkpoint') or {};hashes=cp.get('files_sha256') or {}
    require(cp.get('path')==str(OUTPUT/'checkpoint-5') and type(cp.get('global_step')) is int
        and cp['global_step']==STEP and set(hashes)==set(CHECKPOINT_NAMES)
        and all(sha(v) for v in hashes.values()),'HOLD_CHECKPOINT_BACKUP_CHECKPOINT_SCOPE')
    require(all(digest(files[name])==hashes[name] for name in CHECKPOINT_NAMES),
        'HOLD_CHECKPOINT_BACKUP_FILE_SHA')
    trainer_state_step(files['trainer_state.json'])
    return [{'filename':name,'bytes':len(files[name]),'sha256':digest(files[name])} for name in NAMES]


def archive_payload(files):
    manifest_files=validate_payload(files)
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_STORED,allowZip64=False) as archive:
        for name in NAMES:
            info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));info.create_system=3
            info.external_attr=0o100600<<16
            archive.writestr(info,files[name])
    raw=stream.getvalue()
    require(len(raw)<=MAX_ARCHIVE,'HOLD_CHECKPOINT_BACKUP_ARCHIVE_SIZE')
    manifest={'schema':'NOX_CHECKPOINT_BACKUP_MANIFEST_V1','scope':scope(),'scope_sha256':scope_sha(),
        'archive_format':'ZIP_STORED','archive_bytes':len(raw),'archive_sha256':digest(raw),
        'files':manifest_files,'training_resume_tested':False}
    return raw,manifest


def read_native_archive():
    maximum=(Path('/sys/fs/cgroup')/'memory.max').read_text().strip()
    current=int((Path('/sys/fs/cgroup')/'memory.current').read_text())
    require(maximum!='max' and int(maximum)-current>=512*1024**2,'HOLD_CHECKPOINT_BACKUP_RAM_HEADROOM')
    origin=primitives.read_regular(ROOT/'state'/('owner_maintenance_'+ORIGIN['request']+'.json'),2*1024**2)
    require(digest(origin)==ORIGIN['receipt_sha256'],'HOLD_CHECKPOINT_BACKUP_ORIGIN_ADMISSION')
    files={};total=0
    for name in NAMES:
        path=OUTPUT/'checkpoint-5'/name if name in CHECKPOINT_NAMES else OUTPUT/name
        cap=min(MAX_ARCHIVE-total,MAX_JSON if name in ('owner_lineage.json','owner_receipt_step_5.json','trainer_state.json','adapter_config.json') else MAX_ARCHIVE)
        require(cap>0,'HOLD_CHECKPOINT_BACKUP_TOTAL_SIZE')
        raw=primitives.read_regular(path,cap);files[name]=raw;total+=len(raw)
    return archive_payload(files)


def validate_manifest(value):
    require(isinstance(value,dict) and set(value)=={'schema','scope','scope_sha256','archive_format',
        'archive_bytes','archive_sha256','files','training_resume_tested'}
        and value['schema']=='NOX_CHECKPOINT_BACKUP_MANIFEST_V1' and canonical(value['scope'])==canonical(scope())
        and value['scope_sha256']==scope_sha() and value['archive_format']=='ZIP_STORED'
        and type(value['archive_bytes']) is int and 0<value['archive_bytes']<=MAX_ARCHIVE
        and sha(value['archive_sha256']) and value['training_resume_tested'] is False,
        'HOLD_CHECKPOINT_BACKUP_MANIFEST')
    rows=value['files'];require(isinstance(rows,list) and len(rows)==len(NAMES),'HOLD_CHECKPOINT_BACKUP_MANIFEST_FILES')
    for name,row in zip(NAMES,rows):
        require(isinstance(row,dict) and set(row)=={'filename','bytes','sha256'}
            and row['filename']==name and type(row['bytes']) is int and 0<row['bytes']<=MAX_ARCHIVE
            and sha(row['sha256']),'HOLD_CHECKPOINT_BACKUP_MANIFEST_FILE')
    require(sum(row['bytes'] for row in rows)<value['archive_bytes'], 'HOLD_CHECKPOINT_BACKUP_ARCHIVE_BOUND')
    require(rows[-1]['sha256']==RECEIPT_SHA,'HOLD_CHECKPOINT_BACKUP_MANIFEST_RECEIPT')
    return value


def verify_archive(raw,manifest):
    """Local restore check: read exact entries into memory, no extraction/write."""
    validate_manifest(manifest)
    require(isinstance(raw,bytes) and len(raw)==manifest['archive_bytes']
        and digest(raw)==manifest['archive_sha256'],'HOLD_CHECKPOINT_BACKUP_ARCHIVE_SHA')
    files={}
    with zipfile.ZipFile(io.BytesIO(raw),'r') as archive:
        infos=archive.infolist()
        require(len(infos)==len(NAMES) and not archive.comment,'HOLD_CHECKPOINT_BACKUP_ZIP_COUNT')
        for info,row in zip(infos,manifest['files']):
            require(info.filename==row['filename'] and info.compress_type==zipfile.ZIP_STORED
                and info.file_size==info.compress_size==row['bytes'] and info.flag_bits&1==0
                and not info.is_dir() and not info.extra and not info.comment,
                'HOLD_CHECKPOINT_BACKUP_ZIP_ENTRY')
            value=archive.read(info)
            require(digest(value)==row['sha256'],'HOLD_CHECKPOINT_BACKUP_RESTORED_FILE_SHA')
            files[info.filename]=value
    require(validate_payload(files)==manifest['files'],'HOLD_CHECKPOINT_BACKUP_RESTORED_PROOF')
    return {'schema':'NOX_CHECKPOINT_BACKUP_LOCAL_VERIFICATION_V1','state':'ARCHIVE_AND_NINE_FILES_SHA_VERIFIED',
        'manifest':manifest,'manifest_sha256':digest(canonical(manifest)),
        'successful_optimizer_steps':0,'adapter_delta_verified':False,
        'training_resume_tested':False,'full_model_backup':False,'drive_copy_verified':False}


def seal(public_metadata,request,source):
    public=public_key_metadata(public_metadata);context=primitives.owner_context(request,source)
    raw,manifest=read_native_archive();cipher_bytes=len(raw)+16;chars=((cipher_bytes+2)//3)*4
    chunks=(chars+CHUNK_CHARS-1)//CHUNK_CHARS
    require(chunks<=MAX_CHUNKS and chars<=MAX_CIPHER_CHARS,'HOLD_CHECKPOINT_BACKUP_CHUNK_BUDGET')
    aad={'schema':'NOX_CHECKPOINT_BACKUP_AAD_V1','algorithm':ALGORITHM,'manifest':manifest,
        'manifest_sha256':digest(canonical(manifest)),'key_id':public_metadata['key_id'],
        'transfer_id':public_metadata['transfer_id'],'created_at':int(time.time()),
        'expires_at':public_metadata['expires_at'],'context':context,'plaintext_bytes':len(raw),
        'chunk_chars':CHUNK_CHARS,'chunk_count':chunks,'ciphertext_bytes':cipher_bytes}
    aes=primitives.AESGCM.generate_key(bit_length=256);nonce=os.urandom(12)
    wrapped=public.encrypt(aes,primitives.padding.OAEP(mgf=primitives.padding.MGF1(primitives.hashes.SHA256()),
        algorithm=primitives.hashes.SHA256(),label=OAEP_LABEL))
    cipher=primitives.AESGCM(aes).encrypt(nonce,raw,canonical(aad));encoded=primitives.b64(cipher)
    envelope={'schema':'NOX_CHECKPOINT_BACKUP_ENVELOPE_V1','aad':aad,'wrapped_key':primitives.b64(wrapped),
        'nonce':primitives.b64(nonce),'ciphertext':encoded,'ciphertext_bytes':len(cipher),'ciphertext_sha256':digest(cipher)}
    outer=digest(canonical(envelope));header={'schema':'NOX_CHECKPOINT_BACKUP_TRANSFER_V1',
        'envelope_sha256':outer,'chunks':chunks,'chunk_chars':CHUNK_CHARS,'ciphertext_chars':chars,
        'metadata':{k:v for k,v in envelope.items() if k!='ciphertext'}}
    rows=[{'kind':'checkpoint_backup_ciphertext_header','data':header}]
    rows.extend({'kind':'checkpoint_backup_ciphertext_chunk','data':{'envelope_sha256':outer,
        'index':i,'chunks':chunks,'ciphertext':encoded[i*CHUNK_CHARS:(i+1)*CHUNK_CHARS]}} for i in range(chunks))
    require(all(len(canonical(row))<79000 for row in rows),'HOLD_CHECKPOINT_BACKUP_LOG_LINE_SIZE')
    return rows


def assemble(rows):
    require(isinstance(rows,list) and 2<=len(rows)<=MAX_CHUNKS+1,'HOLD_CHECKPOINT_BACKUP_ROW_COUNT')
    headers=[r['data'] for r in rows if isinstance(r,dict) and set(r)=={'kind','data'} and r['kind']=='checkpoint_backup_ciphertext_header']
    require(len(headers)==1,'HOLD_CHECKPOINT_BACKUP_HEADER_COUNT');h=headers[0]
    require(isinstance(h,dict) and set(h)=={'schema','envelope_sha256','chunks','chunk_chars','ciphertext_chars','metadata'}
        and h['schema']=='NOX_CHECKPOINT_BACKUP_TRANSFER_V1' and sha(h['envelope_sha256'])
        and type(h['chunks']) is int and 1<=h['chunks']<=MAX_CHUNKS
        and h['chunk_chars']==CHUNK_CHARS and type(h['ciphertext_chars']) is int
        and 0<h['ciphertext_chars']<=MAX_CIPHER_CHARS and len(rows)==h['chunks']+1
        and h['chunks']==(h['ciphertext_chars']+CHUNK_CHARS-1)//CHUNK_CHARS,
        'HOLD_CHECKPOINT_BACKUP_HEADER')
    parts={}
    for r in rows:
        require(isinstance(r,dict) and set(r)=={'kind','data'},'HOLD_CHECKPOINT_BACKUP_ROW')
        if r['kind']=='checkpoint_backup_ciphertext_header':continue
        v=r['data'];require(r['kind']=='checkpoint_backup_ciphertext_chunk' and isinstance(v,dict)
            and set(v)=={'envelope_sha256','index','chunks','ciphertext'} and v['envelope_sha256']==h['envelope_sha256']
            and type(v['chunks']) is int and v['chunks']==h['chunks'] and type(v['index']) is int
            and 0<=v['index']<h['chunks'] and v['index'] not in parts and isinstance(v['ciphertext'],str),
            'HOLD_CHECKPOINT_BACKUP_CHUNK')
        expected=CHUNK_CHARS if v['index']<h['chunks']-1 else h['ciphertext_chars']-CHUNK_CHARS*(h['chunks']-1)
        require(len(v['ciphertext'])==expected,'HOLD_CHECKPOINT_BACKUP_CHUNK_LENGTH');parts[v['index']]=v['ciphertext']
    m=h['metadata'];require(isinstance(m,dict) and set(m)=={'schema','aad','wrapped_key','nonce','ciphertext_bytes','ciphertext_sha256'},
        'HOLD_CHECKPOINT_BACKUP_ENVELOPE_SCHEMA')
    envelope=dict(m,ciphertext=''.join(parts[i] for i in range(h['chunks'])))
    require(digest(canonical(envelope))==h['envelope_sha256'],'HOLD_CHECKPOINT_BACKUP_ENVELOPE_SHA')
    return envelope,h['envelope_sha256']


def decrypt(rows,private_pem,public_metadata,request,source):
    public_key_metadata(public_metadata);context=primitives.owner_context(request,source)
    envelope,outer=assemble(rows);a=envelope['aad']
    require(envelope['schema']=='NOX_CHECKPOINT_BACKUP_ENVELOPE_V1' and isinstance(a,dict)
        and set(a)=={'schema','algorithm','manifest','manifest_sha256','key_id','transfer_id','created_at',
                    'expires_at','context','plaintext_bytes','chunk_chars','chunk_count','ciphertext_bytes'},
        'HOLD_CHECKPOINT_BACKUP_AAD_SCHEMA')
    manifest=validate_manifest(a['manifest']);total=manifest['archive_bytes'];chars=((total+18)//3)*4
    require(a['schema']=='NOX_CHECKPOINT_BACKUP_AAD_V1' and a['algorithm']==ALGORITHM
        and a['manifest_sha256']==digest(canonical(manifest)) and a['key_id']==public_metadata['key_id']
        and a['transfer_id']==public_metadata['transfer_id'] and a['expires_at']==public_metadata['expires_at']
        and canonical(a['context'])==canonical(context) and type(a['created_at']) is int
        and public_metadata['created_at']-5<=a['created_at']<=int(time.time())+5 and a['created_at']<a['expires_at']
        and type(a['plaintext_bytes']) is int and a['plaintext_bytes']==total
        and a['chunk_chars']==CHUNK_CHARS and type(a['chunk_count']) is int
        and a['chunk_count']==(chars+CHUNK_CHARS-1)//CHUNK_CHARS
        and type(a['ciphertext_bytes']) is int and a['ciphertext_bytes']==total+16
        and type(envelope['ciphertext_bytes']) is int and envelope['ciphertext_bytes']==total+16,
        'HOLD_CHECKPOINT_BACKUP_AAD_CONTEXT')
    private=primitives.serialization.load_pem_private_key(private_pem,password=None)
    require(isinstance(private,primitives.rsa.RSAPrivateKey) and private.key_size==4096,'HOLD_CHECKPOINT_BACKUP_PRIVATE_KEY')
    der=private.public_key().public_bytes(primitives.serialization.Encoding.DER,primitives.serialization.PublicFormat.SubjectPublicKeyInfo)
    require(digest(der)==public_metadata['key_id'],'HOLD_CHECKPOINT_BACKUP_PRIVATE_KEY')
    cipher=primitives.unb64(envelope['ciphertext'],total+16)
    require(len(cipher)==total+16 and digest(cipher)==envelope['ciphertext_sha256'],'HOLD_CHECKPOINT_BACKUP_CIPHER_SHA')
    wrapped=primitives.unb64(envelope['wrapped_key'],512);nonce=primitives.unb64(envelope['nonce'],12)
    require(len(wrapped)==512 and len(nonce)==12,'HOLD_CHECKPOINT_BACKUP_CRYPTO_SIZE')
    aes=private.decrypt(wrapped,primitives.padding.OAEP(mgf=primitives.padding.MGF1(primitives.hashes.SHA256()),
        algorithm=primitives.hashes.SHA256(),label=OAEP_LABEL))
    require(len(aes)==32,'HOLD_CHECKPOINT_BACKUP_AES_SIZE')
    raw=primitives.AESGCM(aes).decrypt(nonce,cipher,canonical(a))
    proof=verify_archive(raw,manifest)
    proof.update(envelope_sha256=outer,key_id=public_metadata['key_id'],transfer_id=public_metadata['transfer_id'],context=context)
    return raw,proof
