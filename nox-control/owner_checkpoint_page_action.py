#!/usr/bin/env python3
"""One explicit, bounded action on the encrypted checkpoint transport."""
import base64
import hashlib
import os
import types

try:BUNDLE=__NOX_BUNDLE_JSON__
except NameError:BUNDLE={}
ENTRY_SHA='133e49867e5b97493d6bc3047b1b45ec993b42f3772a6e1cde3e6b605a268d95'
ACTION='page'
TRANSFER_ID='6cd298dabe632e4fadd3a39442b328a0'
MANIFEST_SHA='7a367c32efad33b09b4f19b26866fd57262ad4914e1afa32b1815774a0923270'
PAGE_INDICES=(7,)

def main():
    raw=base64.b64decode(BUNDLE.get('owner_checkpoint_backup_deflated_entry.py',''),validate=True)
    if not raw or len(raw)>100000 or hashlib.sha256(raw).hexdigest()!=ENTRY_SHA:
        raise RuntimeError('HOLD_CHECKPOINT_PAGE_ENTRY_PIN')
    module=types.ModuleType('_nox_checkpoint_page_action')
    exec(compile(raw,'<reviewed-checkpoint-page-action>','exec'),module.__dict__)
    module.BUNDLE=BUNDLE
    os.environ['NOX_CHECKPOINT_PAGER_ACTION']=ACTION
    os.environ['NOX_CHECKPOINT_PAGER_TRANSFER_ID']=TRANSFER_ID
    os.environ['NOX_CHECKPOINT_PAGER_MANIFEST_SHA256']=MANIFEST_SHA
    if ACTION!='page' or not 1<=len(PAGE_INDICES)<=2 or tuple(sorted(set(PAGE_INDICES)))!=PAGE_INDICES:
        raise RuntimeError('HOLD_CHECKPOINT_PAGE_BATCH_SCOPE')
    for page_index in PAGE_INDICES:
        if type(page_index) is not int or not 0<=page_index<8:
            raise RuntimeError('HOLD_CHECKPOINT_PAGE_BATCH_SCOPE')
        os.environ['NOX_CHECKPOINT_PAGER_PAGE_INDEX']=str(page_index)
        code=module.main()
        if code not in (None,0):return code
    return 0

if __name__=='__main__':raise SystemExit(main())
