"""V62: bounded read-only file fingerprint scan of large NOX weights.

Not a cleanup tool. No file names/contents exported. Exact SHA for deletion
would be a separate, explicitly approved step after owner-key restore.
"""
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as c

REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
from pathlib import Path
from collections import defaultdict
import os,hashlib,stat,subprocess,json
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V62_BOUNDED_WEIGHT_FINGERPRINT_V1')
roots=[Path('/root/nox'),Path('/root/nox_learn')]
suffixes={'.gguf','.safetensors','.bin','.pth','.pt'}
minimum=64*1024*1024
files=[]
visited_inodes=set()
hardlink_paths=0
for root in roots:
    if not root.is_dir():continue
    for directory,dirs,names in os.walk(root,followlinks=False):
        dirs[:]=[d for d in dirs if d not in ('.git','.ssh','.cache','venv',
          '.venv','node_modules','__pycache__')][:150]
        for name in names:
            p=Path(directory)/name
            if p.suffix.lower() not in suffixes:continue
            try:st=p.lstat()
            except OSError:continue
            if not stat.S_ISREG(st.st_mode) or st.st_size<minimum:continue
            inode=(st.st_dev,st.st_ino)
            if inode in visited_inodes:
                hardlink_paths+=1
                continue
            visited_inodes.add(inode)
            files.append((p,st.st_size))
            if len(files)>1000:raise SystemExit('HOLD_TOO_MANY_WEIGHTS')
print('NATIVE_WEIGHTS_UNIQUE_INODES='+str(len(files)))
print('NATIVE_WEIGHTS_HARDLINK_ALIAS_PATHS='+str(hardlink_paths))
print('NATIVE_WEIGHTS_TOTAL_GIB='+str(round(sum(size for _,size in files)/2**30,3)))
groups=defaultdict(list)
errors=0
for p,size in files:
    h=hashlib.sha256()
    try:
        with p.open('rb',buffering=0) as src:
            for offset in (0,max(0,size//2-32768),max(0,size-65536)):
                src.seek(offset)
                b=src.read(65536)
                if len(b)!=65536:raise OSError('short_read')
                h.update(b)
    except OSError:
        errors+=1
        continue
    groups[(size,h.hexdigest())].append(str(p))
candidates=[v for (size,fingerprint),v in groups.items() if len(v)>1]
candidate_bytes=sum((len(group)-1)*size for (size,fp),group in groups.items() if len(group)>1)
print('NATIVE_WEIGHT_FINGERPRINT_ERROR_COUNT='+str(errors))
print('NATIVE_WEIGHT_PROBABLE_DUPLICATE_GROUPS='+str(len(candidates)))
print('NATIVE_WEIGHT_PROBABLE_DUPLICATE_PATHS='+str(sum(len(group) for group in candidates)))
print('NATIVE_WEIGHT_PROBABLE_RECLAIMABLE_GIB='+str(round(candidate_bytes/2**30,3)))
print('NATIVE_FINGERPRINT_IS_FULL_SHA_VERIFIED=false')
print('NATIVE_DUPLICATE_PATHS_NOT_EXPORTED=true')
print('NATIVE_FILES_DELETED=false')
# The actual disk and compute snapshots are independent of the hash scan.
try:
    st=os.statvfs('/root/nox')
    print('NATIVE_DISK_AVAILABLE_BYTES='+str(st.f_frsize*st.f_bavail))
except OSError:print('NATIVE_DISK_AVAILABLE=HOLD')
try:
    g=subprocess.run(['nvidia-smi','--query-gpu=index,utilization.gpu,memory.used',
        '--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=8)
    if g.returncode==0:
        for line in g.stdout.splitlines()[:2]:
            if all(part.strip().isdigit() for part in line.split(',')):
                print('NATIVE_GPU_LIVE='+line.replace(' ',''))
except (OSError,subprocess.TimeoutExpired):pass
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""

if __name__=="__main__":
    c.REMOTE=REMOTE
    ok=False
    try:ok=c.probe()
    except Exception as exc:
        print("NOX_V62_SCAN="+str(exc) if str(exc).startswith("HOLD_") else "NOX_V62_SCAN=HOLD")
    finally:
        try:
            if not c.cleanup():ok=False
        except Exception:
            print("NOX_V62_TEMP_KEY_CLEANUP=HOLD")
            ok=False
    raise SystemExit(0 if ok else 2)
