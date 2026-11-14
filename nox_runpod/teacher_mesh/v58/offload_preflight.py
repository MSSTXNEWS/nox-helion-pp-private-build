"""V58 export preflight: read-only file-size, backup-link and live-trainer audit.

Reuses the verified per-instance ephemeral SSH from V51 with credential/key
cleanup. Does not copy user data to GitHub or delete/create any remote file.
"""
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as c

REMOTE = r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import os,shutil,subprocess,time,stat,json,re
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V58_NOLOSS_OFFLOAD_PREFLIGHT_V1')
root=Path('/root/nox')
locations=[
('weights',root/'models'),('work_checkpoints',root/'checkpoints'),
('training',root/'training'),('learning',Path('/root/nox_learn')),
('memory',root/'memory'),('knowledge',root/'kb'),
('web',root/'incoming_t800u'),('backup',root/'backup'),
('sources',root/'sources'),('tmp',Path('/tmp')),
('workspace',Path('/workspace')),
]
def folder_stats(folder,cap=9000):
    # stat only; symlinks skipped, no private filenames printed
    size=0;count=0;largest=0;opened=0;quasi=[]
    if not folder.exists():return None
    for base,ds,fs in os.walk(folder,followlinks=False):
        ds[:]=[d for d in ds if d not in ('.git','.ssh','.cache','node_modules',
                     'venv','.venv','__pycache__')][:110]
        for file in fs:
            try:
                p=Path(base)/file
                z=p.lstat()
                if not stat.S_ISREG(z.st_mode):continue
                size+=z.st_size;count+=1;largest=max(largest,z.st_size)
                if z.st_size>=1_000_000_000:opened+=1
            except (OSError,ValueError):continue
            if count>=cap:break
        if count>=cap:break
    return size,count,largest,opened,count>=cap
for label,path in locations:
    try:
        if not path.is_dir():continue
        s=folder_stats(path)
        if s is None:continue
        a,b,z,big,truncated=s
        print('NATIVE_OFFLOAD_'+label.upper()+'_FILES='+str(b))
        print('NATIVE_OFFLOAD_'+label.upper()+'_SIZE_GIB='+str(round(a/2**30,3)))
        print('NATIVE_OFFLOAD_'+label.upper()+'_LARGEST_GIB='+str(round(z/2**30,3)))
        print('NATIVE_OFFLOAD_'+label.upper()+'_FILES_GE_1G='+str(big))
        print('NATIVE_OFFLOAD_'+label.upper()+'_TRUNCATED='+str(truncated).lower())
    except (OSError,PermissionError):
        print('NATIVE_OFFLOAD_'+label.upper()+'=HOLD_SCAN')
# File classes by global source root, bounded and no user paths
classes={'safetensors':0,'optimizer':0,'checkpoint':0,'gguf':0,
         'sqlite':0,'source':0,'archive':0,'partial':0}
total={k:0 for k in classes}
for base,dirs,files in os.walk(root,followlinks=False):
    dirs[:]=[d for d in dirs if d not in ('.git','.ssh','venv','.venv','node_modules','.cache')][:140]
    for name in files:
        p=Path(base)/name
        try:
            info=p.lstat()
            if not stat.S_ISREG(info.st_mode):continue
        except OSError:continue
        low=name.lower()
        kind=('safetensors' if low.endswith('.safetensors') else
              'optimizer' if 'optimizer' in low or low.startswith('optim.') else
              'checkpoint' if 'checkpoint' in low or low.endswith(('.ckpt','.pt','.pth')) else
              'gguf' if low.endswith('.gguf') else
              'sqlite' if low.endswith(('.db','.sqlite','.sqlite3')) else
              'archive' if low.endswith(('.zip','.tar','.gz','.zst','.7z')) else
              'partial' if low.endswith(('.part','.partial','.tmp')) else
              'source' if low.endswith(('.py','.js','.html','.json','.md','.ps1','.sh')) else None)
        if kind:
            classes[kind]+=1;total[kind]+=info.st_size
for k in classes:
    print('NATIVE_CLASS_'+k.upper()+'_COUNT='+str(classes[k]))
    print('NATIVE_CLASS_'+k.upper()+'_GIB='+str(round(total[k]/2**30,3)))
# Check actual GPU processes *without displaying command line or env*.
try:
    r=subprocess.run(['nvidia-smi','--query-gpu=index,memory.used,utilization.gpu','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=10)
    if r.returncode==0:
        for i,line in enumerate(r.stdout.splitlines()[:2]):
            if re.fullmatch('[0-9 ,]+',line):print('NATIVE_GPU_'+str(i)+'_USED_COMPUTE='+line.strip())
except (OSError,subprocess.TimeoutExpired):pass
# Are existing backup tools/bound mounted storage present? Never read credentials.
for n in ('rclone','gsutil','gcloud','aws','rsync','scp','ssh','huggingface-cli','git','zstd','tar'):
    print('NATIVE_OFFLOAD_TOOL_'+n.upper().replace('-','_')+'='+str(bool(shutil.which(n))).lower())
for path in ('/root/.config/rclone/rclone.conf','/root/.config/gcloud',
             '/root/.aws/credentials','/root/.ssh/config',
             '/root/nox/scripts/nox_backup.sh',
             '/root/nox/backup','/mnt/data','/mnt/drive','/workspace/backups'):
    print('NATIVE_OFFLOAD_CONFIG_'+str(len(path))+':'+str(Path(path).exists()).lower())
# Check external mounts from /proc/mounts without revealing host or mount credentials
remote_types={'nfs','nfs4','cifs','sshfs','fuse.rclone','davfs','fuse.sshfs','fuse.gcsfuse'}
mounted=[]
try:
    for line in Path('/proc/mounts').read_text().splitlines()[:350]:
        f=line.split()
        if len(f)>2 and f[2] in remote_types:
            mounted.append(f[2])
except OSError:pass
print('NATIVE_EXTERNAL_MOUNTS_COUNT='+str(len(mounted)))
print('NATIVE_EXTERNAL_MOUNT_TYPES='+','.join(sorted(set(mounted))))
# Quick process ownership check; do not kill, suspend or renice.
try:
    proc=subprocess.run(['ps','-eo','comm='],capture_output=True,text=True,timeout=6)
    text=proc.stdout.lower()
    for label in ('python','llama','rclone','rsync','scp','tar','trainer','torchrun'):
        print('NATIVE_PROCESS_'+label.upper()+'_COUNT='+str(sum(label in x for x in text.splitlines())))
except (OSError,subprocess.TimeoutExpired):pass
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
if __name__=='__main__':
    c.REMOTE=REMOTE
    ok=False
    try:ok=c.probe()
    except Exception as exc:
        print("NOX_V58_PREFLIGHT="+str(exc) if str(exc).startswith("HOLD_") else "NOX_V58_PREFLIGHT=HOLD_NATIVE")
    finally:
        try:
            if not c.cleanup():ok=False
        except Exception:
            print("NOX_V58_CLEANUP=HOLD")
            ok=False
    raise SystemExit(0 if ok else 2)
