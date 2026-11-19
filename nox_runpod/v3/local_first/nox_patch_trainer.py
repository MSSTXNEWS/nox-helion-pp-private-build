#!/usr/bin/env python3
"""Compile-safe copy of archived NOX trainer with all hot I/O configurable.

No existing trainer is modified or started. Only writes a NEW output script and a SHA receipt.
"""
import argparse, ast, hashlib, json, os, pathlib, sys

def hashbytes(b):return hashlib.sha256(b).hexdigest()

def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--source',required=True,help='The original copied archived train_n36.py')
 p.add_argument('--dest',required=True,help='NEW /root/nox_local/scripts/train_n36_local.py')
 args=p.parse_args(argv)
 src=os.path.abspath(args.source); dest=os.path.abspath(args.dest)
 if src==dest or dest.startswith('/workspace/') or dest=='/workspace':
  raise SystemExit('SOURCE_REWRITE_FORBIDDEN_OR_NETWORK_OUTPUT')
 data=open(src,'rb').read()
 text=data.decode('utf8')
 replacements={
  "sys.path.insert(0,'/workspace/nox_seed_gpu')":"sys.path.insert(0,os.environ.get('NOX_SEED_PATH','/root/nox_local/seed'))",
  "W='/workspace/nox36'":"W=os.environ.get('NOX_WORKDIR','/root/nox_local')",
  "BASE=os.environ.get('BASE','/workspace/base36/Qwen3.6-35B-A3B')":"BASE=os.environ.get('BASE','/dev/shm/base36')",
  "TD='/workspace/nox36/data/tok'":"TD=os.environ.get('TD',f'{W}/data/tok')",
 }
 for old,new in replacements.items():
  if text.count(old)!=1:raise SystemExit('SOURCE_CONTRACT_CHANGED_EXPECTED_ONCE: '+old)
  text=text.replace(old,new)
 if "'/workspace" in '\n'.join(line for line in text.splitlines() if not line.strip().startswith('#')):
  raise SystemExit('WORKSPACE_DEPENDENCY_REMAINING')
 ast.parse(text,filename=dest)
 os.makedirs(os.path.dirname(dest),exist_ok=True)
 if os.path.lexists(dest):
  if open(dest,'rb').read()==text.encode('utf8'):
   print('ALREADY_PATCHED_SAME_SHA',hashbytes(text.encode('utf8')));return 0
  raise SystemExit('DEST_EXISTS_DIFFERENT_DO_NOT_OVERWRITE')
 with open(dest+'.nox-new','xb') as f:
  f.write(text.encode('utf8'));f.flush();os.fsync(f.fileno())
 os.replace(dest+'.nox-new',dest)
 receipt={'schema':'nox-trainer-local-path-patch-v1','sourceSha256':hashbytes(data),
  'patchedSha256':hashbytes(text.encode('utf8')),'dest':dest,
  'onlyPathsChanged':True,'trainingAlgorithmUnchanged':True,'trainerStarted':False}
 with open(dest+'.receipt.json','x',encoding='utf8') as f:json.dump(receipt,f,indent=2)
 print(json.dumps(receipt));return 0
if __name__=='__main__':sys.exit(main())
