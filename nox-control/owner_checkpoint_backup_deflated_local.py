#!/usr/bin/env python3
"""Local-only, exact-source lossless archive verification and private recovery.

The frozen local decryptor retains its private-directory, fresh-destination,
key/expiry, AAD, SHA and readback gates. No private key is generated here.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import types
sys.dont_write_bytecode=True

PINS={
 'owner_media_fixture_transport.py':'5208f16465410140ab38da1c1e44a0711667bd34e3a4fc5f17237df11693230f',
 'owner_checkpoint_backup_transport.py':'9b7106f82428e47e6b79d1a79a3536519daeeb5b203b104ec25bb0342e6fc8aa',
 'owner_checkpoint_backup_deflated.py':'c442dc4c9598fec92d030a3d8f9de78f44c96d1b4a2f1abe146f894f9e07b5b8',
 'owner_checkpoint_backup_local.py':'a4a90aeefaf13da9aa17eeb85bc82a10a28e16d08ac14f8c932b8c8e53046c88',
}


def sources():
    result={}
    for name,pin in PINS.items():
        path=Path(__file__).absolute().parent/name
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        try:
            before=os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or not 0<before.st_size<=100000:
                raise RuntimeError('HOLD_DEFLATED_BACKUP_LOCAL_SOURCE')
            raw=os.read(fd,100001);after=os.fstat(fd)
            ident=lambda value:(value.st_dev,value.st_ino,value.st_size,value.st_mtime_ns,value.st_ctime_ns)
            if (len(raw)!=before.st_size or ident(before)!=ident(after)
                    or ident(after)!=ident(path.stat(follow_symlinks=False))
                    or hashlib.sha256(raw).hexdigest()!=pin):
                raise RuntimeError('HOLD_DEFLATED_BACKUP_LOCAL_SOURCE')
        finally:os.close(fd)
        result[name]=raw
    return result


def local_module():
    raw=sources()
    codec=types.ModuleType('_nox_checkpoint_deflated_local_codec')
    exec(compile(raw['owner_checkpoint_backup_deflated.py'],'<reviewed-lossless-codec>','exec'),codec.__dict__)
    postimage=codec.transform_core(raw['owner_checkpoint_backup_transport.py'])
    names=('owner_media_fixture_transport','owner_checkpoint_backup_transport')
    previous={name:sys.modules.get(name) for name in names}
    try:
        for name,code in ((names[0],raw['owner_media_fixture_transport.py']),(names[1],postimage)):
            module=types.ModuleType(name);sys.modules[name]=module
            exec(compile(code,'<reviewed-lossless-backup>','exec'),module.__dict__)
        local=types.ModuleType('_nox_checkpoint_deflated_local')
        exec(compile(raw['owner_checkpoint_backup_local.py'],'<reviewed-local-recovery>','exec'),local.__dict__)
        return local
    finally:
        for name in names:
            if previous[name] is None:sys.modules.pop(name,None)
            else:sys.modules[name]=previous[name]


def main():return local_module().main()


if __name__=='__main__':
    try:main()
    except Exception as exc:
        code=str(exc)
        if not re.fullmatch('HOLD_[A-Z0-9_]{1,120}',code):code='HOLD_DEFLATED_BACKUP_LOCAL'
        print(json.dumps({'state':'HOLD','reason':code}),file=sys.stderr)
        raise SystemExit(2)
