"""Exact three-function lossless ZIP codec delta for the frozen backup core.

The original source file, nine file hashes, scope, AES/RSA, AAD, key validation,
expiry and sealed native context remain unchanged. This codec accepts only its
own ZIP_DEFLATED format; the original ZIP_STORED verifier stays independent.
"""
from __future__ import annotations
import ast
import hashlib
import types

CORE_BASE_SHA='9b7106f82428e47e6b79d1a79a3536519daeeb5b203b104ec25bb0342e6fc8aa'
PAGER_BASE_SHA='899e0fcc857ca9897349f90b9b416c51be0262959c40e82c69e9a2ddd26946f5'
FUNCTIONS={
'archive_payload':r'''
def archive_payload(files):
    manifest_files=validate_payload(files)
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=False) as archive:
        for name in NAMES:
            info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));info.create_system=3
            info.external_attr=0o100600<<16;info.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(info,files[name],compress_type=zipfile.ZIP_DEFLATED,compresslevel=6)
    raw=stream.getvalue()
    require(0<len(raw)<=MAX_ARCHIVE,'HOLD_CHECKPOINT_BACKUP_ARCHIVE_SIZE')
    manifest={'schema':'NOX_CHECKPOINT_BACKUP_MANIFEST_V1','scope':scope(),'scope_sha256':scope_sha(),
        'archive_format':'ZIP_DEFLATED','archive_bytes':len(raw),'archive_sha256':digest(raw),
        'files':manifest_files,'training_resume_tested':False}
    verify_archive(raw,manifest)
    return raw,manifest
''',
'validate_manifest':r'''
def validate_manifest(value):
    require(isinstance(value,dict) and set(value)=={'schema','scope','scope_sha256','archive_format',
        'archive_bytes','archive_sha256','files','training_resume_tested'}
        and value['schema']=='NOX_CHECKPOINT_BACKUP_MANIFEST_V1' and canonical(value['scope'])==canonical(scope())
        and value['scope_sha256']==scope_sha() and value['archive_format']=='ZIP_DEFLATED'
        and type(value['archive_bytes']) is int and 0<value['archive_bytes']<=MAX_ARCHIVE
        and sha(value['archive_sha256']) and value['training_resume_tested'] is False,
        'HOLD_CHECKPOINT_BACKUP_MANIFEST')
    rows=value['files'];require(isinstance(rows,list) and len(rows)==len(NAMES),'HOLD_CHECKPOINT_BACKUP_MANIFEST_FILES')
    for name,row in zip(NAMES,rows):
        require(isinstance(row,dict) and set(row)=={'filename','bytes','sha256'}
            and row['filename']==name and type(row['bytes']) is int and 0<row['bytes']<=MAX_ARCHIVE
            and sha(row['sha256']),'HOLD_CHECKPOINT_BACKUP_MANIFEST_FILE')
    require(sum(row['bytes'] for row in rows)<=MAX_ARCHIVE,'HOLD_CHECKPOINT_BACKUP_ARCHIVE_BOUND')
    require(rows[-1]['sha256']==RECEIPT_SHA,'HOLD_CHECKPOINT_BACKUP_MANIFEST_RECEIPT')
    return value
''',
'verify_archive':r'''
def verify_archive(raw,manifest):
    """Bounded exact-member decompression in memory; never extract or unpickle."""
    validate_manifest(manifest)
    require(isinstance(raw,bytes) and len(raw)==manifest['archive_bytes']
        and digest(raw)==manifest['archive_sha256'],'HOLD_CHECKPOINT_BACKUP_ARCHIVE_SHA')
    files={};total=0
    with zipfile.ZipFile(io.BytesIO(raw),'r') as archive:
        infos=archive.infolist()
        require(len(infos)==len(NAMES) and not archive.comment,'HOLD_CHECKPOINT_BACKUP_ZIP_COUNT')
        for info,row in zip(infos,manifest['files']):
            require(info.filename==row['filename'] and info.compress_type==zipfile.ZIP_DEFLATED
                and info.file_size==row['bytes'] and 0<info.compress_size<=len(raw)
                and 0<=info.header_offset<len(raw) and info.flag_bits&1==0
                and not info.is_dir() and not info.extra and not info.comment,
                'HOLD_CHECKPOINT_BACKUP_ZIP_ENTRY')
            total+=info.file_size
            require(total<=MAX_ARCHIVE,'HOLD_CHECKPOINT_BACKUP_ARCHIVE_BOUND')
            with archive.open(info,'r') as member:
                value=member.read(row['bytes']+1)
                require(len(value)==row['bytes'] and not member.read(1),
                        'HOLD_CHECKPOINT_BACKUP_ZIP_ENTRY')
            require(digest(value)==row['sha256'],'HOLD_CHECKPOINT_BACKUP_RESTORED_FILE_SHA')
            files[info.filename]=value
    require(validate_payload(files)==manifest['files'],'HOLD_CHECKPOINT_BACKUP_RESTORED_PROOF')
    return {'schema':'NOX_CHECKPOINT_BACKUP_LOCAL_VERIFICATION_V1','state':'ARCHIVE_AND_NINE_FILES_SHA_VERIFIED',
        'manifest':manifest,'manifest_sha256':digest(canonical(manifest)),
        'successful_optimizer_steps':0,'adapter_delta_verified':False,
        'training_resume_tested':False,'full_model_backup':False,'drive_copy_verified':False}
'''}


def digest(raw):return hashlib.sha256(raw).hexdigest()
def transform_core(raw):
    if digest(raw)!=CORE_BASE_SHA:raise RuntimeError('HOLD_DEFLATED_BACKUP_CORE_PREIMAGE')
    text=raw.decode();tree=ast.parse(text)
    for name,replacement in FUNCTIONS.items():
        nodes=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name==name]
        if len(nodes)!=1:raise RuntimeError('HOLD_DEFLATED_BACKUP_FUNCTION_ANCHOR')
        old=ast.get_source_segment(raw.decode(),nodes[0])
        if text.count(old)!=1:raise RuntimeError('HOLD_DEFLATED_BACKUP_FUNCTION_ANCHOR')
        text=text.replace(old,replacement.strip(),1)
    compile(text,'<reviewed-deflated-checkpoint-core>','exec')
    return text.encode()


def core_module(raw):
    changed=transform_core(raw);module=types.ModuleType('_nox_deflated_checkpoint_core')
    exec(compile(changed,'<reviewed-deflated-checkpoint-core>','exec'),module.__dict__)
    return module


def transform_pager(raw,codec_sha,core_sha):
    if digest(raw)!=PAGER_BASE_SHA:raise RuntimeError('HOLD_DEFLATED_BACKUP_PAGER_PREIMAGE')
    if any(len(value)!=64 or any(c not in '0123456789abcdef' for c in value) for value in (codec_sha,core_sha)):
        raise RuntimeError('HOLD_DEFLATED_BACKUP_SOURCE_PIN')
    text=raw.decode()
    changes={
        "AREA=Path('/dev/shm/nox_checkpoint_backup_pages')":
            "AREA=Path('/dev/shm/nox_checkpoint_backup_deflated_pages')",
        "SCHEMA='NOX_CHECKPOINT_BACKUP_RAM_PAGER_V1'":
            "SCHEMA='NOX_CHECKPOINT_BACKUP_DEFLATED_RAM_PAGER_V1'",
        " 'owner_checkpoint_backup_transport':'"+CORE_BASE_SHA+"',":
            " 'owner_checkpoint_backup_transport':'"+core_sha+"',\n"
            " 'owner_checkpoint_backup_transport_base':'"+CORE_BASE_SHA+"',\n"
            " 'owner_checkpoint_backup_deflated':'"+codec_sha+"',",
        "'key_id':aad['key_id'],'scope_sha256':core.scope_sha(),'sealed_context':aad['context'],":
            "'key_id':aad['key_id'],'scope_sha256':core.scope_sha(),'sealed_context':aad['context'],\n"
            "        'archive_format':aad['manifest']['archive_format'],",
    }
    for old,new in changes.items():
        if text.count(old)!=1:raise RuntimeError('HOLD_DEFLATED_BACKUP_PAGER_ANCHOR')
        text=text.replace(old,new,1)
    compile(text,'<reviewed-deflated-checkpoint-pager>','exec')
    return text.encode()
