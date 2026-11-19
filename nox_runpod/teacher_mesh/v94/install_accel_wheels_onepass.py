"""NOX V94: one authorized native installation of CPU AI acceleration wheels.

Whitelisted, binary-wheel-only, SHA-locked in isolated /root/nox/tools venv.
No modification of system PyTorch/CUDA, OneHost service, GGUF or S03.
No model downloads. Full isolated smoke + health and 10GB disk gates.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from nox_runpod.teacher_mesh.v72 import onepass_live as runner

REMOTE = r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import hashlib,json,os,re,shutil,subprocess,sys,tempfile,time,urllib.request
from pathlib import Path
R={'schema':'NOX_V72_ONEPASS_NATIVE_RECEIPT_V1','instance_id':60509551,
   'state':'HOLD_TOOLKIT_NOT_INSTALLED','toolkit':'NOX_V94_CPU_AI_ACCEL',
   'production_changed':False,'training_started':False,'main_model_changed':False,
   's03_changed':False,'new_service_created':False,
   'wheels_hash_locked':False,'rollback_possible':True,'smoke_verified':False,
   'installed_into_existing_onehost':False,'checkpoint_modified':False,
   'chat_uninterrupted':False,'disk_floor_new_writes_bytes':10000000000}
def receipt():
    print('NATIVE_V72_JSON='+json.dumps(R,sort_keys=True,separators=(',',':')))
def stop():
    return any(Path(p).exists() for p in (
        '/root/nox/STOP','/root/nox/STOP.flag','/root/nox/stop.flag',
        '/root/nox/.stop','/workspace/NOX_STOP','/root/nox/program/STOP'))
def health(port):
    try:
        with urllib.request.urlopen('http://127.0.0.1:'+str(port)+'/health',timeout=3) as r:return r.status
    except Exception:return None
def run(args,timeout,env):
    x=subprocess.run(args,capture_output=True,text=True,timeout=timeout,env=env)
    return x.returncode
def total_folder(path):
    size=0
    for p,dirs,files in os.walk(path,followlinks=False):
        dirs[:]=[d for d in dirs if not (Path(p)/d).is_symlink()]
        for f in files:
            try:
                item=Path(p)/f
                if item.is_file() and not item.is_symlink():size+=item.stat().st_size
            except OSError:pass
    return size

ROOT=Path('/root/nox/tools/ai-accelerators')
FINAL=ROOT/'v94'
REQUIREMENTS='''orjson>=3.10,<4
zstandard>=0.24,<1
lz4>=4.4,<5
rapidfuzz>=3.12,<4
safetensors>=0.5,<1
huggingface-hub>=0.35,<1
hf-xet>=1.1,<2
diskcache>=5.6,<6
watchdog>=6,<8
faiss-cpu>=1.11,<2
rank-bm25>=0.2,<1
sentencepiece>=0.2,<1
nvidia-ml-py>=12.575,<14
msgpack>=1.1,<2
uvloop>=0.20,<1
xxhash>=3.5,<4
'''
try:
    if stop():raise RuntimeError('HOLD_STOP')
    if health(8080)!=200 or health(8081)!=200:
        raise RuntimeError('HOLD_MAIN_CHAT_HEALTH')
    before=shutil.disk_usage('/root/nox').free
    R['disk_free_before_bytes']=before
    if before<10_700_000_000:raise RuntimeError('HOLD_10GB_NEW_WRITE_BUDGET')
    if not shutil.which('uv'):raise RuntimeError('HOLD_NO_EXISTING_UV')
    shm=shutil.disk_usage('/dev/shm').free
    if shm<1_500_000_000:raise RuntimeError('HOLD_TMPFS_HEADROOM')
    if ROOT.is_symlink():raise RuntimeError('HOLD_NOX_TOOL_ROOT_SYMLINK')
    ROOT.mkdir(parents=True,exist_ok=True)
    if FINAL.exists():
        if FINAL.is_symlink() or not (FINAL/'NOX_V94_RECEIPT.json').is_file():
            raise RuntimeError('HOLD_EXISTING_TOOLKIT_CONFLICT')
        prior=json.loads((FINAL/'NOX_V94_RECEIPT.json').read_text())
        if prior.get('schema')=='NOX_V94_ACCEL_INSTALL_V1' and prior.get('smoke_pass') is True:
            R.update({'state':'LIVE_CHECKS_PASS_ALREADY_INSTALLED',
                      'wheels_hash_locked':True,'smoke_verified':True,
                      'toolkit_path_class':'NOX_TOOLS_V94',
                      'package_count':len(prior.get('packages',{})),
                      'installed_into_existing_onehost':False,
                      'chat_uninterrupted':health(8080)==200 and health(8081)==200})
            receipt();raise SystemExit(0)
        raise RuntimeError('HOLD_EXISTING_TOOLKIT_RECEIPT')
    with tempfile.TemporaryDirectory(prefix='nox-v94-uv-',dir='/dev/shm') as cache:
        cache=Path(cache)
        env=os.environ.copy()
        env.update({'UV_CACHE_DIR':str(cache/'cache'),'TMPDIR':str(cache),
                    'UV_NO_PROGRESS':'1','UV_CONCURRENT_DOWNLOADS':'2',
                    'UV_CONCURRENT_INSTALLS':'2','UV_CONCURRENT_BUILDS':'1',
                    'OMP_NUM_THREADS':'2','OPENBLAS_NUM_THREADS':'2',
                    'RAYON_NUM_THREADS':'4','TOKENIZERS_PARALLELISM':'false',
                    'PIP_DISABLE_PIP_VERSION_CHECK':'1'})
        req=cache/'requirements.in';req.write_text(REQUIREMENTS)
        lock=cache/'requirements.lock'
        rc=run(['uv','pip','compile',str(req),'--python-version','3.10',
                '--generate-hashes','--only-binary',':all:',
                '--output-file',str(lock)],timeout=75,env=env)
        if rc!=0 or not lock.is_file():raise RuntimeError('HOLD_HASHED_BINARY_LOCK_RESOLUTION')
        locked=lock.read_bytes()
        if b'--hash=sha256:' not in locked or len(locked)<100:
            raise RuntimeError('HOLD_NO_SHA256_WHEEL_LOCK')
        R['wheel_lock_sha256']=hashlib.sha256(locked).hexdigest()
        R['wheels_hash_locked']=True
        stage=ROOT/('.v94-stage-'+str(os.getpid()))
        if stage.exists():raise RuntimeError('HOLD_TOOL_STAGE_CONFLICT')
        rc=run(['uv','venv','--python',sys.executable,str(stage)],timeout=10,env=env)
        if rc!=0 or not (stage/'bin/python').is_file():
            # python is often a symlink in venv; accept a valid, executable venv.
            if rc!=0 or not (stage/'bin/python').exists():
                raise RuntimeError('HOLD_CPU_VENV_CREATION')
        rc=run(['uv','pip','sync','--python',str(stage/'bin/python'),
                '--require-hashes','--only-binary',':all:',str(lock)],
                timeout=75,env=env)
        if rc!=0:raise RuntimeError('HOLD_WHEEL_SHA_INSTALL')
        smoke='''import orjson,zstandard,lz4.frame,rapidfuzz,faiss,numpy as np
import safetensors.numpy,watchdog,diskcache,rank_bm25,sentencepiece
import huggingface_hub,hf_xet,uvloop,msgpack,xxhash,pynvml
from rapidfuzz import fuzz
original={'nox':'PRIME','tokens':[1,2,3]}
assert orjson.loads(orjson.dumps(original))==original
assert zstandard.ZstdDecompressor().decompress(
 zstandard.ZstdCompressor(level=3).compress(b'NOX'*32000))==b'NOX'*32000
assert lz4.frame.decompress(lz4.frame.compress(b'S03'*32000))==b'S03'*32000
a=np.eye(4,dtype=np.float32);i=faiss.IndexFlatL2(4);i.add(a)
dist,idx=i.search(a[:1],1);assert int(idx[0][0])==0
assert fuzz.ratio('nox','nox')==100
assert safetensors.numpy.load(safetensors.numpy.save({'x':a}))['x'].shape==(4,4)
assert len(xxhash.xxh3_64_hexdigest(b'NOX'))==16
assert msgpack.unpackb(msgpack.packb({'x':1}))=={'x':1}
import importlib.metadata as m
names=('orjson','zstandard','lz4','rapidfuzz','safetensors','huggingface-hub',
'hf-xet','diskcache','watchdog','faiss-cpu','rank-bm25','sentencepiece',
'nvidia-ml-py','msgpack','uvloop','xxhash')
print(__import__('json').dumps({'versions':{n:m.version(n) for n in names},
  'readiness':'CPU_ACCEL_SMOKE_PASS'},sort_keys=True))
'''
        rc=subprocess.run([str(stage/'bin/python'),'-c',smoke],
                capture_output=True,text=True,timeout=12,env=env)
        if rc.returncode!=0:
            raise RuntimeError('HOLD_ACCEL_TOOLKIT_IMPORT_OR_SMOKE')
        try:tested=json.loads(rc.stdout.strip().splitlines()[-1])
        except Exception:raise RuntimeError('HOLD_ACCEL_SMOKE_REPORT')
        if tested.get('readiness')!='CPU_ACCEL_SMOKE_PASS' or len(tested.get('versions',{}))!=16:
            raise RuntimeError('HOLD_INCOMPLETE_ACCEL_TOOLKIT')
        count=total_folder(stage)
        R['installed_bytes']=count
        if count>650_000_000:raise RuntimeError('HOLD_TOOLKIT_OVER_650MB')
        after=shutil.disk_usage('/root/nox').free
        if after<10_000_000_000:
            raise RuntimeError('HOLD_POST_INSTALL_DISK_FLOOR')
        if stop() or health(8080)!=200 or health(8081)!=200:
            raise RuntimeError('HOLD_CHAT_HEALTH_AFTER_INSTALL')
        (stage/'requirements.lock').write_bytes(locked)
        payload={'schema':'NOX_V94_ACCEL_INSTALL_V1','packages':tested['versions'],
            'wheel_lock_sha256':R['wheel_lock_sha256'],'smoke_pass':True,
            'model_weights_changed':False,'main_model_restarted':False,
            'installed_in_single_isolated_env':True,'installed_into_existing_onehost':False}
        p=stage/'NOX_V94_RECEIPT.json'
        with p.open('x',encoding='utf8') as r:
            json.dump(payload,r,sort_keys=True,indent=2);r.write('\n')
            r.flush();os.fsync(r.fileno())
        os.rename(stage,FINAL)
        readback=json.loads((FINAL/'NOX_V94_RECEIPT.json').read_text())
        if readback!=payload:raise RuntimeError('HOLD_TOOLKIT_READBACK')
        R.update({'state':'LIVE_CHECKS_PASS_ACCEL_WHEELS_STAGED_AND_EXECUTED',
                  'smoke_verified':True,
                  'toolkit_path_class':'NOX_TOOLS_V94',
                  'package_count':len(tested['versions']),
                  'packages':tested['versions'],
                  'disk_free_after_bytes':shutil.disk_usage('/root/nox').free,
                  'chat_uninterrupted':health(8080)==200 and health(8081)==200})
        receipt();raise SystemExit(0)
except Exception as ex:
    reason=str(ex)
    R['state']=reason if reason.startswith('HOLD_') and len(reason)<100 else 'HOLD_INSTALL_EXCEPTION'
    R['chat_uninterrupted']=health(8080)==200 and health(8081)==200
    receipt();raise SystemExit(2)
PYREMOTE
"""
def main():
    # This job runs exactly one native remote command; allow bounded wheel
    # resolution/install time, not the 70s audit timeout of the shared V72.
    original_ssh_run=runner.ssh_run
    def wheel_ssh_run(*,host,port,key,known,script,limit):
        return original_ssh_run(host=host,port=port,key=key,known=known,
                                script=script,limit=min(max(limit,195),220))
    runner.ssh_run=wheel_ssh_run
    runner.REMOTE=REMOTE
    result=runner.onepass()
    native=result.get('native',{})
    for x in ('state','smoke_verified','wheel_lock_sha256','package_count',
              'installed_bytes','disk_free_before_bytes','disk_free_after_bytes',
              'chat_uninterrupted'):
        if x in native:print('NOX_V94_'+x.upper()+'='+str(native[x])[:160])
    pkgs=native.get('packages',{})
    for name in sorted(pkgs):print('NOX_V94_LIBRARY='+name+':'+str(pkgs[name])[:50])
    print('NOX_V94_SSH_REVOKED='+str(result.get('temp_ssh_key_revoked',False)))
    # Single transaction wrapper does not make installed OneHost use the toolkit.
    print('NOX_V94_LIVE_ONEHOST_BINDING_CLAIMED=false')
    return 0 if str(result.get('state','')).startswith('LIVE_CHECKS_PASS') and result.get('temp_ssh_key_revoked') is True else 2
if __name__=='__main__':
    raise SystemExit(main())
