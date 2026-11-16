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
MIN_MODEL_VOLUME_BYTES = 248834257920  # Six unique GGUF files; shared Engram counted once.
# Exact Library receipt: progress v57, file_id file_00000000820481f593d1ab61b7d5745d,
# 870895 bytes; owner record SHA-256 e8dfbfc7f2c1b946d0ca0e88ff7e90673739d059a4a4b2f1eea6b7bd4fbe1469.
# This immutable receipt records all 200 parts and the whole-file SHA for shard 00005.
COLDPACK_PROGRESS_SHA256 = "e8dfbfc7f2c1b946d0ca0e88ff7e90673739d059a4a4b2f1eea6b7bd4fbe1469"
COLDPACK_COMPLETED_FILE = "DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00005-of-00006.gguf"
COLDPACK_PROGRESS_MAX_BYTES = 1024 * 1024
MAX_RANGE = 256 * 1024**2
CHUNK = 1024**2
STOP_NAMES = ("STOP", "STOP.flag", "stop.flag", ".stop", "program/STOP", "state/STOP", "state/STOP.flag", "state/OWNER_MAINTENANCE.flag")
SHA = re.compile(r"[a-f0-9]{64}\Z")
FILE = re.compile(r"(?:DeepSeek-V4\.1-Flash-1017-GSQ-RCO-IQ2_XXS-0000[1-5]-of-00006|DeepSeek-V4\.1-Flash-Engram-IQ4_NL)\.gguf\Z")

# Immutable owner-reviewed LFS identities, pinned independently of input manifest.
# Source: feature/nox-engine-stage-20261116 @ blob 0608cdcacb1573835e4edc194c8ee63d4877180b
# Model revision and total bytes alone cannot authenticate individual files.
PINNED_FILE_FACTS = {
    "DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00001-of-00006.gguf": (
        5780704,
        "f356f198561f56df36f7ab92d7238a926646d76de992c34f15bcb939a5f529b9"
    ),
    "DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00002-of-00006.gguf": (
        39535781184,
        "25af3785ccf925f54137e1ead4c481a8952315dc0b1af6519a99407f67bce8f3"
    ),
    "DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00003-of-00006.gguf": (
        39736712000,
        "8168d0998fc494def2e1952d83c131425a108660aae9d29190f5a8670ab62b48"
    ),
    "DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00004-of-00006.gguf": (
        39036908384,
        "9eb9b4de1968f150dfc207eb31c27be9cd9b5666a9a6246bde8a22b184b4bee0"
    ),
    "DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00005-of-00006.gguf": (
        19923784832,
        "7e35f6b4e6fc46f6c4b152b593d84d683c5ece695ae6ad734f556198c041bec1"
    ),
    "DeepSeek-V4.1-Flash-Engram-IQ4_NL.gguf": (
        110595290816,
        "3dac4c54893ad7aa89103c0028500eadc78e74112cef3a2930a97e67dc9fb4f3"
    )
}

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

def _strict_manifest_pairs(pairs):
    """Reject ambiguous JSON keys at every level, including shard and alias rows."""
    result = {}
    for key, value in pairs:
        require(key not in result, 'HOLD_MANIFEST_DUPLICATE_KEY')
        result[key] = value
    return result


def _reject_manifest_nonfinite(value):
    raise Hold('HOLD_MANIFEST_NONFINITE_JSON')

def _strict_lease_pairs(pairs):
    """Reject ambiguous owner lease keys, including in nested objects."""
    result = {}
    for key, value in pairs:
        require(key not in result, 'HOLD_LEASE_DUPLICATE_KEY')
        result[key] = value
    return result

def _reject_lease_nonfinite(value):
    raise Hold('HOLD_LEASE_NONFINITE_JSON')


def load_manifest(raw):
    require(isinstance(raw, (str, bytes, bytearray)) and len(raw) <= 131072,
            'HOLD_MANIFEST_LIMIT')
    try:
        m = json.loads(raw, object_pairs_hook=_strict_manifest_pairs,
                       parse_constant=_reject_manifest_nonfinite)
    except (ValueError, UnicodeError, TypeError) as exc:
        raise Hold('HOLD_MANIFEST_INVALID_JSON') from exc
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
    require(set(by)==set(PINNED_FILE_FACTS) and all(
        (row['bytes'],row['sha256'])==tuple(PINNED_FILE_FACTS[name])
        for name,row in by.items()), 'HOLD_MANIFEST_FILE_IDENTITY')
    a=m.get('alias')
    require(isinstance(a,dict) and
            a.get('path')=='DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00006-of-00006.gguf' and
            a.get('target')=='DeepSeek-V4.1-Flash-Engram-IQ4_NL.gguf' and
            a.get('duplicate_bytes') is False,'HOLD_SHARED_ENGRAM_ALIAS')
    return by


def reject_completed_coldpack_duplicate(name, progress_raw):
    """Fail closed when the exact pinned Library receipt proves this file complete.

    The Drive model manifest is an immutable source/identity manifest, not a
    live transfer ledger. Its NOT_DOWNLOADED row for shard 00005 is older than
    Library progress v57 and must never authorize another transfer.
    """
    if name != COLDPACK_COMPLETED_FILE:
        return
    require(isinstance(progress_raw, (bytes, bytearray)) and
            0 < len(progress_raw) <= COLDPACK_PROGRESS_MAX_BYTES,
            'HOLD_COLDPACK_PROGRESS_REQUIRED')
    require(hashlib.sha256(progress_raw).hexdigest() == COLDPACK_PROGRESS_SHA256,
            'HOLD_COLDPACK_PROGRESS_UNVERIFIED')
    try:
        progress = json.loads(progress_raw)
    except (ValueError, UnicodeError, TypeError) as exc:
        raise Hold('HOLD_COLDPACK_PROGRESS_INVALID') from exc
    require(isinstance(progress, dict) and
            progress.get('schema') == 'NOX_DEEPSEEK_COLDPACK_PROGRESS_V1' and
            progress.get('revision') == REVISION and
            progress.get('native_ready') is False and
            progress.get('seekable_placement_verified') is False,
            'HOLD_COLDPACK_PROGRESS_IDENTITY')
    matches = [row for row in progress.get('files', [])
               if isinstance(row, dict) and row.get('path') == name]
    require(len(matches) == 1, 'HOLD_COLDPACK_PROGRESS_ENTRY')
    row = matches[0]
    expected_bytes, expected_sha = PINNED_FILE_FACTS[name]
    parts = row.get('parts')
    require(row.get('bytes') == expected_bytes and row.get('sha256') == expected_sha and
            row.get('whole_sha256_verified') is True and isinstance(parts, list) and
            len(parts) == 200, 'HOLD_COLDPACK_PROGRESS_INCOMPLETE')
    total = 0
    for index, part in enumerate(parts, 1):
        expected_part_bytes = 100_000_000 if index < 200 else 23_784_832
        expected_part_name = f'{name}.part{index:04d}'
        remote = part.get('remote') if isinstance(part, dict) else None
        require(isinstance(part, dict) and part.get('index') == index and
                part.get('file') == expected_part_name and
                part.get('offset') == (index - 1) * 100_000_000 and
                part.get('bytes') == expected_part_bytes and
                part.get('state') == 'SAVED_METADATA_VERIFIED' and
                isinstance(remote, dict) and remote.get('name') == expected_part_name and
                remote.get('size_bytes') == expected_part_bytes,
                'HOLD_COLDPACK_PART_INVENTORY')
        total += expected_part_bytes
    require(total == expected_bytes, 'HOLD_COLDPACK_PART_TOTAL')
    raise Hold('HOLD_COLDPACK_ALREADY_COMPLETE')


def read_coldpack_progress_file(path):
    """Bounded no-follow read, tied to the regular file inspected before open."""
    path = Path(path)
    before = regular(path)
    require(before.st_size <= COLDPACK_PROGRESS_MAX_BYTES,
            'HOLD_COLDPACK_PROGRESS_LIMIT')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        opened = os.fstat(fd)
        require(stat.S_ISREG(opened.st_mode) and opened.st_uid == os.geteuid() and
                opened.st_nlink == 1 and
                (opened.st_dev, opened.st_ino, opened.st_size) ==
                (before.st_dev, before.st_ino, before.st_size),
                'HOLD_COLDPACK_PROGRESS_RACE')
        data = bytearray()
        while len(data) <= COLDPACK_PROGRESS_MAX_BYTES:
            chunk = os.read(fd, min(65536, COLDPACK_PROGRESS_MAX_BYTES + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        after = os.fstat(fd)
        require((after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns) ==
                (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns),
                'HOLD_COLDPACK_PROGRESS_RACE')
        require(len(data) == opened.st_size and len(data) <= COLDPACK_PROGRESS_MAX_BYTES,
                'HOLD_COLDPACK_PROGRESS_LIMIT')
        return bytes(data)
    finally:
        os.close(fd)


def stop(root):
    """Fail closed when an owner STOP flag is present OR unreadable.

    Path.exists()/is_symlink() may not distinguish an inaccessible STOP from
    a missing one. Do not authorize a model Range write on ambiguous access.
    """
    for flag in (*(root / name for name in STOP_NAMES), Path('/workspace/NOX_STOP')):
        try:
            os.lstat(flag)  # lstat also detects dangling STOP symlinks
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise Hold('HOLD_OWNER_STOP_UNREADABLE') from exc
        raise Hold('HOLD_OWNER_STOP')

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
    try:
        d=json.loads(path.read_bytes(),object_pairs_hook=_strict_lease_pairs,
                     parse_constant=_reject_lease_nonfinite)
    except (ValueError, UnicodeError, TypeError) as exc:
        raise Hold('HOLD_LEASE_INVALID_JSON') from exc
    require(isinstance(d,dict),'HOLD_LEASE_SCHEMA')
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
    """Metadata-only, STOP-safe inventory: never scan hundreds of GiB without a lease.

    A matching stat size is NOT a matching SHA. Existing files are SHA-verified
    separately by download_one() under its exact owner lease and download lock.
    """
    rows=[]
    for name,row in manifest.items():
        p=target/name;part=target/(name+'.part')
        a,b=regular(p,True),regular(part,True)
        metadata_complete=bool(a and a.st_size==row['bytes'])
        rows.append({'file':name,'expected_bytes':row['bytes'],'expected_sha256':row['sha256'],
                     'present_bytes':a.st_size if a else None,'partial_bytes':b.st_size if b else None,
                     'metadata_complete':metadata_complete,
                     'verification_scope':'SHA_UNCHECKED' if a else 'NO_FINAL_FILE',
                     'verified':False})
    return rows


def finalize_complete_partial(row, partial, final, destination, root, lease_file, request, new_bytes, expected):
    """After a crash or final Range, publish only an intact complete .part.

    This path never requests more network bytes. Partial and final remain
    protected by the original OneHost owner lease and download flock.
    """
    observed=regular(partial)
    require((observed.st_dev, observed.st_ino, observed.st_size)==expected and
            observed.st_size==row['bytes'], 'HOLD_PARTIAL_LENGTH_RACE')
    stop(root);lease(lease_file,request,time.time(),root)
    actual=digest(partial)
    stop(root);lease(lease_file,request,time.time(),root)
    after=regular(partial)
    require((after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns)==
            (observed.st_dev,observed.st_ino,observed.st_size,observed.st_mtime_ns,observed.st_ctime_ns),
            'HOLD_PARTIAL_CHANGED_DURING_HASH')
    require(actual==row['sha256'],'HOLD_FINAL_SHA_MISMATCH')
    # A complete pre-existing partial may have been staged by a prior process.
    # Ensure its contents reach storage before adding its final directory name.
    syncfd=os.open(partial,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        synced=os.fstat(syncfd)
        require((synced.st_dev,synced.st_ino,synced.st_size)==expected,
                'HOLD_PARTIAL_CHANGED_BEFORE_FSYNC')
        os.fsync(syncfd)
    finally:
        os.close(syncfd)
    stop(root);lease(lease_file,request,time.time(),root)
    require(not final.exists() and not final.is_symlink(),'HOLD_FINAL_RACE')
    try:
        os.link(partial,final,follow_symlinks=False)
    except FileExistsError:
        raise Hold('HOLD_FINAL_RACE')
    published=os.stat(final,follow_symlinks=False)
    require(stat.S_ISREG(published.st_mode) and published.st_uid==os.geteuid() and
            (published.st_dev,published.st_ino,published.st_size)==
            (after.st_dev,after.st_ino,after.st_size),'HOLD_PUBLISHED_INODE_MISMATCH')
    os.unlink(partial)
    dfd=os.open(destination,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try: os.fsync(dfd)
    finally: os.close(dfd)
    stop(root);lease(lease_file,request,time.time(),root)
    receipt={'schema':'NOX_DEEPSEEK_RANGE_RECEIPT_V10','request':request,'file':row['path'],
             'bytes':row['bytes'],'sha256':actual,'new_bytes':new_bytes,'at_unix':time.time()}
    atomic_receipt(destination/(row['path']+'.verified.json'),receipt)
    return {'state':'VERIFIED_FINAL','file':row['path'],'new_bytes':new_bytes,'sha256':actual}

def download_one(row,destination,root,lease_file,request,limit=MAX_RANGE,opener=urlopen,progress_raw=None):
    """One bounded transfer. Require correct 206 Content-Range even at offset zero.
    Final path is published only after full SHA. Partial is left untouched on HOLD."""
    require(1<=limit<=MAX_RANGE,'HOLD_RANGE_BUDGET')
    require(isinstance(request,str) and re.fullmatch(r'\d{1,20}',request),'HOLD_REQUEST_ID')
    destination=Path(destination);root=Path(root)
    require(destination.is_dir() and not destination.is_symlink(),'HOLD_SEEKABLE_STORAGE_MISSING')
    name=row['path'];require(FILE.fullmatch(name),'HOLD_UNEXPECTED_FILE')
    reject_completed_coldpack_duplicate(name, progress_raw)
    stop(root);lease(lease_file,request,time.time(),root)
    fd=os.open(destination/'.nox-deepseek-owner.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    partial_guard_fd=None
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
            stop(root);lease(lease_file,request,time.time(),root)
            return {'state':'REUSED_SHA_VERIFIED','new_bytes':0,'file':name,'sha256':row['sha256']}
        partial_stat=regular(partial,True)
        # Keep the admitted inode allocated across HTTP I/O: unlink/recreate may reuse
        # the same st_ino and defeat a later dev/inode/size comparison.
        if partial_stat is not None:
            partial_guard_fd=os.open(partial,os.O_RDONLY|os.O_NOFOLLOW)
            admitted=os.fstat(partial_guard_fd)
            require(stat.S_ISREG(admitted.st_mode) and admitted.st_uid==os.geteuid() and
                    admitted.st_nlink==1 and
                    (admitted.st_dev,admitted.st_ino,admitted.st_size)==
                    (partial_stat.st_dev,partial_stat.st_ino,partial_stat.st_size),
                    'HOLD_PARTIAL_PREIMAGE_CHANGED')
        offset=partial_stat.st_size if partial_stat else 0
        require(offset<=row['bytes'],'HOLD_PARTIAL_ABOVE_TOTAL')
        with tempfile.TemporaryFile(dir=destination) as probe:
            probe.write(b'NOX-P0-seek'); probe.flush(); os.fsync(probe.fileno())
            require(os.pread(probe.fileno(),8,4)==b'P0-seek','HOLD_STORAGE_NOT_SEEKABLE')
        vfs=os.statvfs(destination)
        free=vfs.f_bavail*vfs.f_frsize
        require(free>=row['bytes']-offset+RESERVE,'HOLD_STORAGE_AUTH_OR_SEEKABLE_PLACEMENT')
        # Per-shard free space alone is misleading: a 183GB internal SSD can
        # accept one shard yet can never contain the immutable 248.8GB model.
        # This is a necessary source gate, NOT owner quota/lease admission.
        require(vfs.f_blocks*vfs.f_frsize>=MIN_MODEL_VOLUME_BYTES+RESERVE,
                'HOLD_STORAGE_TOTAL_CAPACITY')
        if offset==row['bytes']:
            # Fully downloaded .part from a prior crash: validate and publish
            # without a redundant HTTP request or duplicate GGUF allocation.
            return finalize_complete_partial(row,partial,final,destination,root,lease_file,request,
                                             new_bytes=0,
                                             expected=(admitted.st_dev,admitted.st_ino,offset))
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
            require(isinstance(length,str) and re.fullmatch(r'[0-9]{1,20}',length) is not None
                    and int(length)==end-offset+1,'HOLD_HTTP_LENGTH')
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
                    # Blocking network I/O may outlive an owner STOP or lease
                    # revocation. Do not append a chunk after either occurs.
                    stop(root);lease(lease_file,request,time.time(),root)
                    output.write(chunk);wrote+=len(chunk)
                output.flush();os.fsync(output.fileno())
        # Never acknowledge a partial Range after owner STOP, lease expiry or inode swap.
        stop(root);lease(lease_file,request,time.time(),root)
        after=regular(partial)
        require((after.st_dev,after.st_ino,after.st_size)==
                (opened.st_dev,opened.st_ino,end+1),'HOLD_PARTIAL_LENGTH_RACE')
        if end+1!=row['bytes']:
            return {'state':'PARTIAL_SHA_PENDING','file':name,'new_bytes':wrote,'part_bytes':end+1}
        return finalize_complete_partial(row,partial,final,destination,root,lease_file,request,
                                         new_bytes=wrote,expected=(opened.st_dev,opened.st_ino,end+1))
    finally:
        if partial_guard_fd is not None: os.close(partial_guard_fd)
        os.close(fd)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('manifest',type=Path)
    ap.add_argument('destination',type=Path)
    ap.add_argument('--inventory',action='store_true')
    ap.add_argument('--download',default='')
    ap.add_argument('--lease',type=Path)
    ap.add_argument('--request',default='')
    ap.add_argument('--coldpack-progress',type=Path)
    ap.add_argument('--max-range-mib',type=int,default=256)
    a=ap.parse_args()
    by=load_manifest(a.manifest.read_bytes())
    if a.inventory:
        print(json.dumps({'status':'READ_ONLY','files':inventory(by,a.destination)},ensure_ascii=False));return
    require(a.download in by,'HOLD_FILE_NOT_IN_MANIFEST')
    require(a.lease is not None and a.request,'HOLD_OWNER_LEASE_REQUIRED')
    progress_raw=None
    if a.download == COLDPACK_COMPLETED_FILE:
        require(a.coldpack_progress is not None,'HOLD_COLDPACK_PROGRESS_REQUIRED')
        progress_raw=read_coldpack_progress_file(a.coldpack_progress)
    result=download_one(by[a.download],a.destination,Path('/root/nox'),a.lease,a.request,
                        a.max_range_mib*1024**2,progress_raw=progress_raw)
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':
    try:main()
    except Hold as e:
        print(json.dumps({'state':'HOLD','reason':str(e)}));raise SystemExit(2)

