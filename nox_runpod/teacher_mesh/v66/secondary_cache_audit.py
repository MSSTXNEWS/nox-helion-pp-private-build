"""NOX V66 secondary cache capacity assessment; read-only SSH, no deletion."""
from __future__ import annotations
from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as c
import time
_api=c.api
def _delayed(method,path,key,data=None):
    x=_api(method,path,key,data)
    if method=="POST" and path.endswith("/ssh/"):time.sleep(15)
    return x
REMOTE=r"""
set -euo pipefail
python3 - <<'PYREMOTE'
import os,stat,json,shutil
from pathlib import Path
print('NOX_NATIVE_V51_SSH_EXECUTED=true')
print('NATIVE_AUDIT_SCHEMA=NOX_V66_SECONDARY_REGENERABLE_CACHES_V1')
roots={
 'apt_downloads':Path('/var/cache/apt/archives'),
 'npm_cache':Path('/root/.npm/_cacache'),
 'conda_downloads':Path('/opt/conda/pkgs'),
 'rust_registry_cache':Path('/root/.cargo/registry/cache'),
 'pip_cache':Path('/root/.cache/pip'),
 'uv_cache':Path('/root/.cache/uv'),
 'pre_commit_cache':Path('/root/.cache/pre-commit'),
 'matplotlib_cache':Path('/root/.cache/matplotlib'),
 'torch_extensions_cache':Path('/root/.cache/torch_extensions'),
 'old_tmp':Path('/tmp'),
}
openfiles=set()
for pid in os.listdir('/proc'):
 if not pid.isdigit():continue
 try:
  for item in list((Path('/proc')/pid/'fd').iterdir())[:192]:
   try:openfiles.add(os.readlink(item).removesuffix(' (deleted)'))
   except (OSError,ValueError):pass
 except OSError:pass
for label,base in roots.items():
 if not base.is_dir() or base.is_symlink():
  print('NATIVE_OTHER_CACHE='+json.dumps({'class':label,'present':False},separators=(',',':')))
  continue
 files=0;bytes_=0;held=0;error=0;syms=0
 for root,dirs,names in os.walk(base,followlinks=False):
  dirs[:]=[d for d in dirs if d not in ('.ssh','.git')][:200]
  for name in names:
   p=Path(root)/name
   try:
    st=p.lstat()
    if stat.S_ISLNK(st.st_mode):syms+=1
    if not stat.S_ISREG(st.st_mode):continue
    files+=1;bytes_+=st.st_size
    if str(p) in openfiles:held+=1
   except (OSError,ValueError):error+=1
   if files>=30000:break
  if files>=30000:break
 print('NATIVE_OTHER_CACHE='+json.dumps({
  'class':label,'present':True,'files':files,'bytes':bytes_,
  'open_file_count':held,'symlinks':syms,'errors':error,'truncated':files>=30000
 },separators=(',',':')))
try:
 s=shutil.disk_usage('/workspace')
 print('NATIVE_FREE_AFTER_PREVIOUS_CLEANUP_BYTES='+str(s.free))
except OSError:print('NATIVE_FREE_AFTER_PREVIOUS_CLEANUP_BYTES=HOLD')
print('NATIVE_READ_ONLY_COMPLETE=true')
PYREMOTE
"""
def main():
 c.REMOTE=REMOTE;c.api=_delayed
 ok=False
 try:ok=c.probe()
 except Exception as e:
  s=str(e)
  print('NOX_V66_SECONDARY='+s if s.startswith('HOLD_') and len(s)<90 else 'NOX_V66_SECONDARY=HOLD_NATIVE')
 finally:
  try:
   if not c.cleanup():ok=False
  except Exception:print('NOX_V66_SECONDARY=HOLD_KEY_REVOKE');ok=False
 return 0 if ok else 2
if __name__=='__main__':raise SystemExit(main())
