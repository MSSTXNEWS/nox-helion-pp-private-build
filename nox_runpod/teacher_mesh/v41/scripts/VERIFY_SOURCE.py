#!/usr/bin/env python3
"""Verify complete V41 file content before staging; no server changes."""
import hashlib,json,pathlib,sys
root=pathlib.Path(__file__).resolve().parents[1]
manifest=json.loads((root/'SOURCE_SHA256.json').read_text('utf8'))
if manifest.get('schema')!='NOX_V41_SOURCE_SHA256':raise SystemExit('HOLD_MANIFEST_SCHEMA')
files=manifest['files']
if len(files)!=manifest['file_count']:raise SystemExit('HOLD_MANIFEST_COUNT')
errors=[]
for rel,h in files.items():
 p=root/rel
 if not p.is_file() or not p.resolve().is_relative_to(root.resolve()):errors.append(rel+':missing');continue
 if hashlib.sha256(p.read_bytes()).hexdigest()!=h:errors.append(rel+':sha')
if errors:
 print('HOLD_SOURCE_HASH_FAILURE',errors[:20]);sys.exit(4)
print('NOX_V41_SHA_PASS',len(files))
