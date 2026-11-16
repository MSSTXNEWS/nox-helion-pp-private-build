"""Stage only ciphertext in owned tmpfs and export bounded checkpoint5 pages.

The frozen backup validator, AES/RSA format and local decryptor are unchanged.
No trainer, current admission pointer, weight, SSD file or service is changed.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time

import owner_checkpoint_backup_transport as core

AREA=Path('/dev/shm/nox_checkpoint_backup_pages')
SCHEMA='NOX_CHECKPOINT_BACKUP_RAM_PAGER_V1'
CHUNKS_PER_PAGE=6
MAX_CIPHER_CHARS=12*1024**2
MAX_MANIFEST_BYTES=65536
SOURCE_PINS={
 'owner_media_fixture_transport':'5208f16465410140ab38da1c1e44a0711667bd34e3a4fc5f17237df11693230f',
 'owner_checkpoint_backup_transport':'9b7106f82428e47e6b79d1a79a3536519daeeb5b203b104ec25bb0342e6fc8aa',
}


def hold(code):raise RuntimeError(code)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def require(value,code):
    if not value:hold(code)
def stopped():
    return any(path.exists() or path.is_symlink() for path in
        [Path('/root/nox')/name for name in ('STOP','STOP.flag','stop.flag','.stop','program/STOP','state/STOP')]
        +[Path('/workspace/NOX_STOP')])


def admission(extra=0,writing=False):
    if stopped():hold('HOLD_CHECKPOINT_PAGER_OWNER_STOP')
    current=int(Path('/sys/fs/cgroup/memory.current').read_text())
    maximum=Path('/sys/fs/cgroup/memory.max').read_text().strip()
    require(maximum.isdigit() and int(maximum)-current>=512*1024**2+extra,
            'HOLD_CHECKPOINT_PAGER_RAM_RESERVE')
    if writing:
        with Path('/proc/self/mountinfo').open('r') as stream:mounts=stream.read(512*1024+1)
        require(len(mounts)<=512*1024 and any(
            len(row.split())>=7 and row.split()[4]=='/dev/shm' and ' - tmpfs ' in row for row in mounts.splitlines()),
            'HOLD_CHECKPOINT_PAGER_TMPFS_REQUIRED')
        values=os.statvfs('/dev/shm')
        require(values.f_bavail*values.f_frsize>=2*1024**3+extra,'HOLD_CHECKPOINT_PAGER_TMPFS_RESERVE')


def owned_directory(path,create=False):
    path=core.primitives.plain(path)
    if create:path.mkdir(mode=0o700,exist_ok=False)
    info=path.stat(follow_symlinks=False)
    require(stat.S_ISDIR(info.st_mode) and info.st_uid==os.geteuid() and stat.S_IMODE(info.st_mode)==0o700,
            'HOLD_CHECKPOINT_PAGER_DIRECTORY_OWNER')
    require(info.st_dev==Path('/dev/shm').stat().st_dev,'HOLD_CHECKPOINT_PAGER_DIRECTORY_DEVICE')
    return path


def identity(info):
    return [info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns]


def write_new(path,raw):
    path=core.primitives.plain(path);owned_directory(path.parent)
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:
        for offset in range(0,len(raw),1024**2):
            if stopped():hold('HOLD_CHECKPOINT_PAGER_OWNER_STOP')
            stream.write(raw[offset:offset+1024**2])
        stream.flush();os.fsync(stream.fileno())
    checked=core.primitives.read_regular(path,max(len(raw),1),private=True)
    require(checked==raw,'HOLD_CHECKPOINT_PAGER_WRITE_READBACK')
    return identity(path.stat(follow_symlinks=False))


def transfer_directory(transfer_id):
    require(isinstance(transfer_id,str) and re.fullmatch('[a-f0-9]{32}',transfer_id),
            'HOLD_CHECKPOINT_PAGER_TRANSFER_ID')
    return AREA/transfer_id


def summary(value,manifest_sha):
    header=value['header'];aad=header['metadata']['aad']
    return {'schema':'NOX_CHECKPOINT_BACKUP_PAGE_SUMMARY_V1','state':'CIPHERTEXT_STAGED_IN_OWNED_TMPFS',
        'manifest_sha256':manifest_sha,'transfer_id':value['transfer_id'],
        'key_id':aad['key_id'],'scope_sha256':core.scope_sha(),'sealed_context':aad['context'],
        'expires_at':value['expires_at'],'envelope_sha256':header['envelope_sha256'],
        'ciphertext_sha256':header['metadata']['ciphertext_sha256'],
        'ciphertext_base64_characters':value['ciphertext_chars'],'chunk_count':header['chunks'],
        'chunks_per_page':CHUNKS_PER_PAGE,'page_count':value['page_count'],
        'maximum_page_ciphertext_characters':CHUNKS_PER_PAGE*core.CHUNK_CHARS,
        'successful_optimizer_steps':0,'full_model_backup':False,
        'training_control_performed':False,'current_training_pointer_read':False,
        'plaintext_staged_on_native_filesystem':False,'ssd_files_written':0}


def prepare(public_metadata,request,source):
    admission(MAX_CIPHER_CHARS,writing=True)
    core.public_key_metadata(public_metadata)
    directory=transfer_directory(public_metadata['transfer_id'])
    # Exclusive creation makes retries inspect the existing immutable transfer;
    # they never silently replace a ciphertext whose pages may be in flight.
    if not AREA.exists():owned_directory(AREA,create=True)
    else:owned_directory(AREA)
    require(not directory.exists() and not directory.is_symlink(),'HOLD_CHECKPOINT_PAGER_ALREADY_STAGED')
    rows=core.seal(public_metadata,request,source)
    envelope,_=core.assemble(rows);header=rows[0]['data']
    encoded=envelope['ciphertext'].encode('ascii')
    require(0<len(encoded)<=MAX_CIPHER_CHARS,'HOLD_CHECKPOINT_PAGER_FIXED_BASELINE_SIZE')
    admission(len(encoded),writing=True)
    owned_directory(directory,create=True)
    cipher_identity=write_new(directory/'ciphertext.b64',encoded)
    manifest={'schema':SCHEMA,'source_pins':SOURCE_PINS,'transfer_id':public_metadata['transfer_id'],
        'created_at':int(time.time()),'expires_at':public_metadata['expires_at'],
        'scope_sha256':core.scope_sha(),'ciphertext_chars':len(encoded),
        'ciphertext_ascii_sha256':digest(encoded),'ciphertext_identity':cipher_identity,
        'chunks_per_page':CHUNKS_PER_PAGE,'page_count':(header['chunks']+CHUNKS_PER_PAGE-1)//CHUNKS_PER_PAGE,
        'chunk_sha256':[digest(row['data']['ciphertext'].encode('ascii')) for row in rows[1:]],
        'header':header}
    raw=core.canonical(manifest)
    require(len(raw)<=MAX_MANIFEST_BYTES,'HOLD_CHECKPOINT_PAGER_MANIFEST_BOUND')
    write_new(directory/'manifest.json',raw)
    verified=load_manifest(public_metadata['transfer_id'],digest(raw))
    return [{'kind':'checkpoint_backup_page_summary','data':summary(verified,digest(raw))},rows[0]]


def load_manifest(transfer_id,expected_sha):
    require(core.sha(expected_sha),'HOLD_CHECKPOINT_PAGER_MANIFEST_PIN')
    owned_directory(AREA);directory=owned_directory(transfer_directory(transfer_id))
    raw=core.primitives.read_regular(directory/'manifest.json',MAX_MANIFEST_BYTES,private=True)
    require(digest(raw)==expected_sha,'HOLD_CHECKPOINT_PAGER_MANIFEST_PIN')
    value=core.decode_json(raw,MAX_MANIFEST_BYTES)
    keys={'schema','source_pins','transfer_id','created_at','expires_at','scope_sha256',
          'ciphertext_chars','ciphertext_ascii_sha256','ciphertext_identity','chunks_per_page',
          'page_count','chunk_sha256','header'}
    require(isinstance(value,dict) and set(value)==keys and value['schema']==SCHEMA
        and value['source_pins']==SOURCE_PINS and value['transfer_id']==transfer_id
        and value['scope_sha256']==core.scope_sha() and type(value['expires_at']) is int
        and type(value['created_at']) is int and value['created_at']<=int(time.time())+5<value['expires_at']
        and value['chunks_per_page']==CHUNKS_PER_PAGE and type(value['ciphertext_chars']) is int
        and 0<value['ciphertext_chars']<=MAX_CIPHER_CHARS and core.sha(value['ciphertext_ascii_sha256']),
        'HOLD_CHECKPOINT_PAGER_MANIFEST_SCOPE')
    h=value['header'];m=h.get('metadata') if isinstance(h,dict) else None
    a=m.get('aad') if isinstance(m,dict) else None
    require(isinstance(h,dict) and h.get('schema')=='NOX_CHECKPOINT_BACKUP_TRANSFER_V1'
        and core.sha(h.get('envelope_sha256')) and type(h.get('chunks')) is int
        and 1<=h['chunks']<=core.MAX_CHUNKS and h.get('chunk_chars')==core.CHUNK_CHARS
        and h.get('ciphertext_chars')==value['ciphertext_chars']
        and h['chunks']==(value['ciphertext_chars']+core.CHUNK_CHARS-1)//core.CHUNK_CHARS
        and value['page_count']==(h['chunks']+CHUNKS_PER_PAGE-1)//CHUNKS_PER_PAGE
        and isinstance(a,dict) and a.get('transfer_id')==transfer_id and a.get('expires_at')==value['expires_at']
        and a.get('algorithm')==core.ALGORITHM and a.get('manifest_sha256')==digest(core.canonical(a.get('manifest'))),
        'HOLD_CHECKPOINT_PAGER_HEADER_SCOPE')
    core.validate_manifest(a['manifest'])
    context=a.get('context') or {}
    require(core.primitives.owner_context(context.get('request'),context.get('source_sha'))==context,
            'HOLD_CHECKPOINT_PAGER_SEALED_CONTEXT')
    hashes=value['chunk_sha256'];ident=value['ciphertext_identity']
    require(isinstance(hashes,list) and len(hashes)==h['chunks'] and all(core.sha(x) for x in hashes)
        and isinstance(ident,list) and len(ident)==5 and all(type(x) is int and x>=0 for x in ident)
        and ident[2]==value['ciphertext_chars'],'HOLD_CHECKPOINT_PAGER_CHUNK_INDEX')
    return value


def page(transfer_id,manifest_sha,index,request,source):
    admission();context=core.primitives.owner_context(request,source)
    value=load_manifest(transfer_id,manifest_sha)
    require(type(index) is int and 0<=index<value['page_count'],'HOLD_CHECKPOINT_PAGER_PAGE_INDEX')
    path=owned_directory(transfer_directory(transfer_id))/'ciphertext.b64'
    path=core.primitives.plain(path)
    fd=os.open(path,os.O_RDONLY|os.O_NONBLOCK|os.O_NOFOLLOW)
    rows=[]
    try:
        info=os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid==os.geteuid() and stat.S_IMODE(info.st_mode)==0o600
            and identity(info)==value['ciphertext_identity'],'HOLD_CHECKPOINT_PAGER_CIPHERTEXT_IDENTITY')
        start=index*CHUNKS_PER_PAGE;end=min(start+CHUNKS_PER_PAGE,value['header']['chunks'])
        for chunk in range(start,end):
            if stopped():hold('HOLD_CHECKPOINT_PAGER_OWNER_STOP')
            size=min(core.CHUNK_CHARS,value['ciphertext_chars']-chunk*core.CHUNK_CHARS)
            raw=os.pread(fd,size,chunk*core.CHUNK_CHARS)
            # A blocking read may finish after the owner revokes the transfer.
            # Do not stage even one post-STOP ciphertext chunk for emission.
            if stopped():hold('HOLD_CHECKPOINT_PAGER_OWNER_STOP')
            require(len(raw)==size and digest(raw)==value['chunk_sha256'][chunk],
                    'HOLD_CHECKPOINT_PAGER_CHUNK_SHA')
            text=raw.decode('ascii')
            require(re.fullmatch('[A-Za-z0-9+/]*={0,2}',text),'HOLD_CHECKPOINT_PAGER_BASE64')
            rows.append({'kind':'checkpoint_backup_ciphertext_chunk','data':{
                'envelope_sha256':value['header']['envelope_sha256'],'index':chunk,
                'chunks':value['header']['chunks'],'ciphertext':text}})
        require(identity(os.fstat(fd))==value['ciphertext_identity']
            and identity(path.stat(follow_symlinks=False))==value['ciphertext_identity'],
            'HOLD_CHECKPOINT_PAGER_CIPHERTEXT_CHANGED')
    finally:os.close(fd)
    rows.append({'kind':'checkpoint_backup_page_receipt','data':{
        'schema':'NOX_CHECKPOINT_BACKUP_PAGE_V1','transfer_id':transfer_id,'manifest_sha256':manifest_sha,
        'page_index':index,'page_count':value['page_count'],'first_chunk':start,'chunk_count':end-start,
        'envelope_sha256':value['header']['envelope_sha256'],'action_context':context,
        'ciphertext_only':True,'files_written':0,'training_control_performed':False}})
    require(len(core.canonical(rows))<390000,'HOLD_CHECKPOINT_PAGER_PAGE_OUTPUT_BOUND')
    if stopped():hold('HOLD_CHECKPOINT_PAGER_OWNER_STOP')
    return rows


def inspect(transfer_id,manifest_sha):
    if stopped():hold('HOLD_CHECKPOINT_PAGER_OWNER_STOP')
    value=load_manifest(transfer_id,manifest_sha)
    return [{'kind':'checkpoint_backup_page_summary','data':summary(value,manifest_sha)},
            {'kind':'checkpoint_backup_ciphertext_header','data':value['header']}]
