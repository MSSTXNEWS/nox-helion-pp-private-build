#!/usr/bin/env python3
"""Pinned, bounded SDXL/Wan preparation for NOX's existing media dispatcher.

No model promotion, deletion, driver installation, or trainer-environment write.
Model files go directly to their admitted destination and receive a full SHA256
check. A failed/interrupted download remains resumable and is never advertised
as ready. The optional supervised engine binds loopback and uses physical GPU1.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import socket
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path('/root/nox')
MEDIA = ROOT/'media'
SHM = Path('/dev/shm/nox_media')
BASE_PYTHON = Path('/root/venv_volta/bin/python')
SERVICE = 'nox-media-comfyui'
CONFIG = ROOT/'config/owner_media_runtime.json'
STATE = ROOT/'state/owner_media'
GIB = 1024**3
DISK_RESERVE = 6*GIB
SHM_RESERVE = 3*GIB
CGROUP_RESERVE = 16*GIB
SETUP_ALLOWANCE = 2*GIB
COMFY_COMMIT = '9aac21f894a122ddb8d825c57ad61c0db5e630db'
COMFY_ARCHIVE = {
    'url':'https://codeload.github.com/Comfy-Org/ComfyUI/tar.gz/'+COMFY_COMMIT,
    'bytes':4452974,
    'sha256':'9e298ea612b659823789bf107adf533e76270baa2ebfe8cd7a2ca57c1230463f',
}
SDXL_REVISION = 'c9a24f48e1c025556787b0c58dd67a091ece2e44'
WAN_REVISION = '123acf1cc74bccbb9bfff8ac1ee72edc08c2341d'
ASSETS = (
    {'kind':'image','role':'checkpoint','subdir':'checkpoints',
     'repo':'ByteDance/SDXL-Lightning','revision':SDXL_REVISION,
     'source_path':'sdxl_lightning_4step.safetensors','filename':'sdxl_lightning_4step.safetensors',
     'bytes':6938040682,'sha256':'e0d996ee0013e79d9d3561f50fcafb9a17e3ff07b780358e3b66d67932c4d490',
     'license':'openrail++','workflow':'sdxl_lightning_4step'},
    {'kind':'video','role':'unet','subdir':'diffusion_models',
     'repo':'Comfy-Org/Wan-2.1','revision':WAN_REVISION,
     'source_path':'split_files/diffusion_models/wan2.1_t2v_1.3B_fp16.safetensors',
     'filename':'wan2.1_t2v_1.3B_fp16.safetensors','bytes':2838303560,
     'sha256':'be531024cd9018cb5b48c40cfbb6a6191645b1c792eb8bf4f8c1c6e10f924dc5',
     'license':'apache-2.0','workflow':'wan21_t2v_13b'},
    {'kind':'video','role':'clip','subdir':'text_encoders',
     'repo':'Comfy-Org/Wan-2.1','revision':WAN_REVISION,
     'source_path':'split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors',
     'filename':'umt5_xxl_fp8_e4m3fn_scaled.safetensors','bytes':6735906897,
     'sha256':'c3355d30191f1f066b26d93fba017ae9809dce6c627dda5f6a66eaa651204f68',
     'license':'apache-2.0','workflow':'wan21_t2v_13b'},
    {'kind':'video','role':'vae','subdir':'vae','repo':'Comfy-Org/Wan-2.1',
     'revision':WAN_REVISION,'source_path':'split_files/vae/wan_2.1_vae.safetensors',
     'filename':'wan_2.1_vae.safetensors','bytes':253815318,
     'sha256':'2fc39d31359a4b0a64f55876d8ff7fa8d780956ae2cb13463b0223e15148976b',
     'license':'apache-2.0','workflow':'wan21_t2v_13b'},
)
# --no-deps prevents pip from changing/reinstalling the shared CUDA/Torch stack.
# This exact original set is retained for the reviewed additive migration.
LEGACY_PYPI_PINS = (
    'comfyui-frontend-package==1.12.14','torchsde==0.2.6','trampoline==0.1.2',
    'numpy==1.26.4','einops==0.8.1','transformers==4.49.0','tokenizers==0.21.0',
    'huggingface-hub==0.29.3','sentencepiece==0.2.0','safetensors==0.5.3',
    'aiohttp==3.11.13','yarl==1.18.3','PyYAML==6.0.2','Pillow==11.1.0',
    'scipy==1.15.2','tqdm==4.67.1','psutil==7.0.0','kornia==0.8.0',
    'kornia_rs==0.1.8','spandrel==0.4.1','soundfile==0.13.1','av==14.2.0',
    'cffi==1.17.1','pycparser==2.22',
)
REQUESTS_PINS = ('requests==2.34.2', 'urllib3==2.8.0', 'charset-normalizer==3.5.2',
                 'certifi==2026.10.23', 'idna==3.20')
# Universal wheels and SHA256s verified against PyPI release JSON, 2026-11-16.
# All five are small pure-Python dependencies; none can replace CUDA or Torch.
REQUESTS_WHEELS = (
    ('https://files.pythonhosted.org/packages/a0/f4/c67b0b3f1b9245e8d266f0f112c500d50e5b4e83cb6f3b71b6528104182a/requests-2.34.2-py3-none-any.whl',
     '2a0d60c172f83ac6ab31e4554906c0f3b3588d37b5cb939b1c061f4907e278e0'),
    ('https://files.pythonhosted.org/packages/92/9d/c4e665119135114480843e7ab388fa94d8480650450e6f8e26b70d323a4c/urllib3-2.8.0-py3-none-any.whl',
     '0cf3cae568d36aa9576b28dfb35f11328f1cb974ca7647d9475ebb86c75ac6e3'),
    ('https://files.pythonhosted.org/packages/fc/ad/d07d7862a62ffa6d79d68074d14823243dd235a77c45262acbf6adeb28bf/charset_normalizer-3.5.2-py3-none-any.whl',
     'b6b751274acb69d77b3323d6b7dbaa3c7fdfc1eb829b7eb61d262f32e1af9685'),
    ('https://files.pythonhosted.org/packages/32/d1/a3652fe2c19134d0d15922177821d863cbd7e842d53a21bbe7e8e3a1b5ac/certifi-2026.10.23-py3-none-any.whl',
     'e9b54de76e530bb6cf0ccd036787103acb58fd42ba930ea8bf948ddbaa2f61d1'),
    ('https://files.pythonhosted.org/packages/58/a2/bb081bab032533a855d44de1d56f8e8426114ff1ba5d1f07a438a0a654f8/idna-3.20-py3-none-any.whl',
     'ab7ae7122974553370f0bdb919e1a960b2cd1bc1ef0276416d896db81c14582c'),
)
AIOHTTP_PINS = ('propcache==0.5.4','multidict==6.9.1','frozenlist==1.8.0',
                'attrs==26.1.0','aiosignal==1.4.0','aiohappyeyeballs==2.7.1',
                'typing-extensions==4.16.0')
# Complete mandatory closure for aiohttp3.11/yarl1.18 on the observed CPython
# 3.12 x86_64 host. multidict7 is incompatible with pinned aiohttp3.11.13.
# The three extension wheels support glibc2.17, below Ubuntu22.04's glibc.
AIOHTTP_WHEELS = (
    ('https://files.pythonhosted.org/packages/85/9f/83a07b6ec0e043c050cfdd35fb0cf1b7897b91d554d6eea293740309afe7/propcache-0.5.4-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl',
     '2814ecd8e818f487bee4b0f921bc4d1c176cc5fc71ac0f072d0fa67eda4ac14b'),
    ('https://files.pythonhosted.org/packages/ed/5b/db08419c1e1f7c9d60cfd2787b2b517d7ae4ebbda8281b48a33eb5141467/multidict-6.9.1-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl',
     '976fd7689d69ec78d67d31d38d396d8adb562f7e8368279f76aed4aa451fa06d'),
    ('https://files.pythonhosted.org/packages/6a/bd/d91c5e39f490a49df14320f4e8c80161cfcce09f1e2cde1edd16a551abb3/frozenlist-1.8.0-cp312-cp312-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl',
     '494a5952b1c597ba44e0e78113a7266e656b9794eec897b19ead706bd7074383'),
    ('https://files.pythonhosted.org/packages/64/b4/17d4b0b2a2dc85a6df63d1157e028ed19f90d4cd97c36717afef2bc2f395/attrs-26.1.0-py3-none-any.whl',
     'c647aa4a12dfbad9333ca4e71fe62ddc36f4e63b2d260a37a8b83d2f043ac309'),
    ('https://files.pythonhosted.org/packages/fb/76/641ae371508676492379f16e2fa48f4e2c11741bd63c48be4b12a6b09cba/aiosignal-1.4.0-py3-none-any.whl',
     '053243f8b92b990551949e63930a839ff0cf0b0ebbe0597b0f3fb19e1a0fe82e'),
    ('https://files.pythonhosted.org/packages/71/43/1947f06babed6b3f1d7f38b0c767f52df66bfb2bc10b468c4a7de9eceff2/aiohappyeyeballs-2.7.1-py3-none-any.whl',
     '9243213661e29250eb41368e5daa826fc017156c3b8a11440826b2e3ed376472'),
    ('https://files.pythonhosted.org/packages/49/d3/b8441a820a491ddfc024b0b0cf0393375b75ea13866d9c66727e54c2fc80/typing_extensions-4.16.0-py3-none-any.whl',
     '481caa481374e813c1b176ada14e97f1f67a4539ce9cfeb3f350d78d6370c2e8'),
)
PYPI_PINS = LEGACY_PYPI_PINS + REQUESTS_PINS + AIOHTTP_PINS
CUDA_PINS = ('torchvision==0.21.0+cu124','torchaudio==2.6.0+cu124')
REQUIRED_NODES = ('CheckpointLoaderSimple','CLIPTextEncode','EmptyLatentImage',
                  'KSampler','VAEDecode','SaveImage','UNETLoader','CLIPLoader',
                  'VAELoader','ModelSamplingSD3','EmptyHunyuanLatentVideo','SaveWEBM')
_EMIT_LOCK = threading.Lock()
_STORAGE_WRITE_LOCK = threading.Lock()


def fail(code):
    raise RuntimeError(code)


def emit(phase, **data):
    with _EMIT_LOCK:
        print('NOX_MEDIA_INSTALL='+json.dumps({'phase':phase, **data},separators=(',',':')), flush=True)


def plain(value):
    path = Path(os.path.abspath(value))
    for probe in (*reversed(path.parents),path):
        if probe.is_symlink(): fail('HOLD_MEDIA_SYMLINK_PATH')
    return path


def sha256(path):
    digest = hashlib.sha256()
    with plain(path).open('rb') as source:
        for block in iter(lambda:source.read(4*1024*1024),b''):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path, obj):
    path = plain(path)
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    fd,tmp = tempfile.mkstemp(prefix='.media-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as target:
            json.dump(obj,target,indent=2,ensure_ascii=False)
            target.write('\n'); target.flush(); os.fsync(target.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


@contextmanager
def lock(name):
    STATE.mkdir(mode=0o700,parents=True,exist_ok=True)
    fd = os.open(plain(STATE/name),os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        try: fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: fail('HOLD_MEDIA_OPERATION_BUSY')
        yield
    finally:
        os.close(fd)


@contextmanager
def gpu_lease():
    # The existing hybrid trainer and media runtime use this exact GPU1 lease.
    path = plain(ROOT/'state/forge_training.lock')
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    fd = os.open(path,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        try: fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: fail('HOLD_MEDIA_GPU1_LEASE_BUSY')
        yield
    finally:
        os.close(fd)


def run(args, timeout=120, env=None, cwd=None):
    try:
        result = subprocess.run(list(map(str,args)),capture_output=True,text=True,
                                timeout=timeout,env=env,cwd=cwd)
    except subprocess.TimeoutExpired:
        fail('HOLD_MEDIA_COMMAND_TIMEOUT')
    if result.returncode:
        # Provider output, environment and arbitrary subprocess text stay private.
        fail('HOLD_MEDIA_COMMAND_EXIT_'+str(result.returncode))
    return result.stdout


def cgroup_headroom():
    try:
        limit = int(Path('/sys/fs/cgroup/memory.max').read_text())
        used = int(Path('/sys/fs/cgroup/memory.current').read_text())
    except (OSError,ValueError): fail('HOLD_FINITE_CGROUP_MEMORY_REQUIRED')
    if not 0 <= used < limit: fail('HOLD_CGROUP_MEMORY_EXHAUSTED')
    return limit-used


def resources():
    return {'disk_free':shutil.disk_usage(ROOT).free,
            'shm_free':shutil.disk_usage('/dev/shm').free,
            'memory_free':cgroup_headroom()}


def asset_path(asset, storage):
    base = SHM if storage=='ram' else MEDIA/'weights'
    return plain(base/'models'/asset['subdir']/asset['filename'])


def plan_assets(budget, existing=None, partials=None):
    """Prefer existing verified assets, then all-RAM, then a bounded split."""
    existing = existing or {}
    partials = partials or {}
    pending = [a for a in ASSETS if a['filename'] not in existing]
    total = sum(a['bytes']-partials.get(a['filename'],{}).get('bytes',0) for a in pending)
    if budget['disk_free'] < DISK_RESERVE+SETUP_ALLOWANCE:
        fail('HOLD_MEDIA_DISK_SETUP_RESERVE')
    if budget['memory_free'] < total+32*GIB:
        fail('HOLD_MEDIA_CGROUP_CACHE_AND_RUNTIME_RESERVE')
    placement = None
    for split in (False,True):
        trial = {a['filename']:partials.get(a['filename'],{}).get('storage',
                 'disk' if split and a['role']=='clip' else 'ram') for a in pending}
        ram = sum(a['bytes']-partials.get(a['filename'],{}).get('bytes',0)
                  for a in pending if trial[a['filename']]=='ram')
        disk = total-ram
        if budget['shm_free'] >= ram+SHM_RESERVE and budget['disk_free'] >= disk+DISK_RESERVE+SETUP_ALLOWANCE:
            placement = trial
            break
    if placement is None: fail('HOLD_MEDIA_MODEL_STORAGE_RESERVE')
    rows = []
    for asset in ASSETS:
        if asset['filename'] in existing:
            row = {**asset, **existing[asset['filename']], 'reused':True}
        else:
            storage = placement[asset['filename']]
            row = {**asset,'storage':storage,'path':str(asset_path(asset,storage)),'reused':False}
        row['source_url'] = 'https://huggingface.co/'+asset['repo']+'/resolve/'+asset['revision']+'/'+asset['source_path']
        row['model_card'] = 'https://huggingface.co/'+asset['repo']+'/blob/'+asset['revision']+'/README.md'
        rows.append(row)
    return rows


def validate_file(path, expected):
    path = plain(path)
    if not path.exists(): return None
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size != expected['bytes']:
        fail('HOLD_MEDIA_EXISTING_FILE_SIZE')
    before = (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns)
    if sha256(path) != expected['sha256']: fail('HOLD_MEDIA_EXISTING_FILE_SHA')
    info = path.stat()
    if before != (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns):
        fail('HOLD_MEDIA_FILE_CHANGED_WHILE_HASHING')
    return {'path':str(path),'verified':True,'stat_mtime_ns':info.st_mtime_ns,
            'stat_device':info.st_dev,'stat_inode':info.st_ino}


def find_existing_assets(engine=None):
    found = {}
    for asset in ASSETS:
        candidates = [asset_path(asset,'ram'),asset_path(asset,'disk')]
        if engine: candidates.append(plain(engine)/'models'/asset['subdir']/asset['filename'])
        for path in candidates:
            if path.exists():
                checked = validate_file(path,asset)
                storage = 'ram' if path.is_relative_to(SHM) else 'disk'
                found[asset['filename']] = {**checked,'storage':storage}
                break
    return found


def existing_partials():
    found = {}
    for asset in ASSETS:
        for storage in ('ram','disk'):
            path = plain(asset_path(asset,storage).with_name(asset['filename']+'.partial'))
            if not path.exists(): continue
            if not path.is_file() or not 0 <= path.stat().st_size <= asset['bytes']:
                fail('HOLD_MEDIA_PARTIAL_SIZE')
            if asset['filename'] in found: fail('HOLD_MEDIA_DUPLICATE_PARTIAL')
            found[asset['filename']] = {'storage':storage,'bytes':path.stat().st_size}
    return found


def get_json(url, limit=2*1024*1024):
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'NOX-owner-media/1'}),timeout=45) as response:
            raw = response.read(limit+1)
    except urllib.error.HTTPError as exc: fail('HOLD_MEDIA_METADATA_HTTP_'+str(exc.code))
    except (OSError,urllib.error.URLError): fail('HOLD_MEDIA_METADATA_UNAVAILABLE')
    if len(raw)>limit: fail('HOLD_MEDIA_METADATA_OVERSIZE')
    return json.loads(raw)


def verify_hf_metadata():
    for repo,revision in sorted({(a['repo'],a['revision']) for a in ASSETS}):
        metadata = get_json('https://huggingface.co/api/models/'+repo+'/revision/'+revision+'?blobs=true')
        if metadata.get('sha') != revision or metadata.get('gated') not in (False,None):
            fail('HOLD_MEDIA_SOURCE_REVISION_OR_GATING')
        files = {row['rfilename']:row for row in metadata.get('siblings',[])}
        for asset in (a for a in ASSETS if a['repo']==repo):
            row = files.get(asset['source_path'],{})
            if row.get('size') != asset['bytes'] or row.get('lfs',{}).get('sha256') != asset['sha256']:
                fail('HOLD_MEDIA_SOURCE_LFS_PIN_MISMATCH')


def check_write_space(directory, pending, reserve):
    if shutil.disk_usage(directory).free < pending+reserve: fail('HOLD_MEDIA_STORAGE_RESERVE')
    if cgroup_headroom() < CGROUP_RESERVE: fail('HOLD_MEDIA_CGROUP_RESERVE')


def download(url, path, expected, reserve=DISK_RESERVE):
    """One resumable file, no Hugging Face cache duplicate, full SHA before rename."""
    path = plain(path)
    if path.exists(): return validate_file(path,expected)
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    part = plain(path.with_name(path.name+'.partial'))
    if part.exists() and (not part.is_file() or part.stat().st_size>expected['bytes']):
        fail('HOLD_MEDIA_PARTIAL_SIZE')
    offset = part.stat().st_size if part.exists() else 0
    check_write_space(path.parent,expected['bytes']-offset,reserve)
    headers = {'User-Agent':'NOX-owner-media/1'}
    if offset: headers['Range']='bytes='+str(offset)+'-'
    if offset < expected['bytes']:
        try:
            response = urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=60)
        except urllib.error.HTTPError as exc: fail('HOLD_MEDIA_DOWNLOAD_HTTP_'+str(exc.code))
        except (OSError,urllib.error.URLError): fail('HOLD_MEDIA_DOWNLOAD_UNAVAILABLE')
        with response:
            if offset and response.status == 206:
                if not response.headers.get('Content-Range','').startswith('bytes '+str(offset)+'-'):
                    fail('HOLD_MEDIA_RESUME_RANGE')
            elif response.status == 200:
                offset = 0
            else: fail('HOLD_MEDIA_DOWNLOAD_STATUS')
            fd = os.open(part,os.O_CREAT|os.O_WRONLY|os.O_NOFOLLOW|(os.O_APPEND if offset else os.O_TRUNC),0o600)
            with os.fdopen(fd,'ab' if offset else 'wb') as target:
                count = offset; last = 0
                while True:
                    block = response.read(4*1024*1024)
                    if not block: break
                    if count+len(block)>expected['bytes']: fail('HOLD_MEDIA_DOWNLOAD_OVERSIZE')
                    # Parallel network reads share this short write admission,
                    # so two writers cannot each spend the same free bytes.
                    with _STORAGE_WRITE_LOCK:
                        check_write_space(path.parent,len(block),reserve)
                        target.write(block)
                    count += len(block)
                    if time.monotonic()-last>30:
                        emit('download',file=path.name,bytes=count,total=expected['bytes']); last=time.monotonic()
                target.flush(); os.fsync(target.fileno())
                if count != expected['bytes']: fail('HOLD_MEDIA_DOWNLOAD_INCOMPLETE')
    checked = validate_file(part,expected)
    if path.exists(): fail('HOLD_MEDIA_DESTINATION_RACE')
    os.rename(part,path)
    return {**checked,'path':str(path),'stat_mtime_ns':path.stat().st_mtime_ns}


def discover_engine():
    candidates = [MEDIA/'ComfyUI',Path('/root/ComfyUI'),ROOT/'ComfyUI',Path('/workspace/ComfyUI')]
    if CONFIG.is_file() and not CONFIG.is_symlink():
        old = json.loads(CONFIG.read_text())
        if old.get('engine_root'): candidates.insert(0,Path(old['engine_root']))
    found = []
    for path in candidates:
        path = plain(path)
        if (path/'main.py').is_file() and (path/'comfy').is_dir() and path not in found:
            found.append(path)
    if len(found)>1: fail('HOLD_MEDIA_MULTIPLE_EXISTING_ENGINES')
    return found[0] if found else None


def extract_source(archive, destination):
    destination = plain(destination)
    if destination.exists(): fail('HOLD_MEDIA_ENGINE_DESTINATION_EXISTS')
    staging = Path(tempfile.mkdtemp(prefix='.comfy-source-',dir=destination.parent))
    total = 0
    with tarfile.open(archive,'r:gz') as source:
        for member in source:
            parts = PurePosixPath(member.name).parts
            if not parts or parts[0] != 'ComfyUI-'+COMFY_COMMIT or '..' in parts or PurePosixPath(member.name).is_absolute():
                fail('HOLD_MEDIA_ARCHIVE_PATH')
            if len(parts)==1: continue
            if not member.isdir() and not member.isfile(): fail('HOLD_MEDIA_ARCHIVE_LINK_OR_TYPE')
            target = plain(staging.joinpath(*parts[1:]))
            if member.isdir(): target.mkdir(parents=True,exist_ok=True); continue
            total += member.size
            if total>128*1024*1024: fail('HOLD_MEDIA_ARCHIVE_EXPANSION')
            target.parent.mkdir(parents=True,exist_ok=True)
            with source.extractfile(member) as inp,target.open('xb') as out:
                shutil.copyfileobj(inp,out,1024*1024)
    if not (staging/'main.py').is_file(): fail('HOLD_MEDIA_ARCHIVE_MAIN_MISSING')
    atomic_json(staging/'nox-source.json',{'commit':COMFY_COMMIT,'archive_sha256':COMFY_ARCHIVE['sha256']})
    staging.rename(destination)
    return destination


def ensure_engine(existing):
    if existing:
        emit('existing_engine_reused',path=str(existing))
        return existing
    MEDIA.mkdir(mode=0o700,parents=True,exist_ok=True)
    archive = MEDIA/'source'/('ComfyUI-'+COMFY_COMMIT+'.tar.gz')
    download(COMFY_ARCHIVE['url'],archive,COMFY_ARCHIVE)
    return extract_source(archive,MEDIA/'ComfyUI')


def base_environment():
    code = "import json,sys,sysconfig,platform,torch;print(json.dumps({'python':sys.version.split()[0],'machine':platform.machine(),'purelib':sysconfig.get_path('purelib'),'torch':torch.__version__,'torch_file':torch.__file__,'cuda':torch.version.cuda,'arch':(torch._C._cuda_getArchFlags() or '').split()}))"
    data = json.loads(run([BASE_PYTHON,'-c',code],60,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','CUDA_VISIBLE_DEVICES':''}))
    if data.get('torch')!='2.6.0+cu124' or data.get('cuda')!='12.4' or 'sm_70' not in data.get('arch',[]):
        fail('HOLD_MEDIA_SHARED_TORCH_SM70_PIN')
    if not str(data.get('purelib','')).startswith('/root/venv_volta/lib/'):
        fail('HOLD_MEDIA_SHARED_ENV_PATH')
    return data


def environment_spec(base, legacy=False):
    return {'schema':1,'shared_purelib':base['purelib'],'shared_torch':base['torch'],
            'torch_file':base['torch_file'],
            'pypi_pins':list(LEGACY_PYPI_PINS if legacy else PYPI_PINS),'cuda_pins':list(CUDA_PINS)}


PIN_AUDIT_CODE = r'''
import importlib.metadata as m,json,pathlib,sys
pins=json.loads(sys.argv[1]);root=pathlib.Path(sys.argv[2]).resolve()
result={'missing':[],'mismatched':[],'outside_isolated_environment':[]}
for pin in pins:
 name,version=pin.split('==',1)
 try:d=m.distribution(name)
 except m.PackageNotFoundError:result['missing'].append(name);continue
 if d.version!=version:result['mismatched'].append(name)
 if not pathlib.Path(d.locate_file('')).resolve().is_relative_to(root):result['outside_isolated_environment'].append(name)
result['ok']=not any(result.values());print(json.dumps(result))
'''


DEPENDENCY_AUDIT_CODE = r'''
import importlib.metadata as m,json,sys
from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
pending=[Requirement(x) for x in json.loads(sys.argv[1])];seen=set();bad=[];env=default_environment()
while pending:
 requirement=pending.pop();name=canonicalize_name(requirement.name)
 try:dist=m.distribution(name)
 except m.PackageNotFoundError:bad.append({'package':name,'reason':'MISSING'});continue
 if requirement.specifier and not requirement.specifier.contains(dist.version,prereleases=True):
  bad.append({'package':name,'reason':'VERSION_MISMATCH'});continue
 extras=tuple(sorted(requirement.extras));key=(name,extras)
 if key in seen:continue
 seen.add(key)
 if len(seen)>128:raise RuntimeError('DEPENDENCY_GRAPH_BUDGET')
 # Torch/CUDA are verified independently by exact version, origin and SM70.
 # Do not resolve their installer dependencies or change the shared stack.
 if name=='torch':continue
 for raw in dist.requires or []:
  item=Requirement(raw)
  if item.marker and not any(item.marker.evaluate({**env,'extra':extra}) for extra in ('',*extras)):continue
  pending.append(item)
print(json.dumps({'ok':not bad,'packages_checked':len(seen),'issues':bad[:64]}))
'''


def pinned_environment(python, purelib, pins, env):
    value = json.loads(run([python,'-c',PIN_AUDIT_CODE,json.dumps(list(pins)),str(purelib)],30,env=env))
    if not isinstance(value,dict) or type(value.get('ok')) is not bool:
        fail('HOLD_MEDIA_PACKAGE_AUDIT_SCHEMA')
    return value


def ensure_environment(base):
    if not str(base.get('python','')).startswith('3.12.') or base.get('machine')!='x86_64':
        fail('HOLD_MEDIA_DEPENDENCY_WHEEL_PLATFORM')
    environment = plain(MEDIA/'venv'); python = environment/'bin/python'
    marker = plain(environment/'nox-environment.json')
    spec = environment_spec(base)
    previous = None
    if environment.exists():
        if not marker.is_file() or marker.stat().st_size>16384:
            fail('HOLD_MEDIA_EXISTING_ENVIRONMENT_SCOPE')
        previous = json.loads(marker.read_text())
        if previous not in (spec,environment_spec(base,legacy=True)):
            fail('HOLD_MEDIA_EXISTING_ENVIRONMENT_SCOPE')
    else:
        run([BASE_PYTHON,'-m','venv',environment],120)
        atomic_json(marker,spec)
    purelib = Path(run([python,'-c','import sysconfig;print(sysconfig.get_path("purelib"))']).strip())
    if not purelib.is_relative_to(environment): fail('HOLD_MEDIA_ISOLATED_INSTALL_PATH')
    # The isolated environment sees the existing CUDA/Torch wheels. All pip
    # targets remain in this new venv; the trainer's dependencies are untouched.
    env = {**os.environ,'PIP_DISABLE_PIP_VERSION_CHECK':'1','PIP_NO_CACHE_DIR':'1',
           'PIP_REQUIRE_VIRTUALENV':'1','PYTHONNOUSERSITE':'1','PYTHONDONTWRITEBYTECODE':'1',
           'CUDA_VISIBLE_DEVICES':''}
    inherited = plain(purelib/'nox_shared_torch.pth')
    migration = previous is not None and previous != spec
    if migration:
        if not inherited.is_file() or inherited.read_text()!=base['purelib']+'\n':
            fail('HOLD_MEDIA_LEGACY_SHARED_PATH_CHANGED')
        # A familiar marker alone does not authorize rewriting an arbitrary env.
        # Every original wheel must still be exactly pinned and local.
        audit = pinned_environment(python,purelib,LEGACY_PYPI_PINS+REQUESTS_PINS+CUDA_PINS,env)
        if audit.get('ok') is not True:
            emit('legacy_environment_unverified',**audit)
            fail('HOLD_MEDIA_LEGACY_PACKAGES_CHANGED')
        emit('additive_dependency_migration',packages=list(AIOHTTP_PINS),shared_torch=base['torch'])
    else:
        if inherited.exists() and inherited.read_text()!=base['purelib']+'\n':
            fail('HOLD_MEDIA_SHARED_PATH_CHANGED')
        inherited.write_text(base['purelib']+'\n')
        installed = pinned_environment(python,purelib,LEGACY_PYPI_PINS+CUDA_PINS,env)
        if installed.get('ok') is not True:
            emit('isolated_environment_installing',packages=len(LEGACY_PYPI_PINS)+len(CUDA_PINS),shared_torch=base['torch'])
            run([python,'-m','pip','install','--no-deps','--ignore-installed','--only-binary=:all:',
                 '--index-url','https://pypi.org/simple',*LEGACY_PYPI_PINS],900,env=env)
            run([python,'-m','pip','install','--no-deps','--ignore-installed','--only-binary=:all:',
                 '--index-url','https://download.pytorch.org/whl/cu124',*CUDA_PINS],600,env=env)
    for pins,wheels in ((REQUESTS_PINS,REQUESTS_WHEELS),(AIOHTTP_PINS,AIOHTTP_WHEELS)):
        additions = pinned_environment(python,purelib,pins,env)
        if additions.get('ok') is not True:
            run([python,'-m','pip','install','--no-deps','--ignore-installed','--only-binary=:all:',
                 '--no-index',*[url+'#sha256='+sha for url,sha in wheels]],300,env=env)
    audit = pinned_environment(python,purelib,PYPI_PINS+CUDA_PINS,env)
    if audit.get('ok') is not True:
        emit('isolated_packages_unverified',**audit)
        fail('HOLD_MEDIA_PINNED_PACKAGES_UNVERIFIED')
    closure = json.loads(run([python,'-c',DEPENDENCY_AUDIT_CODE,json.dumps(list(PYPI_PINS+CUDA_PINS))],30,env=env))
    emit('isolated_dependency_closure',**closure)
    if closure.get('ok') is not True: fail('HOLD_MEDIA_DEPENDENCY_CLOSURE')
    code = "import json,torch,torchvision,torchaudio,transformers,aiohttp,yarl,torchsde,kornia,spandrel,soundfile,sentencepiece,av,requests,urllib3,charset_normalizer,certifi,idna,propcache,multidict,frozenlist,attrs,aiosignal,aiohappyeyeballs,typing_extensions;from av.codec import Codec;print(json.dumps({'torch':torch.__version__,'torch_file':torch.__file__,'transformers':transformers.__version__,'torchvision':torchvision.__version__,'torchaudio':torchaudio.__version__,'av':av.__version__,'requests':requests.__version__,'aiohttp':aiohttp.__version__,'multidict':multidict.__version__,'vp9_encoder':Codec('libvpx-vp9','w').name}))"
    check = json.loads(run([python,'-c',code],120,env=env))
    if check.get('torch_file')!=base['torch_file'] or check.get('torch')!=base['torch']:
        fail('HOLD_MEDIA_TORCH_REUSE_CHANGED')
    if check.get('vp9_encoder')!='libvpx-vp9': fail('HOLD_MEDIA_VP9_ENCODER_MISSING')
    if check.get('requests')!='2.34.2': fail('HOLD_MEDIA_REQUESTS_PIN')
    if check.get('aiohttp')!='3.11.13' or check.get('multidict')!='6.9.1':fail('HOLD_MEDIA_AIOHTTP_PIN')
    # Promote only the known environment marker, and only after full imports.
    # An interrupted migration keeps the old marker and is safely retryable.
    if previous != spec:
        atomic_json(marker,spec)
    emit('isolated_environment_verified',**check)
    return python,check


def model_paths_config(rows):
    # JSON is also valid YAML; ComfyUI accepts lists as newline-separated paths.
    return {'nox_media':{'base_path':'/', **{
        subdir:'\n'.join(sorted({str(Path(row['path']).parent) for row in rows if row['subdir']==subdir}))
        for subdir in sorted({row['subdir'] for row in rows})}}}


def admit_parallel_downloads(rows,disk_setup_allowance=0):
    remaining = {'ram':0,'disk':0}
    for row in rows:
        path = plain(row['path'])
        if path.exists():
            # The download task still rehashes this file before publication.
            if not path.is_file() or path.stat().st_size!=row['bytes']:
                fail('HOLD_MEDIA_EXISTING_FILE_SIZE')
            continue
        partial = plain(path.with_name(path.name+'.partial'))
        size = partial.stat().st_size if partial.exists() else 0
        if (partial.exists() and not partial.is_file()) or not 0 <= size <= row['bytes']:
            fail('HOLD_MEDIA_PARTIAL_SIZE')
        remaining[row['storage']] += row['bytes']-size
    actual = resources()
    if disk_setup_allowance not in (0,SETUP_ALLOWANCE):fail('HOLD_MEDIA_SETUP_ALLOWANCE')
    if actual['disk_free'] < remaining['disk']+DISK_RESERVE+disk_setup_allowance:
        fail('HOLD_MEDIA_PARALLEL_DISK_ADMISSION')
    if actual['shm_free'] < remaining['ram']+SHM_RESERVE:
        fail('HOLD_MEDIA_PARALLEL_SHM_ADMISSION')
    if actual['memory_free'] < sum(remaining.values())+32*GIB:
        fail('HOLD_MEDIA_PARALLEL_MEMORY_ADMISSION')
    return remaining


def download_selected(rows,disk_setup_allowance=0):
    remaining = admit_parallel_downloads(rows,disk_setup_allowance)
    emit('parallel_downloads_admitted',maximum_transfers=3,pending_bytes=remaining,
         concurrent_setup_reserve_bytes=disk_setup_allowance)
    failures = []
    with ThreadPoolExecutor(max_workers=3,thread_name_prefix='nox-media-download') as pool:
        futures = {pool.submit(download,row['source_url'],row['path'],row,
                               SHM_RESERVE if row['storage']=='ram' else DISK_RESERVE+disk_setup_allowance):row for row in rows}
        for future in as_completed(futures):
            row = futures[future]
            try:
                row.update(future.result())
                emit('asset_sha_verified',filename=row['filename'],bytes=row['bytes'],
                     sha256=row['sha256'],storage=row['storage'])
            except Exception as exc:
                failures.append(exc)
    if failures:
        raise failures[0]
    return rows


def prepare_assets_and_environment(base,rows):
    """Admitted downloads continue even if an independent environment check fails."""
    errors=[];environment=None
    # Reserve the whole model transfer plus the original setup allowance before
    # either branch starts; every model write retains its measured space gate.
    admit_parallel_downloads(rows,SETUP_ALLOWANCE)
    emit('preparation_parallel_started',environment_jobs=1,maximum_download_jobs=3)
    with ThreadPoolExecutor(max_workers=2,thread_name_prefix='nox-media-prepare') as pool:
        jobs={pool.submit(ensure_environment,base):'environment',
              pool.submit(download_selected,rows,SETUP_ALLOWANCE):'assets'}
        for future in as_completed(jobs):
            try:
                value=future.result()
                if jobs[future]=='environment':environment=value
            except Exception as exc:
                errors.append(exc);code=str(exc)
                emit('preparation_component_failed',component=jobs[future],
                     code=code if re.fullmatch('HOLD_[A-Z0-9_]+',code) else type(exc).__name__)
    if errors:raise errors[0]
    if environment is None:fail('HOLD_MEDIA_ENVIRONMENT_RESULT_MISSING')
    return environment


def health_chat():
    with urllib.request.urlopen('http://127.0.0.1:8081/health',timeout=8) as response:
        if response.status!=200: fail('HOLD_MEDIA_CHAT_HEALTH')


def process_identity(pid):
    p = Path('/proc')/str(pid)
    fields = (p/'stat').read_text().split(') ',1)[1].split()
    env = dict(part.split('=',1) for part in (p/'environ').read_text().split('\0') if '=' in part)
    argv = [x.decode(errors='replace') for x in (p/'cmdline').read_bytes().split(b'\0') if x]
    return {'pid':pid,'start_ticks':fields[19],'cuda':env.get('CUDA_VISIBLE_DEVICES'),
            'service':env.get('SUPERVISOR_PROCESS_NAME'),'argv':argv}


def service_status():
    result = subprocess.run(['supervisorctl','status',SERVICE],capture_output=True,text=True,timeout=15)
    match = re.match('^'+SERVICE+r'\s+(\w+)(?:\s+pid\s+(\d+))?',result.stdout.strip())
    return {'state':match[1] if match else 'UNKNOWN','pid':int(match[2]) if match and match[2] else None}


def v13_owner_stop_present():
    """Fail closed on owner NOX STOP during V13 pre-production staging.

    File presence is a veto, including symlinks and unreadable marker paths.
    Only the existing owner cutover process may remove STOP; this helper never
    changes owner flags, maintenance leases or service state.
    """
    markers = [ROOT / part for part in (
        'STOP', 'STOP.flag', 'stop.flag', '.stop', 'program/STOP',
        'state/STOP', 'state/STOP.flag', 'state/MEDIA_STOP.flag',
        'state/OWNER_MAINTENANCE.flag')]
    markers.append(Path('/workspace/NOX_STOP'))
    for marker in markers:
        try:
            marker.lstat()
            return True
        except FileNotFoundError:
            continue
        except OSError:
            return True
    # A held owner maintenance flock is a veto even when its marker is
    # temporarily absent. Never create, modify, or clear that lease.
    lease = ROOT / 'state/owner_maintenance.lock'
    try:
        fd = os.open(lease, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    except FileNotFoundError:
        return False
    except OSError:
        return True
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
            return False
        except OSError:
            return True
    finally:
        os.close(fd)


def start_engine(config):
    # Native media setup is allowed offline; activation is NOT allowed under
    # the owner's global MODEL_UPDATE/STOP. Do this before taking any GPU lock.
    if v13_owner_stop_present():
        fail('HOLD_MEDIA_OWNER_STOP_PRESENT')
    with lock('media.lock'),gpu_lease():
        # Recheck after acquiring the GPU/engine locks; an owner STOP may
        # arrive between the initial read and the first service operation.
        if v13_owner_stop_present(): fail('HOLD_MEDIA_OWNER_STOP_PRESENT')
        if not plain(ROOT/'state/TRAIN_HOLD.flag').is_file(): fail('HOLD_MEDIA_TRAINING_MUST_YIELD')
        health_chat()
        current = service_status()
        if current['state']=='RUNNING':
            identity = process_identity(current['pid'])
            if identity['cuda']!='1' or str(Path(config['engine_root'])/'main.py') not in identity['argv']:
                fail('HOLD_MEDIA_EXISTING_SERVICE_IDENTITY')
        else:
            memory = run(['nvidia-smi','-i','1','--query-gpu=memory.free','--format=csv,noheader,nounits']).strip()
            if not memory.isdigit() or int(memory)<27000: fail('HOLD_MEDIA_GPU1_ADMISSION')
            if cgroup_headroom()<32*GIB: fail('HOLD_MEDIA_RUNTIME_RAM_ADMISSION')
            with socket.socket() as s:
                s.settimeout(2)
                if s.connect_ex(('127.0.0.1',8188))==0: fail('HOLD_MEDIA_PORT_ALREADY_OWNED')
            command = [config['python'],str(Path(config['engine_root'])/'main.py'),
                       '--listen','127.0.0.1','--port','8188','--disable-auto-launch',
                       '--disable-all-custom-nodes','--disable-xformers','--use-pytorch-cross-attention',
                       '--fp16-unet','--fp16-text-enc','--fp32-vae','--reserve-vram','4',
                       '--disable-smart-memory','--extra-model-paths-config',config['extra_model_paths'],
                       '--output-directory',config['output_root']]
            # All executable paths are fixed local paths without shell expansion.
            if any(re.search(r'[\s%\r\n]',a) for a in command): fail('HOLD_MEDIA_SERVICE_ARGUMENT')
            source = ('[program:'+SERVICE+']\ncommand='+' '.join(command)+'\n'
                      'directory='+config['engine_root']+'\nautostart=false\nautorestart=false\n'
                      'startsecs=3\nstopwaitsecs=30\nstopasgroup=true\nkillasgroup=true\n'
                      'environment=CUDA_VISIBLE_DEVICES="1",OMP_NUM_THREADS="4",MKL_NUM_THREADS="4",OPENBLAS_NUM_THREADS="1",PYTHONNOUSERSITE="1",PYTHONDONTWRITEBYTECODE="1",TOKENIZERS_PARALLELISM="false"\n'
                      'stdout_logfile='+str(MEDIA/'engine.log')+'\nstderr_logfile='+str(MEDIA/'engine-error.log')+'\n')
            destination = plain('/etc/supervisor/conf.d/'+SERVICE+'.conf')
            if destination.exists() and destination.read_text()!=source: fail('HOLD_MEDIA_SERVICE_CONFIG_CONFLICT')
            if not destination.exists():
                fd = os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
                with os.fdopen(fd,'w') as out: out.write(source); out.flush(); os.fsync(out.fileno())
            run(['supervisorctl','reread'],30)
            run(['supervisorctl','update',SERVICE],30)
            run(['supervisorctl','start',SERVICE],45)
        deadline = time.monotonic()+120
        nodes = None
        while time.monotonic()<deadline:
            current = service_status()
            if current['state'] not in ('RUNNING','STARTING'): fail('HOLD_MEDIA_ENGINE_FAILED_TO_START')
            try:
                nodes = get_json('http://127.0.0.1:8188/object_info',limit=8*1024*1024)
                if all(name in nodes for name in REQUIRED_NODES): break
            except (RuntimeError,ValueError): pass
            time.sleep(2)
        if not isinstance(nodes,dict) or any(name not in nodes for name in REQUIRED_NODES):
            fail('HOLD_MEDIA_REQUIRED_NODES_MISSING')
        identity = process_identity(service_status()['pid'])
        if identity['cuda']!='1' or identity['service']!=SERVICE or str(Path(config['engine_root'])/'main.py') not in identity['argv']:
            fail('HOLD_MEDIA_ENGINE_PROCESS_IDENTITY')
        options = {'checkpoint':('CheckpointLoaderSimple','ckpt_name'),'unet':('UNETLoader','unet_name'),
                   'clip':('CLIPLoader','clip_name'),'vae':('VAELoader','vae_name')}
        for asset in config['assets']:
            node,field = options[asset['role']]
            if asset['filename'] not in nodes[node]['input']['required'][field][0]:
                fail('HOLD_MEDIA_MODEL_OPTION_MISSING')
        health_chat()
        config.update(enabled=True,engine_pid=identity['pid'],start_ticks=identity['start_ticks'],
                      ready_at=time.time(),readiness_scope='ENGINE_AND_FILES_READY_GENERATION_ACCEPTANCE_PENDING')
        atomic_json(CONFIG,config)
        return config


def install(start=False):
    with lock('install.lock'):
        MEDIA.mkdir(mode=0o700,parents=True,exist_ok=True)
        existing_engine = discover_engine()
        rows = plan_assets(resources(),find_existing_assets(existing_engine),existing_partials())
        emit('admitted',assets=[{k:r[k] for k in ('filename','bytes','storage','reused')} for r in rows])
        verify_hf_metadata()
        base = base_environment()
        engine = ensure_engine(existing_engine)
        # Environment setup and the three admitted transfer slots are
        # independent; one missing import cannot prevent all weight downloads.
        python,environment = prepare_assets_and_environment(base,rows)
        paths_file = MEDIA/'extra_model_paths.json'
        atomic_json(paths_file,model_paths_config(rows))
        output = plain(MEDIA/'outputs'); output.mkdir(mode=0o700,parents=True,exist_ok=True)
        config = {'schema_version':1,'enabled':False,'engine_root':str(engine),'python':str(python),
                  'engine_service':SERVICE,'engine_url':'http://127.0.0.1:8188',
                  'extra_model_paths':str(paths_file),'output_root':str(output),
                  'assets':rows,'workflows':['sdxl_lightning_4step','wan21_t2v_13b'],
                  'source_commit':COMFY_COMMIT if not existing_engine else None,
                  'engine_reused':bool(existing_engine),'engine_main_sha256':sha256(engine/'main.py'),
                  'environment':environment,'prepared_at':time.time(),
                  'shm_reserve_bytes':SHM_RESERVE,'disk_reserve_bytes':DISK_RESERVE,
                  'cgroup_reserve_bytes':CGROUP_RESERVE,'ephemeral_cache_rehydrate_required_after_reboot':True,
                  'native_fp8_compute_enabled':False,'training_environment_modified':False,
                  'readiness_scope':'FILES_VERIFIED_ENGINE_NOT_STARTED'}
        atomic_json(CONFIG,config)
        if start: config = start_engine(config)
        emit('prepared',enabled=config['enabled'],config=str(CONFIG),scope=config['readiness_scope'])
        return config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('plan','install','start'))
    parser.add_argument('--start',action='store_true')
    args = parser.parse_args()
    if args.command=='plan':
        engine = discover_engine()
        emit('plan',engine=str(engine) if engine else None,
             assets=plan_assets(resources(),find_existing_assets(engine),existing_partials()))
    elif args.command=='install': install(args.start)
    else:
        config = json.loads(plain(CONFIG).read_text())
        for row in config['assets']: validate_file(row['path'],row)
        start_engine(config)


if __name__=='__main__':
    try: main()
    except Exception as exc:
        code = str(exc)
        emit('held',code=code if re.fullmatch(r'HOLD_[A-Z0-9_]+',code) else type(exc).__name__)
        raise SystemExit(2)
