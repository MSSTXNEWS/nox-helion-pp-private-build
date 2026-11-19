#!/usr/bin/env python3
"""Read-only NOX training local-I/O audit. No GPU/train/kill/network/remote actions."""
from __future__ import annotations
import argparse, datetime, hashlib, json, os, pathlib, stat, sys

NETWORK = ('/workspace', '/workspace-global', '/runpod-volume', '/runpod-volume/', '/mnt/nox-network')

def local_path(p: str) -> str:
    p = os.path.abspath(os.path.expanduser(p))
    if any(p == q.rstrip('/') or p.startswith(q.rstrip('/') + '/') for q in NETWORK):
        raise ValueError('NETWORK_PATH_BLOCKED:' + p)
    # Check each symlink component without following the mount or opening it.
    cur = '/'
    parts = pathlib.PurePosixPath(p).parts[1:]
    for part in parts:
        cur = os.path.join(cur, part)
        if os.path.islink(cur):
            dest = os.readlink(cur)
            if not os.path.isabs(dest):
                dest = os.path.normpath(os.path.join(os.path.dirname(cur), dest))
            dest = os.path.abspath(dest)
            if any(dest == q.rstrip('/') or dest.startswith(q.rstrip('/') + '/') for q in NETWORK):
                raise ValueError('NETWORK_SYMLINK_BLOCKED:' + cur)
    return p

def sha256_file(p: str):
    h = hashlib.sha256()
    with open(p, 'rb', buffering=1024*1024) as f:
        for chunk in iter(lambda: f.read(4*1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()

def assess(args):
    result = {'schema':'nox-local-io-audit-v1',
        'generatedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
        'status':'HOLD','observedStep':None,'expectedStepOwnerReported':args.expected_step,
        'checkpointKind':'PEFT_ADAPTER_NOT_FULL_NOX_WEIGHTS',
        'fullStudentWeightsVerified':False,'trainedQualityVerified':False,
        'windowsTransferVerified':False,'gpuExecutionVerified':False,
        'percentDistilledKnowledge':None,'externalBackupDigestMatched':False,'problems':[], 'checks':{},'paths':{}}
    try:
        root=local_path(args.root)
        base=local_path(args.base)
        data=local_path(args.data or os.path.join(root,'data','tok'))
        checkpoint=local_path(args.ckpt or os.path.join(root,'ckpt','sft','last'))
        trainer=local_path(args.trainer or os.path.join(root,'scripts','train_n36.py'))
        seed=local_path(args.seed or os.path.join(root,'seed','common.py'))
        result['paths']={'root':root,'base':base,'data':data,'checkpoint':checkpoint,'trainer':trainer,'seed':seed}
    except (ValueError,OSError) as e:
        result['problems'].append(str(e));return result
    def check(name,p,regular=True):
        try:
            ok=(os.path.isfile(p) if regular else os.path.isdir(p))
            result['checks'][name]={'present':ok}
            if ok and regular: result['checks'][name]['bytes']=os.path.getsize(p)
        except OSError as exc:
            ok=False;result['checks'][name]={'present':False,'error':str(exc)[:180]}
        if not ok:result['problems'].append('MISSING_'+name)
        return ok
    try:
        disk_path=next((p for p in [root,os.path.dirname(root),'/root','/'] if os.path.exists(p)),'/')
        disk=os.statvfs(disk_path)
        result['localDisk']={'path':disk_path,'freeBytes':disk.f_bavail*disk.f_frsize,
         'totalBytes':disk.f_blocks*disk.f_frsize,
         'freeGiB':round(disk.f_bavail*disk.f_frsize/2**30,2)}
        if result['localDisk']['freeGiB']<args.reserve_gb:
            result['problems'].append('LOCAL_DISK_BELOW_RESERVE_GB')
    except OSError as e:result['problems'].append('LOCAL_DISK_STAT_ERROR:'+str(e)[:140])
    index_path=os.path.join(base,'model.safetensors.index.json')
    if check('model_index',local_path(index_path)):
        try:
            with open(index_path,encoding='utf8') as f: index=json.load(f)
            shards=sorted(set(index['weight_map'].values()))
            if len(shards)<1 or len(shards)>1000: raise ValueError('INVALID_SHARD_COUNT')
            missing=[];total=0
            for shard in shards:
                if not isinstance(shard,str) or pathlib.PurePosixPath(shard).is_absolute() or '..' in pathlib.PurePosixPath(shard).parts:
                    raise ValueError('INVALID_INDEX_RELATIVE_SHARD')
                dest=local_path(os.path.join(base,shard))
                if not os.path.isfile(dest):missing.append(shard)
                else:total+=os.path.getsize(dest)
            result['checks']['base_shards']={'listed':len(shards),'missing':missing,'bytesListed':total,'sha256Verified':False}
            if missing:result['problems'].append('BASE_SHARDS_MISSING')
            if args.hash_base and not missing:
                result['checks']['base_shards']['sha256']=hashlib.sha256('\n'.join(sha256_file(local_path(os.path.join(base,x))) for x in shards).encode()).hexdigest()
                result['checks']['base_shards']['sha256Verified']=True
        except (OSError,ValueError,KeyError,TypeError,json.JSONDecodeError) as e:
            result['problems'].append('BASE_INDEX_INVALID:'+str(e)[:120])
    for k,p in [('training_data',os.path.join(data,'train.pt')),
                ('holdout_data',os.path.join(data,'hold.pt')),
                ('plan',os.path.join(root,'ckpt','sft','plan.json')),
                ('trainer',trainer),('seed_common',seed),
                ('checkpoint_STEP',os.path.join(checkpoint,'STEP')),
                ('checkpoint_adapter',os.path.join(checkpoint,'adapter_model.safetensors')),
                ('checkpoint_optimizer',os.path.join(checkpoint,'opt.pt')),
                ('checkpoint_adapter_config',os.path.join(checkpoint,'adapter_config.json'))]:
        check(k,local_path(p))
    if result['checks'].get('checkpoint_STEP',{}).get('present'):
        try:
            with open(os.path.join(checkpoint,'STEP'),encoding='ascii') as f: text=f.read().strip()
            if not text.isdecimal():raise ValueError('STEP_NOT_INTEGER')
            result['observedStep']=int(text)
            if result['observedStep']<args.expected_step:
                result['problems'].append('STEP_BELOW_OWNER_REPORTED_85')
        except (OSError,ValueError) as e:result['problems'].append('INVALID_CKPT_STEP:'+str(e))
    if result['checks'].get('trainer',{}).get('present'):
        try:
            with open(trainer,'r',encoding='utf8') as f: trainer_src=f.read()
            network_paths=[x for x in ['/workspace/nox36','/workspace/nox_seed_gpu'] if x in trainer_src]
            result['checks']['trainer']['hardcodedNetworkPaths']=network_paths
            if network_paths: result['problems'].append('TRAINER_STILL_DEPENDS_ON_NETWORK_PATH')
        except (OSError,UnicodeError) as e:result['problems'].append('TRAINER_READ_FAIL:'+str(e)[:100])
    if args.hash_checkpoint:
        hashes={}
        for field in ['checkpoint_adapter','checkpoint_optimizer','checkpoint_adapter_config','checkpoint_STEP']:
            p={'checkpoint_adapter':'adapter_model.safetensors','checkpoint_optimizer':'opt.pt',
               'checkpoint_adapter_config':'adapter_config.json','checkpoint_STEP':'STEP'}[field]
            if result['checks'].get(field,{}).get('present'):
                hashes[p]=sha256_file(os.path.join(checkpoint,p))
        result['checks']['checkpoint_hashes']={'files':hashes,'complete':len(hashes)==4}
        if len(hashes)<4:result['problems'].append('CHECKPOINT_DIGEST_INCOMPLETE')
        if args.backup_digest_manifest:
            try:
                digest_path=local_path(args.backup_digest_manifest)
                with open(digest_path,encoding='utf8') as ref: report=json.load(ref)
                expected=report.get('hashes',{})
                if int(report.get('step',-1))!=result.get('observedStep'):
                    raise ValueError('REFERENCE_STEP_MISMATCH')
                if any(expected.get(k)!=v for k,v in hashes.items()):
                    raise ValueError('REFERENCE_SHA256_MISMATCH')
                result['externalBackupDigestMatched']=len(hashes)==4
            except (OSError,ValueError,TypeError,json.JSONDecodeError) as e:
                result['problems'].append('BACKUP_DIGEST_REFERENCE_INVALID:'+str(e)[:120])
    if not result['problems']:
        result['status']='LOCAL_PATHS_READY_CHECKPOINT_HASH_PENDING' if not args.hash_checkpoint else (
            'ADAPTER_BACKUP_DIGEST_MATCHED_NOT_FULL_WEIGHTS' if result['externalBackupDigestMatched'] else
            'LOCAL_ADAPTER_SELF_HASHED_REFERENCE_NOT_VERIFIED')
    return result

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',default='/root/nox_local')
    p.add_argument('--base',default='/dev/shm/base36')
    p.add_argument('--data')
    p.add_argument('--ckpt')
    p.add_argument('--trainer')
    p.add_argument('--seed')
    p.add_argument('--expected-step',type=int,default=85)
    p.add_argument('--reserve-gb',type=float,default=3.0)
    p.add_argument('--hash-checkpoint',action='store_true',help='Read local checkpoint files fully, SHA-256 each')
    p.add_argument('--backup-digest-manifest',help='Optional JP backup SHA JSON; also requires --hash-checkpoint; no remote connection')
    p.add_argument('--hash-base',action='store_true',help='Expensive: SHA-256 every model shard in RAM/local disk')
    p.add_argument('--json-out',help='Optional LOCAL path for atomic written receipt (never /workspace)')
    args=p.parse_args(argv)
    result=assess(args)
    content=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if args.json_out:
        out=local_path(args.json_out)
        os.makedirs(os.path.dirname(out),exist_ok=True)
        tmp=out+'.nox-tmp.'+str(os.getpid())
        with open(tmp,'w',encoding='utf8') as f:
            f.write(content);f.flush();os.fsync(f.fileno())
        os.replace(tmp,out)
    print(content,end='')
    return 0 if result['status']!='HOLD' else 2
if __name__=='__main__':sys.exit(main())
