"""NOX V95: install AI data-prep acceleration in isolated CPU environment.

One existing Vast SSH call; download hashed binary wheels to /dev/shm with
bounded CPU/I/O concurrency; install & test in separate v95-data environment.
No service restart, duplicate Torch install, GPU allocation or S03 mutation.
"""
from __future__ import annotations
from nox_runpod.teacher_mesh.v72 import onepass_live as runner

REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import hashlib,json,os,shutil,subprocess,sys,tempfile,urllib.request,time
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
R={'schema':'NOX_V72_ONEPASS_NATIVE_RECEIPT_V1','instance_id':60509551,
   'state':'HOLD_NOT_INSTALLED','package_count':0,'smoke_pass':False,
   'install_kind':'V95_RAM_STREAMING_DATA_TOOLS','torch_unchanged':True,
   'chat_restarted':False,'s03_unchanged':True,'gpu_allocated':False,
   'runtime_onehost_binding':False,'new_scheduler':False}
def emit():
    print('NATIVE_V72_JSON='+json.dumps(R,sort_keys=True,separators=(',',':')))
def healthy():
    try:
        for p in (8080,8081):
            with urllib.request.urlopen('http://127.0.0.1:'+str(p)+'/health',timeout=3) as r:
                if r.status!=200:return False
        return True
    except Exception:return False
def stopped():
    return any(Path(p).exists() for p in (
       '/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag',
       '/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP'))
def space(path):
    return shutil.disk_usage(path).free
def run(argv,timeout,env):
    return subprocess.run(argv,capture_output=True,text=True,timeout=timeout,env=env)
DEST=Path('/root/nox/tools/ai-accelerators/v95-data')
REQ='''polars>=1.30,<2
pyarrow>=18,<23
ijson>=3.3,<4
aiofiles>=24,<27
threadpoolctl>=3.5,<4
'''
try:
    if stopped() or not healthy():raise RuntimeError('HOLD_STOP_OR_CHAT')
    if not shutil.which('uv'):raise RuntimeError('HOLD_UV_MISSING')
    if space('/root/nox')<11_000_000_000:raise RuntimeError('HOLD_10GB_DISK_FLOOR')
    if space('/dev/shm')<2_500_000_000:raise RuntimeError('HOLD_RAM_CACHE_HEADROOM')
    if DEST.exists():
        if DEST.is_symlink() or not (DEST/'NOX_V95_DATA_RECEIPT.json').is_file():
            raise RuntimeError('HOLD_EXISTING_DATA_ENV_CONFLICT')
        d=json.loads((DEST/'NOX_V95_DATA_RECEIPT.json').read_text())
        if d.get('schema')!='NOX_V95_RAM_DATA_V1' or d.get('smoke_pass') is not True:
            raise RuntimeError('HOLD_EXISTING_DATA_ENV_UNVERIFIED')
        R.update({'state':'LIVE_CHECKS_PASS_ALREADY_INSTALLED',
          'smoke_pass':True,'package_count':len(d['versions']),
          'wheel_lock_sha256':d['wheel_lock_sha256'],
          'chat_healthy_after':healthy()})
        emit();raise SystemExit(0)
    os.nice(10)
    with tempfile.TemporaryDirectory(prefix='nox-v95-wheel-',dir='/dev/shm') as temp:
        path=Path(temp)
        req=path/'requirements.in';req.write_text(REQ)
        locked=path/'requirements.lock'
        env=os.environ.copy()
        env.update({'UV_CACHE_DIR':str(path/'cache'),'TMPDIR':str(path),
          'UV_NO_PROGRESS':'1','UV_CONCURRENT_DOWNLOADS':'2',
          'UV_CONCURRENT_INSTALLS':'2','UV_CONCURRENT_BUILDS':'1',
          'OPENBLAS_NUM_THREADS':'2','OMP_NUM_THREADS':'2',
          'POLARS_MAX_THREADS':'4','RAYON_NUM_THREADS':'4'})
        p=run(['uv','pip','compile',str(req),'--python-version','3.10',
                '--generate-hashes','--only-binary',':all:',
                '--output-file',str(locked)],timeout=60,env=env)
        if p.returncode or not locked.is_file() or b'--hash=sha256:' not in locked.read_bytes():
            raise RuntimeError('HOLD_WHEEL_LOCK_RESOLUTION')
        lock_bytes=locked.read_bytes()
        R['wheel_lock_sha256']=hashlib.sha256(lock_bytes).hexdigest()
        stage=DEST.with_name('.v95-data-stage-'+str(os.getpid()))
        if stage.exists():raise RuntimeError('HOLD_EXISTING_STAGE')
        create=run(['uv','venv','--python',sys.executable,str(stage)],timeout=12,env=env)
        if create.returncode or not (stage/'bin/python').exists():
            raise RuntimeError('HOLD_STAGE_VENV_CREATE')
        inst=run(['uv','pip','sync','--python',str(stage/'bin/python'),
               '--require-hashes','--only-binary',':all:',str(locked)],timeout=95,env=env)
        if inst.returncode:raise RuntimeError('HOLD_SHA_WHEEL_INSTALL')
        # Real streaming-data and in-memory Arrow/Polars API smoke, no private data.
        test='''import polars as pl,pyarrow as pa,io,ijson,aiofiles,threadpoolctl
import importlib.metadata as m,json,hashlib
x=[{'id':i,'v':i%7} for i in range(2048)]
d=pl.DataFrame(x)
z=d.group_by('v').len().sort('v')
assert z.height==7 and int(z['len'].sum())==2048
table=pa.Table.from_pylist(x)
sink=pa.BufferOutputStream()
with pa.ipc.new_stream(sink,table.schema) as writer:writer.write_table(table)
restored=pa.ipc.open_stream(sink.getvalue()).read_all()
assert restored.num_rows==2048
assert len(list(ijson.items(io.BytesIO(b'{"data":[1,2,3]}'),'data.item')))==3
versions={p:m.version(p) for p in ('polars','pyarrow','ijson','aiofiles','threadpoolctl')}
print(json.dumps({'smoke':'PASS','rows':restored.num_rows,'versions':versions},sort_keys=True))
'''
        p=run([str(stage/'bin/python'),'-c',test],timeout=22,env=env)
        if p.returncode:raise RuntimeError('HOLD_DATA_ACCEL_API_SMOKE')
        try:proof=json.loads(p.stdout.strip().splitlines()[-1])
        except Exception:raise RuntimeError('HOLD_SMOKE_RESULT')
        if proof.get('smoke')!='PASS' or len(proof.get('versions',{}))!=5:
            raise RuntimeError('HOLD_INCOMPLETE_DATA_PACK')
        if stopped() or not healthy() or space('/root/nox')<10_000_000_000:
            raise RuntimeError('HOLD_POST_INSTALL_HEALTH_OR_DISK')
        record={'schema':'NOX_V95_RAM_DATA_V1','smoke_pass':True,
                'wheel_lock_sha256':R['wheel_lock_sha256'],
                'versions':proof['versions'],'real_rows_tested':proof['rows'],
                'model_weights_changed':False,'runtime_onehost_binding':False}
        with (stage/'NOX_V95_DATA_RECEIPT.json').open('x') as f:
            json.dump(record,f,sort_keys=True,indent=2)
            f.write('\n');f.flush();os.fsync(f.fileno())
        (stage/'requirements.lock').write_bytes(lock_bytes)
        os.rename(stage,DEST)
        if json.loads((DEST/'NOX_V95_DATA_RECEIPT.json').read_text())!=record:
            raise RuntimeError('HOLD_RECEIPT_READBACK')
        R.update({'state':'LIVE_CHECKS_PASS_V95_RAM_DATA_TOOLS_INSTALLED',
            'smoke_pass':True,'package_count':5,'packages':proof['versions'],
            'ram_download_cache_was_ephemeral':True,
            'chat_healthy_after':healthy(),
            'disk_free_after':space('/root/nox')})
        emit();raise SystemExit(0)
except Exception as e:
    reason=str(e)
    R['state']=reason if reason.startswith('HOLD_') and len(reason)<100 else 'HOLD_DATA_INSTALL_EXCEPTION'
    R['chat_healthy_after']=healthy()
    emit();raise SystemExit(2)
PYREMOTE
"""
def main():
    source=runner.ssh_run
    def extended(*,host,port,key,known,script,limit):
        return source(host=host,port=port,key=key,known=known,script=script,
                      limit=min(max(limit,205),225))
    runner.ssh_run=extended
    runner.REMOTE=REMOTE
    result=runner.onepass()
    native=result.get('native') or {}
    for k in ('state','package_count','smoke_pass','wheel_lock_sha256',
              'chat_healthy_after','disk_free_after'):
        if k in native:print('NOX_V95_'+k.upper()+'='+str(native[k])[:120])
    for k,v in sorted(native.get('packages',{}).items()):
        print('NOX_V95_DATA_LIBRARY='+str(k)+':'+str(v))
    print('NOX_V95_SSH_REVOKED='+str(result.get('temp_ssh_key_revoked')))
    return 0 if str(result.get('state','')).startswith('LIVE_CHECKS_PASS') and result.get('temp_ssh_key_revoked') is True else 2
if __name__=='__main__':
    raise SystemExit(main())
