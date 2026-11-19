#!/usr/bin/env python3
"""NOX V43 PC-only cold-vault downloader. No model execution, services or deletion.

Runs only after --download and explicit model IDs or --all. Existing files are
never overwritten. Exact GGUF content SHA checked; official snapshots are
pinned to source revision, individual file SHA recorded after download.
"""
from __future__ import annotations
import argparse, datetime as dt, hashlib, json, os, pathlib, re, shutil, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'models.v43.json'
ID_RE = re.compile(r'^[a-z0-9-]{3,60}$')
SHA_RE = re.compile(r'^[a-f0-9]{64}$')
REPO_RE = re.compile(r'^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$')


def manifest(path=MANIFEST):
    data=json.loads(pathlib.Path(path).read_text(encoding='utf8'))
    if data.get('schema')!='nox-v43-cold-vault-1':raise ValueError('MANIFEST_SCHEMA_HOLD')
    items=data['models']
    if len(items)!=5 or len({m['id'] for m in items})!=5:raise ValueError('MANIFEST_COUNT_HOLD')
    for m in items:
        if not ID_RE.fullmatch(m['id']) or not REPO_RE.fullmatch(m['source_repo']):raise ValueError('BAD_SOURCE_HOLD')
        if m['method'] not in ('single_file','official_snapshot'):raise ValueError('BAD_METHOD_HOLD')
        if m['method']=='single_file':
            if not m['source_file'].endswith('.gguf') or '/' in m['source_file'] or not SHA_RE.fullmatch(m['sha256']):
                raise ValueError('BAD_GGUF_HOLD')
    return data


def digest_file(path, chunk=8*1024*1024):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(chunk), b''):h.update(b)
    return h.hexdigest()


def existing_status(model,folder, hash_existing=False):
    target=pathlib.Path(folder)
    if model['method']=='single_file':
        f=target/model['source_file']
        if not f.is_file():return 'MISSING'
        if not hash_existing:return 'PRESENT_UNVERIFIED'
        return 'VALID_SHA' if digest_file(f)==model['sha256'] else 'HOLD_SHA_MISMATCH'
    # A snapshot requires its receipt and full pinned file inventory.
    receipt=target/'NOX_V43_VERIFIED_RECEIPT.json'
    if not receipt.is_file():return 'PRESENT_UNVERIFIED' if target.exists() else 'MISSING'
    try:
        data=json.loads(receipt.read_text(encoding='utf8'))
        if data.get('repo_id')!=model['source_repo'] or not SHA_RE.fullmatch(data.get('revision','')):return 'HOLD_UNTRUSTED_RECEIPT'
        records=data.get('files') or []
        if not records:return 'HOLD_EMPTY_RECEIPT'
        for row in records:
            f=(target/row['relative_path']).resolve()
            if not f.is_relative_to(target.resolve()) or not f.is_file() or f.stat().st_size!=row['bytes']:
                return 'HOLD_MISSING_OR_CHANGED_FILE'
            if hash_existing and digest_file(f)!=row['sha256']:return 'HOLD_SHA_MISMATCH'
        return 'VALID_SHA' if hash_existing else 'PRESENT_WITH_RECEIPT'
    except (OSError,ValueError,KeyError,TypeError):return 'HOLD_BAD_RECEIPT'


def disk_admit(vault, estimate_gb, reserve_gb=12):
    path=pathlib.Path(vault)
    path.mkdir(parents=True,exist_ok=True)
    free=shutil.disk_usage(path).free
    need=int((estimate_gb+reserve_gb)*1_000_000_000)
    return {'state':'READY' if free>=need else 'HOLD_DISK',
            'free_gb':round(free/1e9,2),'required_gb':round(need/1e9,2)}


def save_receipt(path, payload):
    dest=pathlib.Path(path)
    if dest.exists():
        raise FileExistsError('HOLD_RECEIPT_EXISTS_NO_OVERWRITE')
    tmp=dest.with_suffix(dest.suffix+'.partial')
    with tmp.open('x',encoding='utf8') as f:
        f.write(json.dumps(payload,ensure_ascii=False,indent=2)+'\n');f.flush();os.fsync(f.fileno())
    os.replace(tmp,dest)


def fetch_one(model,vault,hub_api=None,download_file=None,snapshot=None):
    """Library injected for tests; real huggingface_hub resolved in main only."""
    folder=pathlib.Path(vault)/model['id']
    current=existing_status(model,folder,hash_existing=True)
    if current=='VALID_SHA':return {'id':model['id'],'state':'SKIP_SHA_VERIFIED','dir':str(folder)}
    if current.startswith('HOLD_'):return {'id':model['id'],'state':current}
    # Resume incomplete official snapshot ONLY at its previously pinned 40-char revision.
    pending=folder/'NOX_V43_PENDING_REVISION.json'
    pinned=None
    if model['method']=='official_snapshot' and folder.exists() and any(folder.iterdir()):
        if not pending.is_file():
            return {'id':model['id'],'state':'HOLD_EXISTING_SNAPSHOT_UNVERIFIED'}
        try:
            p=json.loads(pending.read_text(encoding='utf8'))
            if p.get('repo_id')!=model['source_repo'] or not re.fullmatch(r'[a-f0-9]{40}',p.get('revision','')):
                return {'id':model['id'],'state':'HOLD_BAD_PENDING_REVISION'}
            pinned=p['revision']
        except (OSError,ValueError,TypeError):
            return {'id':model['id'],'state':'HOLD_BAD_PENDING_REVISION'}
    # Preserve space needed for checkpoints; PC drive is cold storage, not Vast.
    d=disk_admit(vault,model['approx_gb'])
    if d['state']!='READY':return {'id':model['id'],**d}
    if hub_api is None or download_file is None or snapshot is None:
        return {'id':model['id'],'state':'HOLD_HUB_LIBRARY_NOT_AVAILABLE'}
    # Pin the revision before fetching bytes; never execute remote repository code.
    revision=pinned
    if revision is None:
        info=hub_api.model_info(model['source_repo'])
        revision=info.sha
    if not isinstance(revision,str) or not re.fullmatch(r'[a-f0-9]{40}',revision):
        return {'id':model['id'],'state':'HOLD_UPSTREAM_REVISION_UNVERIFIED'}
    folder.mkdir(parents=True,exist_ok=True)
    if model['method']=='official_snapshot' and not pending.exists():
        save_receipt(pending,{'repo_id':model['source_repo'],'revision':revision,
                              'purpose':'PINNED_RESUMABLE_OFFICIAL_SNAPSHOT_ONLY'})
    if model['method']=='single_file':
        dest=folder/model['source_file']
        if dest.exists():return {'id':model['id'],'state':'HOLD_PREEXISTING_FILE_NOT_VERIFIED'}
        file_path=download_file(repo_id=model['source_repo'],filename=model['source_file'],revision=revision,local_dir=str(folder))
        if pathlib.Path(file_path).resolve()!=dest.resolve() or not dest.is_file():
            return {'id':model['id'],'state':'HOLD_DOWNLOADED_FILE_LOCATION'}
        actual=digest_file(dest)
        if actual!=model['sha256']:return {'id':model['id'],'state':'HOLD_DOWNLOADED_SHA_MISMATCH', 'actual_sha256':actual}
        files=[{'relative_path':model['source_file'],'sha256':actual,'bytes':dest.stat().st_size}]
    else:
        snapshot(repo_id=model['source_repo'],revision=revision,local_dir=str(folder),
                 allow_patterns=['*.safetensors','*.json','*.txt','*.model','*.pth','*.yaml','*.bin','*.vocab','*.merges','tokenizer*'],
                 ignore_patterns=['assets/*','examples/*','google/*','*.py','*.sh'])
        files=[]
        for f in sorted(folder.rglob('*')):
            if f.is_file() and '.cache' not in f.parts:
                files.append({'relative_path':f.relative_to(folder).as_posix(),
                              'sha256':digest_file(f),'bytes':f.stat().st_size})
        if not files or not any(f['bytes']>100_000_000 for f in files):
            return {'id':model['id'],'state':'HOLD_NO_LARGE_WEIGHT_FILE'}
    receipt={'schema':'NOX_V43_FILE_RECEIPT','id':model['id'],'repo_id':model['source_repo'],
             'revision':revision,'verified_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
             'files':files,'executable_code_loaded':False,
             'ready_for_inference':False,'ready_for_training':False}
    save_receipt(folder/'NOX_V43_VERIFIED_RECEIPT.json',receipt)
    return {'id':model['id'],'state':'DOWNLOADED_AND_HASHED','revision':revision,'files':len(files),
            'bytes':sum(f['bytes'] for f in files),'dir':str(folder)}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',default=r'C:\NOX_HELION\MODEL_VAULT' if os.name=='nt' else str(pathlib.Path.home()/'NOX_HELION'/'MODEL_VAULT'))
    p.add_argument('--ids',nargs='*')
    p.add_argument('--all',action='store_true')
    p.add_argument('--download',action='store_true',help='Explicitly allow downloading model weights')
    p.add_argument('--audit-hashes',action='store_true')
    args=p.parse_args(argv)
    data=manifest()
    all_models={m['id']:m for m in data['models']}
    selected=list(all_models) if args.all else (args.ids or list(all_models))
    if any(k not in all_models for k in selected):p.error('unknown model ID')
    if args.download:
        if not args.all and not args.ids:p.error('for downloads provide --ids ... or --all')
        try:
            from huggingface_hub import HfApi, hf_hub_download, snapshot_download
            hub=HfApi()
        except ImportError:
            print('HOLD_INSTALL_DEPENDENCY: py -3 -m pip install huggingface_hub');return 4
    else: hub=hf_hub_download=snapshot_download=None
    out=[]
    for key in selected:
        m=all_models[key]
        folder=pathlib.Path(args.root)/m['id']
        if args.download:
            try:r=fetch_one(m,args.root,hub,hf_hub_download,snapshot_download)
            except Exception as e:r={'id':key,'state':'HOLD_DOWNLOAD_ERROR','error':type(e).__name__}
        else:
            r={'id':key,'state':existing_status(m,folder,hash_existing=args.audit_hashes),
               'tier':m['tier'],'estimate_gb':m['approx_gb'],'path':str(folder)}
        out.append(r)
        print(json.dumps(r,ensure_ascii=False),flush=True)
    if args.download and any(x['state'].startswith('HOLD_') for x in out):return 4
    return 0

if __name__=='__main__':sys.exit(main())
