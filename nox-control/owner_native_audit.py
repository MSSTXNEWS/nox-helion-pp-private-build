#!/usr/bin/env python3
"""One-shot narrow mapping readback; legacy audit helpers are not executed by main."""
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


def main():
    # The owner workflow still pins and authorizes this source and uses its
    # existing temporary SSH transport/cleanup. Do not run legacy audit workers.
    row = {'section':'native_mapping_readback','worker_pid':os.getpid(),'result':native_mapping_readback()}
    print('NOX_MAINT_AUDIT='+json.dumps(row,separators=(',',':'),allow_nan=False),flush=True)
    print('NOX_MAINT_AUDIT_COMPLETE=true',flush=True)
if __name__=='__main__':main()

