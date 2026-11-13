#!/usr/bin/env python3
"""Validate real full SHA of 35B/GGUF artifacts from an owner-approved manifest.

No GGUF conversion or trainer shutdown. Use low-I/O scheduling on busy V100.
Requires exact expected hash per file and forbids path traversal and symlinks.
"""
from __future__ import annotations
import argparse,hashlib,json,re
from pathlib import Path


def verify(root,manifest):
    root=Path(root).resolve(strict=True)
    if not root.is_dir():raise ValueError('ROOT_REQUIRED')
    if manifest.get('schema')!='NOX_V37_EXPECTED_PARTS_SHA256' or not isinstance(manifest.get('parts'),list):
        raise ValueError('MANIFEST_SCHEMA_HOLD')
    statuses=[]
    for it in manifest['parts']:
        rel=it.get('relative_path')
        sha=it.get('sha256')
        size=it.get('bytes')
        if not isinstance(rel,str) or rel.startswith('/') or '\\' in rel or '..' in Path(rel).parts or not re.fullmatch(r'[0-9a-f]{64}',str(sha)):
            raise ValueError('UNSAFE_MANIFEST_ITEM')
        p=root/rel
        if p.is_symlink() or not p.is_file() or not p.resolve().is_relative_to(root):
            statuses.append({'part':rel,'state':'MISSING_OR_SYMLINK_HOLD'});continue
        if type(size)is not int or p.stat().st_size!=size:
            statuses.append({'part':rel,'state':'SIZE_MISMATCH_HOLD'});continue
        h=hashlib.sha256()
        with p.open('rb') as f:
            for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
        statuses.append({'part':rel,'state':'SHA_PASS' if h.hexdigest()==sha else 'SHA_MISMATCH_HOLD'})
    return {'state':'ALL_PARTS_SHA_PASS' if all(x['state']=='SHA_PASS' for x in statuses) and statuses else 'HOLD',
            'parts':statuses,'gguf_generated':False,'weight_training_started':False}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--manifest',required=True)
    a=p.parse_args();m=json.loads(Path(a.manifest).read_text('utf-8'))
    print(json.dumps(verify(a.root,m),ensure_ascii=False,indent=2))
