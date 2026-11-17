#!/usr/bin/env python3
"""Explicit audit profiles; default is bounded authenticated source readback."""
from __future__ import annotations
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import json, os, re, shutil, subprocess, sys, time

SAFE=re.compile(r'^[A-Za-z0-9_./+@:= -]{1,300}$')
ROOTS=('/root/nox','/root/nox_learn','/workspace')

def run(argv, seconds=12):
    try:
        p=subprocess.run(argv,capture_output=True,text=True,timeout=seconds)
        return p.returncode,p.stdout[:200000]
    except Exception as e:return 99,type(e).__name__

def num(path):
    try:
        v=Path(path).read_text().strip()
        return int(v) if v.isdigit() else v[:40]
    except OSError:return None

def hardware():
    rc,g=run(['nvidia-smi','--query-gpu=index,name,uuid,memory.total,memory.used,utilization.gpu,temperature.gpu','--format=csv,noheader,nounits'])
    _,a=run(['nvidia-smi','--query-compute-apps=pid,gpu_uuid,used_gpu_memory','--format=csv,noheader,nounits'])
    return {'gpu_rc':rc,'gpu':[x for x in g.splitlines() if SAFE.fullmatch(x.replace(',',''))][:4],
      'gpu_apps':[x for x in a.splitlines() if SAFE.fullmatch(x.replace(',',''))][:16],
      'cpus':os.cpu_count(),'load':list(os.getloadavg()),
      'cgroup_max':num('/sys/fs/cgroup/memory.max'),'cgroup_current':num('/sys/fs/cgroup/memory.current'),
      'cpu_max':num('/sys/fs/cgroup/cpu.max'),
      'disk':{r:dict(zip(('total','used','free'),shutil.disk_usage(r))) for r in ROOTS if Path(r).is_dir()}}

def proc_start_ticks(proc_dir, expected_pid):
    """Read Linux /proc/<pid>/stat field 22; verify PID despite ')' in comm.

    A numeric PID without a validated start tick is not proof of process identity.
    Do not export cmdline, environment, or the raw stat record.
    """
    raw=(Path(proc_dir)/'stat').read_text()
    prefix=str(expected_pid)+' ('
    boundary=raw.rfind(') ')
    if not raw.startswith(prefix) or boundary<len(prefix):
        raise ValueError('HOLD_PID_STAT_IDENTITY')
    fields=raw[boundary+2:].split()
    if len(fields)<20 or not fields[19].isdigit():
        raise ValueError('HOLD_PID_START_TICKS')
    return int(fields[19])

def process_rows(proc_root=Path('/proc')):
    rows=[]
    flags={'-m','--model','--model-path','--model_path','--base-model','--student','--output_dir','--output-dir','--config','-c'}
    for p in Path(proc_root).iterdir():
        if not p.name.isdigit():continue
        try:
            initial_ticks=proc_start_ticks(p,int(p.name))
            argv=(p/'cmdline').read_bytes().decode(errors='replace').strip('\0').split('\0')
            if not argv or not any(k in ' '.join(argv[:3]).lower() for k in ('nox','llama','train','python','supervisor','rclone','jupyter')):continue
            args=[]
            for i,v in enumerate(argv):
                if v in flags and i+1<len(argv) and SAFE.fullmatch(argv[i+1]) and '://' not in argv[i+1]:args.append([v,argv[i+1]])
            row={'pid':int(p.name),'comm':(p/'comm').read_text().strip()[:60],
                 'executable':os.path.basename(argv[0]),'arguments':args[:12]}
            scripts=[v for v in argv[1:5] if v.endswith(('.py','.sh')) and SAFE.fullmatch(v)]
            if scripts:row['scripts']=scripts
            # Do not attribute a reused PID to the model observed earlier.
            if proc_start_ticks(p,int(p.name)) != initial_ticks:continue
            row['start_ticks']=initial_ticks
            rows.append(row)
        except (OSError,ValueError):continue
    return rows[:100]

def v13_owner_fence_metadata(root=Path('/root/nox'), workspace_stop=Path('/workspace/NOX_STOP'), lstat=os.lstat):
    """READ-ONLY marker presence, not authorization to start, stop, or write.

    Preserve unreadable markers as UNKNOWN; missing flags at one instant are
    never evidence of an owner lease, safe release, or completed shutdown.
    Do not open, follow, hash or export marker contents.
    """
    paths = {
        'STOP': root / 'STOP',
        'STOP_FLAG': root / 'STOP.flag',
        'LOWER_STOP_FLAG': root / 'stop.flag',
        'DOT_STOP': root / '.stop',
        'PROGRAM_STOP': root / 'program/STOP',
        'STATE_STOP': root / 'state/STOP',
        'STATE_STOP_FLAG': root / 'state/STOP.flag',
        'MEDIA_STOP': root / 'state/MEDIA_STOP.flag',
        'OWNER_MAINTENANCE': root / 'state/OWNER_MAINTENANCE.flag',
        'WORKSPACE_STOP': workspace_stop,
        'TRAIN_HOLD': root / 'state/TRAIN_HOLD.flag',
    }
    rows = {}
    for name, path in paths.items():
        try:
            lstat(path)
            rows[name] = 'PRESENT'
        except FileNotFoundError:
            rows[name] = 'NOT_FOUND_AT_SNAPSHOT'
        except OSError:
            rows[name] = 'UNKNOWN_UNREADABLE'
    owner_names = tuple(name for name in rows if name != 'TRAIN_HOLD')
    owner_observed = [rows[name] for name in owner_names]
    status = ('PRESENT' if 'PRESENT' in owner_observed else
              'UNKNOWN' if 'UNKNOWN_UNREADABLE' in owner_observed else
              'NOT_OBSERVED_NOT_AUTHORIZED')
    return {
        'scope': 'READ_ONLY_MARKER_METADATA',
        'owner_stop_state': status,
        'train_hold_state': rows['TRAIN_HOLD'],
        'markers': rows,
        'owner_lease_state': 'NOT_CHECKED',
        'may_clear_stop': False,
        'may_start_nox': False,
        'may_write_native': False,
        'pid_starttime_verified': False,
    }


def supervisor():
    fence=v13_owner_fence_metadata()
    binary=shutil.which('supervisorctl')
    if not binary:
        binary=next((x for x in ('/opt/venv/bin/supervisorctl','/usr/local/bin/supervisorctl') if Path(x).is_file()),None)
    if not binary:return {'available':False,'owner_fence_readonly':fence}
    candidates=[None]+[x for x in ('/etc/supervisor/supervisord.conf','/etc/supervisord.conf','/root/nox/supervisord.conf') if Path(x).is_file()]
    results=[]
    for c in candidates:
        args=[binary]+(['-c',c] if c else [])+['status']
        rc,out=run(args)
        rows=[]
        for line in out.splitlines():
            m=re.match(r'^([A-Za-z0-9_.:-]+)\s+(RUNNING|STARTING|STOPPED|FATAL|BACKOFF|EXITED|STOPPING|UNKNOWN)\b(.*)$',line)
            if m:
                pid=re.search(r'\bpid (\d+)',m.group(3))
                rows.append({'name':m.group(1),'state':m.group(2),'pid':int(pid[1]) if pid else None})
        results.append({'config':c,'rc':rc,'services':rows})
        if rows:break
    return {'available':True,'results':results,'owner_fence_readonly':fence}

def v13_wheelhouse_admission(record):
    """Metadata-only ABI gate for the Drive CP311/cu126 wheelhouse, never an installer.

    A matching wheel tag is not a GPU smoke, driver test, license approval, or
    native installation receipt. Incompatible installed Python environments
    must not be modified to make a source check pass.
    """
    if not isinstance(record, dict) or not isinstance(record.get('_runtime'), dict):
        return 'HOLD_WHEELHOUSE_RUNTIME_ABI_UNKNOWN'
    runtime = record['_runtime']
    if runtime.get('python_abi') != 'cpython-311':
        return 'HOLD_WHEELHOUSE_CP311_PYTHON_ABI_MISMATCH'
    if runtime.get('platform') != 'linux-x86_64':
        return 'HOLD_WHEELHOUSE_LINUX_X86_64_PLATFORM_MISMATCH'
    # A CP311 cache tag alone is not enough: it can disagree with the
    # interpreter's actual version. Reject contradictory or missing evidence
    # rather than labelling a potentially CP312 process a candidate.
    python_version = runtime.get('python_version')
    if not isinstance(python_version, str) or re.fullmatch(r'3\.11\.\d+', python_version) is None:
        return 'HOLD_WHEELHOUSE_CP311_VERSION_MISMATCH'
    version = record.get('torch')
    if not isinstance(version, str) or not version:
        return 'HOLD_WHEELHOUSE_TORCH_BUILD_UNKNOWN'
    # A forged package label such as "unknown+cu126" is not a PyTorch build.
    if re.fullmatch(r'[1-9]\d*\.\d+\.\d+\+cu126', version) is None:
        return 'HOLD_WHEELHOUSE_CU126_TORCH_BUILD_MISMATCH'
    return 'SOURCE_ONLY_WHEELHOUSE_ABI_CANDIDATE_NATIVE_SM70_HOLD'


def packages():
    code="import importlib.metadata as m,json,sys,sysconfig; names=['torch','transformers','accelerate','datasets','deepspeed','safetensors','peft','bitsandbytes','trl','psutil','nvidia-ml-py','diffusers','opencv-python','imageio-ffmpeg']; d={'_runtime':{'python_abi':sys.implementation.cache_tag,'python_version':'.'.join(map(str,sys.version_info[:3])),'platform':sysconfig.get_platform()}};\nfor n in names:\n try:d[n]=m.version(n)\n except m.PackageNotFoundError:d[n]=None\nprint(json.dumps(d))"
    found={}
    for p in ('/root/venv_volta/bin/python','/opt/venv/bin/python','/root/nox/.venv/bin/python','/usr/bin/python3'):
        if Path(p).is_file():
            rc,out=run([p,'-c',code])
            try:
                row=json.loads(out) if rc==0 else {'status':'IMPORT_FAILED'}
                if isinstance(row,dict) and rc==0:
                    row['_wheelhouse_candidate']=v13_wheelhouse_admission(row)
                found[p]=row
            except ValueError:found[p]={'status':'INVALID_OUTPUT'}
    return found

# Exact immutable DeepSeek pins mirrored from v51/hf_range_probe.py.
# The offline source test asserts these rows remain identical to that manifest.
MODEL_ROOT='/root/nox/models'
MODEL_MANIFEST_REVISION='65d53bc8be65123e255ff02f3ded958b6dbf54fd'
PINNED_MODEL_FILES=(
 ('DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00001-of-00006.gguf',5780704,'f356f198561f56df36f7ab92d7238a926646d76de992c34f15bcb939a5f529b9'),
 ('DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00002-of-00006.gguf',39535781184,'25af3785ccf925f54137e1ead4c481a8952315dc0b1af6519a99407f67bce8f3'),
 ('DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00003-of-00006.gguf',39736712000,'8168d0998fc494def2e1952d83c131425a108660aae9d29190f5a8670ab62b48'),
 ('DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00004-of-00006.gguf',39036908384,'9eb9b4de1968f150dfc207eb31c27be9cd9b5666a9a6246bde8a22b184b4bee0'),
 ('DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00005-of-00006.gguf',19923784832,'7e35f6b4e6fc46f6c4b152b593d84d683c5ece695ae6ad734f556198c041bec1'),
 ('DeepSeek-V4.1-Flash-Engram-IQ4_NL.gguf',110595290816,'3dac4c54893ad7aa89103c0028500eadc78e74112cef3a2930a97e67dc9fb4f3'),
)

def pinned_model_paths(root=MODEL_ROOT,lstat=os.lstat):
    """Metadata-only, no-follow stat for the six immutable targets under one root."""
    root_path=Path(root)
    if not root_path.is_absolute():
        return {'status':'HOLD_MODEL_ROOT_NOT_ABSOLUTE','root':str(root_path),'manifest_revision':MODEL_MANIFEST_REVISION,'files':[]}
    root_parts=root_path.parts
    ancestors=[]; current=Path(root_path.anchor)
    for part in root_parts[1:]:
        current=current/part
        ancestors.append(current)
    try:
        for ancestor in ancestors:
            mode=lstat(str(ancestor)).st_mode
            if __import__('stat').S_ISLNK(mode):
                return {'status':'HOLD_MODEL_PATH_SYMLINK','root':str(root_path),'manifest_revision':MODEL_MANIFEST_REVISION,
                        'files':[{'path':str(root_path/name),'exists':None,'type':'blocked',
                                  'bytes':None,'expected_bytes':size,'sha_status':'NOT_CHECKED',
                                  'path_status':'HOLD_MODEL_PATH_SYMLINK'}
                                 for name,size,_ in PINNED_MODEL_FILES]}
            if not __import__('stat').S_ISDIR(mode):
                return {'status':'HOLD_MODEL_ROOT_COMPONENT_TYPE','root':str(root_path),'manifest_revision':MODEL_MANIFEST_REVISION,
                        'files':[{'path':str(root_path/name),'exists':None,'type':'blocked',
                                  'bytes':None,'expected_bytes':size,'sha_status':'NOT_CHECKED',
                                  'path_status':'HOLD_MODEL_ROOT_COMPONENT_TYPE'}
                                 for name,size,_ in PINNED_MODEL_FILES]}
    except FileNotFoundError:
        pass
    except OSError as exc:
        status='HOLD_MODEL_PATH_STAT_'+type(exc).__name__.upper()
        return {'status':status,'root':str(root_path),'manifest_revision':MODEL_MANIFEST_REVISION,
                'files':[{'path':str(root_path/name),'exists':None,'type':'unknown',
                          'bytes':None,'expected_bytes':size,'sha_status':'NOT_CHECKED',
                          'path_status':status} for name,size,_ in PINNED_MODEL_FILES]}
    results=[]
    for name,expected_bytes,sha256 in PINNED_MODEL_FILES:
        if (not name or Path(name).name!=name or '/' in name or '\\\\' in name
                or name in ('.','..')):
            return {'status':'HOLD_MODEL_PATH_ESCAPE','files':[]}
        target=root_path/name
        path=str(target)
        row={'path':path,'exists':False,'type':'missing','bytes':None,
             'expected_bytes':expected_bytes,'sha_status':'NOT_CHECKED'}
        try:
            observed=lstat(path)
            mode=observed.st_mode
            statmod=__import__('stat')
            if statmod.S_ISLNK(mode):
                row.update({'type':'symlink','path_status':'HOLD_MODEL_PATH_SYMLINK'})
                results.append(row)
                continue
            if statmod.S_ISREG(mode):
                row.update({'exists':True,'type':'regular','bytes':observed.st_size,
                            'size_status':'MATCH' if observed.st_size==expected_bytes else 'MISMATCH'})
            elif statmod.S_ISDIR(mode):
                row.update({'exists':True,'type':'directory','bytes':None})
            else:
                row.update({'exists':True,'type':'other','bytes':None})
            results.append(row)
        except FileNotFoundError:
            results.append(row)
        except OSError as exc:
            row.update({'type':'unknown','path_status':'HOLD_MODEL_PATH_STAT_'+type(exc).__name__.upper()})
            results.append(row)
    # Overall status must fail closed. The caller must not treat unreadable, bad-sized,
    # or nonregular candidates as a clean model inventory just because other rows passed.
    path_holds=[r['path_status'] for r in results if r.get('path_status')]
    if 'HOLD_MODEL_PATH_SYMLINK' in path_holds:
        status='HOLD_MODEL_PATH_SYMLINK'
    elif path_holds:
        status=path_holds[0]
    elif any(r['type'] not in ('regular','missing') for r in results):
        status='HOLD_MODEL_TARGET_TYPE'
    elif any(r.get('size_status')=='MISMATCH' for r in results):
        status='HOLD_MODEL_FILE_SIZE_MISMATCH'
    elif any(r['type']=='missing' for r in results):
        # Missing GGUF files are not an admitted model, even if every readable
        # pathname was safe. In particular, never report OK for an empty root.
        status='HOLD_MODEL_FILES_MISSING'
    else:
        status='HOLD_MODEL_SHA_UNVERIFIED'  # File sizes match, but full GGUF SHA was NOT checked.
    return {'status':status,'root':str(root_path),'manifest_revision':MODEL_MANIFEST_REVISION,
            'files':results}

def models():
    return {'pinned_model_paths':pinned_model_paths()}

def storage():
    rc=shutil.which('rclone')
    if not rc:return {'rclone_present':False}
    status,out=run([rc,'listremotes'])
    names=[x.strip() for x in out.splitlines() if re.fullmatch(r'[A-Za-z0-9_.-]{1,64}:',x.strip())]
    checks=[]
    for remote in names[:3]:
        code,out=run([rc,'about',remote,'--json'],15)
        try:
            d=json.loads(out);clean={k:d[k] for k in ('total','used','free','trashed') if type(d.get(k)) is int}
        except (ValueError,TypeError):clean={}
        checks.append({'remote':remote,'about_rc':code,'capacity':clean})
    return {'rclone_present':True,'list_rc':status,'remotes':names,'checks':checks,
            'known_config_present':{x:Path(x).is_file() for x in ('/root/.config/rclone/rclone.conf','/root/nox/rclone.conf')}}

# Read only the current Linux mount namespace. Device source strings are intentionally
# omitted because they can contain remote paths or credentials. statvfs reads metadata only.
BLOCK_FILESYSTEMS={'ext2','ext3','ext4','xfs','btrfs','zfs','vfat','exfat','ntfs'}
LOCAL_CAPACITY_FILESYSTEMS=BLOCK_FILESYSTEMS|{'overlay','tmpfs','ramfs'}
def _unescape_mountinfo(value):
    return re.sub(r'\\([0-7]{3})',lambda m:chr(int(m.group(1),8)),value)

def _capacity_row(path,mount_rows,statvfs,path_exists):
    exists=bool(path_exists(path))
    matches=[r for r in mount_rows if path==r['mountpoint'] or path.startswith(r['mountpoint'].rstrip('/')+'/')]
    mount=max(matches,key=lambda r:len(r['mountpoint'])) if matches else None
    try:
        if not exists:raise FileNotFoundError(path)
        if mount is None or mount['filesystem'] not in LOCAL_CAPACITY_FILESYSTEMS:
            raise OSError('filesystem is outside the local capacity allowlist')
        st=statvfs(path); block_size=st.f_frsize or st.f_bsize
        total=int(st.f_blocks)*int(block_size); available=int(st.f_bavail)*int(block_size)
    except (OSError,AttributeError,TypeError,ValueError):
        total=None; available=None
    row={'path':path,'exists':exists,'mountpoint':mount['mountpoint'] if mount else None,
         'filesystem':mount['filesystem'] if mount else None,
         'device_major_minor':mount['device_major_minor'] if mount else None,
         'total_bytes':total,'available_bytes':available}
    return row

def _mount_inventory_from_text(text,statvfs=os.statvfs,path_exists=None):
    rows=[]; mount_by_path={}; type_counts={}
    lines=text.splitlines(); truncated=len(lines)>4096
    for line in lines[:4096]:
        try:
            before,after=line.split(' - ',1)
            left=before.split(); right=after.split()
            if len(left)<6 or len(right)<3:continue
            fstype=right[0]; mountpoint=_unescape_mountinfo(left[4]); dev=left[2]
            if not SAFE.fullmatch(mountpoint) or not re.fullmatch(r'\d+:\d+',dev):continue
            if re.fullmatch(r'[A-Za-z0-9_.+-]{1,64}',fstype):
                type_counts[fstype]=type_counts.get(fstype,0)+1
            entry={'mountpoint':mountpoint,'filesystem':fstype,'device_major_minor':dev}
            mount_by_path[mountpoint]=entry
            if fstype in BLOCK_FILESYSTEMS and not any(r['mountpoint']==mountpoint for r in rows):
                try:
                    st=statvfs(mountpoint); block_size=st.f_frsize or st.f_bsize
                    total=int(st.f_blocks)*int(block_size); available=int(st.f_bavail)*int(block_size)
                except (OSError,AttributeError,TypeError,ValueError):
                    total=None; available=None
                rows.append({**entry,'total_bytes':total,'available_bytes':available})
        except (ValueError,IndexError):continue
    if len(rows)>512:
        rows=rows[:512]; truncated=True
    rows.sort(key=lambda r:(r['mountpoint'],r['filesystem'],r['device_major_minor']))
    if path_exists is None:path_exists=lambda p:Path(p).exists()
    all_mount_rows=list(mount_by_path.values())
    data_entry=mount_by_path.get('/data')
    paths=[_capacity_row(p,all_mount_rows,statvfs,path_exists) for p in ('/','/data','/workspace')]
    return {'scope':'current_process_mount_namespace_only','provider_disk_visibility':'not_established',
            'mountinfo_readable':True,'mountinfo_entry_count':len(lines),'filesystem_type_counts':type_counts,
            'data_mount_present':data_entry is not None,'data_mount_entry':data_entry,
            'storage_paths':paths,'eligible_block_mount_count':len(rows),'truncated':truncated,'mounts':rows}

def mount_inventory():
    try:
        text=Path('/proc/self/mountinfo').read_text()
    except OSError as e:
        return {'scope':'current_process_mount_namespace_only','mountinfo_readable':False,
                'error':type(e).__name__,'mounts':[]}
    return _mount_inventory_from_text(text)

def worker(i):
    try:
        functions=(hardware,process_rows,supervisor,packages,models,storage,mount_inventory)
        return {'section':functions[i].__name__,'worker_pid':os.getpid(),'result':functions[i]()}
    except Exception as e:return {'section':str(i),'worker_pid':os.getpid(),'error':type(e).__name__}

O2_CODE_PATHS = (
    'scripts/chat_proxy.py', 'scripts/nox_v29_chat_bridge.py',
    'scripts/nox_priority_arbiter.py', 'scripts/owner_chat_ui.py',
    'scripts/nox_web29_onehost_18775.py', 'scripts/nox_dispatcher_t855u.py',
    'incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site/pc/resonance.html',
    'incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site/pc/nox-chat.js',
    'incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site/nox-v135-resonance-owner-bridge.js',
    'incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site/owner-chat-ui.js',
)
# These are prior observations, not a claim that these PID roles remain valid.
# No process discovery, cmdline, environ, configuration or user data is read.
O2_PRIOR_PIDS = {'proxy':3367881, 'arbiter':3350646, 'web':3368105, 'model_supervisor':3266857}
O2_STAT_KEYS = frozenset(('anon','file','shmem','inactive_anon','active_anon','inactive_file',
    'active_file','file_dirty','file_writeback','slab_reclaimable','slab_unreclaimable',
    'sock','kernel_stack','pagetables'))
O2_FILE_LIMIT = 262144
O2_TOTAL_CODE_LIMIT = 2097152


def _o2_directory(path):
    """Open every directory component without following symlinks."""
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('scope')
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open('/', flags)
    try:
        for part in path.parts[1:]:
            child = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def _o2_read(path, limit, *, digest_only=False, deadline=None):
    """Bounded regular-file read; confirm the named inode still matches.

    No error text or source bytes are returned for a failed read. The time
    check bounds progress between reads; it cannot interrupt a blocked kernel IO.
    """
    import hashlib, stat
    path = Path(path)
    parent = file_fd = checked_parent = None
    try:
        parent = _o2_directory(path.parent)
        file_fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=parent)
        before = os.fstat(file_fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise ValueError('type_or_size')
        identity = lambda value: (value.st_dev,value.st_ino,value.st_size,value.st_mtime_ns,value.st_ctime_ns)
        digest, chunks, total = hashlib.sha256(), [], 0
        while True:
            if deadline is not None and time.monotonic() > deadline:
                raise ValueError('time')
            block = os.read(file_fd, min(16384,limit-total+1))
            if not block:
                break
            total += len(block)
            if total > limit:
                raise ValueError('growth')
            digest.update(block)
            if not digest_only:
                chunks.append(block)
        checked_parent = _o2_directory(path.parent)
        old_dir, new_dir = os.fstat(parent), os.fstat(checked_parent)
        named = os.stat(path.name, dir_fd=checked_parent, follow_symlinks=False)
        if ((old_dir.st_dev,old_dir.st_ino) != (new_dir.st_dev,new_dir.st_ino)
                or identity(before) != identity(os.fstat(file_fd)) or identity(before) != identity(named)):
            raise ValueError('changed')
        if digest_only and total != before.st_size:
            raise ValueError('changed_size')
        return {'state':'OBSERVED','bytes_read':total,'sha256':digest.hexdigest(),
                'value':None if digest_only else b''.join(chunks)}
    except (OSError,ValueError):
        return {'state':'UNKNOWN_UNSAFE_UNREADABLE_CHANGED_OR_LIMIT','bytes_read':0,'sha256':None,'value':None}
    finally:
        for fd in (file_fd,parent,checked_parent):
            if fd is not None:
                os.close(fd)


def _o2_number(raw):
    if not re.fullmatch(rb'[0-9]{1,20}\s*',raw):
        raise ValueError('counter')
    return int(raw)


def _o2_metric(raw, name):
    import math
    if name in ('memory.current','memory.max'):
        return None if name == 'memory.max' and raw.strip() == b'max' else _o2_number(raw)
    if name == 'memory.stat':
        result, seen = {}, set()
        for line in raw.splitlines():
            key, value = line.split()
            if key in seen:
                raise ValueError('duplicate_counter')
            seen.add(key)
            number = _o2_number(value)
            key = key.decode('ascii')
            if key in O2_STAT_KEYS:
                result[key] = number
        if not {'anon','file','shmem'}.issubset(result):
            raise ValueError('missing_counter')
        return result
    result = {}
    for line in raw.splitlines():
        fields = line.split()
        if not fields or fields[0] not in (b'some',b'full') or fields[0].decode() in result:
            raise ValueError('pressure')
        parts = [field.split(b'=') for field in fields[1:]]
        if len(parts) != 4 or any(len(part) != 2 for part in parts):
            raise ValueError('pressure_fields')
        pairs = dict(parts)
        if set(pairs) != {b'avg10',b'avg60',b'avg300',b'total'}:
            raise ValueError('pressure_fields')
        values = {'total':_o2_number(pairs[b'total'])}
        for key in (b'avg10',b'avg60',b'avg300'):
            value = float(pairs[key])
            if not math.isfinite(value) or not 0 <= value <= 100:
                raise ValueError('pressure_value')
            values[key.decode()] = value
        result[fields[0].decode()] = values
    if 'some' not in result or name != 'cpu.pressure' and 'full' not in result:
        raise ValueError('pressure_missing')
    return result


def _o2_pid(proc, pid):
    import hashlib
    try:
        raw = _o2_read(Path(proc)/str(pid)/'stat',8192)['value']
        prefix = str(pid).encode() + b' ('
        if raw is None or not raw.startswith(prefix):
            raise ValueError('identity')
        tail = raw[raw.rindex(b') ')+2:].split()
        ticks = _o2_number(tail[19])
        membership = _o2_read(Path(proc)/str(pid)/'cgroup',8192)['value']
        lines = [line for line in membership.splitlines() if line.startswith(b'0::')]
        if len(lines) != 1 or not re.fullmatch(rb'0::/[A-Za-z0-9_./:@-]{0,4096}',lines[0]) or b'..' in lines[0][3:].split(b'/'):
            raise ValueError('membership')
        return {'pid':pid,'start_ticks':ticks,'membership_sha256':hashlib.sha256(lines[0]).hexdigest(),
                'membership_is_namespace_root':lines[0] == b'0::/'}
    except (AttributeError,ValueError,IndexError,TypeError):
        return None


def native_mapping_readback(root=Path('/root/nox'), cgroup=Path('/sys/fs/cgroup'),
                            proc=Path('/proc'), prior_pids=None):
    """Only new mapping evidence; no HTTP, commands, model probes or writes."""
    pids = O2_PRIOR_PIDS if prior_pids is None else prior_pids
    if set(pids) - set(O2_PRIOR_PIDS) or any(type(pid) is not int or pid <= 0 for pid in pids.values()):
        raise ValueError('pid_scope')
    before = {name:_o2_pid(proc,pid) for name,pid in pids.items()}
    files, remaining, deadline = [], O2_TOTAL_CODE_LIMIT, time.monotonic()+3
    for relative in O2_CODE_PATHS:
        allowance = min(O2_FILE_LIMIT,max(0,remaining-1))
        read = (_o2_read(Path(root)/relative,allowance,digest_only=True,deadline=deadline) if remaining else
                {'state':'UNKNOWN_TOTAL_BUDGET','bytes_read':0,'sha256':None})
        # Charge the full per-file allowance after an uncertain read; a changing
        # file must not reset the aggregate budget through a failed hash.
        charged = read['bytes_read'] if read['state']=='OBSERVED' else min(allowance+1,remaining)
        remaining -= charged
        files.append({'relative_path':relative,'state':read['state'],'sha256':read['sha256'],
                      'bytes':read['bytes_read'] if read['state']=='OBSERVED' else None,
                      'serving_mapping':'UNKNOWN','executed_code_mapping':'UNKNOWN'})
    metrics = {}
    for name in ('memory.current','memory.max','memory.stat','memory.pressure','io.pressure','cpu.pressure'):
        read = _o2_read(Path(cgroup)/name,65536 if name=='memory.stat' else 8192)
        try:
            value = _o2_metric(read['value'],name)
            metrics[name] = {'state':'OBSERVED','value':value}
        except (ValueError,TypeError,AttributeError,UnicodeError):
            metrics[name] = {'state':'UNKNOWN','value':None}
    processes = []
    for name,pid in pids.items():
        after = _o2_pid(proc,pid)
        stable = before[name] is not None and before[name] == after
        processes.append({'prior_audit_role':name,'pid':pid,'state':'CONSISTENT_SNAPSHOT' if stable else 'UNKNOWN_CHANGED_OR_UNREADABLE',
                          'identity':after if stable else None,'current_role_binding':'UNKNOWN'})
    return {'schema':'NOX_NATIVE_MAPPING_READBACK_V1','read_only':True,'native_accepted':False,
            'observed_unix':round(time.time(),3),'source_pid_reference':'audit job 134219312713',
            'code_files':files,'cgroup':{'scope':'VISIBLE_MOUNT_ROOT_ONLY','process_to_mount_binding':'UNKNOWN',
                'hidden_ancestor_limits':'UNKNOWN','metrics':metrics},'processes':processes,
            'owner_activity':{'CHAT_ACTIVE':'UNKNOWN','MODE':'UNKNOWN','activity_epoch':'UNKNOWN','binding':'NOT_VERIFIED_NOT_READ'},
            'atomic_lease':False,'model_calls':0,'http_calls':0,'source_content_exported':False,'gpu_pid_namespace_mapping':'UNKNOWN',
            'budget':{'code_file_bytes':O2_FILE_LIMIT,'total_code_bytes':O2_TOTAL_CODE_LIMIT,'code_time_seconds':3},
            'limitations':['PID role is from a prior audit; consistency does not attest current service/code or prevent ABA changes.',
                          'File presence/hash does not prove WEB serving or executed-code binding.',
                          'Counters are a non-atomic visible mount-root observation; cache is not guaranteed available RAM.',
                          'No CHAT_ACTIVE/MODE/epoch binding or resource lease is established.']}


"""Embedded in the existing audit script; no operator or workflow changes."""
O2_SOURCE_PRIMITIVES = 'IiIiTWVtb3J5LW9ubHkgYXV0aGVudGljYXRlZCB0cmFuc3BvcnQgb2YgdHdvIGZpeGVkIHN5bnRoZXRpYyBRQSBhcnRpZmFjdHMuIiIiCmZyb20gX19mdXR1cmVfXyBpbXBvcnQgYW5ub3RhdGlvbnMKCmltcG9ydCBiYXNlNjQKaW1wb3J0IGhhc2hsaWIKaW1wb3J0IGpzb24KaW1wb3J0IG9zCmZyb20gcGF0aGxpYiBpbXBvcnQgUGF0aAppbXBvcnQgcmUKaW1wb3J0IHN0YXQKaW1wb3J0IHRpbWUKCmZyb20gY3J5cHRvZ3JhcGh5Lmhhem1hdC5wcmltaXRpdmVzIGltcG9ydCBoYXNoZXMsIHNlcmlhbGl6YXRpb24KZnJvbSBjcnlwdG9ncmFwaHkuaGF6bWF0LnByaW1pdGl2ZXMuYXN5bW1ldHJpYyBpbXBvcnQgcGFkZGluZywgcnNhCmZyb20gY3J5cHRvZ3JhcGh5Lmhhem1hdC5wcmltaXRpdmVzLmNpcGhlcnMuYWVhZCBpbXBvcnQgQUVTR0NNCgpGSUxFUyA9ICgKICAgIHsna2luZCc6ICdpbWFnZScsICdmaWxlbmFtZSc6ICdub3gtcWEtaW1hZ2UucG5nJywgJ2J5dGVzJzogMjkxOTI5LAogICAgICdzaGEyNTYnOiAnOTk2ZThmMWFhMTU2YzgyNzY4YWQzNDk2NTA4NDQwYmUxYTJjOTZhNDlmYjI4NTk0MzkwNGYxMmM3OTI5NWFjMicsCiAgICAgJ25hdGl2ZV9wYXRoJzogJy9yb290L25veC9tZWRpYS9vdXRwdXRzL25veC80MmQwYTY3YTI3NWQ0MTcxOWZjZjJlODc2OGYyOTc1ZC9pbWFnZV8wMDAwMV8ucG5nJ30sCiAgICB7J2tpbmQnOiAndmlkZW8nLCAnZmlsZW5hbWUnOiAnbm94LXFhLXZpZGVvLndlYm0nLCAnYnl0ZXMnOiAyOTM0OSwKICAgICAnc2hhMjU2JzogJzhmMDBlMmI5NmNiMTcwMzQyYWY4YTdjYmQ2NWQ5ZWQ5Mzg4NDljMGE3ZGQ3MTcyZDBmOWM5ZGM1NmQ4NmIxMzUnLAogICAgICduYXRpdmVfcGF0aCc6ICcvcm9vdC9ub3gvbWVkaWEvb3V0cHV0cy9ub3gvNjljODhmMzkxNGM3NzA3OWRiMGYzMWFmMzljM2IxYTIvdmlkZW9fMDAwMDFfLndlYm0nfSwKKQpBQ0NFUFRFRF9SRUNFSVBUX1NIQSA9ICdmMjI0MzUzNjI4YzFhZWY3YWM1ZmY3MGM5ZDc0YTBmNGExYjgyNTY5YmNjYjcwYWI1OWZhZjIzNGJkYmU0ZmRiJwpJTlNUQU5DRV9JRCA9IDYwNTA5NTUxCkFMR09SSVRITSA9ICdSU0E0MDk2LU9BRVAtU0hBMjU2K0EyNTZHQ00nCk9BRVBfTEFCRUwgPSBiJ05PWF9TWU5USEVUSUNfTUVESUFfUkVWSUVXX1YxJwpDSFVOS19DSEFSUyA9IDYwMDAwICAjIEpTT04gb3ZlcmhlYWQgc3RheXMgd2VsbCBiZWxvdyBhbiA4MEtCIHB1YmxpYyBsb2cgbGluZS4KTUFYX0lOUFVUID0gNzAwMDAwCk1BWF9UVEwgPSAzNjAwCgoKY2xhc3MgVHJhbnNwb3J0SG9sZChSdW50aW1lRXJyb3IpOgogICAgcGFzcwoKCmRlZiByZXF1aXJlKGNvbmRpdGlvbiwgY29kZT0nSE9MRF9NRURJQV9GSVhUVVJFX1RSQU5TUE9SVCcpOgogICAgaWYgbm90IGNvbmRpdGlvbjoKICAgICAgICByYWlzZSBUcmFuc3BvcnRIb2xkKGNvZGUpCgoKZGVmIGNhbm9uaWNhbCh2YWx1ZSk6CiAgICByZXR1cm4ganNvbi5kdW1wcyh2YWx1ZSwgc29ydF9rZXlzPVRydWUsIHNlcGFyYXRvcnM9KCcsJywgJzonKSwgYWxsb3dfbmFuPUZhbHNlKS5lbmNvZGUoKQoKCmRlZiBkaWdlc3QocmF3KToKICAgIHJldHVybiBoYXNobGliLnNoYTI1NihyYXcpLmhleGRpZ2VzdCgpCgoKZGVmIHVuaXF1ZShwYWlycyk6CiAgICB2YWx1ZSA9IHt9CiAgICBmb3Iga2V5LCBpdGVtIGluIHBhaXJzOgogICAgICAgIHJlcXVpcmUoa2V5IG5vdCBpbiB2YWx1ZSwgJ0hPTERfTUVESUFfRklYVFVSRV9EVVBMSUNBVEVfSlNPTl9LRVknKQogICAgICAgIHZhbHVlW2tleV0gPSBpdGVtCiAgICByZXR1cm4gdmFsdWUKCgpkZWYgZGVjb2RlX2pzb24ocmF3KToKICAgIHJlcXVpcmUoaXNpbnN0YW5jZShyYXcsIGJ5dGVzKSBhbmQgbGVuKHJhdykgPD0gTUFYX0lOUFVULCAnSE9MRF9NRURJQV9GSVhUVVJFX0lOUFVUX1NJWkUnKQogICAgcmV0dXJuIGpzb24ubG9hZHMocmF3LCBvYmplY3RfcGFpcnNfaG9vaz11bmlxdWUsCiAgICAgICAgICAgICAgICAgICAgICBwYXJzZV9jb25zdGFudD1sYW1iZGEgXzogKF8gZm9yIF8gaW4gKCkpLnRocm93KFRyYW5zcG9ydEhvbGQoJ0hPTERfTUVESUFfRklYVFVSRV9KU09OX05VTUJFUicpKSkKCgpkZWYgcHVibGljX2ZpbGVzKCk6CiAgICByZXR1cm4gW3trZXk6IHJvd1trZXldIGZvciBrZXkgaW4gKCdraW5kJywgJ2ZpbGVuYW1lJywgJ2J5dGVzJywgJ3NoYTI1NicpfSBmb3Igcm93IGluIEZJTEVTXQoKCmRlZiBtYW5pZmVzdCgpOgogICAgcmV0dXJuIHsnc2NoZW1hJzogJ05PWF9TWU5USEVUSUNfTUVESUFfTUFOSUZFU1RfVjEnLCAnaW5zdGFuY2VfaWQnOiBJTlNUQU5DRV9JRCwKICAgICAgICAgICAgJ2FjY2VwdGVkX3JlY2VpcHRfc2hhMjU2JzogQUNDRVBURURfUkVDRUlQVF9TSEEsICdmaWxlcyc6IHB1YmxpY19maWxlcygpfQoKCmRlZiBtYW5pZmVzdF9zaGEoKToKICAgIHJldHVybiBkaWdlc3QoY2Fub25pY2FsKG1hbmlmZXN0KCkpKQoKCmRlZiBwbGFpbihwYXRoKToKICAgIHBhdGggPSBQYXRoKHBhdGgpCiAgICByZXF1aXJlKHBhdGguaXNfYWJzb2x1dGUoKSBhbmQgJy4uJyBub3QgaW4gcGF0aC5wYXJ0cwogICAgICAgICAgICBhbmQgbm90IGFueShpdGVtLmlzX3N5bWxpbmsoKSBmb3IgaXRlbSBpbiAocGF0aCwgKnBhdGgucGFyZW50cykpLCAnSE9MRF9NRURJQV9GSVhUVVJFX1BBVEgnKQogICAgcmV0dXJuIHBhdGgKCgpkZWYgcmVhZF9yZWd1bGFyKHBhdGgsIG1heGltdW0sICosIHByaXZhdGU9RmFsc2UpOgogICAgcGF0aCA9IHBsYWluKHBhdGgpCiAgICBmZCA9IG9zLm9wZW4ocGF0aCwgb3MuT19SRE9OTFkgfCBvcy5PX05PRk9MTE9XIHwgb3MuT19OT05CTE9DSykKICAgIHRyeToKICAgICAgICBiZWZvcmUgPSBvcy5mc3RhdChmZCkKICAgICAgICByZXF1aXJlKHN0YXQuU19JU1JFRyhiZWZvcmUuc3RfbW9kZSkgYW5kIGJlZm9yZS5zdF91aWQgPT0gb3MuZ2V0ZXVpZCgpCiAgICAgICAgICAgICAgICBhbmQgbm90IGJlZm9yZS5zdF9tb2RlICYgKDBvMDc3IGlmIHByaXZhdGUgZWxzZSAwbzAyMikKICAgICAgICAgICAgICAgIGFuZCBiZWZvcmUuc3RfbmxpbmsgPT0gMSBhbmQgMCA8PSBiZWZvcmUuc3Rfc2l6ZSA8PSBtYXhpbXVtLCAnSE9MRF9NRURJQV9GSVhUVVJFX0ZJTEVfU0NPUEUnKQogICAgICAgIHBhcnRzID0gW107IGNvdW50ID0gMAogICAgICAgIHdoaWxlIFRydWU6CiAgICAgICAgICAgIGJsb2NrID0gb3MucmVhZChmZCwgbWluKDY1NTM2LCBtYXhpbXVtKzEtY291bnQpKQogICAgICAgICAgICBpZiBub3QgYmxvY2s6CiAgICAgICAgICAgICAgICBicmVhawogICAgICAgICAgICBjb3VudCArPSBsZW4oYmxvY2spOyByZXF1aXJlKGNvdW50IDw9IG1heGltdW0sICdIT0xEX01FRElBX0ZJWFRVUkVfRklMRV9TSVpFJyk7IHBhcnRzLmFwcGVuZChibG9jaykKICAgICAgICBhZnRlciA9IG9zLmZzdGF0KGZkKTsgbmFtZWQgPSBwYXRoLnN0YXQoZm9sbG93X3N5bWxpbmtzPUZhbHNlKQogICAgICAgIGZvciBrZXkgaW4gKCdzdF9kZXYnLCAnc3RfaW5vJywgJ3N0X3NpemUnLCAnc3RfbXRpbWVfbnMnLCAnc3RfY3RpbWVfbnMnKToKICAgICAgICAgICAgcmVxdWlyZShnZXRhdHRyKGJlZm9yZSwga2V5KSA9PSBnZXRhdHRyKGFmdGVyLCBrZXkpID09IGdldGF0dHIobmFtZWQsIGtleSksICdIT0xEX01FRElBX0ZJWFRVUkVfRklMRV9DSEFOR0VEJykKICAgICAgICByZXF1aXJlKGNvdW50ID09IGJlZm9yZS5zdF9zaXplLCAnSE9MRF9NRURJQV9GSVhUVVJFX0ZJTEVfU0laRScpCiAgICAgICAgcmV0dXJuIGInJy5qb2luKHBhcnRzKQogICAgZmluYWxseToKICAgICAgICBvcy5jbG9zZShmZCkKCgpkZWYgYjY0KHJhdyk6CiAgICByZXR1cm4gYmFzZTY0LmI2NGVuY29kZShyYXcpLmRlY29kZSgnYXNjaWknKQoKCmRlZiB1bmI2NCh2YWx1ZSwgbWF4aW11bSk6CiAgICByZXF1aXJlKGlzaW5zdGFuY2UodmFsdWUsIHN0cikgYW5kIGxlbih2YWx1ZSkgPD0gKChtYXhpbXVtKzIpLy8zKSo0LCAnSE9MRF9NRURJQV9GSVhUVVJFX0JBU0U2NF9TSVpFJykKICAgIHJhdyA9IGJhc2U2NC5iNjRkZWNvZGUodmFsdWUsIHZhbGlkYXRlPVRydWUpCiAgICByZXF1aXJlKGxlbihyYXcpIDw9IG1heGltdW0gYW5kIGI2NChyYXcpID09IHZhbHVlLCAnSE9MRF9NRURJQV9GSVhUVVJFX0JBU0U2NCcpCiAgICByZXR1cm4gcmF3CgoKZGVmIHB1YmxpY19rZXlfbWV0YWRhdGEodmFsdWUsICosIG5vdz1Ob25lKToKICAgIG5vdyA9IGludCh0aW1lLnRpbWUoKSkgaWYgbm93IGlzIE5vbmUgZWxzZSBub3cKICAgIHJlcXVpcmUoaXNpbnN0YW5jZSh2YWx1ZSwgZGljdCkgYW5kIHNldCh2YWx1ZSkgPT0geydzY2hlbWEnLCAna2V5X2lkJywgJ3B1YmxpY19rZXlfcGVtJywgJ3RyYW5zZmVyX2lkJywKICAgICAgICAgICAgJ2NyZWF0ZWRfYXQnLCAnZXhwaXJlc19hdCcsICdtYW5pZmVzdF9zaGEyNTYnfSwgJ0hPTERfTUVESUFfRklYVFVSRV9LRVlfTUVUQURBVEEnKQogICAgcmVxdWlyZSh2YWx1ZVsnc2NoZW1hJ10gPT0gJ05PWF9NRURJQV9SRVZJRVdfUFVCTElDX0tFWV9WMScgYW5kIHZhbHVlWydtYW5pZmVzdF9zaGEyNTYnXSA9PSBtYW5pZmVzdF9zaGEoKQogICAgICAgICAgICBhbmQgaXNpbnN0YW5jZSh2YWx1ZVsndHJhbnNmZXJfaWQnXSwgc3RyKSBhbmQgcmUuZnVsbG1hdGNoKCdbYS1mMC05XXszMn0nLCB2YWx1ZVsndHJhbnNmZXJfaWQnXSkKICAgICAgICAgICAgYW5kIHR5cGUodmFsdWVbJ2NyZWF0ZWRfYXQnXSkgaXMgaW50IGFuZCB0eXBlKHZhbHVlWydleHBpcmVzX2F0J10pIGlzIGludAogICAgICAgICAgICBhbmQgMCA8IHZhbHVlWydleHBpcmVzX2F0J10tdmFsdWVbJ2NyZWF0ZWRfYXQnXSA8PSBNQVhfVFRMCiAgICAgICAgICAgIGFuZCB2YWx1ZVsnY3JlYXRlZF9hdCddLTUgPD0gbm93IDwgdmFsdWVbJ2V4cGlyZXNfYXQnXSwgJ0hPTERfTUVESUFfRklYVFVSRV9LRVlfQ09OVEVYVCcpCiAgICBwZW0gPSB2YWx1ZVsncHVibGljX2tleV9wZW0nXQogICAgcmVxdWlyZShpc2luc3RhbmNlKHBlbSwgc3RyKSBhbmQgcGVtLnN0YXJ0c3dpdGgoJy0tLS0tQkVHSU4gUFVCTElDIEtFWS0tLS0tXG4nKSBhbmQgbGVuKHBlbSkgPD0gMTIwMCwKICAgICAgICAgICAgJ0hPTERfTUVESUFfRklYVFVSRV9QVUJMSUNfS0VZJykKICAgIGtleSA9IHNlcmlhbGl6YXRpb24ubG9hZF9wZW1fcHVibGljX2tleShwZW0uZW5jb2RlKCdhc2NpaScpKQogICAgcmVxdWlyZShpc2luc3RhbmNlKGtleSwgcnNhLlJTQVB1YmxpY0tleSkgYW5kIGtleS5rZXlfc2l6ZSA9PSA0MDk2IGFuZCBrZXkucHVibGljX251bWJlcnMoKS5lID09IDY1NTM3LAogICAgICAgICAgICAnSE9MRF9NRURJQV9GSVhUVVJFX1BVQkxJQ19LRVknKQogICAgZGVyID0ga2V5LnB1YmxpY19ieXRlcyhzZXJpYWxpemF0aW9uLkVuY29kaW5nLkRFUiwgc2VyaWFsaXphdGlvbi5QdWJsaWNGb3JtYXQuU3ViamVjdFB1YmxpY0tleUluZm8pCiAgICByZXF1aXJlKHZhbHVlWydrZXlfaWQnXSA9PSBkaWdlc3QoZGVyKSwgJ0hPTERfTUVESUFfRklYVFVSRV9LRVlfSUQnKQogICAgcmV0dXJuIGtleQoKCmRlZiBvd25lcl9jb250ZXh0KHJlcXVlc3QsIHNvdXJjZSk6CiAgICByZXF1aXJlKGlzaW5zdGFuY2UocmVxdWVzdCwgc3RyKSBhbmQgcmUuZnVsbG1hdGNoKCdbMC05XXsxLDI0fScsIHJlcXVlc3QpCiAgICAgICAgICAgIGFuZCBpc2luc3RhbmNlKHNvdXJjZSwgc3RyKSBhbmQgcmUuZnVsbG1hdGNoKCdbYS1mMC05XXs0MH0nLCBzb3VyY2UpLCAnSE9MRF9NRURJQV9GSVhUVVJFX09XTkVSX0NPTlRFWFQnKQogICAgcmV0dXJuIHsncmVxdWVzdCc6IHJlcXVlc3QsICdzb3VyY2Vfc2hhJzogc291cmNlfQoKCmRlZiByZWFkX25hdGl2ZV9maWxlcygpOgogICAgcmVzdWx0ID0gW10KICAgIGZvciByb3cgaW4gRklMRVM6CiAgICAgICAgcmF3ID0gcmVhZF9yZWd1bGFyKHJvd1snbmF0aXZlX3BhdGgnXSwgcm93WydieXRlcyddKQogICAgICAgIHJlcXVpcmUobGVuKHJhdykgPT0gcm93WydieXRlcyddIGFuZCBkaWdlc3QocmF3KSA9PSByb3dbJ3NoYTI1NiddLCAnSE9MRF9NRURJQV9GSVhUVVJFX05BVElWRV9TSEEnKQogICAgICAgIHJlc3VsdC5hcHBlbmQocmF3KQogICAgcmV0dXJuIHJlc3VsdAoKCmRlZiBzZWFsKHB1YmxpY19tZXRhZGF0YSwgcmVxdWVzdCwgc291cmNlKToKICAgICIiIk5hdGl2ZSBlbnRyeTogb25seSB0aGUgdHdvIGltbXV0YWJsZSBhcHByb3ZlZCBwYXRocyBtYXkgYmUgcmVhZC4iIiIKICAgIHB1YmxpYyA9IHB1YmxpY19rZXlfbWV0YWRhdGEocHVibGljX21ldGFkYXRhKQogICAgY29udGV4dCA9IG93bmVyX2NvbnRleHQocmVxdWVzdCwgc291cmNlKQogICAgcmF3ID0gYicnLmpvaW4ocmVhZF9uYXRpdmVfZmlsZXMoKSkKICAgIGNpcGhlcl9ieXRlcyA9IGxlbihyYXcpKzE2CiAgICBjaXBoZXJfY2hhcnMgPSAoKGNpcGhlcl9ieXRlcysyKS8vMykqNAogICAgYWFkID0geydzY2hlbWEnOiAnTk9YX01FRElBX1JFVklFV19BQURfVjEnLCAnYWxnb3JpdGhtJzogQUxHT1JJVEhNLCAnbWFuaWZlc3QnOiBtYW5pZmVzdCgpLAogICAgICAgICAgICdtYW5pZmVzdF9zaGEyNTYnOiBtYW5pZmVzdF9zaGEoKSwgJ2tleV9pZCc6IHB1YmxpY19tZXRhZGF0YVsna2V5X2lkJ10sCiAgICAgICAgICAgJ3RyYW5zZmVyX2lkJzogcHVibGljX21ldGFkYXRhWyd0cmFuc2Zlcl9pZCddLCAnY3JlYXRlZF9hdCc6IGludCh0aW1lLnRpbWUoKSksCiAgICAgICAgICAgJ2V4cGlyZXNfYXQnOiBwdWJsaWNfbWV0YWRhdGFbJ2V4cGlyZXNfYXQnXSwgJ2NvbnRleHQnOiBjb250ZXh0LCAncGxhaW50ZXh0X2J5dGVzJzogbGVuKHJhdyksCiAgICAgICAgICAgJ2NodW5rX2NoYXJzJzogQ0hVTktfQ0hBUlMsICdjaHVua19jb3VudCc6IChjaXBoZXJfY2hhcnMrQ0hVTktfQ0hBUlMtMSkvL0NIVU5LX0NIQVJTLAogICAgICAgICAgICdjaXBoZXJ0ZXh0X2J5dGVzJzogY2lwaGVyX2J5dGVzfQogICAgYWVzID0gQUVTR0NNLmdlbmVyYXRlX2tleShiaXRfbGVuZ3RoPTI1Nik7IG5vbmNlID0gb3MudXJhbmRvbSgxMikKICAgIHdyYXBwZWQgPSBwdWJsaWMuZW5jcnlwdChhZXMsIHBhZGRpbmcuT0FFUChtZ2Y9cGFkZGluZy5NR0YxKGhhc2hlcy5TSEEyNTYoKSksCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICBhbGdvcml0aG09aGFzaGVzLlNIQTI1NigpLCBsYWJlbD1PQUVQX0xBQkVMKSkKICAgIGNpcGhlciA9IEFFU0dDTShhZXMpLmVuY3J5cHQobm9uY2UsIHJhdywgY2Fub25pY2FsKGFhZCkpCiAgICBlbnZlbG9wZSA9IHsnc2NoZW1hJzogJ05PWF9NRURJQV9SRVZJRVdfRU5WRUxPUEVfVjEnLCAnYWFkJzogYWFkLCAnd3JhcHBlZF9rZXknOiBiNjQod3JhcHBlZCksCiAgICAgICAgICAgICAgICAnbm9uY2UnOiBiNjQobm9uY2UpLCAnY2lwaGVydGV4dCc6IGI2NChjaXBoZXIpLCAnY2lwaGVydGV4dF9ieXRlcyc6IGxlbihjaXBoZXIpLAogICAgICAgICAgICAgICAgJ2NpcGhlcnRleHRfc2hhMjU2JzogZGlnZXN0KGNpcGhlcil9CiAgICBlbmNvZGVkID0gZW52ZWxvcGVbJ2NpcGhlcnRleHQnXQogICAgY2h1bmtzID0gW2VuY29kZWRbaTppK0NIVU5LX0NIQVJTXSBmb3IgaSBpbiByYW5nZSgwLCBsZW4oZW5jb2RlZCksIENIVU5LX0NIQVJTKV0KICAgIHNoYSA9IGRpZ2VzdChjYW5vbmljYWwoZW52ZWxvcGUpKQogICAgaGVhZGVyID0geydzY2hlbWEnOiAnTk9YX01FRElBX1JFVklFV19UUkFOU0ZFUl9WMScsICdlbnZlbG9wZV9zaGEyNTYnOiBzaGEsCiAgICAgICAgICAgICAgJ2NodW5rcyc6IGxlbihjaHVua3MpLCAnY2h1bmtfY2hhcnMnOiBDSFVOS19DSEFSUywgJ2NpcGhlcnRleHRfY2hhcnMnOiBsZW4oZW5jb2RlZCksCiAgICAgICAgICAgICAgJ21ldGFkYXRhJzoge2tleTogdmFsdWUgZm9yIGtleSwgdmFsdWUgaW4gZW52ZWxvcGUuaXRlbXMoKSBpZiBrZXkgIT0gJ2NpcGhlcnRleHQnfX0KICAgIHJvd3MgPSBbeydraW5kJzogJ21lZGlhX2ZpeHR1cmVfY2lwaGVydGV4dF9oZWFkZXInLCAnZGF0YSc6IGhlYWRlcn1dCiAgICByb3dzICs9IFt7J2tpbmQnOiAnbWVkaWFfZml4dHVyZV9jaXBoZXJ0ZXh0X2NodW5rJywgJ2RhdGEnOiB7J2VudmVsb3BlX3NoYTI1Nic6IHNoYSwgJ2luZGV4JzogaSwKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgJ2NodW5rcyc6IGxlbihjaHVua3MpLCAnY2lwaGVydGV4dCc6IGNodW5rfX0KICAgICAgICAgICAgIGZvciBpLCBjaHVuayBpbiBlbnVtZXJhdGUoY2h1bmtzKV0KICAgIHJlcXVpcmUoYWxsKGxlbihjYW5vbmljYWwocm93KSkgPCA3OTAwMCBmb3Igcm93IGluIHJvd3MpLCAnSE9MRF9NRURJQV9GSVhUVVJFX0xPR19MSU5FX1NJWkUnKQogICAgcmV0dXJuIHJvd3MKCgpkZWYgYXNzZW1ibGUocm93cyk6CiAgICByZXF1aXJlKGlzaW5zdGFuY2Uocm93cywgbGlzdCkgYW5kIDIgPD0gbGVuKHJvd3MpIDw9IDIwLCAnSE9MRF9NRURJQV9GSVhUVVJFX0NIVU5LX0NPVU5UJykKICAgIGhlYWRlcnMgPSBbcm93WydkYXRhJ10gZm9yIHJvdyBpbiByb3dzIGlmIGlzaW5zdGFuY2Uocm93LCBkaWN0KSBhbmQgc2V0KHJvdykgPT0geydraW5kJywgJ2RhdGEnfQogICAgICAgICAgICAgICBhbmQgcm93WydraW5kJ10gPT0gJ21lZGlhX2ZpeHR1cmVfY2lwaGVydGV4dF9oZWFkZXInXQogICAgcmVxdWlyZShsZW4oaGVhZGVycykgPT0gMSwgJ0hPTERfTUVESUFfRklYVFVSRV9TSU5HTEVfSEVBREVSJykKICAgIGhlYWRlciA9IGhlYWRlcnNbMF0KICAgIHJlcXVpcmUoaXNpbnN0YW5jZShoZWFkZXIsIGRpY3QpIGFuZCBzZXQoaGVhZGVyKSA9PSB7J3NjaGVtYScsICdlbnZlbG9wZV9zaGEyNTYnLCAnY2h1bmtzJywgJ2NodW5rX2NoYXJzJywKICAgICAgICAgICAgJ2NpcGhlcnRleHRfY2hhcnMnLCAnbWV0YWRhdGEnfSBhbmQgaGVhZGVyWydzY2hlbWEnXSA9PSAnTk9YX01FRElBX1JFVklFV19UUkFOU0ZFUl9WMScKICAgICAgICAgICAgYW5kIHR5cGUoaGVhZGVyWydjaHVua3MnXSkgaXMgaW50IGFuZCAxIDw9IGhlYWRlclsnY2h1bmtzJ10gPD0gMTYKICAgICAgICAgICAgYW5kIGhlYWRlclsnY2h1bmtfY2hhcnMnXSA9PSBDSFVOS19DSEFSUyBhbmQgdHlwZShoZWFkZXJbJ2NpcGhlcnRleHRfY2hhcnMnXSkgaXMgaW50CiAgICAgICAgICAgIGFuZCAwIDwgaGVhZGVyWydjaXBoZXJ0ZXh0X2NoYXJzJ10gPD0gTUFYX0lOUFVUIGFuZCBsZW4ocm93cykgPT0gaGVhZGVyWydjaHVua3MnXSsxLAogICAgICAgICAgICAnSE9MRF9NRURJQV9GSVhUVVJFX0hFQURFUicpCiAgICBjaHVua3MgPSB7fQogICAgZm9yIHJvdyBpbiByb3dzOgogICAgICAgIHJlcXVpcmUoaXNpbnN0YW5jZShyb3csIGRpY3QpIGFuZCBzZXQocm93KSA9PSB7J2tpbmQnLCAnZGF0YSd9LCAnSE9MRF9NRURJQV9GSVhUVVJFX0NIVU5LX1NDSEVNQScpCiAgICAgICAgaWYgcm93WydraW5kJ10gPT0gJ21lZGlhX2ZpeHR1cmVfY2lwaGVydGV4dF9oZWFkZXInOgogICAgICAgICAgICBjb250aW51ZQogICAgICAgIHBhcnQgPSByb3dbJ2RhdGEnXQogICAgICAgIHJlcXVpcmUocm93WydraW5kJ10gPT0gJ21lZGlhX2ZpeHR1cmVfY2lwaGVydGV4dF9jaHVuaycgYW5kIGlzaW5zdGFuY2UocGFydCwgZGljdCkKICAgICAgICAgICAgICAgIGFuZCBzZXQocGFydCkgPT0geydlbnZlbG9wZV9zaGEyNTYnLCAnaW5kZXgnLCAnY2h1bmtzJywgJ2NpcGhlcnRleHQnfQogICAgICAgICAgICAgICAgYW5kIHBhcnRbJ2VudmVsb3BlX3NoYTI1NiddID09IGhlYWRlclsnZW52ZWxvcGVfc2hhMjU2J10gYW5kIHBhcnRbJ2NodW5rcyddID09IGhlYWRlclsnY2h1bmtzJ10KICAgICAgICAgICAgICAgIGFuZCB0eXBlKHBhcnRbJ2luZGV4J10pIGlzIGludCBhbmQgMCA8PSBwYXJ0WydpbmRleCddIDwgaGVhZGVyWydjaHVua3MnXSBhbmQgcGFydFsnaW5kZXgnXSBub3QgaW4gY2h1bmtzCiAgICAgICAgICAgICAgICBhbmQgaXNpbnN0YW5jZShwYXJ0WydjaXBoZXJ0ZXh0J10sIHN0ciksICdIT0xEX01FRElBX0ZJWFRVUkVfQ0hVTktfU0NIRU1BJykKICAgICAgICBleHBlY3RlZCA9IENIVU5LX0NIQVJTIGlmIHBhcnRbJ2luZGV4J10gPCBoZWFkZXJbJ2NodW5rcyddLTEgZWxzZSBoZWFkZXJbJ2NpcGhlcnRleHRfY2hhcnMnXS1DSFVOS19DSEFSUyooaGVhZGVyWydjaHVua3MnXS0xKQogICAgICAgIHJlcXVpcmUoMCA8IGV4cGVjdGVkIDw9IENIVU5LX0NIQVJTIGFuZCBsZW4ocGFydFsnY2lwaGVydGV4dCddKSA9PSBleHBlY3RlZCwgJ0hPTERfTUVESUFfRklYVFVSRV9DSFVOS19TSVpFJykKICAgICAgICBjaHVua3NbcGFydFsnaW5kZXgnXV0gPSBwYXJ0WydjaXBoZXJ0ZXh0J10KICAgIG1ldGFkYXRhID0gaGVhZGVyWydtZXRhZGF0YSddCiAgICByZXF1aXJlKGlzaW5zdGFuY2UobWV0YWRhdGEsIGRpY3QpIGFuZCBzZXQobWV0YWRhdGEpID09IHsnc2NoZW1hJywgJ2FhZCcsICd3cmFwcGVkX2tleScsICdub25jZScsCiAgICAgICAgICAgICdjaXBoZXJ0ZXh0X2J5dGVzJywgJ2NpcGhlcnRleHRfc2hhMjU2J30sICdIT0xEX01FRElBX0ZJWFRVUkVfRU5WRUxPUEVfU0NIRU1BJykKICAgIGVudmVsb3BlID0gZGljdChtZXRhZGF0YSwgY2lwaGVydGV4dD0nJy5qb2luKGNodW5rc1tpXSBmb3IgaSBpbiByYW5nZShoZWFkZXJbJ2NodW5rcyddKSkpCiAgICByZXF1aXJlKGRpZ2VzdChjYW5vbmljYWwoZW52ZWxvcGUpKSA9PSBoZWFkZXJbJ2VudmVsb3BlX3NoYTI1NiddLCAnSE9MRF9NRURJQV9GSVhUVVJFX0VOVkVMT1BFX1NIQScpCiAgICByZXR1cm4gZW52ZWxvcGUsIGhlYWRlclsnZW52ZWxvcGVfc2hhMjU2J10KCgpkZWYgZGVjcnlwdChyb3dzLCBwcml2YXRlX3BlbSwgcHVibGljX21ldGFkYXRhLCByZXF1ZXN0LCBzb3VyY2UpOgogICAgcHVibGljX2tleV9tZXRhZGF0YShwdWJsaWNfbWV0YWRhdGEpCiAgICBjb250ZXh0ID0gb3duZXJfY29udGV4dChyZXF1ZXN0LCBzb3VyY2UpCiAgICBlbnZlbG9wZSwgb3V0ZXJfc2hhID0gYXNzZW1ibGUocm93cykKICAgIGFhZCA9IGVudmVsb3BlWydhYWQnXQogICAgdG90YWwgPSBzdW0ocm93WydieXRlcyddIGZvciByb3cgaW4gRklMRVMpCiAgICBleHBlY3RlZF9jaHVua3MgPSAoKCgodG90YWwrMTYrMikvLzMpKjQpK0NIVU5LX0NIQVJTLTEpLy9DSFVOS19DSEFSUwogICAgcmVxdWlyZShlbnZlbG9wZVsnc2NoZW1hJ10gPT0gJ05PWF9NRURJQV9SRVZJRVdfRU5WRUxPUEVfVjEnIGFuZCBpc2luc3RhbmNlKGFhZCwgZGljdCkKICAgICAgICAgICAgYW5kIHNldChhYWQpID09IHsnc2NoZW1hJywgJ2FsZ29yaXRobScsICdtYW5pZmVzdCcsICdtYW5pZmVzdF9zaGEyNTYnLCAna2V5X2lkJywgJ3RyYW5zZmVyX2lkJywKICAgICAgICAgICAgICAgICAgICAgICAgICAgICdjcmVhdGVkX2F0JywgJ2V4cGlyZXNfYXQnLCAnY29udGV4dCcsICdwbGFpbnRleHRfYnl0ZXMnLAogICAgICAgICAgICAgICAgICAgICAgICAgICAgJ2NodW5rX2NoYXJzJywgJ2NodW5rX2NvdW50JywgJ2NpcGhlcnRleHRfYnl0ZXMnfQogICAgICAgICAgICBhbmQgYWFkWydzY2hlbWEnXSA9PSAnTk9YX01FRElBX1JFVklFV19BQURfVjEnIGFuZCBhYWRbJ2FsZ29yaXRobSddID09IEFMR09SSVRITQogICAgICAgICAgICBhbmQgYWFkWydtYW5pZmVzdCddID09IG1hbmlmZXN0KCkgYW5kIGFhZFsnbWFuaWZlc3Rfc2hhMjU2J10gPT0gbWFuaWZlc3Rfc2hhKCkKICAgICAgICAgICAgYW5kIGFhZFsna2V5X2lkJ10gPT0gcHVibGljX21ldGFkYXRhWydrZXlfaWQnXSBhbmQgYWFkWyd0cmFuc2Zlcl9pZCddID09IHB1YmxpY19tZXRhZGF0YVsndHJhbnNmZXJfaWQnXQogICAgICAgICAgICBhbmQgYWFkWydleHBpcmVzX2F0J10gPT0gcHVibGljX21ldGFkYXRhWydleHBpcmVzX2F0J10gYW5kIGFhZFsnY29udGV4dCddID09IGNvbnRleHQKICAgICAgICAgICAgYW5kIHR5cGUoYWFkWydjcmVhdGVkX2F0J10pIGlzIGludCBhbmQgcHVibGljX21ldGFkYXRhWydjcmVhdGVkX2F0J10tNSA8PSBhYWRbJ2NyZWF0ZWRfYXQnXSA8PSBpbnQodGltZS50aW1lKCkpKzUKICAgICAgICAgICAgYW5kIGFhZFsnY3JlYXRlZF9hdCddIDwgYWFkWydleHBpcmVzX2F0J10gYW5kIGFhZFsncGxhaW50ZXh0X2J5dGVzJ10gPT0gdG90YWwKICAgICAgICAgICAgYW5kIGFhZFsnY2h1bmtfY2hhcnMnXSA9PSBDSFVOS19DSEFSUyBhbmQgYWFkWydjaHVua19jb3VudCddID09IGV4cGVjdGVkX2NodW5rcwogICAgICAgICAgICBhbmQgYWFkWydjaXBoZXJ0ZXh0X2J5dGVzJ10gPT0gdG90YWwrMTYKICAgICAgICAgICAgYW5kIGVudmVsb3BlWydjaXBoZXJ0ZXh0X2J5dGVzJ10gPT0gdG90YWwrMTYsICdIT0xEX01FRElBX0ZJWFRVUkVfQUFEJykKICAgIHByaXZhdGUgPSBzZXJpYWxpemF0aW9uLmxvYWRfcGVtX3ByaXZhdGVfa2V5KHByaXZhdGVfcGVtLCBwYXNzd29yZD1Ob25lKQogICAgcmVxdWlyZShpc2luc3RhbmNlKHByaXZhdGUsIHJzYS5SU0FQcml2YXRlS2V5KSBhbmQgcHJpdmF0ZS5rZXlfc2l6ZSA9PSA0MDk2LCAnSE9MRF9NRURJQV9GSVhUVVJFX1BSSVZBVEVfS0VZJykKICAgIGRlciA9IHByaXZhdGUucHVibGljX2tleSgpLnB1YmxpY19ieXRlcyhzZXJpYWxpemF0aW9uLkVuY29kaW5nLkRFUiwgc2VyaWFsaXphdGlvbi5QdWJsaWNGb3JtYXQuU3ViamVjdFB1YmxpY0tleUluZm8pCiAgICByZXF1aXJlKGRpZ2VzdChkZXIpID09IHB1YmxpY19tZXRhZGF0YVsna2V5X2lkJ10sICdIT0xEX01FRElBX0ZJWFRVUkVfUFJJVkFURV9LRVknKQogICAgY2lwaGVyID0gdW5iNjQoZW52ZWxvcGVbJ2NpcGhlcnRleHQnXSwgdG90YWwrMTYpCiAgICByZXF1aXJlKGxlbihjaXBoZXIpID09IHRvdGFsKzE2IGFuZCBkaWdlc3QoY2lwaGVyKSA9PSBlbnZlbG9wZVsnY2lwaGVydGV4dF9zaGEyNTYnXSwgJ0hPTERfTUVESUFfRklYVFVSRV9DSVBIRVJURVhUX1NIQScpCiAgICB3cmFwcGVkID0gdW5iNjQoZW52ZWxvcGVbJ3dyYXBwZWRfa2V5J10sIDUxMik7IG5vbmNlID0gdW5iNjQoZW52ZWxvcGVbJ25vbmNlJ10sIDEyKQogICAgcmVxdWlyZShsZW4od3JhcHBlZCkgPT0gNTEyIGFuZCBsZW4obm9uY2UpID09IDEyLCAnSE9MRF9NRURJQV9GSVhUVVJFX0NSWVBUT19TSVpFJykKICAgIGFlcyA9IHByaXZhdGUuZGVjcnlwdCh3cmFwcGVkLCBwYWRkaW5nLk9BRVAobWdmPXBhZGRpbmcuTUdGMShoYXNoZXMuU0hBMjU2KCkpLAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgYWxnb3JpdGhtPWhhc2hlcy5TSEEyNTYoKSwgbGFiZWw9T0FFUF9MQUJFTCkpCiAgICByZXF1aXJlKGxlbihhZXMpID09IDMyLCAnSE9MRF9NRURJQV9GSVhUVVJFX0NSWVBUT19LRVlfU0laRScpCiAgICByYXcgPSBBRVNHQ00oYWVzKS5kZWNyeXB0KG5vbmNlLCBjaXBoZXIsIGNhbm9uaWNhbChhYWQpKQogICAgcmVxdWlyZShsZW4ocmF3KSA9PSB0b3RhbCwgJ0hPTERfTUVESUFfRklYVFVSRV9QTEFJTlRFWFRfU0laRScpCiAgICBvZmZzZXQgPSAwOyBmaWxlcyA9IFtdCiAgICBmb3Igcm93IGluIEZJTEVTOgogICAgICAgIGl0ZW0gPSByYXdbb2Zmc2V0Om9mZnNldCtyb3dbJ2J5dGVzJ11dOyBvZmZzZXQgKz0gcm93WydieXRlcyddCiAgICAgICAgcmVxdWlyZShkaWdlc3QoaXRlbSkgPT0gcm93WydzaGEyNTYnXSwgJ0hPTERfTUVESUFfRklYVFVSRV9SRUNPVkVSRURfU0hBJykKICAgICAgICBmaWxlcy5hcHBlbmQoKHJvd1snZmlsZW5hbWUnXSwgaXRlbSkpCiAgICByZXR1cm4gZmlsZXMsIHsnc2NoZW1hJzogJ05PWF9NRURJQV9SRVZJRVdfTE9DQUxfUkVDRUlQVF9WMScsICdlbnZlbG9wZV9zaGEyNTYnOiBvdXRlcl9zaGEsCiAgICAgICAgICAgICAgICAgICAnbWFuaWZlc3Rfc2hhMjU2JzogbWFuaWZlc3Rfc2hhKCksICdrZXlfaWQnOiBwdWJsaWNfbWV0YWRhdGFbJ2tleV9pZCddLAogICAgICAgICAgICAgICAgICAgJ2NvbnRleHQnOiBjb250ZXh0LCAnZmlsZXMnOiBwdWJsaWNfZmlsZXMoKSwgJ3Zpc3VhbF9yZXZpZXdfY29tcGxldGVkJzogRmFsc2V9Cg=='
O2_SOURCE_PRIMITIVES_SHA = '5208f16465410140ab38da1c1e44a0711667bd34e3a4fc5f17237df11693230f'
O2_SOURCE_TRANSPORT = 'IiIiT25lLXVzZSBhdXRoZW50aWNhdGVkIHJlYWRiYWNrIG9mIGZpeGVkIHNvdXJjZSBmaWxlczsgbm8gbmF0aXZlIHdyaXRlcy4KCkNyeXB0byBwcmltaXRpdmVzIGFuZCBlbnZlbG9wZSBjb25zdHJ1Y3Rpb24gZm9sbG93IHRoZSBleGlzdGluZyByZXZpZXdlZApvd25lcl9tZWRpYV9maXh0dXJlX3RyYW5zcG9ydC4gU291cmNlIGJ5dGVzIG5ldmVyIGxlYXZlIGFuIGVuY3J5cHRlZCBlbnZlbG9wZS4KTm8gY29uZmlndXJhdGlvbiwgc3RhdGUsIGVudmlyb25tZW50IGR1bXAsIGhpc3Rvcnkgb3IgdXNlciBkYXRhIGlzIHNlbGVjdGVkLgoiIiIKZnJvbSBfX2Z1dHVyZV9fIGltcG9ydCBhbm5vdGF0aW9ucwppbXBvcnQgaGFzaGxpYgppbXBvcnQganNvbgppbXBvcnQgb3MKZnJvbSBwYXRobGliIGltcG9ydCBQYXRoCmltcG9ydCByZQppbXBvcnQgdGltZQppbXBvcnQgb3duZXJfbWVkaWFfZml4dHVyZV90cmFuc3BvcnQgYXMgcHJpbWl0aXZlcwoKRklMRVMgPSAoeydyZWxhdGl2ZV9wYXRoJzogJ3NjcmlwdHMvY29tbW9uLnB5JywgJ2J5dGVzJzogTm9uZSwgJ3NoYTI1Nic6IE5vbmV9LCB7J3JlbGF0aXZlX3BhdGgnOiAnaW5jb21pbmdfdDgwMHUvdjI5XzMvTk9YX0hFTElPTl9XRUJfVjI5XzNfRlJPWkVOXzIwMjYxMTEzL3NpdGUvcGMvdjI0L25veC12MjQtY2hhdC5qcycsICdieXRlcyc6IE5vbmUsICdzaGEyNTYnOiBOb25lfSkKRklMRV9MSU1JVCA9IDI2MjE0NApUT1RBTF9MSU1JVCA9IDIwOTcxNTIKQ0hVTktfQ0hBUlMgPSA2MDAwMApNQVhfQ0hVTktTID0gNDcKTUFYX1RUTCA9IDM2MDAKQUxHT1JJVEhNID0gJ1JTQTQwOTYtT0FFUC1TSEEyNTYrQTI1NkdDTScKT0FFUF9MQUJFTCA9IGInTk9YX0ZJWEVEX1NPVVJDRV9SRUFEQkFDS19WMScKU1RBVEVTID0gZnJvemVuc2V0KCgnT0JTRVJWRUQnLCAnVU5LTk9XTl9VTlNBRkVfVU5SRUFEQUJMRV9DSEFOR0VEX09SX0xJTUlUJywKICAgICAgICAgICAgICAgICAgICAnVU5LTk9XTl9UT1RBTF9CVURHRVQnLCAnVU5LTk9XTl9QSU5fTUlTTUFUQ0gnKSkKQ09ORklHX1BBVEggPSAnY29uZmlnL293bmVyX25hdGl2ZV9zdWJhZ2VudHMuanNvbicKUkVHSVNUUllfUEFUSCA9ICdzdGF0ZS9wcmlvcml0eS9wYXVzZWRfa25vd2xlZGdlX3BpZHMuanNvbicKUE9MSUNZX1BBVEggPSAnL3Jvb3Qvbm94L3N0YXRlL2Rpc3BhdGNoZXIvcG9saWNpZXMvTk9YX1dFQl9XRUlHSFRTX1YwNi5tZCcKTUVUQURBVEFfTElNSVRTID0gKChDT05GSUdfUEFUSCwgMjYyMTQ0KSwgKFJFR0lTVFJZX1BBVEgsIDY1NTM2KSkKTUVUQURBVEFfUkVTRVJWRSA9IHN1bShsaW1pdCArIDEgZm9yIF8sIGxpbWl0IGluIE1FVEFEQVRBX0xJTUlUUykKTUVUQURBVEFfSlNPTl9MSU1JVCA9IDIwMDAwCk1PRFVMRV9OQU1FUyA9ICgnb3duZXJfc3ViYWdlbnRfcHJvY2Vzc2VzLnB5JywgJ293bmVyX2F1dG9ub215X3Bvb2wucHknLCAnb3duZXJfc3ViYWdlbnRfZGlzcGF0Y2hlci5weScpCgoKY2xhc3MgU291cmNlSG9sZChSdW50aW1lRXJyb3IpOgogICAgcGFzcwoKCmRlZiByZXF1aXJlKGNvbmRpdGlvbik6CiAgICBpZiBub3QgY29uZGl0aW9uOgogICAgICAgIHJhaXNlIFNvdXJjZUhvbGQoJ0hPTERfU09VUkNFX1JFQURCQUNLJykKCgpkZWYgY2Fub25pY2FsKHZhbHVlKToKICAgIHJldHVybiBwcmltaXRpdmVzLmNhbm9uaWNhbCh2YWx1ZSkKCgpkZWYgZGlnZXN0KHZhbHVlKToKICAgIHJldHVybiBoYXNobGliLnNoYTI1Nih2YWx1ZSkuaGV4ZGlnZXN0KCkKCgpkZWYgaXNfc2hhKHZhbHVlKToKICAgIHJldHVybiBpc2luc3RhbmNlKHZhbHVlLCBzdHIpIGFuZCByZS5mdWxsbWF0Y2goJ1thLWYwLTldezY0fScsIHZhbHVlKSBpcyBub3QgTm9uZQoKCmRlZiBzY29wZSgpOgogICAgcmV0dXJuIHsnc2NoZW1hJzogJ05PWF9GSVhFRF9TT1VSQ0VfU0NPUEVfVjEnLCAnaW5zdGFuY2VfaWQnOiA2MDUwOTU1MSwKICAgICAgICAgICAgJ2ZpbGVzJzogbGlzdChGSUxFUyksICdmaWxlX2xpbWl0JzogRklMRV9MSU1JVCwgJ3RvdGFsX2xpbWl0JzogVE9UQUxfTElNSVQsCiAgICAgICAgICAgICdzZWxlY3Rpb24nOiAnRklYRURfU09VUkNFX0FORF9VSV9PTkxZJywgJ25hdGl2ZV9tdXRhdGlvbnMnOiBGYWxzZSwKICAgICAgICAgICAgJ21ldGFkYXRhX3Byb2plY3Rpb25zJzogW3sncmVsYXRpdmVfcGF0aCc6IHBhdGgsICdsaW1pdCc6IGxpbWl0fSBmb3IgcGF0aCwgbGltaXQgaW4gTUVUQURBVEFfTElNSVRTXX0KCgpkZWYgc2NvcGVfc2hhKCk6CiAgICByZXR1cm4gZGlnZXN0KGNhbm9uaWNhbChzY29wZSgpKSkKCgpkZWYgcHVibGljX2tleV9tZXRhZGF0YSh2YWx1ZSwgbm93PU5vbmUpOgogICAgbm93ID0gaW50KHRpbWUudGltZSgpKSBpZiBub3cgaXMgTm9uZSBlbHNlIG5vdwogICAgcmVxdWlyZShpc2luc3RhbmNlKHZhbHVlLCBkaWN0KSBhbmQgc2V0KHZhbHVlKSA9PSB7J3NjaGVtYScsICdrZXlfaWQnLCAncHVibGljX2tleV9wZW0nLAogICAgICAgICAgICAndHJhbnNmZXJfaWQnLCAnY3JlYXRlZF9hdCcsICdleHBpcmVzX2F0JywgJ3Njb3BlX3NoYTI1Nid9KQogICAgcmVxdWlyZSh2YWx1ZVsnc2NoZW1hJ10gPT0gJ05PWF9GSVhFRF9TT1VSQ0VfUFVCTElDX0tFWV9WMScKICAgICAgICAgICAgYW5kIHZhbHVlWydzY29wZV9zaGEyNTYnXSA9PSBzY29wZV9zaGEoKQogICAgICAgICAgICBhbmQgaXNpbnN0YW5jZSh2YWx1ZVsndHJhbnNmZXJfaWQnXSwgc3RyKQogICAgICAgICAgICBhbmQgcmUuZnVsbG1hdGNoKCdbYS1mMC05XXszMn0nLCB2YWx1ZVsndHJhbnNmZXJfaWQnXSkKICAgICAgICAgICAgYW5kIHR5cGUodmFsdWVbJ2NyZWF0ZWRfYXQnXSkgaXMgaW50IGFuZCB0eXBlKHZhbHVlWydleHBpcmVzX2F0J10pIGlzIGludAogICAgICAgICAgICBhbmQgMCA8IHZhbHVlWydleHBpcmVzX2F0J10gLSB2YWx1ZVsnY3JlYXRlZF9hdCddIDw9IE1BWF9UVEwKICAgICAgICAgICAgYW5kIHZhbHVlWydjcmVhdGVkX2F0J10gLSA1IDw9IG5vdyA8IHZhbHVlWydleHBpcmVzX2F0J10pCiAgICBwZW0gPSB2YWx1ZVsncHVibGljX2tleV9wZW0nXQogICAgcmVxdWlyZShpc2luc3RhbmNlKHBlbSwgc3RyKSBhbmQgcGVtLnN0YXJ0c3dpdGgoJy0tLS0tQkVHSU4gUFVCTElDIEtFWS0tLS0tXG4nKSBhbmQgbGVuKHBlbSkgPD0gMTIwMCkKICAgIGtleSA9IHByaW1pdGl2ZXMuc2VyaWFsaXphdGlvbi5sb2FkX3BlbV9wdWJsaWNfa2V5KHBlbS5lbmNvZGUoJ2FzY2lpJykpCiAgICByZXF1aXJlKGlzaW5zdGFuY2Uoa2V5LCBwcmltaXRpdmVzLnJzYS5SU0FQdWJsaWNLZXkpIGFuZCBrZXkua2V5X3NpemUgPT0gNDA5NgogICAgICAgICAgICBhbmQga2V5LnB1YmxpY19udW1iZXJzKCkuZSA9PSA2NTUzNykKICAgIGRlciA9IGtleS5wdWJsaWNfYnl0ZXMocHJpbWl0aXZlcy5zZXJpYWxpemF0aW9uLkVuY29kaW5nLkRFUiwKICAgICAgICAgICAgICAgICAgICAgICAgICAgcHJpbWl0aXZlcy5zZXJpYWxpemF0aW9uLlB1YmxpY0Zvcm1hdC5TdWJqZWN0UHVibGljS2V5SW5mbykKICAgIHJlcXVpcmUodmFsdWVbJ2tleV9pZCddID09IGRpZ2VzdChkZXIpKQogICAgcmV0dXJuIGtleQoKCmRlZiByZWFkX3NvdXJjZXMocm9vdD1QYXRoKCcvcm9vdC9ub3gnKSk6CiAgICAiIiJTdGFibGUgbm8tZm9sbG93IHJlYWRzLCBpbmNsdWRpbmcgYW5jZXN0b3JzOyAzcyBjb29wZXJhdGl2ZSBJTyBidWRnZXQuCgogICAgVGhlIGRlYWRsaW5lIGlzIGNoZWNrZWQgYmV0d2VlbiByZWFkcy4gSXQgY2Fubm90IGludGVycnVwdCBhIGJsb2NrZWQga2VybmVsCiAgICBzeXNjYWxsLiBUaGUgZW5jbG9zaW5nIGlzb2xhdGVkIHN1YnByb2Nlc3MgaGFzIGEgc2VwYXJhdGUgNjBzIHRpbWVvdXQuCiAgICBVbmtub3duIGZpbGVzIGNvbnN1bWUgdGhlaXIgd2hvbGUgYXR0ZW1wdGVkIGFsbG93YW5jZSwgcHJldmVudGluZyByZXNldCBvZgogICAgdGhlIGFnZ3JlZ2F0ZSByZWFkIGJ1ZGdldC4gT25seSBleGFjdCBwaW5uZWQgYnl0ZXMgb3IgbmV3IGZpeGVkIHBhdGhzIHNlYWwuCiAgICAiIiIKICAgIHJvd3MsIHBheWxvYWQsIHJlbWFpbmluZyA9IFtdLCBbXSwgVE9UQUxfTElNSVQgLSBNRVRBREFUQV9SRVNFUlZFCiAgICBkZWFkbGluZSA9IHRpbWUubW9ub3RvbmljKCkgKyAzCiAgICBmb3Igc2VsZWN0ZWQgaW4gRklMRVM6CiAgICAgICAgcmVsYXRpdmUgPSBzZWxlY3RlZFsncmVsYXRpdmVfcGF0aCddCiAgICAgICAgY2FwID0gbWluKEZJTEVfTElNSVQsIG1heCgwLCByZW1haW5pbmcgLSAxKSkKICAgICAgICByZWFkID0gKF9vMl9yZWFkKFBhdGgocm9vdCkgLyByZWxhdGl2ZSwgY2FwLCBkZWFkbGluZT1kZWFkbGluZSkgaWYgcmVtYWluaW5nIGVsc2UKICAgICAgICAgICAgICAgIHsnc3RhdGUnOiAnVU5LTk9XTl9UT1RBTF9CVURHRVQnLCAnYnl0ZXNfcmVhZCc6IDAsICdzaGEyNTYnOiBOb25lLCAndmFsdWUnOiBOb25lfSkKICAgICAgICByZW1haW5pbmcgLT0gKHJlYWRbJ2J5dGVzX3JlYWQnXSBpZiByZWFkWydzdGF0ZSddID09ICdPQlNFUlZFRCcgZWxzZSBtaW4oY2FwICsgMSwgcmVtYWluaW5nKSkKICAgICAgICBzdGF0ZSA9IHJlYWRbJ3N0YXRlJ10KICAgICAgICBpZiBzdGF0ZSA9PSAnT0JTRVJWRUQnIGFuZCBzZWxlY3RlZFsnc2hhMjU2J10gaXMgbm90IE5vbmU6CiAgICAgICAgICAgIGlmIHJlYWRbJ3NoYTI1NiddICE9IHNlbGVjdGVkWydzaGEyNTYnXSBvciByZWFkWydieXRlc19yZWFkJ10gIT0gc2VsZWN0ZWRbJ2J5dGVzJ106CiAgICAgICAgICAgICAgICBzdGF0ZSA9ICdVTktOT1dOX1BJTl9NSVNNQVRDSCcKICAgICAgICBhY2NlcHRlZCA9IHN0YXRlID09ICdPQlNFUlZFRCcKICAgICAgICByb3dzLmFwcGVuZCh7J3JlbGF0aXZlX3BhdGgnOiByZWxhdGl2ZSwgJ3N0YXRlJzogc3RhdGUsCiAgICAgICAgICAgICAgICAgICAgICdieXRlcyc6IHJlYWRbJ2J5dGVzX3JlYWQnXSBpZiBhY2NlcHRlZCBlbHNlIE5vbmUsCiAgICAgICAgICAgICAgICAgICAgICdzaGEyNTYnOiByZWFkWydzaGEyNTYnXSBpZiBhY2NlcHRlZCBlbHNlIE5vbmV9KQogICAgICAgIGlmIGFjY2VwdGVkOgogICAgICAgICAgICBwYXlsb2FkLmFwcGVuZChyZWFkWyd2YWx1ZSddKQogICAgcmF3ID0gYicnLmpvaW4ocGF5bG9hZCkKICAgIHJlcXVpcmUobGVuKHJhdykgPD0gVE9UQUxfTElNSVQpCiAgICBtYW5pZmVzdCA9IHsnc2NoZW1hJzogJ05PWF9GSVhFRF9TT1VSQ0VfTUFOSUZFU1RfVjEnLCAnc2NvcGVfc2hhMjU2Jzogc2NvcGVfc2hhKCksCiAgICAgICAgICAgICAgICAnZmlsZXMnOiByb3dzLCAncGxhaW50ZXh0X2J5dGVzJzogbGVuKHJhdyksICdwbGFpbnRleHRfc2hhMjU2JzogZGlnZXN0KHJhdyksCiAgICAgICAgICAgICAgICAnY29tcGxldGUnOiBhbGwocm93WydzdGF0ZSddID09ICdPQlNFUlZFRCcgZm9yIHJvdyBpbiByb3dzKSwKICAgICAgICAgICAgICAgICdyZWFkX29ubHknOiBUcnVlLCAnbmF0aXZlX2FjY2VwdGVkJzogRmFsc2UsCiAgICAgICAgICAgICAgICAnc2VydmluZ19hbmRfZXhlY3V0ZWRfbWFwcGluZyc6ICdVTktOT1dOJywKICAgICAgICAgICAgICAgICduYXRpdmVfbWV0YWRhdGEnOiByZWFkX25hdGl2ZV9tZXRhZGF0YShyb290LCBkZWFkbGluZSl9CiAgICByZXR1cm4gcmF3LCBtYW5pZmVzdAoKCmRlZiB2YWxpZGF0ZV9tYW5pZmVzdChtYW5pZmVzdCk6CiAgICByZXF1aXJlKGlzaW5zdGFuY2UobWFuaWZlc3QsIGRpY3QpIGFuZCBzZXQobWFuaWZlc3QpID09IHsnc2NoZW1hJywgJ3Njb3BlX3NoYTI1NicsICdmaWxlcycsCiAgICAgICAgICAgICdwbGFpbnRleHRfYnl0ZXMnLCAncGxhaW50ZXh0X3NoYTI1NicsICdjb21wbGV0ZScsICdyZWFkX29ubHknLCAnbmF0aXZlX2FjY2VwdGVkJywKICAgICAgICAgICAgJ3NlcnZpbmdfYW5kX2V4ZWN1dGVkX21hcHBpbmcnLCAnbmF0aXZlX21ldGFkYXRhJ30pCiAgICByZXF1aXJlKG1hbmlmZXN0WydzY2hlbWEnXSA9PSAnTk9YX0ZJWEVEX1NPVVJDRV9NQU5JRkVTVF9WMScgYW5kIG1hbmlmZXN0WydzY29wZV9zaGEyNTYnXSA9PSBzY29wZV9zaGEoKQogICAgICAgICAgICBhbmQgbWFuaWZlc3RbJ3JlYWRfb25seSddIGlzIFRydWUgYW5kIG1hbmlmZXN0WyduYXRpdmVfYWNjZXB0ZWQnXSBpcyBGYWxzZQogICAgICAgICAgICBhbmQgbWFuaWZlc3RbJ3NlcnZpbmdfYW5kX2V4ZWN1dGVkX21hcHBpbmcnXSA9PSAnVU5LTk9XTicKICAgICAgICAgICAgYW5kIHR5cGUobWFuaWZlc3RbJ3BsYWludGV4dF9ieXRlcyddKSBpcyBpbnQgYW5kIDAgPD0gbWFuaWZlc3RbJ3BsYWludGV4dF9ieXRlcyddIDw9IFRPVEFMX0xJTUlUCiAgICAgICAgICAgIGFuZCBpc19zaGEobWFuaWZlc3RbJ3BsYWludGV4dF9zaGEyNTYnXSkpCiAgICByb3dzID0gbWFuaWZlc3RbJ2ZpbGVzJ10KICAgIHJlcXVpcmUoaXNpbnN0YW5jZShyb3dzLCBsaXN0KSBhbmQgbGVuKHJvd3MpID09IGxlbihGSUxFUykpCiAgICB0b3RhbCA9IDAKICAgIGZvciBzZWxlY3RlZCwgcm93IGluIHppcChGSUxFUywgcm93cyk6CiAgICAgICAgcmVxdWlyZShpc2luc3RhbmNlKHJvdywgZGljdCkgYW5kIHNldChyb3cpID09IHsncmVsYXRpdmVfcGF0aCcsICdzdGF0ZScsICdieXRlcycsICdzaGEyNTYnfQogICAgICAgICAgICAgICAgYW5kIHJvd1sncmVsYXRpdmVfcGF0aCddID09IHNlbGVjdGVkWydyZWxhdGl2ZV9wYXRoJ10gYW5kIHJvd1snc3RhdGUnXSBpbiBTVEFURVMpCiAgICAgICAgaWYgcm93WydzdGF0ZSddID09ICdPQlNFUlZFRCc6CiAgICAgICAgICAgIHJlcXVpcmUodHlwZShyb3dbJ2J5dGVzJ10pIGlzIGludCBhbmQgMCA8PSByb3dbJ2J5dGVzJ10gPD0gRklMRV9MSU1JVCBhbmQgaXNfc2hhKHJvd1snc2hhMjU2J10pKQogICAgICAgICAgICBpZiBzZWxlY3RlZFsnc2hhMjU2J10gaXMgbm90IE5vbmU6CiAgICAgICAgICAgICAgICByZXF1aXJlKHJvd1snc2hhMjU2J10gPT0gc2VsZWN0ZWRbJ3NoYTI1NiddIGFuZCByb3dbJ2J5dGVzJ10gPT0gc2VsZWN0ZWRbJ2J5dGVzJ10pCiAgICAgICAgICAgIHRvdGFsICs9IHJvd1snYnl0ZXMnXQogICAgICAgIGVsc2U6CiAgICAgICAgICAgIHJlcXVpcmUocm93WydieXRlcyddIGlzIE5vbmUgYW5kIHJvd1snc2hhMjU2J10gaXMgTm9uZSkKICAgIHJlcXVpcmUodG90YWwgPT0gbWFuaWZlc3RbJ3BsYWludGV4dF9ieXRlcyddIGFuZCBtYW5pZmVzdFsnY29tcGxldGUnXSBpcwogICAgICAgICAgICBhbGwocm93WydzdGF0ZSddID09ICdPQlNFUlZFRCcgZm9yIHJvdyBpbiByb3dzKSkKICAgIHJlcXVpcmUoaXNpbnN0YW5jZShtYW5pZmVzdFsnbmF0aXZlX21ldGFkYXRhJ10sIGRpY3QpCiAgICAgICAgICAgIGFuZCBzZXQobWFuaWZlc3RbJ25hdGl2ZV9tZXRhZGF0YSddKSA9PSB7J2NvbmZpZycsICdwYXVzZWRfcmVnaXN0cnknfQogICAgICAgICAgICBhbmQgbGVuKGNhbm9uaWNhbChtYW5pZmVzdFsnbmF0aXZlX21ldGFkYXRhJ10pKSA8PSBNRVRBREFUQV9KU09OX0xJTUlUKQogICAgcmV0dXJuIG1hbmlmZXN0CgoKZGVmIF9zYWZlX2lkKHZhbHVlKToKICAgIHJldHVybiB2YWx1ZSBpZiBpc2luc3RhbmNlKHZhbHVlLCBzdHIpIGFuZCByZS5mdWxsbWF0Y2goJ1tBLVphLXowLTlfLi1dezEsMTI4fScsIHZhbHVlKSBlbHNlIE5vbmUKCgpkZWYgX21ldGFkYXRhX2pzb24ocm9vdCwgcmVsYXRpdmUsIGxpbWl0LCBkZWFkbGluZSk6CiAgICByZWFkID0gX28yX3JlYWQoUGF0aChyb290KSAvIHJlbGF0aXZlLCBsaW1pdCwgZGVhZGxpbmU9ZGVhZGxpbmUpCiAgICByZXN1bHQgPSB7J3N0YXRlJzogcmVhZFsnc3RhdGUnXSwgJ2J5dGVzJzogcmVhZFsnYnl0ZXNfcmVhZCddIGlmIHJlYWRbJ3N0YXRlJ10gPT0gJ09CU0VSVkVEJyBlbHNlIE5vbmUsCiAgICAgICAgICAgICAgJ3NoYTI1Nic6IHJlYWRbJ3NoYTI1NiddfQogICAgaWYgcmVhZFsnc3RhdGUnXSAhPSAnT0JTRVJWRUQnOgogICAgICAgIHJldHVybiBOb25lLCByZXN1bHQKICAgIHRyeToKICAgICAgICB2YWx1ZSA9IGpzb24ubG9hZHMocmVhZFsndmFsdWUnXSwgb2JqZWN0X3BhaXJzX2hvb2s9cHJpbWl0aXZlcy51bmlxdWUsCiAgICAgICAgICAgICAgICAgICAgICAgICAgIHBhcnNlX2NvbnN0YW50PWxhbWJkYSBfOiByZXF1aXJlKEZhbHNlKSkKICAgICAgICByZXR1cm4gdmFsdWUsIHJlc3VsdAogICAgZXhjZXB0IEV4Y2VwdGlvbjoKICAgICAgICByZXN1bHRbJ3N0YXRlJ10gPSAnVU5LTk9XTl9KU09OJwogICAgICAgIHJldHVybiBOb25lLCByZXN1bHQKCgpkZWYgcmVhZF9uYXRpdmVfbWV0YWRhdGEocm9vdCwgZGVhZGxpbmUpOgogICAgIiIiT25seSBleHBsaWNpdCBjb25maWcgZmllbGRzIGFuZCByZWdpc3RyeSB0eXBlIGNvdW50cyBjcm9zcyB0aGUgYm91bmRhcnkuCgogICAgTm8gcXVldWUgc3RhdGUsIHBvbGljeSB0ZXh0LCBvdGhlciBwYXJhbXMsIHRpdGxlcywgdXNlciBjb250ZW50LCBjcmVkZW50aWFscywKICAgIGVudmlyb25tZW50IG9yIHJhdyBwYXVzZWQgUElEcyBhcmUgcmV0dXJuZWQuIEJ1ZGdldCB3YXMgcmVzZXJ2ZWQgYWJvdmUuCiAgICAiIiIKICAgIHZhbHVlLCBjb25maWcgPSBfbWV0YWRhdGFfanNvbihyb290LCBDT05GSUdfUEFUSCwgMjYyMTQ0LCBkZWFkbGluZSkKICAgIGlmIGlzaW5zdGFuY2UodmFsdWUsIGRpY3QpIGFuZCB2YWx1ZS5nZXQoJ3NjaGVtYScpID09ICdOT1hfTkFUSVZFX1NVQkFHRU5UX0JJTkRJTkdfVjEnOgogICAgICAgIGNvbmZpZy51cGRhdGUoc2NoZW1hPSdOT1hfTkFUSVZFX1NVQkFHRU5UX0JJTkRJTkdfVjEnLAogICAgICAgICAgICBwb2xpY3lfaWQ9J05PWF9XRUJfV0VJR0hUU19WMDYnIGlmIHZhbHVlLmdldCgncG9saWN5X2lkJykgPT0gJ05PWF9XRUJfV0VJR0hUU19WMDYnIGVsc2UgTm9uZSwKICAgICAgICAgICAgbW9kZT12YWx1ZS5nZXQoJ21vZGUnKSBpZiB2YWx1ZS5nZXQoJ21vZGUnKSBpbiAoJ05PUk1BTCcsICdGT1JTQVpIJykgZWxzZSBOb25lLAogICAgICAgICAgICB0YXJnZXQ9dmFsdWUuZ2V0KCd0YXJnZXQnKSBpZiB0eXBlKHZhbHVlLmdldCgndGFyZ2V0JykpIGlzIGludCBhbmQgdmFsdWVbJ3RhcmdldCddIGluICgzLCA2KSBlbHNlIE5vbmUsCiAgICAgICAgICAgIGluc3RhbmNlX2lkPTYwNTA5NTUxIGlmIHR5cGUodmFsdWUuZ2V0KCdpbnN0YW5jZV9pZCcpKSBpcyBpbnQgYW5kIHZhbHVlWydpbnN0YW5jZV9pZCddID09IDYwNTA5NTUxIGVsc2UgTm9uZSwKICAgICAgICAgICAgb3duZXJfYXV0aG9yaXplZD12YWx1ZS5nZXQoJ293bmVyX2F1dGhvcml6ZWQnKSBpZiB0eXBlKHZhbHVlLmdldCgnb3duZXJfYXV0aG9yaXplZCcpKSBpcyBib29sIGVsc2UgTm9uZSkKICAgICAgICBwb2xpY3kgPSB2YWx1ZS5nZXQoJ3BvbGljeScpOyBwb2xpY3kgPSBwb2xpY3kgaWYgaXNpbnN0YW5jZShwb2xpY3ksIGRpY3QpIGVsc2Uge30KICAgICAgICBjb25maWdbJ3BvbGljeSddID0geydwYXRoJzogUE9MSUNZX1BBVEggaWYgcG9saWN5LmdldCgncGF0aCcpID09IFBPTElDWV9QQVRIIGVsc2UgTm9uZSwKICAgICAgICAgICAgICAgICAgICAgICAgICAgICdzaGEyNTYnOiBwb2xpY3kuZ2V0KCdzaGEyNTYnKSBpZiBpc19zaGEocG9saWN5LmdldCgnc2hhMjU2JykpIGVsc2UgTm9uZSwKICAgICAgICAgICAgICAgICAgICAgICAgICAgICdwb2xpY3lfY29udGVudF9yZWFkJzogRmFsc2V9CiAgICAgICAgcGlucyA9IHZhbHVlLmdldCgnbW9kdWxlX3BpbnMnKTsgcGlucyA9IHBpbnMgaWYgaXNpbnN0YW5jZShwaW5zLCBkaWN0KSBlbHNlIHt9CiAgICAgICAgY29uZmlnWydtb2R1bGVfcGlucyddID0ge25hbWU6IHBpbnMuZ2V0KG5hbWUpIGlmIGlzX3NoYShwaW5zLmdldChuYW1lKSkgZWxzZSBOb25lIGZvciBuYW1lIGluIE1PRFVMRV9OQU1FU30KICAgICAgICBjb25maWdbJ2NhdGFsb2dfc2hhMjU2J10gPSB2YWx1ZS5nZXQoJ2NhdGFsb2dfc2hhMjU2JykgaWYgaXNfc2hhKHZhbHVlLmdldCgnY2F0YWxvZ19zaGEyNTYnKSkgZWxzZSBOb25lCiAgICAgICAgY2F0YWxvZyA9IHZhbHVlLmdldCgnY2F0YWxvZycpCiAgICAgICAgc2VsZWN0ZWQgPSB7J3NjaGVtYSc6IE5vbmUsICd0YXNrX2NvdW50JzogTm9uZSwgJ3Rhc2tzJzogW10sICdwcm9qZWN0aW9uX2NvbXBsZXRlJzogRmFsc2UsCiAgICAgICAgICAgICAgICAgICAgJ2NsYWltZWRfZGlnZXN0X21hdGNoZXMnOiBOb25lfQogICAgICAgIGNvbmZpZ1snY2F0YWxvZyddID0gc2VsZWN0ZWQKICAgICAgICBpZiBpc2luc3RhbmNlKGNhdGFsb2csIGRpY3QpIGFuZCBjYXRhbG9nLmdldCgnc2NoZW1hJykgPT0gJ05PWF9BVVRPTk9NWV9QUk9DRVNTX1BPT0xfVjEnOgogICAgICAgICAgICB0YXNrcyA9IGNhdGFsb2cuZ2V0KCd0YXNrcycpCiAgICAgICAgICAgIGlmIGlzaW5zdGFuY2UodGFza3MsIGxpc3QpIGFuZCBsZW4odGFza3MpIDw9IDI1NjoKICAgICAgICAgICAgICAgIHNlbGVjdGVkLnVwZGF0ZShzY2hlbWE9J05PWF9BVVRPTk9NWV9QUk9DRVNTX1BPT0xfVjEnLCB0YXNrX2NvdW50PWxlbih0YXNrcykpCiAgICAgICAgICAgICAgICB0cnk6CiAgICAgICAgICAgICAgICAgICAgZGlnZXN0X3JhdyA9IGpzb24uZHVtcHMoY2F0YWxvZywgZW5zdXJlX2FzY2lpPUZhbHNlLCBzb3J0X2tleXM9VHJ1ZSwKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICBzZXBhcmF0b3JzPSgnLCcsICc6JyksIGFsbG93X25hbj1GYWxzZSkuZW5jb2RlKCkKICAgICAgICAgICAgICAgICAgICBzZWxlY3RlZFsnY2xhaW1lZF9kaWdlc3RfbWF0Y2hlcyddID0gZGlnZXN0KGRpZ2VzdF9yYXcpID09IGNvbmZpZ1snY2F0YWxvZ19zaGEyNTYnXQogICAgICAgICAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbjoKICAgICAgICAgICAgICAgICAgICBwYXNzCiAgICAgICAgICAgICAgICB2YWxpZCA9IFRydWUKICAgICAgICAgICAgICAgIGZvciByb3cgaW4gdGFza3M6CiAgICAgICAgICAgICAgICAgICAgaWYgbm90IGlzaW5zdGFuY2Uocm93LCBkaWN0KSBvciBub3QgX3NhZmVfaWQocm93LmdldCgnaWQnKSk6CiAgICAgICAgICAgICAgICAgICAgICAgIHZhbGlkID0gRmFsc2U7IGJyZWFrCiAgICAgICAgICAgICAgICAgICAgZGVwcyA9IHJvdy5nZXQoJ2RlcHMnLCBbXSkKICAgICAgICAgICAgICAgICAgICBpZiBub3QgaXNpbnN0YW5jZShkZXBzLCBsaXN0KSBvciBsZW4oZGVwcykgPiAyNTYgb3IgYW55KG5vdCBfc2FmZV9pZChpdGVtKSBmb3IgaXRlbSBpbiBkZXBzKToKICAgICAgICAgICAgICAgICAgICAgICAgdmFsaWQgPSBGYWxzZTsgYnJlYWsKICAgICAgICAgICAgICAgICAgICBwYXJhbXMgPSByb3cuZ2V0KCdwYXJhbXMnKTsgcGFyYW1zID0gcGFyYW1zIGlmIGlzaW5zdGFuY2UocGFyYW1zLCBkaWN0KSBlbHNlIHt9CiAgICAgICAgICAgICAgICAgICAgcHJvamVjdGVkID0geydpZCc6IHJvd1snaWQnXSwgJ2hhbmRsZXInOiBfc2FmZV9pZChyb3cuZ2V0KCdoYW5kbGVyJykpLAogICAgICAgICAgICAgICAgICAgICAgICAncmVzb3VyY2UnOiByb3cuZ2V0KCdyZXNvdXJjZScpIGlmIHJvdy5nZXQoJ3Jlc291cmNlJykgaW4gKCdDUFVfTElHSFQnLCAnQ1BVX0lPJywgJ0dQVV9FWENMVVNJVkUnKSBlbHNlIE5vbmUsCiAgICAgICAgICAgICAgICAgICAgICAgICdkZXBzJzogZGVwcywgJ3NvdXJjZV9zaGEyNTYnOiByb3cuZ2V0KCdzb3VyY2Vfc2hhMjU2JykgaWYgaXNfc2hhKHJvdy5nZXQoJ3NvdXJjZV9zaGEyNTYnKSkgZWxzZSBOb25lLAogICAgICAgICAgICAgICAgICAgICAgICAncm9sZSc6IHBhcmFtcy5nZXQoJ3JvbGUnKSBpZiBwYXJhbXMuZ2V0KCdyb2xlJykgaW4gKCdydW50aW1lJywgJ21lbW9yeScsICd3ZWlnaHRzJykgZWxzZSBOb25lfQogICAgICAgICAgICAgICAgICAgIHNlbGVjdGVkWyd0YXNrcyddLmFwcGVuZChwcm9qZWN0ZWQpCiAgICAgICAgICAgICAgICAgICAgaWYgbGVuKGNhbm9uaWNhbChjb25maWcpKSA+IDE2MDAwOgogICAgICAgICAgICAgICAgICAgICAgICBzZWxlY3RlZFsndGFza3MnXS5wb3AoKTsgdmFsaWQgPSBGYWxzZTsgYnJlYWsKICAgICAgICAgICAgICAgIHNlbGVjdGVkWydwcm9qZWN0aW9uX2NvbXBsZXRlJ10gPSB2YWxpZCBhbmQgbGVuKHNlbGVjdGVkWyd0YXNrcyddKSA9PSBsZW4odGFza3MpCiAgICBlbGlmIGNvbmZpZ1snc3RhdGUnXSA9PSAnT0JTRVJWRUQnOgogICAgICAgIGNvbmZpZ1snc3RhdGUnXSA9ICdVTktOT1dOX1NDSEVNQScKICAgIHZhbHVlLCByZWdpc3RyeSA9IF9tZXRhZGF0YV9qc29uKHJvb3QsIFJFR0lTVFJZX1BBVEgsIDY1NTM2LCBkZWFkbGluZSkKICAgIGlmIGlzaW5zdGFuY2UodmFsdWUsIGxpc3QpIGFuZCBsZW4odmFsdWUpIDw9IDUxMjoKICAgICAgICBsZWdhY3kgPSBzdW0odHlwZShyb3cpIGlzIGludCBhbmQgcm93ID4gMCBvciBpc2luc3RhbmNlKHJvdywgc3RyKSBhbmQgcm93LmlzZGlnaXQoKSBhbmQgbGVuKHJvdykgPD0gMjAKICAgICAgICAgICAgICAgICAgICAgZm9yIHJvdyBpbiB2YWx1ZSkKICAgICAgICBpZGVudGl0aWVzID0gc3VtKGlzaW5zdGFuY2Uocm93LCBkaWN0KSBhbmQgc2V0KHJvdykgPT0geydwaWQnLCAnc3RhcnRfdGlja3MnLCAnY21kbGluZV9zaGEyNTYnfQogICAgICAgICAgICBhbmQgdHlwZShyb3cuZ2V0KCdwaWQnKSkgaXMgaW50IGFuZCByb3dbJ3BpZCddID4gMCBhbmQgdHlwZShyb3cuZ2V0KCdzdGFydF90aWNrcycpKSBpcyBpbnQKICAgICAgICAgICAgYW5kIHJvd1snc3RhcnRfdGlja3MnXSA+PSAwIGFuZCBpc19zaGEocm93LmdldCgnY21kbGluZV9zaGEyNTYnKSkgZm9yIHJvdyBpbiB2YWx1ZSkKICAgICAgICByZWdpc3RyeS51cGRhdGUoZm9ybWF0PSdMSVNUJywgdG90YWxfcmVjb3Jkcz1sZW4odmFsdWUpLCBsZWdhY3lfYmFyZV9yZWNvcmRzPWxlZ2FjeSwKICAgICAgICAgICAgICAgICAgICAgICAgaWRlbnRpdHlfcmVjb3Jkcz1pZGVudGl0aWVzLCBvdGhlcl9yZWNvcmRzPWxlbih2YWx1ZSkgLSBsZWdhY3kgLSBpZGVudGl0aWVzKQogICAgZWxpZiByZWdpc3RyeVsnc3RhdGUnXSA9PSAnT0JTRVJWRUQnOgogICAgICAgIHJlZ2lzdHJ5LnVwZGF0ZShzdGF0ZT0nVU5LTk9XTl9TQ0hFTUEnLCBmb3JtYXQ9J1VOS05PV04nKQogICAgcmVzdWx0ID0geydjb25maWcnOiBjb25maWcsICdwYXVzZWRfcmVnaXN0cnknOiByZWdpc3RyeX0KICAgIHJlcXVpcmUobGVuKGNhbm9uaWNhbChyZXN1bHQpKSA8PSBNRVRBREFUQV9KU09OX0xJTUlUKQogICAgcmV0dXJuIHJlc3VsdAoKCmRlZiBzZWFsKHB1YmxpY19tZXRhZGF0YSwgcmVxdWVzdCwgc291cmNlLCByb290PVBhdGgoJy9yb290L25veCcpKToKICAgIHB1YmxpYyA9IHB1YmxpY19rZXlfbWV0YWRhdGEocHVibGljX21ldGFkYXRhKQogICAgY29udGV4dCA9IHByaW1pdGl2ZXMub3duZXJfY29udGV4dChyZXF1ZXN0LCBzb3VyY2UpCiAgICByYXcsIG1hbmlmZXN0ID0gcmVhZF9zb3VyY2VzKHJvb3QpCiAgICB2YWxpZGF0ZV9tYW5pZmVzdChtYW5pZmVzdCkKICAgIHRvdGFsID0gbGVuKHJhdyk7IGNoYXJzID0gKCh0b3RhbCArIDE4KSAvLyAzKSAqIDQKICAgIGNodW5rcyA9IChjaGFycyArIENIVU5LX0NIQVJTIC0gMSkgLy8gQ0hVTktfQ0hBUlMKICAgIHJlcXVpcmUoMSA8PSBjaHVua3MgPD0gTUFYX0NIVU5LUykKICAgIGFhZCA9IHsnc2NoZW1hJzogJ05PWF9GSVhFRF9TT1VSQ0VfQUFEX1YxJywgJ2FsZ29yaXRobSc6IEFMR09SSVRITSwKICAgICAgICAgICAnbWFuaWZlc3QnOiBtYW5pZmVzdCwgJ2tleV9pZCc6IHB1YmxpY19tZXRhZGF0YVsna2V5X2lkJ10sCiAgICAgICAgICAgJ3RyYW5zZmVyX2lkJzogcHVibGljX21ldGFkYXRhWyd0cmFuc2Zlcl9pZCddLCAnY3JlYXRlZF9hdCc6IGludCh0aW1lLnRpbWUoKSksCiAgICAgICAgICAgJ2V4cGlyZXNfYXQnOiBwdWJsaWNfbWV0YWRhdGFbJ2V4cGlyZXNfYXQnXSwgJ2NvbnRleHQnOiBjb250ZXh0LAogICAgICAgICAgICdwbGFpbnRleHRfYnl0ZXMnOiB0b3RhbCwgJ2NpcGhlcnRleHRfYnl0ZXMnOiB0b3RhbCArIDE2LAogICAgICAgICAgICdjaHVua19jaGFycyc6IENIVU5LX0NIQVJTLCAnY2h1bmtfY291bnQnOiBjaHVua3N9CiAgICBhZXMgPSBwcmltaXRpdmVzLkFFU0dDTS5nZW5lcmF0ZV9rZXkoYml0X2xlbmd0aD0yNTYpOyBub25jZSA9IG9zLnVyYW5kb20oMTIpCiAgICB3cmFwcGVkID0gcHVibGljLmVuY3J5cHQoYWVzLCBwcmltaXRpdmVzLnBhZGRpbmcuT0FFUCgKICAgICAgICBtZ2Y9cHJpbWl0aXZlcy5wYWRkaW5nLk1HRjEocHJpbWl0aXZlcy5oYXNoZXMuU0hBMjU2KCkpLAogICAgICAgIGFsZ29yaXRobT1wcmltaXRpdmVzLmhhc2hlcy5TSEEyNTYoKSwgbGFiZWw9T0FFUF9MQUJFTCkpCiAgICBjaXBoZXIgPSBwcmltaXRpdmVzLkFFU0dDTShhZXMpLmVuY3J5cHQobm9uY2UsIHJhdywgY2Fub25pY2FsKGFhZCkpCiAgICBlbmNvZGVkID0gcHJpbWl0aXZlcy5iNjQoY2lwaGVyKQogICAgZW52ZWxvcGUgPSB7J3NjaGVtYSc6ICdOT1hfRklYRURfU09VUkNFX0VOVkVMT1BFX1YxJywgJ2FhZCc6IGFhZCwKICAgICAgICAgICAgICAgICd3cmFwcGVkX2tleSc6IHByaW1pdGl2ZXMuYjY0KHdyYXBwZWQpLCAnbm9uY2UnOiBwcmltaXRpdmVzLmI2NChub25jZSksCiAgICAgICAgICAgICAgICAnY2lwaGVydGV4dCc6IGVuY29kZWQsICdjaXBoZXJ0ZXh0X3NoYTI1Nic6IGRpZ2VzdChjaXBoZXIpfQogICAgb3V0ZXIgPSBkaWdlc3QoY2Fub25pY2FsKGVudmVsb3BlKSkKICAgIHJvd3MgPSBbeydraW5kJzogJ3NvdXJjZV9jaXBoZXJ0ZXh0X2hlYWRlcicsICdkYXRhJzogewogICAgICAgICdzY2hlbWEnOiAnTk9YX0ZJWEVEX1NPVVJDRV9UUkFOU0ZFUl9WMScsICdlbnZlbG9wZV9zaGEyNTYnOiBvdXRlciwKICAgICAgICAnY2h1bmtzJzogY2h1bmtzLCAnY2lwaGVydGV4dF9jaGFycyc6IGxlbihlbmNvZGVkKSwKICAgICAgICAnbWV0YWRhdGEnOiB7azogdiBmb3IgaywgdiBpbiBlbnZlbG9wZS5pdGVtcygpIGlmIGsgIT0gJ2NpcGhlcnRleHQnfX19XQogICAgcm93cyArPSBbeydraW5kJzogJ3NvdXJjZV9jaXBoZXJ0ZXh0X2NodW5rJywgJ2RhdGEnOiB7CiAgICAgICAgJ2VudmVsb3BlX3NoYTI1Nic6IG91dGVyLCAnaW5kZXgnOiBpLCAnY2h1bmtzJzogY2h1bmtzLAogICAgICAgICdjaXBoZXJ0ZXh0JzogZW5jb2RlZFtpICogQ0hVTktfQ0hBUlM6KGkgKyAxKSAqIENIVU5LX0NIQVJTXX19IGZvciBpIGluIHJhbmdlKGNodW5rcyldCiAgICByZXF1aXJlKGFsbChsZW4oY2Fub25pY2FsKHJvdykpIDwgNzkwMDAgZm9yIHJvdyBpbiByb3dzKSkKICAgIHJldHVybiByb3dzCgoKZGVmIGFzc2VtYmxlKHJvd3MpOgogICAgcmVxdWlyZShpc2luc3RhbmNlKHJvd3MsIGxpc3QpIGFuZCAyIDw9IGxlbihyb3dzKSA8PSBNQVhfQ0hVTktTICsgMSkKICAgIGZpcnN0ID0gcm93c1swXQogICAgcmVxdWlyZShpc2luc3RhbmNlKGZpcnN0LCBkaWN0KSBhbmQgc2V0KGZpcnN0KSA9PSB7J2tpbmQnLCAnZGF0YSd9CiAgICAgICAgICAgIGFuZCBmaXJzdFsna2luZCddID09ICdzb3VyY2VfY2lwaGVydGV4dF9oZWFkZXInKQogICAgaGVhZGVyID0gZmlyc3RbJ2RhdGEnXQogICAgcmVxdWlyZShpc2luc3RhbmNlKGhlYWRlciwgZGljdCkgYW5kIHNldChoZWFkZXIpID09IHsnc2NoZW1hJywgJ2VudmVsb3BlX3NoYTI1NicsICdjaHVua3MnLAogICAgICAgICAgICAnY2lwaGVydGV4dF9jaGFycycsICdtZXRhZGF0YSd9IGFuZCBoZWFkZXJbJ3NjaGVtYSddID09ICdOT1hfRklYRURfU09VUkNFX1RSQU5TRkVSX1YxJwogICAgICAgICAgICBhbmQgaXNfc2hhKGhlYWRlclsnZW52ZWxvcGVfc2hhMjU2J10pIGFuZCB0eXBlKGhlYWRlclsnY2h1bmtzJ10pIGlzIGludAogICAgICAgICAgICBhbmQgMSA8PSBoZWFkZXJbJ2NodW5rcyddIDw9IE1BWF9DSFVOS1MgYW5kIGxlbihyb3dzKSA9PSBoZWFkZXJbJ2NodW5rcyddICsgMQogICAgICAgICAgICBhbmQgdHlwZShoZWFkZXJbJ2NpcGhlcnRleHRfY2hhcnMnXSkgaXMgaW50CiAgICAgICAgICAgIGFuZCAwIDwgaGVhZGVyWydjaXBoZXJ0ZXh0X2NoYXJzJ10gPD0gKChUT1RBTF9MSU1JVCArIDE4KSAvLyAzKSAqIDQKICAgICAgICAgICAgYW5kIGhlYWRlclsnY2h1bmtzJ10gPT0gKGhlYWRlclsnY2lwaGVydGV4dF9jaGFycyddICsgQ0hVTktfQ0hBUlMgLSAxKSAvLyBDSFVOS19DSEFSUykKICAgIHBhcnRzID0gW10KICAgIGZvciBpLCByb3cgaW4gZW51bWVyYXRlKHJvd3NbMTpdKToKICAgICAgICByZXF1aXJlKGlzaW5zdGFuY2Uocm93LCBkaWN0KSBhbmQgc2V0KHJvdykgPT0geydraW5kJywgJ2RhdGEnfSBhbmQgcm93WydraW5kJ10gPT0gJ3NvdXJjZV9jaXBoZXJ0ZXh0X2NodW5rJykKICAgICAgICB2YWx1ZSA9IHJvd1snZGF0YSddCiAgICAgICAgcmVxdWlyZShpc2luc3RhbmNlKHZhbHVlLCBkaWN0KSBhbmQgc2V0KHZhbHVlKSA9PSB7J2VudmVsb3BlX3NoYTI1NicsICdpbmRleCcsICdjaHVua3MnLCAnY2lwaGVydGV4dCd9CiAgICAgICAgICAgICAgICBhbmQgdmFsdWVbJ2VudmVsb3BlX3NoYTI1NiddID09IGhlYWRlclsnZW52ZWxvcGVfc2hhMjU2J10gYW5kIHR5cGUodmFsdWVbJ2luZGV4J10pIGlzIGludAogICAgICAgICAgICAgICAgYW5kIHZhbHVlWydpbmRleCddID09IGkgYW5kIHR5cGUodmFsdWVbJ2NodW5rcyddKSBpcyBpbnQgYW5kIHZhbHVlWydjaHVua3MnXSA9PSBoZWFkZXJbJ2NodW5rcyddCiAgICAgICAgICAgICAgICBhbmQgaXNpbnN0YW5jZSh2YWx1ZVsnY2lwaGVydGV4dCddLCBzdHIpCiAgICAgICAgICAgICAgICBhbmQgbGVuKHZhbHVlWydjaXBoZXJ0ZXh0J10pID09IG1pbihDSFVOS19DSEFSUywgaGVhZGVyWydjaXBoZXJ0ZXh0X2NoYXJzJ10gLSBpICogQ0hVTktfQ0hBUlMpKQogICAgICAgIHBhcnRzLmFwcGVuZCh2YWx1ZVsnY2lwaGVydGV4dCddKQogICAgbWV0YSA9IGhlYWRlclsnbWV0YWRhdGEnXQogICAgcmVxdWlyZShpc2luc3RhbmNlKG1ldGEsIGRpY3QpIGFuZCBzZXQobWV0YSkgPT0geydzY2hlbWEnLCAnYWFkJywgJ3dyYXBwZWRfa2V5JywgJ25vbmNlJywgJ2NpcGhlcnRleHRfc2hhMjU2J30pCiAgICBlbnZlbG9wZSA9IGRpY3QobWV0YSwgY2lwaGVydGV4dD0nJy5qb2luKHBhcnRzKSkKICAgIHJlcXVpcmUoZGlnZXN0KGNhbm9uaWNhbChlbnZlbG9wZSkpID09IGhlYWRlclsnZW52ZWxvcGVfc2hhMjU2J10pCiAgICByZXR1cm4gZW52ZWxvcGUsIGhlYWRlclsnZW52ZWxvcGVfc2hhMjU2J10KCgpkZWYgZGVjcnlwdChyb3dzLCBwcml2YXRlX3BlbSwgcHVibGljX21ldGFkYXRhLCByZXF1ZXN0LCBzb3VyY2UpOgogICAgcHVibGljX2tleV9tZXRhZGF0YShwdWJsaWNfbWV0YWRhdGEpCiAgICBjb250ZXh0ID0gcHJpbWl0aXZlcy5vd25lcl9jb250ZXh0KHJlcXVlc3QsIHNvdXJjZSkKICAgIGVudmVsb3BlLCBvdXRlciA9IGFzc2VtYmxlKHJvd3MpOyBhYWQgPSBlbnZlbG9wZVsnYWFkJ10KICAgIHJlcXVpcmUoZW52ZWxvcGVbJ3NjaGVtYSddID09ICdOT1hfRklYRURfU09VUkNFX0VOVkVMT1BFX1YxJyBhbmQgaXNpbnN0YW5jZShhYWQsIGRpY3QpCiAgICAgICAgICAgIGFuZCBzZXQoYWFkKSA9PSB7J3NjaGVtYScsICdhbGdvcml0aG0nLCAnbWFuaWZlc3QnLCAna2V5X2lkJywgJ3RyYW5zZmVyX2lkJywgJ2NyZWF0ZWRfYXQnLAogICAgICAgICAgICAgICAgICAgICAgICAgICAgJ2V4cGlyZXNfYXQnLCAnY29udGV4dCcsICdwbGFpbnRleHRfYnl0ZXMnLCAnY2lwaGVydGV4dF9ieXRlcycsICdjaHVua19jaGFycycsICdjaHVua19jb3VudCd9KQogICAgbWFuaWZlc3QgPSB2YWxpZGF0ZV9tYW5pZmVzdChhYWRbJ21hbmlmZXN0J10pOyB0b3RhbCA9IG1hbmlmZXN0WydwbGFpbnRleHRfYnl0ZXMnXQogICAgY2hhcnMgPSAoKHRvdGFsICsgMTgpIC8vIDMpICogNAogICAgcmVxdWlyZShhYWRbJ3NjaGVtYSddID09ICdOT1hfRklYRURfU09VUkNFX0FBRF9WMScgYW5kIGFhZFsnYWxnb3JpdGhtJ10gPT0gQUxHT1JJVEhNCiAgICAgICAgICAgIGFuZCBhYWRbJ2tleV9pZCddID09IHB1YmxpY19tZXRhZGF0YVsna2V5X2lkJ10gYW5kIGFhZFsndHJhbnNmZXJfaWQnXSA9PSBwdWJsaWNfbWV0YWRhdGFbJ3RyYW5zZmVyX2lkJ10KICAgICAgICAgICAgYW5kIGFhZFsnZXhwaXJlc19hdCddID09IHB1YmxpY19tZXRhZGF0YVsnZXhwaXJlc19hdCddIGFuZCBhYWRbJ2NvbnRleHQnXSA9PSBjb250ZXh0CiAgICAgICAgICAgIGFuZCB0eXBlKGFhZFsnY3JlYXRlZF9hdCddKSBpcyBpbnQKICAgICAgICAgICAgYW5kIHB1YmxpY19tZXRhZGF0YVsnY3JlYXRlZF9hdCddIC0gNSA8PSBhYWRbJ2NyZWF0ZWRfYXQnXSA8PSBpbnQodGltZS50aW1lKCkpICsgNQogICAgICAgICAgICBhbmQgYWFkWydjcmVhdGVkX2F0J10gPCBhYWRbJ2V4cGlyZXNfYXQnXSBhbmQgdHlwZShhYWRbJ3BsYWludGV4dF9ieXRlcyddKSBpcyBpbnQKICAgICAgICAgICAgYW5kIGFhZFsncGxhaW50ZXh0X2J5dGVzJ10gPT0gdG90YWwgYW5kIHR5cGUoYWFkWydjaXBoZXJ0ZXh0X2J5dGVzJ10pIGlzIGludAogICAgICAgICAgICBhbmQgYWFkWydjaXBoZXJ0ZXh0X2J5dGVzJ10gPT0gdG90YWwgKyAxNiBhbmQgYWFkWydjaHVua19jaGFycyddID09IENIVU5LX0NIQVJTCiAgICAgICAgICAgIGFuZCB0eXBlKGFhZFsnY2h1bmtfY291bnQnXSkgaXMgaW50IGFuZCBhYWRbJ2NodW5rX2NvdW50J10gPT0gKGNoYXJzICsgQ0hVTktfQ0hBUlMgLSAxKSAvLyBDSFVOS19DSEFSUykKICAgIHByaXZhdGUgPSBwcmltaXRpdmVzLnNlcmlhbGl6YXRpb24ubG9hZF9wZW1fcHJpdmF0ZV9rZXkocHJpdmF0ZV9wZW0sIHBhc3N3b3JkPU5vbmUpCiAgICByZXF1aXJlKGlzaW5zdGFuY2UocHJpdmF0ZSwgcHJpbWl0aXZlcy5yc2EuUlNBUHJpdmF0ZUtleSkgYW5kIHByaXZhdGUua2V5X3NpemUgPT0gNDA5NikKICAgIGRlciA9IHByaXZhdGUucHVibGljX2tleSgpLnB1YmxpY19ieXRlcyhwcmltaXRpdmVzLnNlcmlhbGl6YXRpb24uRW5jb2RpbmcuREVSLAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgcHJpbWl0aXZlcy5zZXJpYWxpemF0aW9uLlB1YmxpY0Zvcm1hdC5TdWJqZWN0UHVibGljS2V5SW5mbykKICAgIHJlcXVpcmUoZGlnZXN0KGRlcikgPT0gcHVibGljX21ldGFkYXRhWydrZXlfaWQnXSkKICAgIGNpcGhlciA9IHByaW1pdGl2ZXMudW5iNjQoZW52ZWxvcGVbJ2NpcGhlcnRleHQnXSwgdG90YWwgKyAxNikKICAgIHJlcXVpcmUobGVuKGNpcGhlcikgPT0gdG90YWwgKyAxNiBhbmQgZGlnZXN0KGNpcGhlcikgPT0gZW52ZWxvcGVbJ2NpcGhlcnRleHRfc2hhMjU2J10pCiAgICB3cmFwcGVkID0gcHJpbWl0aXZlcy51bmI2NChlbnZlbG9wZVsnd3JhcHBlZF9rZXknXSwgNTEyKTsgbm9uY2UgPSBwcmltaXRpdmVzLnVuYjY0KGVudmVsb3BlWydub25jZSddLCAxMikKICAgIHJlcXVpcmUobGVuKHdyYXBwZWQpID09IDUxMiBhbmQgbGVuKG5vbmNlKSA9PSAxMikKICAgIGFlcyA9IHByaXZhdGUuZGVjcnlwdCh3cmFwcGVkLCBwcmltaXRpdmVzLnBhZGRpbmcuT0FFUCgKICAgICAgICBtZ2Y9cHJpbWl0aXZlcy5wYWRkaW5nLk1HRjEocHJpbWl0aXZlcy5oYXNoZXMuU0hBMjU2KCkpLAogICAgICAgIGFsZ29yaXRobT1wcmltaXRpdmVzLmhhc2hlcy5TSEEyNTYoKSwgbGFiZWw9T0FFUF9MQUJFTCkpCiAgICByZXF1aXJlKGxlbihhZXMpID09IDMyKQogICAgcmF3ID0gcHJpbWl0aXZlcy5BRVNHQ00oYWVzKS5kZWNyeXB0KG5vbmNlLCBjaXBoZXIsIGNhbm9uaWNhbChhYWQpKQogICAgcmVxdWlyZShsZW4ocmF3KSA9PSB0b3RhbCBhbmQgZGlnZXN0KHJhdykgPT0gbWFuaWZlc3RbJ3BsYWludGV4dF9zaGEyNTYnXSkKICAgIG9mZnNldCwgZmlsZXMgPSAwLCB7fQogICAgZm9yIHJvdyBpbiBtYW5pZmVzdFsnZmlsZXMnXToKICAgICAgICBpZiByb3dbJ3N0YXRlJ10gIT0gJ09CU0VSVkVEJzoKICAgICAgICAgICAgY29udGludWUKICAgICAgICBpdGVtID0gcmF3W29mZnNldDpvZmZzZXQgKyByb3dbJ2J5dGVzJ11dOyBvZmZzZXQgKz0gcm93WydieXRlcyddCiAgICAgICAgcmVxdWlyZShkaWdlc3QoaXRlbSkgPT0gcm93WydzaGEyNTYnXSkKICAgICAgICBmaWxlc1tyb3dbJ3JlbGF0aXZlX3BhdGgnXV0gPSBpdGVtCiAgICByZXR1cm4gZmlsZXMsIHsnc2NoZW1hJzogJ05PWF9GSVhFRF9TT1VSQ0VfTE9DQUxfUkVDRUlQVF9WMScsICdlbnZlbG9wZV9zaGEyNTYnOiBvdXRlciwKICAgICAgICAgICAgICAgICAgICdtYW5pZmVzdCc6IG1hbmlmZXN0LCAna2V5X2lkJzogcHVibGljX21ldGFkYXRhWydrZXlfaWQnXSwgJ2NvbnRleHQnOiBjb250ZXh0fQoKCmRlZiBfbzJfZGlyZWN0b3J5KHBhdGgpOgogICAgIiIiT3BlbiBldmVyeSBkaXJlY3RvcnkgY29tcG9uZW50IHdpdGhvdXQgZm9sbG93aW5nIHN5bWxpbmtzLiIiIgogICAgcGF0aCA9IFBhdGgocGF0aCkKICAgIGlmIG5vdCBwYXRoLmlzX2Fic29sdXRlKCkgb3IgJy4uJyBpbiBwYXRoLnBhcnRzOgogICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoJ3Njb3BlJykKICAgIGZsYWdzID0gb3MuT19SRE9OTFkgfCBvcy5PX0RJUkVDVE9SWSB8IG9zLk9fTk9GT0xMT1cgfCBvcy5PX0NMT0VYRUMKICAgIGZkID0gb3Mub3BlbignLycsIGZsYWdzKQogICAgdHJ5OgogICAgICAgIGZvciBwYXJ0IGluIHBhdGgucGFydHNbMTpdOgogICAgICAgICAgICBjaGlsZCA9IG9zLm9wZW4ocGFydCwgZmxhZ3MsIGRpcl9mZD1mZCkKICAgICAgICAgICAgb3MuY2xvc2UoZmQpCiAgICAgICAgICAgIGZkID0gY2hpbGQKICAgICAgICByZXR1cm4gZmQKICAgIGV4Y2VwdCBCYXNlRXhjZXB0aW9uOgogICAgICAgIG9zLmNsb3NlKGZkKQogICAgICAgIHJhaXNlCgoKZGVmIF9vMl9yZWFkKHBhdGgsIGxpbWl0LCAqLCBkaWdlc3Rfb25seT1GYWxzZSwgZGVhZGxpbmU9Tm9uZSk6CiAgICAiIiJCb3VuZGVkIHJlZ3VsYXItZmlsZSByZWFkOyBjb25maXJtIHRoZSBuYW1lZCBpbm9kZSBzdGlsbCBtYXRjaGVzLgoKICAgIE5vIGVycm9yIHRleHQgb3Igc291cmNlIGJ5dGVzIGFyZSByZXR1cm5lZCBmb3IgYSBmYWlsZWQgcmVhZC4gVGhlIHRpbWUKICAgIGNoZWNrIGJvdW5kcyBwcm9ncmVzcyBiZXR3ZWVuIHJlYWRzOyBpdCBjYW5ub3QgaW50ZXJydXB0IGEgYmxvY2tlZCBrZXJuZWwgSU8uCiAgICAiIiIKICAgIGltcG9ydCBoYXNobGliLCBzdGF0CiAgICBwYXRoID0gUGF0aChwYXRoKQogICAgcGFyZW50ID0gZmlsZV9mZCA9IGNoZWNrZWRfcGFyZW50ID0gTm9uZQogICAgdHJ5OgogICAgICAgIHBhcmVudCA9IF9vMl9kaXJlY3RvcnkocGF0aC5wYXJlbnQpCiAgICAgICAgZmlsZV9mZCA9IG9zLm9wZW4ocGF0aC5uYW1lLCBvcy5PX1JET05MWSB8IG9zLk9fTk9GT0xMT1cgfCBvcy5PX05PTkJMT0NLIHwgb3MuT19DTE9FWEVDLCBkaXJfZmQ9cGFyZW50KQogICAgICAgIGJlZm9yZSA9IG9zLmZzdGF0KGZpbGVfZmQpCiAgICAgICAgaWYgbm90IHN0YXQuU19JU1JFRyhiZWZvcmUuc3RfbW9kZSkgb3IgYmVmb3JlLnN0X3NpemUgPiBsaW1pdDoKICAgICAgICAgICAgcmFpc2UgVmFsdWVFcnJvcigndHlwZV9vcl9zaXplJykKICAgICAgICBpZGVudGl0eSA9IGxhbWJkYSB2YWx1ZTogKHZhbHVlLnN0X2Rldix2YWx1ZS5zdF9pbm8sdmFsdWUuc3Rfc2l6ZSx2YWx1ZS5zdF9tdGltZV9ucyx2YWx1ZS5zdF9jdGltZV9ucykKICAgICAgICBkaWdlc3QsIGNodW5rcywgdG90YWwgPSBoYXNobGliLnNoYTI1NigpLCBbXSwgMAogICAgICAgIHdoaWxlIFRydWU6CiAgICAgICAgICAgIGlmIGRlYWRsaW5lIGlzIG5vdCBOb25lIGFuZCB0aW1lLm1vbm90b25pYygpID4gZGVhZGxpbmU6CiAgICAgICAgICAgICAgICByYWlzZSBWYWx1ZUVycm9yKCd0aW1lJykKICAgICAgICAgICAgYmxvY2sgPSBvcy5yZWFkKGZpbGVfZmQsIG1pbigxNjM4NCxsaW1pdC10b3RhbCsxKSkKICAgICAgICAgICAgaWYgbm90IGJsb2NrOgogICAgICAgICAgICAgICAgYnJlYWsKICAgICAgICAgICAgdG90YWwgKz0gbGVuKGJsb2NrKQogICAgICAgICAgICBpZiB0b3RhbCA+IGxpbWl0OgogICAgICAgICAgICAgICAgcmFpc2UgVmFsdWVFcnJvcignZ3Jvd3RoJykKICAgICAgICAgICAgZGlnZXN0LnVwZGF0ZShibG9jaykKICAgICAgICAgICAgaWYgbm90IGRpZ2VzdF9vbmx5OgogICAgICAgICAgICAgICAgY2h1bmtzLmFwcGVuZChibG9jaykKICAgICAgICBjaGVja2VkX3BhcmVudCA9IF9vMl9kaXJlY3RvcnkocGF0aC5wYXJlbnQpCiAgICAgICAgb2xkX2RpciwgbmV3X2RpciA9IG9zLmZzdGF0KHBhcmVudCksIG9zLmZzdGF0KGNoZWNrZWRfcGFyZW50KQogICAgICAgIG5hbWVkID0gb3Muc3RhdChwYXRoLm5hbWUsIGRpcl9mZD1jaGVja2VkX3BhcmVudCwgZm9sbG93X3N5bWxpbmtzPUZhbHNlKQogICAgICAgIGlmICgob2xkX2Rpci5zdF9kZXYsb2xkX2Rpci5zdF9pbm8pICE9IChuZXdfZGlyLnN0X2RldixuZXdfZGlyLnN0X2lubykKICAgICAgICAgICAgICAgIG9yIGlkZW50aXR5KGJlZm9yZSkgIT0gaWRlbnRpdHkob3MuZnN0YXQoZmlsZV9mZCkpIG9yIGlkZW50aXR5KGJlZm9yZSkgIT0gaWRlbnRpdHkobmFtZWQpKToKICAgICAgICAgICAgcmFpc2UgVmFsdWVFcnJvcignY2hhbmdlZCcpCiAgICAgICAgaWYgdG90YWwgIT0gYmVmb3JlLnN0X3NpemU6CiAgICAgICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoJ2NoYW5nZWRfc2l6ZScpCiAgICAgICAgcmV0dXJuIHsnc3RhdGUnOidPQlNFUlZFRCcsJ2J5dGVzX3JlYWQnOnRvdGFsLCdzaGEyNTYnOmRpZ2VzdC5oZXhkaWdlc3QoKSwKICAgICAgICAgICAgICAgICd2YWx1ZSc6Tm9uZSBpZiBkaWdlc3Rfb25seSBlbHNlIGInJy5qb2luKGNodW5rcyl9CiAgICBleGNlcHQgKE9TRXJyb3IsVmFsdWVFcnJvcik6CiAgICAgICAgcmV0dXJuIHsnc3RhdGUnOidVTktOT1dOX1VOU0FGRV9VTlJFQURBQkxFX0NIQU5HRURfT1JfTElNSVQnLCdieXRlc19yZWFkJzowLCdzaGEyNTYnOk5vbmUsJ3ZhbHVlJzpOb25lfQogICAgZmluYWxseToKICAgICAgICBmb3IgZmQgaW4gKGZpbGVfZmQscGFyZW50LGNoZWNrZWRfcGFyZW50KToKICAgICAgICAgICAgaWYgZmQgaXMgbm90IE5vbmU6CiAgICAgICAgICAgICAgICBvcy5jbG9zZShmZCkKCgo='
O2_SOURCE_TRANSPORT_SHA = '8a442972b01d3068634592542f61795de8676915ed3e0fb03c465a2027de8c0e'
O2_SOURCE_PUBLIC_METADATA = {'schema': 'NOX_FIXED_SOURCE_PUBLIC_KEY_V1', 'key_id': 'c6c12dbf2fb366a21848fd7bd39999bd54568b82c4f505a3458075c80aecf5dd', 'public_key_pem': '-----BEGIN PUBLIC KEY-----\nMIICIjANBgkqhkiG9w0BAQEFAAOCAg8AMIICCgKCAgEAzIjdYB7OL9sr8Tb+Pwlm\nlkrrwdapRm4yMgbz7HSSxeBhLp638kUWMiVq5UXJywwjsACE7n5tAZ6GgIV6AVWV\nOkAOAPEOevdtdNLkFDczue98OhzDt8F4jp0woTQzQjdOL/G+Q6zfOFYu5zgA50kI\ncFvAS6/SsHNpbHA9TxMU8VLDLwgiSSukyVa12Qs9HKI4t7AJS6d2pVY+15c/OF9Y\nk6N15qQNAA4heIvzKEZ/c98XUW0UgekPyWRJommVyCiLF5X3R3mS31/iJRhuOzQV\n0n6lmuSJ15E6Jpw7LOs1WnUKia6lbM+30JKALrKF0SI5AjCFhZccY7/gKM9AxXg7\nKKBMdgorgqgzisleC93tfAN7RMFiWm9eidvdDBdmOLLtFUGF7lHlXG7Avt84eDQL\nlV2vk+/6PshSv8LnCPfFRLqZYUUWp3H7kWN056LkXzaTczaJ1FwB3CIyDxifpV3I\nBRwUXuXTczLv3q/j15lHBtRaTWYDXpBcDPFdeOU1tGi1W7LQSjrAOJ6mm3UNCsM9\nkEsMqjMW5zRCbNhPkkPSgRWDRP8yCwX2igZ96s1XG4keCKKZSmsI75yH3DzgwDkH\nN8BDf9xny3HE22zfC2Onu0pGIc1VQCIz0/h8RJzoCUxo7BzEbkSCnb7R1oyMFtdo\nWtAcl8LsSGwMQaAsf8axB8sCAwEAAQ==\n-----END PUBLIC KEY-----\n', 'transfer_id': '9ac7782253048ad338e83e3cbff807cd', 'created_at': 1794939770, 'expires_at': 1794943370, 'scope_sha256': '4b54e425d70dd9ac2003f3593d588a131fb2b7ed2c57563be96e459c3f3e37a2'}

O2_SOURCE_CHILD = r'''
import sys
sys.dont_write_bytecode = True
import base64, hashlib, json, types
stage = 'INPUT'
try:
    raw = sys.stdin.buffer.read(131073)
    if len(raw) > 131072:
        raise ValueError()
    value = json.loads(raw)
    stage = 'CRYPTO_AND_SOURCE_MODULES'
    for name in ('owner_media_fixture_transport', 'owner_source_readback_transport'):
        item = value['modules'][name]
        code = base64.b64decode(item['bytes'], validate=True)
        if len(code) > 65536 or hashlib.sha256(code).hexdigest() != item['sha256']:
            raise ValueError()
        module = types.ModuleType(name)
        sys.modules[name] = module
        exec(compile(code, '<fixed-source-readback>', 'exec'), module.__dict__)
    stage = 'COLLECT_AND_SEAL'
    rows = sys.modules['owner_source_readback_transport'].seal(
        value['public_metadata'], value['request'], value['source_sha'])
    stage = 'EMIT_CIPHERTEXT'
    for row in rows:
        print('NOX_MAINT_AUDIT=' + json.dumps(row, separators=(',', ':'), allow_nan=False), flush=True)
    print('NOX_MAINT_AUDIT_COMPLETE=true', flush=True)
except BaseException:
    # Neither exception text nor native source bytes can cross this boundary.
    print('NOX_MAINT_AUDIT=' + json.dumps({'kind': 'source_export_failure', 'data': {
        'stage': stage, 'reason': 'HOLD_ENCRYPTED_SOURCE_READBACK'}}), flush=True)
    raise SystemExit(2)
'''


def encrypted_source_readback():
    """Existing owner context only; a clean child emits ciphertext or fixed HOLD.

    The 3s source-read progress budget does not interrupt a blocked kernel IO.
    The isolated child has a separate 60s timeout; the existing SSH operator's
    150s audit timeout and cleanup contract remain unchanged.
    """
    import base64, hashlib
    request = os.environ.get('NOX_OWNER_REQUEST_ID', '')
    source = os.environ.get('NOX_OWNER_SOURCE_SHA', '')
    try:
        if not re.fullmatch('[0-9]{1,24}', request) or not re.fullmatch('[a-f0-9]{40}', source):
            raise ValueError()
        modules = {}
        for name, encoded, pin in (
                ('owner_media_fixture_transport', O2_SOURCE_PRIMITIVES, O2_SOURCE_PRIMITIVES_SHA),
                ('owner_source_readback_transport', O2_SOURCE_TRANSPORT, O2_SOURCE_TRANSPORT_SHA)):
            code = base64.b64decode(encoded, validate=True)
            if len(code) > 65536 or hashlib.sha256(code).hexdigest() != pin:
                raise ValueError()
            modules[name] = {'bytes': encoded, 'sha256': pin}
        payload = json.dumps({'modules': modules, 'public_metadata': O2_SOURCE_PUBLIC_METADATA,
                              'request': request, 'source_sha': source}).encode()
        if len(payload) > 131072:
            raise ValueError()
        result = subprocess.run(['/usr/bin/python3', '-I', '-B', '-c', O2_SOURCE_CHILD],
            input=payload, capture_output=True, timeout=60,
            env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'PYTHONNOUSERSITE': '1',
                 'PYTHONDONTWRITEBYTECODE': '1', 'CUDA_VISIBLE_DEVICES': '',
                 'OMP_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1'})
        if result.returncode or len(result.stdout) > 3 * 1024 * 1024:
            raise ValueError()
        lines = result.stdout.decode('ascii').splitlines()
        if not 3 <= len(lines) <= 49 or lines[-1] != 'NOX_MAINT_AUDIT_COMPLETE=true':
            raise ValueError()
        for line in lines[:-1]:
            if len(line) >= 80000 or not line.startswith('NOX_MAINT_AUDIT='):
                raise ValueError()
            row = json.loads(line.split('=', 1)[1])
            if set(row) != {'kind', 'data'} or row['kind'] not in (
                    'source_ciphertext_header', 'source_ciphertext_chunk'):
                raise ValueError()
        for line in lines:
            print(line, flush=True)
        return 0
    except Exception:
        # Never echo unverified child stdout/stderr, tracebacks, or exception text.
        print('NOX_MAINT_AUDIT=' + json.dumps({'kind': 'source_export_failure', 'data': {
            'stage': 'BOUNDED_EXPORT', 'reason': 'HOLD_ENCRYPTED_SOURCE_READBACK'}}), flush=True)
        return 2


def full_audit():
    """Legacy seven-section OS audit; only runs by explicit profile selection."""
    with ProcessPoolExecutor(max_workers=7) as pool:
        for row in pool.map(worker,range(7)):
            print('NOX_MAINT_AUDIT=' + json.dumps(row, separators=(',', ':')), flush=True)
    print('NOX_MAINT_AUDIT_COMPLETE=true', flush=True)
    return 0


def main(profile='encrypted-source-readback'):
    if profile == 'encrypted-source-readback':
        return encrypted_source_readback()
    if profile == 'mapping-readback':
        row = {'section': 'native_mapping_readback', 'worker_pid': os.getpid(),
               'result': native_mapping_readback()}
        print('NOX_MAINT_AUDIT=' + json.dumps(row, separators=(',', ':'), allow_nan=False), flush=True)
        print('NOX_MAINT_AUDIT_COMPLETE=true', flush=True)
        return 0
    if profile == 'full-audit':
        return full_audit()
    raise ValueError('unknown audit profile')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile', choices=('encrypted-source-readback', 'mapping-readback', 'full-audit'),
                        default='encrypted-source-readback')
    raise SystemExit(main(parser.parse_args().profile))
