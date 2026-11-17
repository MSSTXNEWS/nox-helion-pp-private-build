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
O2_SOURCE_TRANSPORT = 'IiIiT25lLXVzZSBhdXRoZW50aWNhdGVkIHJlYWRiYWNrIG9mIGZpeGVkIHNvdXJjZSBmaWxlczsgbm8gbmF0aXZlIHdyaXRlcy4KCkNyeXB0byBwcmltaXRpdmVzIGFuZCBlbnZlbG9wZSBjb25zdHJ1Y3Rpb24gZm9sbG93IHRoZSBleGlzdGluZyByZXZpZXdlZApvd25lcl9tZWRpYV9maXh0dXJlX3RyYW5zcG9ydC4gU291cmNlIGJ5dGVzIG5ldmVyIGxlYXZlIGFuIGVuY3J5cHRlZCBlbnZlbG9wZS4KTm8gY29uZmlndXJhdGlvbiwgc3RhdGUsIGVudmlyb25tZW50IGR1bXAsIGhpc3Rvcnkgb3IgdXNlciBkYXRhIGlzIHNlbGVjdGVkLgoiIiIKZnJvbSBfX2Z1dHVyZV9fIGltcG9ydCBhbm5vdGF0aW9ucwppbXBvcnQgaGFzaGxpYgppbXBvcnQganNvbgppbXBvcnQgb3MKZnJvbSBwYXRobGliIGltcG9ydCBQYXRoCmltcG9ydCByZQppbXBvcnQgdGltZQppbXBvcnQgb3duZXJfbWVkaWFfZml4dHVyZV90cmFuc3BvcnQgYXMgcHJpbWl0aXZlcwoKRklMRVMgPSAoeydyZWxhdGl2ZV9wYXRoJzogJ3NjcmlwdHMvY2hhdF9wcm94eS5weScsICdieXRlcyc6IDEwMDE0OSwgJ3NoYTI1Nic6ICdhMDMxMTk4MTdkNjk1YjFkYzdjYTI2ODFhNjBiYzU2NGEwYWE4OTE0Njg1ODJiYmYxMWI3MDU5MmUyYjRkZmQ2J30sIHsncmVsYXRpdmVfcGF0aCc6ICdzY3JpcHRzL25veF92MjlfY2hhdF9icmlkZ2UucHknLCAnYnl0ZXMnOiA0NzgzMSwgJ3NoYTI1Nic6ICcwY2ZmMmU3YWVlMDY4NTcxYjI4OTVlYzQ3NjI1NWU5N2VmM2I4NWJkOTMxMDRhMjdhODIyYWNmYjg0MDg2MzJiJ30sIHsncmVsYXRpdmVfcGF0aCc6ICdzY3JpcHRzL25veF9wcmlvcml0eV9hcmJpdGVyLnB5JywgJ2J5dGVzJzogODgxNSwgJ3NoYTI1Nic6ICc0YzlkZjliYmRhYTJkNzg4NzY2MDkwYjQ2NmUzYWZmMjI2ZDNjMjE0Y2U5MzZhYzE1NTllNzg1NmE5MTkwYmUwJ30sIHsncmVsYXRpdmVfcGF0aCc6ICdzY3JpcHRzL293bmVyX2NoYXRfdWkucHknLCAnYnl0ZXMnOiA0ODU0LCAnc2hhMjU2JzogJ2RhMmNlYTIxZDIxZDNjMTEyOWJjYjY2MjFjZDUyOTM0NjlhMDg1YWQ4NjE5MjRhOGM1Y2M2Mzk4MTU3N2E4NjYnfSwgeydyZWxhdGl2ZV9wYXRoJzogJ3NjcmlwdHMvbm94X3dlYjI5X29uZWhvc3RfMTg3NzUucHknLCAnYnl0ZXMnOiAyODI1LCAnc2hhMjU2JzogJzBhMDE2NWU1YjA2MWY4OGVjNjAwMDljNDlhM2MxMmU5ODIzYTQ1Yjg5MDQ0NjA0MTg2ZTMwN2M4MWZiNzAxZTYnfSwgeydyZWxhdGl2ZV9wYXRoJzogJ3NjcmlwdHMvbm94X2Rpc3BhdGNoZXJfdDg1NXUucHknLCAnYnl0ZXMnOiA3MTM5NywgJ3NoYTI1Nic6ICc5YWUwYzY3NTIzOTY3NzU2MjA2YTBkYTMxZDFhMWNhYjY1MjgxZGMyZjRmMjg5ODlmMjE1NmNkMjdkYTQzYTIxJ30sIHsncmVsYXRpdmVfcGF0aCc6ICdpbmNvbWluZ190ODAwdS92MjlfMy9OT1hfSEVMSU9OX1dFQl9WMjlfM19GUk9aRU5fMjAyNjExMTMvc2l0ZS9wYy9yZXNvbmFuY2UuaHRtbCcsICdieXRlcyc6IDEzOTg0LCAnc2hhMjU2JzogJzU5N2VkZTdjZjY4ZTc2MDZmYzZiNzYxZjdkMzY2ZTE0NzM3Zjg2ZmZhNTBkNjQ4YjYzNzg1N2IyMjc1ZDA3MGInfSwgeydyZWxhdGl2ZV9wYXRoJzogJ2luY29taW5nX3Q4MDB1L3YyOV8zL05PWF9IRUxJT05fV0VCX1YyOV8zX0ZST1pFTl8yMDI2MTExMy9zaXRlL3BjL25veC1jaGF0LmpzJywgJ2J5dGVzJzogNjU0MjUsICdzaGEyNTYnOiAnN2ZjZDRhYmY3ZjA5MGNhNjZjNTRkOTBlNDMyZjRjNGU0MzNlODg3ZTBiYTVlYTBjODlmZTFhY2FmM2EzNDIzOCd9LCB7J3JlbGF0aXZlX3BhdGgnOiAnc2NyaXB0cy9vd25lcl9jaGF0X3N0cmVhbS5weScsICdieXRlcyc6IE5vbmUsICdzaGEyNTYnOiBOb25lfSwgeydyZWxhdGl2ZV9wYXRoJzogJ3NjcmlwdHMvb3duZXJfc3ViYWdlbnRfZGlzcGF0Y2hlci5weScsICdieXRlcyc6IE5vbmUsICdzaGEyNTYnOiBOb25lfSwgeydyZWxhdGl2ZV9wYXRoJzogJ3NjcmlwdHMvb3duZXJfc3ViYWdlbnRfcHJvY2Vzc2VzLnB5JywgJ2J5dGVzJzogTm9uZSwgJ3NoYTI1Nic6IE5vbmV9LCB7J3JlbGF0aXZlX3BhdGgnOiAnc2NyaXB0cy9vd25lcl9hdXRvbm9teV9wb29sLnB5JywgJ2J5dGVzJzogTm9uZSwgJ3NoYTI1Nic6IE5vbmV9LCB7J3JlbGF0aXZlX3BhdGgnOiAnc2NyaXB0cy9hZ2VudF9sb29wLnB5JywgJ2J5dGVzJzogTm9uZSwgJ3NoYTI1Nic6IE5vbmV9KQpGSUxFX0xJTUlUID0gMjYyMTQ0ClRPVEFMX0xJTUlUID0gMjA5NzE1MgpDSFVOS19DSEFSUyA9IDYwMDAwCk1BWF9DSFVOS1MgPSA0NwpNQVhfVFRMID0gMzYwMApBTEdPUklUSE0gPSAnUlNBNDA5Ni1PQUVQLVNIQTI1NitBMjU2R0NNJwpPQUVQX0xBQkVMID0gYidOT1hfRklYRURfU09VUkNFX1JFQURCQUNLX1YxJwpTVEFURVMgPSBmcm96ZW5zZXQoKCdPQlNFUlZFRCcsICdVTktOT1dOX1VOU0FGRV9VTlJFQURBQkxFX0NIQU5HRURfT1JfTElNSVQnLAogICAgICAgICAgICAgICAgICAgICdVTktOT1dOX1RPVEFMX0JVREdFVCcsICdVTktOT1dOX1BJTl9NSVNNQVRDSCcpKQoKCmNsYXNzIFNvdXJjZUhvbGQoUnVudGltZUVycm9yKToKICAgIHBhc3MKCgpkZWYgcmVxdWlyZShjb25kaXRpb24pOgogICAgaWYgbm90IGNvbmRpdGlvbjoKICAgICAgICByYWlzZSBTb3VyY2VIb2xkKCdIT0xEX1NPVVJDRV9SRUFEQkFDSycpCgoKZGVmIGNhbm9uaWNhbCh2YWx1ZSk6CiAgICByZXR1cm4gcHJpbWl0aXZlcy5jYW5vbmljYWwodmFsdWUpCgoKZGVmIGRpZ2VzdCh2YWx1ZSk6CiAgICByZXR1cm4gaGFzaGxpYi5zaGEyNTYodmFsdWUpLmhleGRpZ2VzdCgpCgoKZGVmIGlzX3NoYSh2YWx1ZSk6CiAgICByZXR1cm4gaXNpbnN0YW5jZSh2YWx1ZSwgc3RyKSBhbmQgcmUuZnVsbG1hdGNoKCdbYS1mMC05XXs2NH0nLCB2YWx1ZSkgaXMgbm90IE5vbmUKCgpkZWYgc2NvcGUoKToKICAgIHJldHVybiB7J3NjaGVtYSc6ICdOT1hfRklYRURfU09VUkNFX1NDT1BFX1YxJywgJ2luc3RhbmNlX2lkJzogNjA1MDk1NTEsCiAgICAgICAgICAgICdmaWxlcyc6IGxpc3QoRklMRVMpLCAnZmlsZV9saW1pdCc6IEZJTEVfTElNSVQsICd0b3RhbF9saW1pdCc6IFRPVEFMX0xJTUlULAogICAgICAgICAgICAnc2VsZWN0aW9uJzogJ0ZJWEVEX1NPVVJDRV9BTkRfVUlfT05MWScsICduYXRpdmVfbXV0YXRpb25zJzogRmFsc2V9CgoKZGVmIHNjb3BlX3NoYSgpOgogICAgcmV0dXJuIGRpZ2VzdChjYW5vbmljYWwoc2NvcGUoKSkpCgoKZGVmIHB1YmxpY19rZXlfbWV0YWRhdGEodmFsdWUsIG5vdz1Ob25lKToKICAgIG5vdyA9IGludCh0aW1lLnRpbWUoKSkgaWYgbm93IGlzIE5vbmUgZWxzZSBub3cKICAgIHJlcXVpcmUoaXNpbnN0YW5jZSh2YWx1ZSwgZGljdCkgYW5kIHNldCh2YWx1ZSkgPT0geydzY2hlbWEnLCAna2V5X2lkJywgJ3B1YmxpY19rZXlfcGVtJywKICAgICAgICAgICAgJ3RyYW5zZmVyX2lkJywgJ2NyZWF0ZWRfYXQnLCAnZXhwaXJlc19hdCcsICdzY29wZV9zaGEyNTYnfSkKICAgIHJlcXVpcmUodmFsdWVbJ3NjaGVtYSddID09ICdOT1hfRklYRURfU09VUkNFX1BVQkxJQ19LRVlfVjEnCiAgICAgICAgICAgIGFuZCB2YWx1ZVsnc2NvcGVfc2hhMjU2J10gPT0gc2NvcGVfc2hhKCkKICAgICAgICAgICAgYW5kIGlzaW5zdGFuY2UodmFsdWVbJ3RyYW5zZmVyX2lkJ10sIHN0cikKICAgICAgICAgICAgYW5kIHJlLmZ1bGxtYXRjaCgnW2EtZjAtOV17MzJ9JywgdmFsdWVbJ3RyYW5zZmVyX2lkJ10pCiAgICAgICAgICAgIGFuZCB0eXBlKHZhbHVlWydjcmVhdGVkX2F0J10pIGlzIGludCBhbmQgdHlwZSh2YWx1ZVsnZXhwaXJlc19hdCddKSBpcyBpbnQKICAgICAgICAgICAgYW5kIDAgPCB2YWx1ZVsnZXhwaXJlc19hdCddIC0gdmFsdWVbJ2NyZWF0ZWRfYXQnXSA8PSBNQVhfVFRMCiAgICAgICAgICAgIGFuZCB2YWx1ZVsnY3JlYXRlZF9hdCddIC0gNSA8PSBub3cgPCB2YWx1ZVsnZXhwaXJlc19hdCddKQogICAgcGVtID0gdmFsdWVbJ3B1YmxpY19rZXlfcGVtJ10KICAgIHJlcXVpcmUoaXNpbnN0YW5jZShwZW0sIHN0cikgYW5kIHBlbS5zdGFydHN3aXRoKCctLS0tLUJFR0lOIFBVQkxJQyBLRVktLS0tLVxuJykgYW5kIGxlbihwZW0pIDw9IDEyMDApCiAgICBrZXkgPSBwcmltaXRpdmVzLnNlcmlhbGl6YXRpb24ubG9hZF9wZW1fcHVibGljX2tleShwZW0uZW5jb2RlKCdhc2NpaScpKQogICAgcmVxdWlyZShpc2luc3RhbmNlKGtleSwgcHJpbWl0aXZlcy5yc2EuUlNBUHVibGljS2V5KSBhbmQga2V5LmtleV9zaXplID09IDQwOTYKICAgICAgICAgICAgYW5kIGtleS5wdWJsaWNfbnVtYmVycygpLmUgPT0gNjU1MzcpCiAgICBkZXIgPSBrZXkucHVibGljX2J5dGVzKHByaW1pdGl2ZXMuc2VyaWFsaXphdGlvbi5FbmNvZGluZy5ERVIsCiAgICAgICAgICAgICAgICAgICAgICAgICAgIHByaW1pdGl2ZXMuc2VyaWFsaXphdGlvbi5QdWJsaWNGb3JtYXQuU3ViamVjdFB1YmxpY0tleUluZm8pCiAgICByZXF1aXJlKHZhbHVlWydrZXlfaWQnXSA9PSBkaWdlc3QoZGVyKSkKICAgIHJldHVybiBrZXkKCgpkZWYgcmVhZF9zb3VyY2VzKHJvb3Q9UGF0aCgnL3Jvb3Qvbm94JykpOgogICAgIiIiU3RhYmxlIG5vLWZvbGxvdyByZWFkcywgaW5jbHVkaW5nIGFuY2VzdG9yczsgM3MgY29vcGVyYXRpdmUgSU8gYnVkZ2V0LgoKICAgIFRoZSBkZWFkbGluZSBpcyBjaGVja2VkIGJldHdlZW4gcmVhZHMuIEl0IGNhbm5vdCBpbnRlcnJ1cHQgYSBibG9ja2VkIGtlcm5lbAogICAgc3lzY2FsbC4gVGhlIGVuY2xvc2luZyBpc29sYXRlZCBzdWJwcm9jZXNzIGhhcyBhIHNlcGFyYXRlIDYwcyB0aW1lb3V0LgogICAgVW5rbm93biBmaWxlcyBjb25zdW1lIHRoZWlyIHdob2xlIGF0dGVtcHRlZCBhbGxvd2FuY2UsIHByZXZlbnRpbmcgcmVzZXQgb2YKICAgIHRoZSBhZ2dyZWdhdGUgcmVhZCBidWRnZXQuIE9ubHkgZXhhY3QgcGlubmVkIGJ5dGVzIG9yIG5ldyBmaXhlZCBwYXRocyBzZWFsLgogICAgIiIiCiAgICByb3dzLCBwYXlsb2FkLCByZW1haW5pbmcgPSBbXSwgW10sIFRPVEFMX0xJTUlUCiAgICBkZWFkbGluZSA9IHRpbWUubW9ub3RvbmljKCkgKyAzCiAgICBmb3Igc2VsZWN0ZWQgaW4gRklMRVM6CiAgICAgICAgcmVsYXRpdmUgPSBzZWxlY3RlZFsncmVsYXRpdmVfcGF0aCddCiAgICAgICAgY2FwID0gbWluKEZJTEVfTElNSVQsIG1heCgwLCByZW1haW5pbmcgLSAxKSkKICAgICAgICByZWFkID0gKF9vMl9yZWFkKFBhdGgocm9vdCkgLyByZWxhdGl2ZSwgY2FwLCBkZWFkbGluZT1kZWFkbGluZSkgaWYgcmVtYWluaW5nIGVsc2UKICAgICAgICAgICAgICAgIHsnc3RhdGUnOiAnVU5LTk9XTl9UT1RBTF9CVURHRVQnLCAnYnl0ZXNfcmVhZCc6IDAsICdzaGEyNTYnOiBOb25lLCAndmFsdWUnOiBOb25lfSkKICAgICAgICByZW1haW5pbmcgLT0gKHJlYWRbJ2J5dGVzX3JlYWQnXSBpZiByZWFkWydzdGF0ZSddID09ICdPQlNFUlZFRCcgZWxzZSBtaW4oY2FwICsgMSwgcmVtYWluaW5nKSkKICAgICAgICBzdGF0ZSA9IHJlYWRbJ3N0YXRlJ10KICAgICAgICBpZiBzdGF0ZSA9PSAnT0JTRVJWRUQnIGFuZCBzZWxlY3RlZFsnc2hhMjU2J10gaXMgbm90IE5vbmU6CiAgICAgICAgICAgIGlmIHJlYWRbJ3NoYTI1NiddICE9IHNlbGVjdGVkWydzaGEyNTYnXSBvciByZWFkWydieXRlc19yZWFkJ10gIT0gc2VsZWN0ZWRbJ2J5dGVzJ106CiAgICAgICAgICAgICAgICBzdGF0ZSA9ICdVTktOT1dOX1BJTl9NSVNNQVRDSCcKICAgICAgICBhY2NlcHRlZCA9IHN0YXRlID09ICdPQlNFUlZFRCcKICAgICAgICByb3dzLmFwcGVuZCh7J3JlbGF0aXZlX3BhdGgnOiByZWxhdGl2ZSwgJ3N0YXRlJzogc3RhdGUsCiAgICAgICAgICAgICAgICAgICAgICdieXRlcyc6IHJlYWRbJ2J5dGVzX3JlYWQnXSBpZiBhY2NlcHRlZCBlbHNlIE5vbmUsCiAgICAgICAgICAgICAgICAgICAgICdzaGEyNTYnOiByZWFkWydzaGEyNTYnXSBpZiBhY2NlcHRlZCBlbHNlIE5vbmV9KQogICAgICAgIGlmIGFjY2VwdGVkOgogICAgICAgICAgICBwYXlsb2FkLmFwcGVuZChyZWFkWyd2YWx1ZSddKQogICAgcmF3ID0gYicnLmpvaW4ocGF5bG9hZCkKICAgIHJlcXVpcmUobGVuKHJhdykgPD0gVE9UQUxfTElNSVQpCiAgICBtYW5pZmVzdCA9IHsnc2NoZW1hJzogJ05PWF9GSVhFRF9TT1VSQ0VfTUFOSUZFU1RfVjEnLCAnc2NvcGVfc2hhMjU2Jzogc2NvcGVfc2hhKCksCiAgICAgICAgICAgICAgICAnZmlsZXMnOiByb3dzLCAncGxhaW50ZXh0X2J5dGVzJzogbGVuKHJhdyksICdwbGFpbnRleHRfc2hhMjU2JzogZGlnZXN0KHJhdyksCiAgICAgICAgICAgICAgICAnY29tcGxldGUnOiBhbGwocm93WydzdGF0ZSddID09ICdPQlNFUlZFRCcgZm9yIHJvdyBpbiByb3dzKSwKICAgICAgICAgICAgICAgICdyZWFkX29ubHknOiBUcnVlLCAnbmF0aXZlX2FjY2VwdGVkJzogRmFsc2UsCiAgICAgICAgICAgICAgICAnc2VydmluZ19hbmRfZXhlY3V0ZWRfbWFwcGluZyc6ICdVTktOT1dOJ30KICAgIHJldHVybiByYXcsIG1hbmlmZXN0CgoKZGVmIHZhbGlkYXRlX21hbmlmZXN0KG1hbmlmZXN0KToKICAgIHJlcXVpcmUoaXNpbnN0YW5jZShtYW5pZmVzdCwgZGljdCkgYW5kIHNldChtYW5pZmVzdCkgPT0geydzY2hlbWEnLCAnc2NvcGVfc2hhMjU2JywgJ2ZpbGVzJywKICAgICAgICAgICAgJ3BsYWludGV4dF9ieXRlcycsICdwbGFpbnRleHRfc2hhMjU2JywgJ2NvbXBsZXRlJywgJ3JlYWRfb25seScsICduYXRpdmVfYWNjZXB0ZWQnLAogICAgICAgICAgICAnc2VydmluZ19hbmRfZXhlY3V0ZWRfbWFwcGluZyd9KQogICAgcmVxdWlyZShtYW5pZmVzdFsnc2NoZW1hJ10gPT0gJ05PWF9GSVhFRF9TT1VSQ0VfTUFOSUZFU1RfVjEnIGFuZCBtYW5pZmVzdFsnc2NvcGVfc2hhMjU2J10gPT0gc2NvcGVfc2hhKCkKICAgICAgICAgICAgYW5kIG1hbmlmZXN0WydyZWFkX29ubHknXSBpcyBUcnVlIGFuZCBtYW5pZmVzdFsnbmF0aXZlX2FjY2VwdGVkJ10gaXMgRmFsc2UKICAgICAgICAgICAgYW5kIG1hbmlmZXN0WydzZXJ2aW5nX2FuZF9leGVjdXRlZF9tYXBwaW5nJ10gPT0gJ1VOS05PV04nCiAgICAgICAgICAgIGFuZCB0eXBlKG1hbmlmZXN0WydwbGFpbnRleHRfYnl0ZXMnXSkgaXMgaW50IGFuZCAwIDw9IG1hbmlmZXN0WydwbGFpbnRleHRfYnl0ZXMnXSA8PSBUT1RBTF9MSU1JVAogICAgICAgICAgICBhbmQgaXNfc2hhKG1hbmlmZXN0WydwbGFpbnRleHRfc2hhMjU2J10pKQogICAgcm93cyA9IG1hbmlmZXN0WydmaWxlcyddCiAgICByZXF1aXJlKGlzaW5zdGFuY2Uocm93cywgbGlzdCkgYW5kIGxlbihyb3dzKSA9PSBsZW4oRklMRVMpKQogICAgdG90YWwgPSAwCiAgICBmb3Igc2VsZWN0ZWQsIHJvdyBpbiB6aXAoRklMRVMsIHJvd3MpOgogICAgICAgIHJlcXVpcmUoaXNpbnN0YW5jZShyb3csIGRpY3QpIGFuZCBzZXQocm93KSA9PSB7J3JlbGF0aXZlX3BhdGgnLCAnc3RhdGUnLCAnYnl0ZXMnLCAnc2hhMjU2J30KICAgICAgICAgICAgICAgIGFuZCByb3dbJ3JlbGF0aXZlX3BhdGgnXSA9PSBzZWxlY3RlZFsncmVsYXRpdmVfcGF0aCddIGFuZCByb3dbJ3N0YXRlJ10gaW4gU1RBVEVTKQogICAgICAgIGlmIHJvd1snc3RhdGUnXSA9PSAnT0JTRVJWRUQnOgogICAgICAgICAgICByZXF1aXJlKHR5cGUocm93WydieXRlcyddKSBpcyBpbnQgYW5kIDAgPD0gcm93WydieXRlcyddIDw9IEZJTEVfTElNSVQgYW5kIGlzX3NoYShyb3dbJ3NoYTI1NiddKSkKICAgICAgICAgICAgaWYgc2VsZWN0ZWRbJ3NoYTI1NiddIGlzIG5vdCBOb25lOgogICAgICAgICAgICAgICAgcmVxdWlyZShyb3dbJ3NoYTI1NiddID09IHNlbGVjdGVkWydzaGEyNTYnXSBhbmQgcm93WydieXRlcyddID09IHNlbGVjdGVkWydieXRlcyddKQogICAgICAgICAgICB0b3RhbCArPSByb3dbJ2J5dGVzJ10KICAgICAgICBlbHNlOgogICAgICAgICAgICByZXF1aXJlKHJvd1snYnl0ZXMnXSBpcyBOb25lIGFuZCByb3dbJ3NoYTI1NiddIGlzIE5vbmUpCiAgICByZXF1aXJlKHRvdGFsID09IG1hbmlmZXN0WydwbGFpbnRleHRfYnl0ZXMnXSBhbmQgbWFuaWZlc3RbJ2NvbXBsZXRlJ10gaXMKICAgICAgICAgICAgYWxsKHJvd1snc3RhdGUnXSA9PSAnT0JTRVJWRUQnIGZvciByb3cgaW4gcm93cykpCiAgICByZXR1cm4gbWFuaWZlc3QKCgpkZWYgc2VhbChwdWJsaWNfbWV0YWRhdGEsIHJlcXVlc3QsIHNvdXJjZSwgcm9vdD1QYXRoKCcvcm9vdC9ub3gnKSk6CiAgICBwdWJsaWMgPSBwdWJsaWNfa2V5X21ldGFkYXRhKHB1YmxpY19tZXRhZGF0YSkKICAgIGNvbnRleHQgPSBwcmltaXRpdmVzLm93bmVyX2NvbnRleHQocmVxdWVzdCwgc291cmNlKQogICAgcmF3LCBtYW5pZmVzdCA9IHJlYWRfc291cmNlcyhyb290KQogICAgdmFsaWRhdGVfbWFuaWZlc3QobWFuaWZlc3QpCiAgICB0b3RhbCA9IGxlbihyYXcpOyBjaGFycyA9ICgodG90YWwgKyAxOCkgLy8gMykgKiA0CiAgICBjaHVua3MgPSAoY2hhcnMgKyBDSFVOS19DSEFSUyAtIDEpIC8vIENIVU5LX0NIQVJTCiAgICByZXF1aXJlKDEgPD0gY2h1bmtzIDw9IE1BWF9DSFVOS1MpCiAgICBhYWQgPSB7J3NjaGVtYSc6ICdOT1hfRklYRURfU09VUkNFX0FBRF9WMScsICdhbGdvcml0aG0nOiBBTEdPUklUSE0sCiAgICAgICAgICAgJ21hbmlmZXN0JzogbWFuaWZlc3QsICdrZXlfaWQnOiBwdWJsaWNfbWV0YWRhdGFbJ2tleV9pZCddLAogICAgICAgICAgICd0cmFuc2Zlcl9pZCc6IHB1YmxpY19tZXRhZGF0YVsndHJhbnNmZXJfaWQnXSwgJ2NyZWF0ZWRfYXQnOiBpbnQodGltZS50aW1lKCkpLAogICAgICAgICAgICdleHBpcmVzX2F0JzogcHVibGljX21ldGFkYXRhWydleHBpcmVzX2F0J10sICdjb250ZXh0JzogY29udGV4dCwKICAgICAgICAgICAncGxhaW50ZXh0X2J5dGVzJzogdG90YWwsICdjaXBoZXJ0ZXh0X2J5dGVzJzogdG90YWwgKyAxNiwKICAgICAgICAgICAnY2h1bmtfY2hhcnMnOiBDSFVOS19DSEFSUywgJ2NodW5rX2NvdW50JzogY2h1bmtzfQogICAgYWVzID0gcHJpbWl0aXZlcy5BRVNHQ00uZ2VuZXJhdGVfa2V5KGJpdF9sZW5ndGg9MjU2KTsgbm9uY2UgPSBvcy51cmFuZG9tKDEyKQogICAgd3JhcHBlZCA9IHB1YmxpYy5lbmNyeXB0KGFlcywgcHJpbWl0aXZlcy5wYWRkaW5nLk9BRVAoCiAgICAgICAgbWdmPXByaW1pdGl2ZXMucGFkZGluZy5NR0YxKHByaW1pdGl2ZXMuaGFzaGVzLlNIQTI1NigpKSwKICAgICAgICBhbGdvcml0aG09cHJpbWl0aXZlcy5oYXNoZXMuU0hBMjU2KCksIGxhYmVsPU9BRVBfTEFCRUwpKQogICAgY2lwaGVyID0gcHJpbWl0aXZlcy5BRVNHQ00oYWVzKS5lbmNyeXB0KG5vbmNlLCByYXcsIGNhbm9uaWNhbChhYWQpKQogICAgZW5jb2RlZCA9IHByaW1pdGl2ZXMuYjY0KGNpcGhlcikKICAgIGVudmVsb3BlID0geydzY2hlbWEnOiAnTk9YX0ZJWEVEX1NPVVJDRV9FTlZFTE9QRV9WMScsICdhYWQnOiBhYWQsCiAgICAgICAgICAgICAgICAnd3JhcHBlZF9rZXknOiBwcmltaXRpdmVzLmI2NCh3cmFwcGVkKSwgJ25vbmNlJzogcHJpbWl0aXZlcy5iNjQobm9uY2UpLAogICAgICAgICAgICAgICAgJ2NpcGhlcnRleHQnOiBlbmNvZGVkLCAnY2lwaGVydGV4dF9zaGEyNTYnOiBkaWdlc3QoY2lwaGVyKX0KICAgIG91dGVyID0gZGlnZXN0KGNhbm9uaWNhbChlbnZlbG9wZSkpCiAgICByb3dzID0gW3sna2luZCc6ICdzb3VyY2VfY2lwaGVydGV4dF9oZWFkZXInLCAnZGF0YSc6IHsKICAgICAgICAnc2NoZW1hJzogJ05PWF9GSVhFRF9TT1VSQ0VfVFJBTlNGRVJfVjEnLCAnZW52ZWxvcGVfc2hhMjU2Jzogb3V0ZXIsCiAgICAgICAgJ2NodW5rcyc6IGNodW5rcywgJ2NpcGhlcnRleHRfY2hhcnMnOiBsZW4oZW5jb2RlZCksCiAgICAgICAgJ21ldGFkYXRhJzoge2s6IHYgZm9yIGssIHYgaW4gZW52ZWxvcGUuaXRlbXMoKSBpZiBrICE9ICdjaXBoZXJ0ZXh0J319fV0KICAgIHJvd3MgKz0gW3sna2luZCc6ICdzb3VyY2VfY2lwaGVydGV4dF9jaHVuaycsICdkYXRhJzogewogICAgICAgICdlbnZlbG9wZV9zaGEyNTYnOiBvdXRlciwgJ2luZGV4JzogaSwgJ2NodW5rcyc6IGNodW5rcywKICAgICAgICAnY2lwaGVydGV4dCc6IGVuY29kZWRbaSAqIENIVU5LX0NIQVJTOihpICsgMSkgKiBDSFVOS19DSEFSU119fSBmb3IgaSBpbiByYW5nZShjaHVua3MpXQogICAgcmVxdWlyZShhbGwobGVuKGNhbm9uaWNhbChyb3cpKSA8IDc5MDAwIGZvciByb3cgaW4gcm93cykpCiAgICByZXR1cm4gcm93cwoKCmRlZiBhc3NlbWJsZShyb3dzKToKICAgIHJlcXVpcmUoaXNpbnN0YW5jZShyb3dzLCBsaXN0KSBhbmQgMiA8PSBsZW4ocm93cykgPD0gTUFYX0NIVU5LUyArIDEpCiAgICBmaXJzdCA9IHJvd3NbMF0KICAgIHJlcXVpcmUoaXNpbnN0YW5jZShmaXJzdCwgZGljdCkgYW5kIHNldChmaXJzdCkgPT0geydraW5kJywgJ2RhdGEnfQogICAgICAgICAgICBhbmQgZmlyc3RbJ2tpbmQnXSA9PSAnc291cmNlX2NpcGhlcnRleHRfaGVhZGVyJykKICAgIGhlYWRlciA9IGZpcnN0WydkYXRhJ10KICAgIHJlcXVpcmUoaXNpbnN0YW5jZShoZWFkZXIsIGRpY3QpIGFuZCBzZXQoaGVhZGVyKSA9PSB7J3NjaGVtYScsICdlbnZlbG9wZV9zaGEyNTYnLCAnY2h1bmtzJywKICAgICAgICAgICAgJ2NpcGhlcnRleHRfY2hhcnMnLCAnbWV0YWRhdGEnfSBhbmQgaGVhZGVyWydzY2hlbWEnXSA9PSAnTk9YX0ZJWEVEX1NPVVJDRV9UUkFOU0ZFUl9WMScKICAgICAgICAgICAgYW5kIGlzX3NoYShoZWFkZXJbJ2VudmVsb3BlX3NoYTI1NiddKSBhbmQgdHlwZShoZWFkZXJbJ2NodW5rcyddKSBpcyBpbnQKICAgICAgICAgICAgYW5kIDEgPD0gaGVhZGVyWydjaHVua3MnXSA8PSBNQVhfQ0hVTktTIGFuZCBsZW4ocm93cykgPT0gaGVhZGVyWydjaHVua3MnXSArIDEKICAgICAgICAgICAgYW5kIHR5cGUoaGVhZGVyWydjaXBoZXJ0ZXh0X2NoYXJzJ10pIGlzIGludAogICAgICAgICAgICBhbmQgMCA8IGhlYWRlclsnY2lwaGVydGV4dF9jaGFycyddIDw9ICgoVE9UQUxfTElNSVQgKyAxOCkgLy8gMykgKiA0CiAgICAgICAgICAgIGFuZCBoZWFkZXJbJ2NodW5rcyddID09IChoZWFkZXJbJ2NpcGhlcnRleHRfY2hhcnMnXSArIENIVU5LX0NIQVJTIC0gMSkgLy8gQ0hVTktfQ0hBUlMpCiAgICBwYXJ0cyA9IFtdCiAgICBmb3IgaSwgcm93IGluIGVudW1lcmF0ZShyb3dzWzE6XSk6CiAgICAgICAgcmVxdWlyZShpc2luc3RhbmNlKHJvdywgZGljdCkgYW5kIHNldChyb3cpID09IHsna2luZCcsICdkYXRhJ30gYW5kIHJvd1sna2luZCddID09ICdzb3VyY2VfY2lwaGVydGV4dF9jaHVuaycpCiAgICAgICAgdmFsdWUgPSByb3dbJ2RhdGEnXQogICAgICAgIHJlcXVpcmUoaXNpbnN0YW5jZSh2YWx1ZSwgZGljdCkgYW5kIHNldCh2YWx1ZSkgPT0geydlbnZlbG9wZV9zaGEyNTYnLCAnaW5kZXgnLCAnY2h1bmtzJywgJ2NpcGhlcnRleHQnfQogICAgICAgICAgICAgICAgYW5kIHZhbHVlWydlbnZlbG9wZV9zaGEyNTYnXSA9PSBoZWFkZXJbJ2VudmVsb3BlX3NoYTI1NiddIGFuZCB0eXBlKHZhbHVlWydpbmRleCddKSBpcyBpbnQKICAgICAgICAgICAgICAgIGFuZCB2YWx1ZVsnaW5kZXgnXSA9PSBpIGFuZCB0eXBlKHZhbHVlWydjaHVua3MnXSkgaXMgaW50IGFuZCB2YWx1ZVsnY2h1bmtzJ10gPT0gaGVhZGVyWydjaHVua3MnXQogICAgICAgICAgICAgICAgYW5kIGlzaW5zdGFuY2UodmFsdWVbJ2NpcGhlcnRleHQnXSwgc3RyKQogICAgICAgICAgICAgICAgYW5kIGxlbih2YWx1ZVsnY2lwaGVydGV4dCddKSA9PSBtaW4oQ0hVTktfQ0hBUlMsIGhlYWRlclsnY2lwaGVydGV4dF9jaGFycyddIC0gaSAqIENIVU5LX0NIQVJTKSkKICAgICAgICBwYXJ0cy5hcHBlbmQodmFsdWVbJ2NpcGhlcnRleHQnXSkKICAgIG1ldGEgPSBoZWFkZXJbJ21ldGFkYXRhJ10KICAgIHJlcXVpcmUoaXNpbnN0YW5jZShtZXRhLCBkaWN0KSBhbmQgc2V0KG1ldGEpID09IHsnc2NoZW1hJywgJ2FhZCcsICd3cmFwcGVkX2tleScsICdub25jZScsICdjaXBoZXJ0ZXh0X3NoYTI1Nid9KQogICAgZW52ZWxvcGUgPSBkaWN0KG1ldGEsIGNpcGhlcnRleHQ9Jycuam9pbihwYXJ0cykpCiAgICByZXF1aXJlKGRpZ2VzdChjYW5vbmljYWwoZW52ZWxvcGUpKSA9PSBoZWFkZXJbJ2VudmVsb3BlX3NoYTI1NiddKQogICAgcmV0dXJuIGVudmVsb3BlLCBoZWFkZXJbJ2VudmVsb3BlX3NoYTI1NiddCgoKZGVmIGRlY3J5cHQocm93cywgcHJpdmF0ZV9wZW0sIHB1YmxpY19tZXRhZGF0YSwgcmVxdWVzdCwgc291cmNlKToKICAgIHB1YmxpY19rZXlfbWV0YWRhdGEocHVibGljX21ldGFkYXRhKQogICAgY29udGV4dCA9IHByaW1pdGl2ZXMub3duZXJfY29udGV4dChyZXF1ZXN0LCBzb3VyY2UpCiAgICBlbnZlbG9wZSwgb3V0ZXIgPSBhc3NlbWJsZShyb3dzKTsgYWFkID0gZW52ZWxvcGVbJ2FhZCddCiAgICByZXF1aXJlKGVudmVsb3BlWydzY2hlbWEnXSA9PSAnTk9YX0ZJWEVEX1NPVVJDRV9FTlZFTE9QRV9WMScgYW5kIGlzaW5zdGFuY2UoYWFkLCBkaWN0KQogICAgICAgICAgICBhbmQgc2V0KGFhZCkgPT0geydzY2hlbWEnLCAnYWxnb3JpdGhtJywgJ21hbmlmZXN0JywgJ2tleV9pZCcsICd0cmFuc2Zlcl9pZCcsICdjcmVhdGVkX2F0JywKICAgICAgICAgICAgICAgICAgICAgICAgICAgICdleHBpcmVzX2F0JywgJ2NvbnRleHQnLCAncGxhaW50ZXh0X2J5dGVzJywgJ2NpcGhlcnRleHRfYnl0ZXMnLCAnY2h1bmtfY2hhcnMnLCAnY2h1bmtfY291bnQnfSkKICAgIG1hbmlmZXN0ID0gdmFsaWRhdGVfbWFuaWZlc3QoYWFkWydtYW5pZmVzdCddKTsgdG90YWwgPSBtYW5pZmVzdFsncGxhaW50ZXh0X2J5dGVzJ10KICAgIGNoYXJzID0gKCh0b3RhbCArIDE4KSAvLyAzKSAqIDQKICAgIHJlcXVpcmUoYWFkWydzY2hlbWEnXSA9PSAnTk9YX0ZJWEVEX1NPVVJDRV9BQURfVjEnIGFuZCBhYWRbJ2FsZ29yaXRobSddID09IEFMR09SSVRITQogICAgICAgICAgICBhbmQgYWFkWydrZXlfaWQnXSA9PSBwdWJsaWNfbWV0YWRhdGFbJ2tleV9pZCddIGFuZCBhYWRbJ3RyYW5zZmVyX2lkJ10gPT0gcHVibGljX21ldGFkYXRhWyd0cmFuc2Zlcl9pZCddCiAgICAgICAgICAgIGFuZCBhYWRbJ2V4cGlyZXNfYXQnXSA9PSBwdWJsaWNfbWV0YWRhdGFbJ2V4cGlyZXNfYXQnXSBhbmQgYWFkWydjb250ZXh0J10gPT0gY29udGV4dAogICAgICAgICAgICBhbmQgdHlwZShhYWRbJ2NyZWF0ZWRfYXQnXSkgaXMgaW50CiAgICAgICAgICAgIGFuZCBwdWJsaWNfbWV0YWRhdGFbJ2NyZWF0ZWRfYXQnXSAtIDUgPD0gYWFkWydjcmVhdGVkX2F0J10gPD0gaW50KHRpbWUudGltZSgpKSArIDUKICAgICAgICAgICAgYW5kIGFhZFsnY3JlYXRlZF9hdCddIDwgYWFkWydleHBpcmVzX2F0J10gYW5kIHR5cGUoYWFkWydwbGFpbnRleHRfYnl0ZXMnXSkgaXMgaW50CiAgICAgICAgICAgIGFuZCBhYWRbJ3BsYWludGV4dF9ieXRlcyddID09IHRvdGFsIGFuZCB0eXBlKGFhZFsnY2lwaGVydGV4dF9ieXRlcyddKSBpcyBpbnQKICAgICAgICAgICAgYW5kIGFhZFsnY2lwaGVydGV4dF9ieXRlcyddID09IHRvdGFsICsgMTYgYW5kIGFhZFsnY2h1bmtfY2hhcnMnXSA9PSBDSFVOS19DSEFSUwogICAgICAgICAgICBhbmQgdHlwZShhYWRbJ2NodW5rX2NvdW50J10pIGlzIGludCBhbmQgYWFkWydjaHVua19jb3VudCddID09IChjaGFycyArIENIVU5LX0NIQVJTIC0gMSkgLy8gQ0hVTktfQ0hBUlMpCiAgICBwcml2YXRlID0gcHJpbWl0aXZlcy5zZXJpYWxpemF0aW9uLmxvYWRfcGVtX3ByaXZhdGVfa2V5KHByaXZhdGVfcGVtLCBwYXNzd29yZD1Ob25lKQogICAgcmVxdWlyZShpc2luc3RhbmNlKHByaXZhdGUsIHByaW1pdGl2ZXMucnNhLlJTQVByaXZhdGVLZXkpIGFuZCBwcml2YXRlLmtleV9zaXplID09IDQwOTYpCiAgICBkZXIgPSBwcml2YXRlLnB1YmxpY19rZXkoKS5wdWJsaWNfYnl0ZXMocHJpbWl0aXZlcy5zZXJpYWxpemF0aW9uLkVuY29kaW5nLkRFUiwKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIHByaW1pdGl2ZXMuc2VyaWFsaXphdGlvbi5QdWJsaWNGb3JtYXQuU3ViamVjdFB1YmxpY0tleUluZm8pCiAgICByZXF1aXJlKGRpZ2VzdChkZXIpID09IHB1YmxpY19tZXRhZGF0YVsna2V5X2lkJ10pCiAgICBjaXBoZXIgPSBwcmltaXRpdmVzLnVuYjY0KGVudmVsb3BlWydjaXBoZXJ0ZXh0J10sIHRvdGFsICsgMTYpCiAgICByZXF1aXJlKGxlbihjaXBoZXIpID09IHRvdGFsICsgMTYgYW5kIGRpZ2VzdChjaXBoZXIpID09IGVudmVsb3BlWydjaXBoZXJ0ZXh0X3NoYTI1NiddKQogICAgd3JhcHBlZCA9IHByaW1pdGl2ZXMudW5iNjQoZW52ZWxvcGVbJ3dyYXBwZWRfa2V5J10sIDUxMik7IG5vbmNlID0gcHJpbWl0aXZlcy51bmI2NChlbnZlbG9wZVsnbm9uY2UnXSwgMTIpCiAgICByZXF1aXJlKGxlbih3cmFwcGVkKSA9PSA1MTIgYW5kIGxlbihub25jZSkgPT0gMTIpCiAgICBhZXMgPSBwcml2YXRlLmRlY3J5cHQod3JhcHBlZCwgcHJpbWl0aXZlcy5wYWRkaW5nLk9BRVAoCiAgICAgICAgbWdmPXByaW1pdGl2ZXMucGFkZGluZy5NR0YxKHByaW1pdGl2ZXMuaGFzaGVzLlNIQTI1NigpKSwKICAgICAgICBhbGdvcml0aG09cHJpbWl0aXZlcy5oYXNoZXMuU0hBMjU2KCksIGxhYmVsPU9BRVBfTEFCRUwpKQogICAgcmVxdWlyZShsZW4oYWVzKSA9PSAzMikKICAgIHJhdyA9IHByaW1pdGl2ZXMuQUVTR0NNKGFlcykuZGVjcnlwdChub25jZSwgY2lwaGVyLCBjYW5vbmljYWwoYWFkKSkKICAgIHJlcXVpcmUobGVuKHJhdykgPT0gdG90YWwgYW5kIGRpZ2VzdChyYXcpID09IG1hbmlmZXN0WydwbGFpbnRleHRfc2hhMjU2J10pCiAgICBvZmZzZXQsIGZpbGVzID0gMCwge30KICAgIGZvciByb3cgaW4gbWFuaWZlc3RbJ2ZpbGVzJ106CiAgICAgICAgaWYgcm93WydzdGF0ZSddICE9ICdPQlNFUlZFRCc6CiAgICAgICAgICAgIGNvbnRpbnVlCiAgICAgICAgaXRlbSA9IHJhd1tvZmZzZXQ6b2Zmc2V0ICsgcm93WydieXRlcyddXTsgb2Zmc2V0ICs9IHJvd1snYnl0ZXMnXQogICAgICAgIHJlcXVpcmUoZGlnZXN0KGl0ZW0pID09IHJvd1snc2hhMjU2J10pCiAgICAgICAgZmlsZXNbcm93WydyZWxhdGl2ZV9wYXRoJ11dID0gaXRlbQogICAgcmV0dXJuIGZpbGVzLCB7J3NjaGVtYSc6ICdOT1hfRklYRURfU09VUkNFX0xPQ0FMX1JFQ0VJUFRfVjEnLCAnZW52ZWxvcGVfc2hhMjU2Jzogb3V0ZXIsCiAgICAgICAgICAgICAgICAgICAnbWFuaWZlc3QnOiBtYW5pZmVzdCwgJ2tleV9pZCc6IHB1YmxpY19tZXRhZGF0YVsna2V5X2lkJ10sICdjb250ZXh0JzogY29udGV4dH0KCgpkZWYgX28yX2RpcmVjdG9yeShwYXRoKToKICAgICIiIk9wZW4gZXZlcnkgZGlyZWN0b3J5IGNvbXBvbmVudCB3aXRob3V0IGZvbGxvd2luZyBzeW1saW5rcy4iIiIKICAgIHBhdGggPSBQYXRoKHBhdGgpCiAgICBpZiBub3QgcGF0aC5pc19hYnNvbHV0ZSgpIG9yICcuLicgaW4gcGF0aC5wYXJ0czoKICAgICAgICByYWlzZSBWYWx1ZUVycm9yKCdzY29wZScpCiAgICBmbGFncyA9IG9zLk9fUkRPTkxZIHwgb3MuT19ESVJFQ1RPUlkgfCBvcy5PX05PRk9MTE9XIHwgb3MuT19DTE9FWEVDCiAgICBmZCA9IG9zLm9wZW4oJy8nLCBmbGFncykKICAgIHRyeToKICAgICAgICBmb3IgcGFydCBpbiBwYXRoLnBhcnRzWzE6XToKICAgICAgICAgICAgY2hpbGQgPSBvcy5vcGVuKHBhcnQsIGZsYWdzLCBkaXJfZmQ9ZmQpCiAgICAgICAgICAgIG9zLmNsb3NlKGZkKQogICAgICAgICAgICBmZCA9IGNoaWxkCiAgICAgICAgcmV0dXJuIGZkCiAgICBleGNlcHQgQmFzZUV4Y2VwdGlvbjoKICAgICAgICBvcy5jbG9zZShmZCkKICAgICAgICByYWlzZQoKCmRlZiBfbzJfcmVhZChwYXRoLCBsaW1pdCwgKiwgZGlnZXN0X29ubHk9RmFsc2UsIGRlYWRsaW5lPU5vbmUpOgogICAgIiIiQm91bmRlZCByZWd1bGFyLWZpbGUgcmVhZDsgY29uZmlybSB0aGUgbmFtZWQgaW5vZGUgc3RpbGwgbWF0Y2hlcy4KCiAgICBObyBlcnJvciB0ZXh0IG9yIHNvdXJjZSBieXRlcyBhcmUgcmV0dXJuZWQgZm9yIGEgZmFpbGVkIHJlYWQuIFRoZSB0aW1lCiAgICBjaGVjayBib3VuZHMgcHJvZ3Jlc3MgYmV0d2VlbiByZWFkczsgaXQgY2Fubm90IGludGVycnVwdCBhIGJsb2NrZWQga2VybmVsIElPLgogICAgIiIiCiAgICBpbXBvcnQgaGFzaGxpYiwgc3RhdAogICAgcGF0aCA9IFBhdGgocGF0aCkKICAgIHBhcmVudCA9IGZpbGVfZmQgPSBjaGVja2VkX3BhcmVudCA9IE5vbmUKICAgIHRyeToKICAgICAgICBwYXJlbnQgPSBfbzJfZGlyZWN0b3J5KHBhdGgucGFyZW50KQogICAgICAgIGZpbGVfZmQgPSBvcy5vcGVuKHBhdGgubmFtZSwgb3MuT19SRE9OTFkgfCBvcy5PX05PRk9MTE9XIHwgb3MuT19OT05CTE9DSyB8IG9zLk9fQ0xPRVhFQywgZGlyX2ZkPXBhcmVudCkKICAgICAgICBiZWZvcmUgPSBvcy5mc3RhdChmaWxlX2ZkKQogICAgICAgIGlmIG5vdCBzdGF0LlNfSVNSRUcoYmVmb3JlLnN0X21vZGUpIG9yIGJlZm9yZS5zdF9zaXplID4gbGltaXQ6CiAgICAgICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoJ3R5cGVfb3Jfc2l6ZScpCiAgICAgICAgaWRlbnRpdHkgPSBsYW1iZGEgdmFsdWU6ICh2YWx1ZS5zdF9kZXYsdmFsdWUuc3RfaW5vLHZhbHVlLnN0X3NpemUsdmFsdWUuc3RfbXRpbWVfbnMsdmFsdWUuc3RfY3RpbWVfbnMpCiAgICAgICAgZGlnZXN0LCBjaHVua3MsIHRvdGFsID0gaGFzaGxpYi5zaGEyNTYoKSwgW10sIDAKICAgICAgICB3aGlsZSBUcnVlOgogICAgICAgICAgICBpZiBkZWFkbGluZSBpcyBub3QgTm9uZSBhbmQgdGltZS5tb25vdG9uaWMoKSA+IGRlYWRsaW5lOgogICAgICAgICAgICAgICAgcmFpc2UgVmFsdWVFcnJvcigndGltZScpCiAgICAgICAgICAgIGJsb2NrID0gb3MucmVhZChmaWxlX2ZkLCBtaW4oMTYzODQsbGltaXQtdG90YWwrMSkpCiAgICAgICAgICAgIGlmIG5vdCBibG9jazoKICAgICAgICAgICAgICAgIGJyZWFrCiAgICAgICAgICAgIHRvdGFsICs9IGxlbihibG9jaykKICAgICAgICAgICAgaWYgdG90YWwgPiBsaW1pdDoKICAgICAgICAgICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoJ2dyb3d0aCcpCiAgICAgICAgICAgIGRpZ2VzdC51cGRhdGUoYmxvY2spCiAgICAgICAgICAgIGlmIG5vdCBkaWdlc3Rfb25seToKICAgICAgICAgICAgICAgIGNodW5rcy5hcHBlbmQoYmxvY2spCiAgICAgICAgY2hlY2tlZF9wYXJlbnQgPSBfbzJfZGlyZWN0b3J5KHBhdGgucGFyZW50KQogICAgICAgIG9sZF9kaXIsIG5ld19kaXIgPSBvcy5mc3RhdChwYXJlbnQpLCBvcy5mc3RhdChjaGVja2VkX3BhcmVudCkKICAgICAgICBuYW1lZCA9IG9zLnN0YXQocGF0aC5uYW1lLCBkaXJfZmQ9Y2hlY2tlZF9wYXJlbnQsIGZvbGxvd19zeW1saW5rcz1GYWxzZSkKICAgICAgICBpZiAoKG9sZF9kaXIuc3RfZGV2LG9sZF9kaXIuc3RfaW5vKSAhPSAobmV3X2Rpci5zdF9kZXYsbmV3X2Rpci5zdF9pbm8pCiAgICAgICAgICAgICAgICBvciBpZGVudGl0eShiZWZvcmUpICE9IGlkZW50aXR5KG9zLmZzdGF0KGZpbGVfZmQpKSBvciBpZGVudGl0eShiZWZvcmUpICE9IGlkZW50aXR5KG5hbWVkKSk6CiAgICAgICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoJ2NoYW5nZWQnKQogICAgICAgIGlmIHRvdGFsICE9IGJlZm9yZS5zdF9zaXplOgogICAgICAgICAgICByYWlzZSBWYWx1ZUVycm9yKCdjaGFuZ2VkX3NpemUnKQogICAgICAgIHJldHVybiB7J3N0YXRlJzonT0JTRVJWRUQnLCdieXRlc19yZWFkJzp0b3RhbCwnc2hhMjU2JzpkaWdlc3QuaGV4ZGlnZXN0KCksCiAgICAgICAgICAgICAgICAndmFsdWUnOk5vbmUgaWYgZGlnZXN0X29ubHkgZWxzZSBiJycuam9pbihjaHVua3MpfQogICAgZXhjZXB0IChPU0Vycm9yLFZhbHVlRXJyb3IpOgogICAgICAgIHJldHVybiB7J3N0YXRlJzonVU5LTk9XTl9VTlNBRkVfVU5SRUFEQUJMRV9DSEFOR0VEX09SX0xJTUlUJywnYnl0ZXNfcmVhZCc6MCwnc2hhMjU2JzpOb25lLCd2YWx1ZSc6Tm9uZX0KICAgIGZpbmFsbHk6CiAgICAgICAgZm9yIGZkIGluIChmaWxlX2ZkLHBhcmVudCxjaGVja2VkX3BhcmVudCk6CiAgICAgICAgICAgIGlmIGZkIGlzIG5vdCBOb25lOgogICAgICAgICAgICAgICAgb3MuY2xvc2UoZmQpCgoK'
O2_SOURCE_TRANSPORT_SHA = '83be062fd6da18f5a77d2e84d48c9cb426ae26bb85960299d5c8d6b6c5fbbe00'
O2_SOURCE_PUBLIC_METADATA = {'schema': 'NOX_FIXED_SOURCE_PUBLIC_KEY_V1', 'key_id': 'e56f72f66e7bf8b111d72178ec41a90028b42eec41f008b2c6b6a13ad67410f5', 'public_key_pem': '-----BEGIN PUBLIC KEY-----\nMIICIjANBgkqhkiG9w0BAQEFAAOCAg8AMIICCgKCAgEAnDDPwOnLhiUl6jf24M2Z\nqqpAspv9nMdFRfspXhK4M68Zb9ZH7WF3miEmVHkhg9p2oqyMcEX36qod3AwLVKW0\nkvncgvgJ+n9tfeT+10sjpxE7HwckVJHQ5f2i3vSX74yyF4IX6Ko14kOcWOL6bely\nro50eAAq2hqVwqFHNJtPAHJK5FV4DYxoF4PZXG67RTscSuIFw5XifLNMQhHiw53E\nwUTk1ZM9KzuT/Em2a6f5RhePl0Lz7jMnnEQzmydF3P8S24ItO3zv5begFMS7T7/p\nDwvfZN4bL2PZVPFE4gbf8sYzIr/N83a9Y93aRFYTxB6yWSRKilzS/nsYmSCqgQa8\npBl1uCJo+0401DWmqXg/wPXFQ5WCsD0GIQtoWKG51QrhxZvazrtz5o6I7YUldIiu\nQ7G0E4rHs+FuugpM1bjeLlD448ETbUAk56SpzVLuHX+COJJdvdjWUsa/3KUQu4Tu\nOVJVmNNLgFacm2oqbVPDfenYN+bKbu8JtxupUckjxuP6mAERAJN89JkjS8P3xAdc\nk2dtxOjVbrAHreLWGK/6yrbETK7P3gPKPnbDl1InpGT38Ur/apH5ALI5IKoCSoT2\nZE7WmWpsrNIousPvl5TdRIKwn86jXKQzD9d/jS3wLodDqu0Hl2IuEXH7uey/Hxnq\nNhd/O9X9bW7s5/YI7bCxwJMCAwEAAQ==\n-----END PUBLIC KEY-----\n', 'transfer_id': 'ff5187565221f17ad753d00fa3814b7f', 'created_at': 1794937928, 'expires_at': 1794941528, 'scope_sha256': '649b029e499a683a7cfcef5b2541fef92f179d95be01ac092f261f56d4cbd03c'}

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
