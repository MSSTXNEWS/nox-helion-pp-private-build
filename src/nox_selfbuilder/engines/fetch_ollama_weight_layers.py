#!/usr/bin/env python3
"""NOX Express: isolated, content-addressed Ollama model acquisition only.
No model is admitted or installed into a user's Ollama by this script.
Use --execute on an authorized network-capable CI/Windows host.
"""
import argparse, hashlib, json, os, re, shutil, sys, tempfile, time, urllib.request
from pathlib import Path
from urllib.parse import urlsplit

MODELS = {
    "qwen2.5-coder:7b": {"display_digest_prefix": "dae161e27b0e", "role":"CODER", "expected_approx_bytes":4700000000, "license":"Apache-2.0", "url":"https://ollama.com/library/qwen2.5-coder:7b"},
    "qwen3-embedding:0.6b": {"display_digest_prefix": "ac6da0dfba84", "role":"EMBEDDING", "expected_approx_bytes":639000000, "license":"Apache-2.0-review", "url":"https://ollama.com/library/qwen3-embedding:0.6b"},
}
REGISTRY="https://registry.ollama.ai"
DIGEST=re.compile(r'^sha256:([0-9a-f]{64})$')

def sha_file(path):
    h=hashlib.sha256()
    with open(path,'rb') as fp:
        for block in iter(lambda:fp.read(2**20),b''):h.update(block)
    return h.hexdigest()

def secure_open(url, *, headers=None, timeout=90):
    if urlsplit(url).scheme!='https' or urlsplit(url).hostname!='registry.ollama.ai':
        raise ValueError('ONLY_OFFICIAL_OLLAMA_REGISTRY_ALLOWED')
    response=urllib.request.urlopen(urllib.request.Request(url,headers=headers or {"User-Agent":"NOX-EXPRESS-Block2/1.0"}),timeout=timeout)
    # Ollama registry may return time-bounded CDN URLs; only public HTTPS, no credential forwarding.
    if urlsplit(response.geturl()).scheme!='https':
        response.close();raise ValueError('UNTRUSTED_REDIRECT_PROTOCOL')
    return response

def manifest_and_blobs(model, tag):
    with secure_open(f'{REGISTRY}/v2/library/{model}/manifests/{tag}',headers={'Accept':'application/vnd.docker.distribution.manifest.v2+json','User-Agent':'NOX-EXPRESS-Block2/1.0'}) as response:
        data=response.read(2**20+1)
    if len(data)>2**20: raise ValueError('MANIFEST_TOO_LARGE')
    parsed=json.loads(data)
    if parsed.get('schemaVersion')!=2 or not isinstance(parsed.get('layers'),list): raise ValueError('INVALID_OCI_MANIFEST')
    manifest_sha=hashlib.sha256(data).hexdigest()
    layers=[parsed.get('config',{})]+parsed['layers']
    out=[]
    for item in layers:
        found=DIGEST.fullmatch(str(item.get('digest','')))
        if not found:raise ValueError('INVALID_LAYER_DIGEST')
        size=item.get('size')
        if not isinstance(size,int) or not (0<size<10*1024**3):raise ValueError('UNSAFE_LAYER_SIZE')
        out.append({'digest':item['digest'],'bytes':size,'mediaType':item.get('mediaType','')})
    if sum(i['bytes'] for i in out)>10*1024**3:raise ValueError('MODEL_OVER_BUDGET')
    return data,manifest_sha,out

def manifest_cache_target(out, model, version):
    """Reject redirected/dangling OCI manifest cache directories and files."""
    root = Path(out)
    if root.is_symlink() or getattr(root, 'is_junction', lambda: False)():
        raise ValueError('UNSAFE_MANIFEST_CACHE_ROOT')
    root.mkdir(parents=True, exist_ok=True)
    if not root.is_dir() or root.is_symlink() or getattr(root, 'is_junction', lambda: False)():
        raise ValueError('UNSAFE_MANIFEST_CACHE_ROOT')
    current = root
    for part in ('manifests', 'registry.ollama.ai', 'library', model):
        current = current / part
        if current.is_symlink() or getattr(current, 'is_junction', lambda: False)():
            raise ValueError('UNSAFE_MANIFEST_CACHE_DIRECTORY')
        if current.exists() and not current.is_dir():
            raise ValueError('UNSAFE_MANIFEST_CACHE_DIRECTORY')
        current.mkdir(exist_ok=True)
        if not current.is_dir() or current.is_symlink() or getattr(current, 'is_junction', lambda: False)():
            raise ValueError('UNSAFE_MANIFEST_CACHE_DIRECTORY')
    target = current / version
    if target.is_symlink() or getattr(target, 'is_junction', lambda: False)() or (target.exists() and not target.is_file()):
        raise ValueError('UNSAFE_MANIFEST_CACHE_FILE')
    return target

def download_blob(model,digest,expected_size,root):
    match=DIGEST.fullmatch(digest)
    if not match: raise ValueError('INVALID_LAYER_DIGEST')
    hexsha=match.group(1)
    folder=root/'blobs'
    # A valid hash must never bless a redirected cache path.  Windows
    # junctions and symlinks can point to arbitrary user data even when the
    # referred-to bytes happen to have the expected digest.
    if folder.is_symlink() or getattr(folder,'is_junction',lambda:False)():
        raise ValueError('UNSAFE_BLOB_CACHE_DIRECTORY')
    folder.mkdir(parents=True,exist_ok=True)
    if not folder.is_dir() or folder.is_symlink() or getattr(folder,'is_junction',lambda:False)():
        raise ValueError('UNSAFE_BLOB_CACHE_DIRECTORY')
    done=folder/f'sha256-{hexsha}'
    # Path.exists() is false for dangling links; reject links before any
    # existence/hash check so they can never become a trusted OCI blob.
    if done.is_symlink() or getattr(done,'is_junction',lambda:False)():
        raise ValueError('UNSAFE_PREEXISTING_BLOB_PATH')
    if done.exists():
        if not done.is_file():
            raise ValueError('UNSAFE_PREEXISTING_BLOB_PATH')
        if done.stat().st_size==expected_size and sha_file(done)==hexsha:
            return {'digest':digest,'bytes':expected_size,'status':'ALREADY_SHA256_VERIFIED'}
        raise ValueError('PREEXISTING_BLOB_SHA_MISMATCH')
    # No unchecked partial is ever renamed to a content-addressed blob.
    partial=folder/f'.partial-{hexsha}'
    # A complete interrupted transfer has no remaining HTTP range (416).
    # Preserve mismatched partials for diagnosis rather than discard their bytes.
    if partial.is_symlink() or getattr(partial,'is_junction',lambda:False)():
        raise ValueError('UNSAFE_PARTIAL_BLOB_PATH')
    if partial.exists() and not partial.is_file():
        raise ValueError('UNSAFE_PARTIAL_BLOB_PATH')
    offset=partial.stat().st_size if partial.exists() else 0
    if offset==expected_size and sha_file(partial)==hexsha:
        os.replace(partial,done)
        return {'digest':digest,'bytes':expected_size,'status':'RECOVERED_COMPLETE_SHA256_VERIFIED'}
    if offset>=expected_size and partial.exists():
        quarantine=folder/f'.corrupt-{hexsha}-{time.time_ns()}'
        if quarantine.exists() or quarantine.is_symlink():
            raise ValueError('PARTIAL_QUARANTINE_COLLISION')
        partial.rename(quarantine)
        offset=0
    headers={'User-Agent':'NOX-EXPRESS-Block2/1.0'}
    if offset: headers['Range']=f'bytes={offset}-'
    url=f'{REGISTRY}/v2/library/{model}/blobs/{digest}'
    with secure_open(url,headers=headers,timeout=120) as response:
        code=getattr(response,'status',response.getcode())
        if offset and code!=206:
            # No guessing whether the server resumed; explicit fresh GET.
            partial.unlink(missing_ok=True)
            offset=0
            response.close()
            return download_blob(model,digest,expected_size,root)
        with open(partial,'ab' if offset else 'wb') as target:
            count=offset
            while True:
                block=response.read(2**20)
                if not block:break
                count+=len(block)
                if count>expected_size:raise ValueError('BLOB_EXCEEDS_OCI_DECLARED_SIZE')
                target.write(block)
    if partial.stat().st_size!=expected_size or sha_file(partial)!=hexsha:
        raise ValueError('BLOB_SHA256_OR_SIZE_MISMATCH')
    os.replace(partial,done)
    return {'digest':digest,'bytes':expected_size,'status':'DOWNLOADED_SHA256_VERIFIED'}

def acquire(tag,out,execute=False):
    if tag not in MODELS:raise ValueError('MODEL_NOT_IN_OWNER_ALLOWLIST')
    model,version=tag.split(':',1)
    receipt={'schema':'NOX-EXPRESS-MODEL-ACQUISITION-v1','tag':tag,'source':MODELS[tag]['url'],'status':'NOT_DOWNLOADED','installed':False,'integrated':False,'license_status':'REVIEW_REQUIRED','registry':REGISTRY}
    if not execute:return receipt
    if shutil.disk_usage(out.parent).free<6*1024**3:
        raise RuntimeError('INSUFFICIENT_FREE_SPACE_REQUIRE_AT_LEAST_6_GIB')
    # Refuse redirected cache paths before any network transfer.
    manifest_cache_target(out,model,version)
    content,manifest_sha,layers=manifest_and_blobs(model,version)
    if not manifest_sha.startswith(MODELS[tag]['display_digest_prefix']):
        raise ValueError('OFFICIAL_OLLAMA_MANIFEST_DIGEST_CHANGED__OWNER_REVIEW_REQUIRED')
    receipt['manifest_sha256']=manifest_sha
    receipt['layers']=[]
    for item in layers:
        receipt['layers'].append(download_blob(model,item['digest'],item['bytes'],out))
    # Revalidate after downloads: a junction could have appeared during I/O.
    manifest_target=manifest_cache_target(out,model,version)
    # Preserve exact OCI bytes; JSON reserialization changes the digest.
    if hashlib.sha256(content).hexdigest()!=manifest_sha:
        raise ValueError('OFFICIAL_MANIFEST_BYTE_IDENTITY_MISMATCH')
    if manifest_target.exists():
        # Never destroy a mismatching preimage: preserve it for investigation.
        if sha_file(manifest_target)!=manifest_sha:
            raise ValueError('PREEXISTING_MANIFEST_SHA_MISMATCH')
    else:
        staged=None
        try:
            with tempfile.NamedTemporaryFile(mode='wb',dir=manifest_target.parent,prefix='.'+version+'-',suffix='.part',delete=False) as output:
                staged=Path(output.name)
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            if sha_file(staged)!=manifest_sha:
                raise ValueError('STAGED_MANIFEST_SHA256_MISMATCH')
            manifest_target=manifest_cache_target(out,model,version)
            if manifest_target.exists():
                raise ValueError('MANIFEST_CACHE_PUBLICATION_COLLISION')
            os.replace(staged,manifest_target)
        finally:
            if staged is not None:
                staged.unlink(missing_ok=True)
    receipt.update(status='DOWNLOADED_ALL_LAYERS_SHA256_VERIFIED',bytes=sum(x['bytes'] for x in layers),manifest_store_path=str(manifest_target.relative_to(out)),manifest_file_sha256=sha_file(manifest_target),license_status='OWNER_REVIEW_OF_LICENSE_LAYER_REQUIRED')
    return receipt

def main(argv=None):
    ap=argparse.ArgumentParser()
    ap.add_argument('--out',required=True,help='Standalone staging dir, not the live Ollama store')
    ap.add_argument('--execute',action='store_true',help='Actively fetch model layers; without this flag only reports allowed models')
    ap.add_argument('--models',nargs='+',default=list(MODELS),choices=list(MODELS))
    args=ap.parse_args(argv)
    root=Path(args.out).resolve()
    root.mkdir(parents=True,exist_ok=True)
    receipts=[]
    for tag in args.models:
        try:receipt=acquire(tag,root,args.execute)
        except Exception as error:receipt={'tag':tag,'status':'HOLD','error':f'{type(error).__name__}:{str(error)[:250]}','integrated':False,'installed':False}
        receipts.append(receipt)
        print(f'{tag}: {receipt["status"]}',flush=True)
    root.mkdir(parents=True, exist_ok=True)
    (root/'NOX_MODEL_DOWNLOAD_RECEIPT.json').write_text(json.dumps({'models':receipts,'source':'Ollama official registry','gate':'REGISTRY_PENDING_OWNER'},indent=2,ensure_ascii=False),encoding='utf-8')
    return 0 if args.execute and all(r['status']=='DOWNLOADED_ALL_LAYERS_SHA256_VERIFIED' for r in receipts) else (2 if args.execute else 0)

if __name__=='__main__':sys.exit(main())
