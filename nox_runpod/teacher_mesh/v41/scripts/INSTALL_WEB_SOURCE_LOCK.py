#!/usr/bin/env python3
"""NOX V41 atomic-ish source-locked patch of EXISTING V29.3 training pages.

No new server, no auto launch; preflight checks every file BEFORE touching any.
Backups retained for independent rollback, on errors original bytes restored.
"""
from __future__ import annotations
import argparse,hashlib,json,os,pathlib,shutil

ASSETS=('nox-learning-3axes.js','nox-learning-3axes.css','nox-learning-3axes-dashboard.json')
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()

def install(target_web_root,apply=False):
    root=pathlib.Path(__file__).resolve().parents[1]
    target=pathlib.Path(target_web_root).resolve()
    contract=json.loads((root/'source_contract/WEB_V29_3_BASELINE.json').read_text('utf8'))
    if not target.is_dir() or target.is_symlink():return {'state':'HOLD_WEB_ROOT_NOT_VERIFIED'}
    originals=[]
    for name,entry in contract['web_paths'].items():
        rel=name.removeprefix('site/')
        dest=target/rel;src=root/'web'/name
        if not dest.is_file() or dest.is_symlink() or not src.is_file():
            return {'state':'HOLD_WEB_SOURCE_MISSING','path':str(dest)}
        if sha(dest)!=entry['base_sha256'] or sha(src)!=entry['patched_sha256']:
            return {'state':'HOLD_BASELINE_SHA_MISMATCH','path':str(dest)}
        if dest.with_name(dest.name+'.nox41-original.bak').exists():
            return {'state':'HOLD_PREEXISTING_BACKUP','path':str(dest)}
        originals.append((src,dest))
    assets=[]
    for a in ASSETS:
        src=root/'web'/a;dest=target/a
        if not src.is_file() or dest.exists() or dest.is_symlink():
            return {'state':'HOLD_ASSET_CONFLICT','path':str(dest)}
        assets.append((src,dest))
    if not apply:
        return {'state':'READY_SOURCE_LOCK_ONLY','no_write':True,'files':[str(p) for _,p in originals],
                'new_assets':[str(p) for _,p in assets]}
    backups=[];new_files=[]
    try:
        for src,dest in originals:
            backup=dest.with_name(dest.name+'.nox41-original.bak')
            # O_EXCL avoids overwriting any backup, with fsync of its contents.
            with backup.open('xb') as f:
                f.write(dest.read_bytes());f.flush();os.fsync(f.fileno())
            backups.append((backup,dest))
        for src,dest in assets:
            with dest.open('xb') as f:
                f.write(src.read_bytes());f.flush();os.fsync(f.fileno())
            new_files.append(dest)
        for src,dest in originals:
            tmp=dest.with_name(dest.name+'.nox41-tmp')
            with tmp.open('xb') as f:
                f.write(src.read_bytes());f.flush();os.fsync(f.fileno())
            os.replace(tmp,dest)
        if any(sha(dest)!=sha(src) for src,dest in originals+assets):
            raise RuntimeError('READBACK_HASH_MISMATCH')
    except Exception as ex:
        for tmp in target.rglob('*.nox41-tmp'):
            try:tmp.unlink()
            except OSError:pass
        for backup,dest in reversed(backups):
            if backup.is_file():
                try:shutil.copy2(backup,dest)
                except OSError:pass
        for dest in new_files:
            try:dest.unlink()
            except OSError:pass
        return {'state':'HOLD_APPLY_FAILED_ROLLBACK_ATTEMPTED','error':type(ex).__name__,
                'requires_manual_restore_check':True}
    return {'state':'INSTALLED_WEB_FILES_ONLY_SOURCE_VERIFIED',
            'server_restarted':False,'training_changed':False,'backups':[str(b) for b,_ in backups]}

def main():
    p=argparse.ArgumentParser();p.add_argument('--target-web-root',required=True)
    p.add_argument('--apply',action='store_true');a=p.parse_args()
    result=install(a.target_web_root,a.apply)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if result['state'].startswith('HOLD'):raise SystemExit(4)
if __name__=='__main__':main()
