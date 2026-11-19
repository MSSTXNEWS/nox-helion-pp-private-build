#!/usr/bin/env python3
"""Pinned lossless codec wrapper around the frozen finite ciphertext pager.

Only public metadata enters this action. The original modules are never
overwritten; the isolated child receives their reviewed in-memory postimages.
"""
import base64
import hashlib
import json
import re
import types

try:BUNDLE=__NOX_BUNDLE_JSON__
except NameError:BUNDLE={}
PINS={
 'owner_media_fixture_transport.py':'5208f16465410140ab38da1c1e44a0711667bd34e3a4fc5f17237df11693230f',
 'owner_checkpoint_backup_transport.py':'9b7106f82428e47e6b79d1a79a3536519daeeb5b203b104ec25bb0342e6fc8aa',
 'owner_checkpoint_backup_pager.py':'899e0fcc857ca9897349f90b9b416c51be0262959c40e82c69e9a2ddd26946f5',
 'owner_checkpoint_backup_pager_entry.py':'a4d000f8193d2b18330e77a839c538dddae19d57bfcf4c9905fa3f1506ae654b',
 'owner_checkpoint_backup_deflated.py':'c442dc4c9598fec92d030a3d8f9de78f44c96d1b4a2f1abe146f894f9e07b5b8',
}
# Root pins fresh public metadata immediately before prepare. No private key
# is generated, read, transmitted or installed by this native action.
PUBLIC_METADATA_SHA='a5e09d3f6a98c9195c79e3befd155a723c7413dd02720afcc93d0181e78b54f5'


def digest(raw):return hashlib.sha256(raw).hexdigest()
def checked_bundle():
    result={}
    for name,pin in PINS.items():
        raw=base64.b64decode(BUNDLE.get(name,''),validate=True)
        if not raw or len(raw)>100000 or digest(raw)!=pin:
            raise RuntimeError('HOLD_DEFLATED_BACKUP_BUNDLE_PIN')
        result[name]=raw
    return result


def configured_entry():
    raw=checked_bundle()
    codec=types.ModuleType('_nox_checkpoint_deflated_codec')
    exec(compile(raw['owner_checkpoint_backup_deflated.py'],'<reviewed-lossless-codec>','exec'),codec.__dict__)
    core=codec.transform_core(raw['owner_checkpoint_backup_transport.py'])
    pager=codec.transform_pager(raw['owner_checkpoint_backup_pager.py'],
        PINS['owner_checkpoint_backup_deflated.py'],digest(core))
    entry=types.ModuleType('_nox_checkpoint_deflated_pager_entry')
    exec(compile(raw['owner_checkpoint_backup_pager_entry.py'],'<reviewed-pager-entry>','exec'),entry.__dict__)
    entry.BUNDLE=dict(BUNDLE)
    entry.BUNDLE['owner_checkpoint_backup_transport.py']=base64.b64encode(core).decode('ascii')
    entry.BUNDLE['owner_checkpoint_backup_pager.py']=base64.b64encode(pager).decode('ascii')
    entry.PINS={'owner_media_fixture_transport':PINS['owner_media_fixture_transport.py'],
        'owner_checkpoint_backup_transport':digest(core),'owner_checkpoint_backup_pager':digest(pager)}
    entry.PUBLIC_METADATA_SHA=PUBLIC_METADATA_SHA
    return entry


def main():return configured_entry().main()


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        code=str(exc)
        if not re.fullmatch('HOLD_[A-Z0-9_]{1,120}',code):code='HOLD_DEFLATED_BACKUP_ENTRY'
        print('NOX_MAINT_REPAIR='+json.dumps({'kind':'checkpoint_backup_pager_hold',
            'data':{'reason':code}},separators=(',',':')),flush=True)
        raise SystemExit(2)
