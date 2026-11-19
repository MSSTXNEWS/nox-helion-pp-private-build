#!/usr/bin/env python3
"""Local-only recovery and byte verification; never creates or prints a key."""
import sys
sys.dont_write_bytecode=True
import argparse
import json
import os
from pathlib import Path
import stat
import owner_checkpoint_backup_transport as transport


def private_directory(path,create=False):
    path=transport.primitives.plain(path)
    if create:path.mkdir(mode=0o700,exist_ok=False)
    info=path.stat()
    transport.require(stat.S_ISDIR(info.st_mode) and info.st_uid==os.geteuid() and not info.st_mode&0o077,
        'HOLD_CHECKPOINT_BACKUP_PRIVATE_DIRECTORY')
    return path
def write_new(path,raw):
    path=transport.primitives.plain(path);private_directory(path.parent)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())


def recover(directory,raw,request,source):
    directory=private_directory(directory)
    destination=directory/'restored'
    transport.require(not destination.exists() and not destination.is_symlink(),'HOLD_CHECKPOINT_BACKUP_ALREADY_RECOVERED')
    private=transport.primitives.read_regular(directory/'private.pem',8192,private=True)
    public=transport.decode_json(transport.primitives.read_regular(directory/'public_metadata.json',8192,private=True))
    rows=transport.decode_json(raw,transport.MAX_WIRE)
    archive,proof=transport.decrypt(rows,private,public,request,source)
    destination=private_directory(destination,create=True)
    name='nox-checkpoint5-zero-update.zip';write_new(destination/name,archive)
    local=transport.primitives.read_regular(destination/name,transport.MAX_ARCHIVE,private=True)
    transport.require(transport.digest(local)==proof['manifest']['archive_sha256'],'HOLD_CHECKPOINT_BACKUP_LOCAL_READBACK')
    write_new(destination/'verification.json',transport.canonical(proof)+b'\n')
    return {'schema':'NOX_CHECKPOINT_BACKUP_LOCAL_READY_V1','state':'PRIVATE_ARCHIVE_AND_NINE_HASHES_VERIFIED',
        'archive_name':name,'archive_bytes':len(local),'archive_sha256':transport.digest(local),
        'manifest_sha256':proof['manifest_sha256'],'files':proof['manifest']['files'],
        'successful_optimizer_steps':0,'training_resume_tested':False,'full_model_backup':False,
        'drive_copy_verified':False}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--directory',required=True);parser.add_argument('--request',required=True);parser.add_argument('--source',required=True)
    args=parser.parse_args();raw=sys.stdin.buffer.read(transport.MAX_WIRE+1)
    transport.require(len(raw)<=transport.MAX_WIRE,'HOLD_CHECKPOINT_BACKUP_LOCAL_INPUT_SIZE')
    print(json.dumps(recover(args.directory,raw,args.request,args.source),sort_keys=True))


if __name__=='__main__':
    try:main()
    except Exception as exc:
        code=str(exc)
        if not code.startswith('HOLD_') or not all(c.isupper() or c.isdigit() or c=='_' for c in code):
            code='HOLD_CHECKPOINT_BACKUP_LOCAL_'+type(exc).__name__.upper()
        print(json.dumps({'state':'HOLD','reason':code}),file=sys.stderr);raise SystemExit(2)
