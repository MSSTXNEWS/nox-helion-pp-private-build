#!/usr/bin/env python3
"""Copy only selected files/directories from local staging to local scratch.
Dry-run by default. Atomic, bytewise SHA-256 verified, never deletes/overwrites.
This intentionally refuses /workspace and network symlink sources: they may hang in D-state.
"""
from __future__ import annotations
import argparse, datetime, hashlib, json, os, pathlib, shutil, sys, uuid
from nox_local_preflight import local_path, sha256_file

DENIED={'id_rsa','id_ed25519','id_ecdsa','nox_srv_key','.env','credentials.json','aws_credentials'}

def source_items(source, target):
    if os.path.isfile(source) and not os.path.islink(source):
        return [(source,target)]
    if not os.path.isdir(source) or os.path.islink(source):
        raise ValueError('NOT_A_LOCAL_DIRECTORY_OR_FILE')
    items=[]
    for root,dirs,files in os.walk(source,followlinks=False):
        for d in dirs:
            if os.path.islink(os.path.join(root,d)): raise ValueError('SOURCE_SYMLINK_DIRECTORY:'+d)
        for name in files:
            if name in DENIED or name.endswith(('.pem','.key')) or '.ssh' in root.split(os.sep):
                raise ValueError('SECRET_FILE_CANNOT_BE_COPIED:'+name)
            p=os.path.join(root,name)
            if os.path.islink(p):raise ValueError('SOURCE_SYMLINK_FILE:'+p)
            items.append((p,os.path.join(target,os.path.relpath(p,source))))
    return sorted(items)

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',required=True)
    p.add_argument('--target',required=True)
    p.add_argument('--apply',action='store_true',help='Default is inventory/dry-run. This authorizes only copying.')
    p.add_argument('--expect-step',type=int,help='Require source STEP to equal this exact value, e.g. 85')
    p.add_argument('--reserve-gb',type=float,default=3.0)
    args=p.parse_args(argv)
    try:
        source=local_path(args.source);target=local_path(args.target)
        if source==target or target.startswith(source+os.sep) or source.startswith(target+os.sep):
            raise ValueError('SOURCE_TARGET_NESTED')
        files=source_items(source,target)
        if not files:raise ValueError('SOURCE_EMPTY')
        if args.expect_step is not None:
            steps=[p for p,_ in files if os.path.basename(p)=='STEP']
            if len(steps)!=1 or open(steps[0],encoding='ascii').read().strip()!=str(args.expect_step):
                raise ValueError('STEP_MISMATCH_OR_MISSING_EXPECTED_'+str(args.expect_step))
        total=sum(os.path.getsize(a) for a,b in files)
        parent=os.path.dirname(target)
        while not os.path.exists(parent):parent=os.path.dirname(parent)
        local_path(parent)
        st=os.statvfs(parent);avail=st.f_bavail*st.f_frsize
        needed=total+int(args.reserve_gb*1024**3)
        if avail<needed:raise ValueError(f'INSUFFICIENT_LOCAL_DISK_FREE:{avail}_NEED:{needed}')
        results=[]
        if args.apply:
            for src,dst in files:
                local_path(dst)
                os.makedirs(os.path.dirname(dst),exist_ok=True)
                srcsha=sha256_file(src)
                if os.path.lexists(dst):
                    if os.path.islink(dst) or not os.path.isfile(dst) or sha256_file(dst)!=srcsha:
                        raise ValueError('DEST_EXISTS_DIFFERENT_NO_OVERWRITE:'+dst)
                    mode='already_verified'
                else:
                    temp=dst+'.nox-copy-'+uuid.uuid4().hex
                    try:
                        with open(src,'rb',buffering=1048576) as s,open(temp,'xb',buffering=1048576) as d:
                            while True:
                                b=s.read(4*1024*1024)
                                if not b:break
                                d.write(b)
                            d.flush();os.fsync(d.fileno())
                        if sha256_file(temp)!=srcsha:raise ValueError('COPIED_SHA256_MISMATCH:'+dst)
                        if os.path.lexists(dst):raise ValueError('DEST_APPEARED_DURING_COPY:'+dst)
                        os.rename(temp,dst)
                    finally:
                        # On failure, leave the temp chunk for forensics; never delete user data.
                        pass
                    mode='copied_verified'
                results.append({'file':os.path.relpath(src,source) if os.path.isdir(source) else os.path.basename(src),
                                'bytes':os.path.getsize(src),'sha256':srcsha,'result':mode})
        out={'schema':'nox-local-copy-receipt-v1','timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),
             'status':'VERIFIED_LOCAL_COPY' if args.apply else 'DRY_RUN_NOT_COPIED',
             'source':source,'target':target,'files':len(files),'bytes':total,'freeBytesBefore':avail,
             'reservedGiB':args.reserve_gb,'expectedStep':args.expect_step,'receipts':results}
        if args.apply:
            rec_dir='/root/nox_local/_receipts' if target.startswith('/root/nox_local') else os.path.join(os.path.dirname(target),'_receipts')
            os.makedirs(rec_dir,exist_ok=True)
            fn=os.path.join(rec_dir,'copy-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8]+'.json')
            with open(fn,'x',encoding='utf8') as f:
                json.dump(out,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
            out['receiptPath']=fn
        print(json.dumps(out,ensure_ascii=False,indent=2))
        return 0
    except Exception as e:
        print(json.dumps({'schema':'nox-local-copy-receipt-v1','status':'HOLD','reason':str(e)[:220],
                          'copiedUnknownIfPriorFiles':'NO_DELETION_PERFORMED'},ensure_ascii=False))
        return 2
if __name__=='__main__':sys.exit(main())
