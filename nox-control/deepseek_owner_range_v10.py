#!/usr/bin/env python3
"""NOX P0 V10: single existing OneHost owner-fenced GGUF shard transfer.

Source only until admitted by the original native owner controller. No scheduler,
serving backend, trainer, weights promotion, model deletion or automatic retry.
"""
from __future__ import annotations
import argparse, fcntl, hashlib, json, os, re, stat, tempfile, time
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

INSTANCE = 60509551
REVISION = "65d53bc8be65123e255ff02f3ded958b6dbf54fd"
REPO = "ISTA-DASLab/DeepSeek-V4.1-Flash-1017-GSQ-RCO-GGUF"
RESERVE = 16 * 1024**3
MAX_RANGE = 256 * 1024**2
CHUNK = 1024**2
STOP_NAMES = ("STOP", "STOP.flag", "stop.flag", ".stop", "program/STOP", "state/STOP")
SHA = re.compile(r"[a-f0-9]{64}\Z")
FILE = re.compile(r"(?:DeepSeek-V4\.1-Flash-1017-GSQ-RCO-IQ2_XXS-0000[1-5]-of-00006|DeepSeek-V4\.1-Flash-Engram-IQ4_NL)\.gguf\Z")

class Hold(RuntimeError): pass

def require(ok, reason):
    if not ok: raise Hold(reason)

def regular(path: Path, allow_missing=False):
    path=Path(path)
    for p in (path, *path.parents): require(not p.is_symlink(), 'HOLD_SYMLINK_PATH')
    if not path.exists():
        require(allow_missing, 'HOLD_MISSING_FILE')
        return None
    st=path.stat()
    require(stat.S_ISREG(st.st_mode) and st.st_uid==os.geteuid(), 'HOLD_NONREGULAR_OR_UNOWNED_FILE')
    # A hardlinked .part could append directly into a unique checkpoint or S03 backup.
    require(st.st_nlink==1, 'HOLD_HARDLINK_PATH')
    return st

def canonical(d):
    return json.dumps(d,sort_keys=True,separators=(',', ':'),allow_nan=False).encode()

def load_manifest(raw):
    require(len(raw)<=131072, 'HOLD_MANIFEST_LIMIT')
    m=json.loads(raw)
    require(isinstance(m,dict) and m.get('schema')=='NOX_MODEL_DOWNLOAD_MANIFEST_V1','HOLD_MANIFEST_SCHEMA')
    require(m.get('repository')==REPO and m.get('revision')==REVISION,'HOLD_MANIFEST_REVISION')
    rows=m.get('files')
    require(isinstance(rows,list) and len(rows)==6,'HOLD_MANIFEST_COUNT')
    by={}
    for row in rows:
        require(isinstance(row,dict),'HOLD_MANIFEST_ROW')
        name,n,sha,url=(row.get(k) for k in ('path','bytes','sha256','url'))
        require(isinstance(name,str) and FILE.fullmatch(name) and name not in by,'HOLD_MANIFEST_PATH')
        require(type(n) is int and n>0 and isinstance(sha,str) and SHA.fullmatch(sha),'HOLD_MANIFEST_DIGEST')
        expect=f'https://huggingface.co/{REPO}/resolve/{REVISION}/{name}'
        require(url==expect,'HOLD_MANIFEST_URL')
        by[name]=row
    require(sum(row['bytes'] for row in by.values())==m.get('total_unique_gguf_bytes')==248834257920,
            'HOLD_MANIFEST_TOTAL')
    a=m.get('alias')
    require(isinstance(a,dict) and
            a.get('path')=='DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00006-of-00006.gguf' and
            a.get('target')=='DeepSeek-V4.1-Flash-Engram-IQ4_NL.gguf' and
            a.get('duplicate_bytes') is False,'HOLD_SHARED_ENGRAM_ALIAS')
    return by

def stop(root):
    require(not any((root/p).exists() or (root/p).is_symlink() for p in STOP_NAMES),'HOLD_OWNER_STOP')
    require(not Path('/workspace/NOX_STOP').exists(),'HOLD_OWNER_STOP')

def lease(path,request,now,root):
    # Only existing OneHost is authorised to issue this lease. This script cannot create one.
    path=Path(path)
    # The original OneHost lease must be beneath the actual dispatcher path.
    # Prefix-only checks admit /state/dispatcher/../forged.json outside the
    # owner lease directory even though every element is a regular file.
    base=Path(root)/'state'/'dispatcher'
    require(path.is_absolute() and '..' not in path.parts and
            path.parts[:len(base.parts)]==base.parts and len(path.parts)>len(base.parts),
            'HOLD_LEASE_ORIGIN')
    st=regular(path)
    require(st.st_size<=8192 and not (st.st_mode & 0o077),'HOLD_LEASE_PERMISSIONS')
    d=json.loads(path.read_bytes())
    require(d.get('schema')=='NOX_ONEHOST_OWNER_LEASE_V1' and
            d.get('instance_id')==INSTANCE and d.get('owner')=='MSSTXNEWS' and
            d.get('resource')=='p0.model_download' and d.get('request_id')==request and
            type(d.get('expires_unix')) in (int,float) and now<d['expires_unix']<=now+7200,
            'HOLD_ORIGINAL_LEASE')
    return d

def final_url_allowed(url):
    p=urlparse(url); host=(p.hostname or '').lower()
    return p.scheme=='https' and (host=='huggingface.co' or host.endswith('.xethub.hf.co') or
                                   host.endswith('.hf.co') or host.endswith('.cloudfront.net'))

def content_range(header,start,end,total):
    m=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)',header or '')
    require(m is not None,'HOLD_HTTP_CONTENT_RANGE')
    lo,hi,n=map(int,m.groups())
    require(lo==start and hi==end and n==total,'HOLD_HTTP_RANGE_MISMATCH')

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        while chunk:=stream.read(8*CHUNK): h.update(chunk)
    return h.hexdigest()

def atomic_receipt(path,obj):
    fd,tmp=tempfile.mkstemp(prefix='.nox-ds-v10-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:
            os.fchmod(f.fileno(),0o600)
            f.write(canonical(obj)); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

def inventory(manifest,target):
    rows=[]
    for name,row in manifest.items():
        p=target/name;part=target/(name+'.part')
        a,b=regular(p,True),regular(part,True)
        rows.append({'file':name,'expected_bytes':row['bytes'],'expected_sha256':row['sha256'],
                     'present_bytes':a.st_size if a else None,'partial_bytes':b.st_size if b else None,
                     'verified':bool(a and a.st_size==row['bytes'] and digest(p)==row['sha256'])})
    return rows

def download_one(row,destination,root,lease_file,request,limit=MAX_RANGE,opener=urlopen):
    """One bounded transfer. Require correct 206 Content-Range even at offset zero.
    Final path is published only after full SHA. Partial is left untouched on HOLD."""
    require(1<=limit<=MAX_RANGE,'HOLD_RANGE_BUDGET')
    require(isinstance(request,str) and re.fullmatch(r'\d{1,20}',request),'HOLD_REQUEST_ID')
    destination=Path(destination);root=Path(root)
    require(destination.is_dir() and not destination.is_symlink(),'HOLD_SEEKABLE_STORAGE_MISSING')
    name=row['path'];require(FILE.fullmatch(name),'HOLD_UNEXPECTED_FILE')
    stop(root);lease(lease_file,request,time.time(),root)
    fd=os.open(destination/'.nox-deepseek-owner.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        lock_st=os.fstat(fd)
        require(stat.S_ISREG(lock_st.st_mode) and lock_st.st_uid==os.geteuid() and
                lock_st.st_nlink==1, 'HOLD_LOCK_FILE_UNSAFE')
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        final,partial=destination/name,destination/(name+'.part')
        existing=regular(final,True)
        if existing:
            require(existing.st_size==row['bytes'] and digest(final)==row['sha256'],
                    'HOLD_EXISTING_FINAL_UNVERIFIED')
            return {'state':'REUSED_SHA_VERIFIED','new_bytes':0,'file':name,'sha256':row['sha256']}
        partial_stat=regular(partial,True)
        offset=partial_stat.st_size if partial_stat else 0
        require(offset<row['bytes'],'HOLD_PARTIAL_AT_OR_ABOVE_TOTAL')
        with tempfile.TemporaryFile(dir=destination) as probe:
            probe.write(b'NOX-P0-seek'); probe.flush(); os.fsync(probe.fileno())
            require(os.pread(probe.fileno(),8,4)==b'P0-seek','HOLD_STORAGE_NOT_SEEKABLE')
        free=os.statvfs(destination).f_bavail*os.statvfs(destination).f_frsize
        require(free>=row['bytes']-offset+RESERVE,'HOLD_STORAGE_AUTH_OR_SEEKABLE_PLACEMENT')
        end=min(row['bytes']-1,offset+limit-1)
        request_url=Request(row['url'],headers={'Range':f'bytes={offset}-{end}',
                            'Accept-Encoding':'identity','User-Agent':'NOX-Owner-P0-Range-V10'})
        require(final_url_allowed(request_url.full_url),'HOLD_DOWNLOAD_HOST')
        with opener(request_url,timeout=30) as response:
            require(getattr(response,'status',None)==206,'HOLD_RANGE_NOT_SUPPORTED')
            require(final_url_allowed(response.geturl()),'HOLD_REDIRECT_OR_TLS')
            content_range(response.headers.get('Content-Range'),offset,end,row['bytes'])
            require(response.headers.get('Content-Encoding','identity').lower()=='identity',
                    'HOLD_CONTENT_ENCODING')
            length=response.headers.get('Content-Length')
            require(length is not None and int(length)==end-offset+1,'HOLD_HTTP_LENGTH')
            # Bind an append to the inode admitted BEFORE network I/O, not a raced replacement.
            flags=os.O_WRONLY|os.O_APPEND|os.O_NOFOLLOW
            if partial_stat is None: flags|=os.O_CREAT|os.O_EXCL
            try: partfd=os.open(partial,flags,0o600)
            except FileExistsError: raise Hold('HOLD_PARTIAL_CREATE_RACE')
            wrote=0
            with os.fdopen(partfd,'ab',buffering=0) as output:
                opened=os.fstat(output.fileno())
                require(stat.S_ISREG(opened.st_mode) and opened.st_uid==os.geteuid() and
                        opened.st_nlink==1, 'HOLD_PARTIAL_FD_UNSAFE')
                if partial_stat is None:
                    require(opened.st_size==0,'HOLD_PARTIAL_CHANGED')
                else:
                    require((opened.st_dev,opened.st_ino,opened.st_size)==
                            (partial_stat.st_dev,partial_stat.st_ino,offset),'HOLD_PARTIAL_CHANGED')
                require(output.tell()==offset,'HOLD_CONCURRENT_PARTIAL_CHANGE')
                while wrote<end-offset+1:
                    stop(root);lease(lease_file,request,time.time(),root)
                    chunk=response.read(min(CHUNK,end-offset+1-wrote))
                    require(chunk,'HOLD_EARLY_EOF')
                    output.write(chunk);wrote+=len(chunk)
                output.flush();os.fsync(output.fileno())
        require(partial.stat().st_size==end+1,'HOLD_PARTIAL_LENGTH_RACE')
        if end+1!=row['bytes']:
            return {'state':'PARTIAL_SHA_PENDING','file':name,'new_bytes':wrote,'part_bytes':end+1}
        actual=digest(partial)
        require(actual==row['sha256'],'HOLD_FINAL_SHA_MISMATCH')
        stop(root);lease(lease_file,request,time.time(),root)
        require(not final.exists(),'HOLD_FINAL_RACE')
        os.replace(partial,final)
        receipt={'schema':'NOX_DEEPSEEK_RANGE_RECEIPT_V10','request':request,'file':name,
                 'bytes':row['bytes'],'sha256':actual,'new_bytes':wrote,'at_unix':time.time()}
        atomic_receipt(destination/(name+'.verified.json'),receipt)
        return {'state':'VERIFIED_FINAL','file':name,'new_bytes':wrote,'sha256':actual}
    finally:
        os.close(fd)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('manifest',type=Path)
    ap.add_argument('destination',type=Path)
    ap.add_argument('--inventory',action='store_true')
    ap.add_argument('--download',default='')
    ap.add_argument('--lease',type=Path)
    ap.add_argument('--request',default='')
    ap.add_argument('--max-range-mib',type=int,default=256)
    a=ap.parse_args()
    by=load_manifest(a.manifest.read_bytes())
    if a.inventory:
        print(json.dumps({'status':'READ_ONLY','files':inventory(by,a.destination)},ensure_ascii=False));return
    require(a.download in by,'HOLD_FILE_NOT_IN_MANIFEST')
    require(a.lease is not None and a.request,'HOLD_OWNER_LEASE_REQUIRED')
    result=download_one(by[a.download],a.destination,Path('/root/nox'),a.lease,a.request,
                        a.max_range_mib*1024**2)
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':
    try:main()
    except Hold as e:
        print(json.dumps({'state':'HOLD','reason':str(e)}));raise SystemExit(2)
