"""NOX V69: read-only safe cold-file selection and /dev/shm capacity probe.

No download, backup mutation, model load, symlink change or deletion.
Temporary SSH and deletion-of-key come from established NOX V51.
"""
from __future__ import annotations
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as c
import time
_orig=c.api
def _api(method,path,key,data=None):
    r=_orig(method,path,key,data)
    if method=="POST" and path.endswith("/ssh/"):time.sleep(15)
    return r
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import os,stat,hashlib,json,shutil,time
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V69_SAFE_OFFSITE_RAM_CANDIDATES_V1')
roots={
 'backup':Path('/root/nox/backup'),
 'incoming':Path('/root/nox/incoming_t800u'),
 'source_archives':Path('/root/nox/sources')
}
opens=set()
for item in os.listdir('/proc'):
 if not item.isdigit():continue
 try:
  p=Path('/proc')/item/'fd'
  for f in list(p.iterdir())[:220]:
   try:opens.add(os.readlink(f).removesuffix(' (deleted)'))
   except (OSError,ValueError):pass
 except OSError:pass
wanted={'.zip','.tar','.gz','.tgz','.xz','.zst','.7z','.bak','.json','.sqlite','.sqlite3','.db','.py','.html','.js','.css','.md','.txt','.ps1','.sh'}
for name,root in roots.items():
 if not root.is_dir() or root.is_symlink():continue
 total=0;file_count=0;items=[];open_count=0
 for base,dirs,files in os.walk(root,followlinks=False):
  dirs[:]=[d for d in dirs if d not in ('.ssh','.git','.cache','venv','node_modules')][:100]
  for fn in files:
   path=Path(base)/fn
   try:
    st=path.lstat()
    if not stat.S_ISREG(st.st_mode):continue
    file_count+=1;total+=st.st_size
    used=str(path) in opens
    open_count+=used
    if st.st_size>=4_000_000 and len(items)<200:
      items.append((st.st_size,path,st.st_mtime_ns,used,st.st_nlink))
   except OSError:pass
   if file_count>=25000:break
  if file_count>=25000:break
 items.sort(key=lambda x:x[0],reverse=True)
 print('NATIVE_OFFSITE_ROOT='+json.dumps({'class':name,'bytes':total,'files':file_count,
  'open_fds':open_count,'truncated':file_count>=25000},separators=(',',':')))
 for size,p,mtime,used,link_count in items[:12]:
  rel=str(p.relative_to(root))
  # path fingerprint excludes plaintext filenames from logs.
  print('NATIVE_OFFSITE_CANDIDATE='+json.dumps({
   'root':name,'size_bytes':size,
   'relative_path_sha16':hashlib.sha256(rel.encode()).hexdigest()[:16],
   'ext':p.suffix.lower(),'open_fd':used,'links':link_count,
   'mtime_unix':int(mtime//1000000000)
  },separators=(',',':')))
ram=shutil.disk_usage('/dev/shm')
disk=shutil.disk_usage('/workspace')
print('NATIVE_RAM_TMPFS='+json.dumps({'total_bytes':ram.total,'free_bytes':ram.free,
 'workspace_free_bytes':disk.free},separators=(',',':')))
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
def main():
 c.REMOTE=REMOTE;c.api=_api
 ok=False
 try:ok=c.probe()
 except Exception as e:
  s=str(e)
  print("NOX_V69_PROBE="+s if s.startswith("HOLD_") and len(s)<110 else "NOX_V69_PROBE=HOLD_NATIVE")
 finally:
  try:
   if not c.cleanup():ok=False
  except Exception:print("NOX_V69_PROBE=HOLD_KEY_REVOKE");ok=False
 return 0 if ok else 2
if __name__=="__main__":raise SystemExit(main())
